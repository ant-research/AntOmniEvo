from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import subprocess
import uuid
from datetime import datetime
from typing import Any

from antomnievo.common.utils.concurrency_pool import ConcurrencyPool
from antomnievo.interface.data_inst import DataInst
from antomnievo.interface.system import System
from antomnievo.model.candidate_data import CandidateMeta
from antomnievo.model.rollout_result import RolloutResult
from antomnievo.model.system_result import SystemResult
from antomnievo.model.trajectory import Span, Trajectory
from antomnievo.model.usage_stats import UsageStats

logger = logging.getLogger(__name__)


def _parse_dt(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    with contextlib.suppress(ValueError, TypeError):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return None


def _rehydrate_span(d: dict) -> Span:
    """Convert a span dict from tbtest's trajectory.json into a Span.

    tbtest / antomnievo share the JSON shape but use different attribute names
    on the Python side (``parent_id`` vs ``parent_span_id``, ``type`` vs
    ``span_type``), so we rehydrate field-by-field.
    """
    start = _parse_dt(d.get("start_time")) or datetime.now()
    end = _parse_dt(d.get("end_time"))
    children = [_rehydrate_span(c) for c in (d.get("children") or [])]
    return Span(
        id=d.get("id") or str(uuid.uuid4()),
        parent_span_id=d.get("parent_id"),
        name=d.get("name") or "",
        span_type=d.get("type") or "span",
        input=d.get("input"),
        output=d.get("output"),
        start_time=start,
        end_time=end,
        children=children,
    )


def _parse_trajectory(trajectory_path: str) -> Trajectory:
    """Load ``<trial>/trajectory.json`` (already in antomnievo shape) into a Trajectory."""
    with open(trajectory_path, encoding="utf-8") as f:
        data = json.load(f)
    root_spans = [_rehydrate_span(s) for s in (data.get("trajectory") or [])]
    return Trajectory(
        root_span_list=root_spans,
        session_id=data.get("session_id"),
        trace_id=data.get("trace_id"),
    )


def _find_trial_dirs_for_task(job_dir: str, data_id: str) -> list[str]:
    """Return trial directories under *job_dir* matching *data_id*.

    Harbor names trial dirs ``<task_name>__<hash>``.  We prefix-match on
    ``<data_id>__`` and also accept an exact-name match as a fallback.
    """
    if not os.path.isdir(job_dir):
        return []

    prefix = f"{data_id}__"
    results: list[str] = []
    for entry in os.listdir(job_dir):
        full = os.path.join(job_dir, entry)
        if not os.path.isdir(full):
            continue
        if entry.startswith(prefix) or entry == data_id:
            results.append(full)
    return sorted(results)


def _read_usage_stats(trial_dir: str) -> UsageStats | None:
    """Read token usage from a Harbor trial's ``result.json``.

    Uses the Harbor TrialResult schema:
    ``agent_result.n_input_tokens / n_output_tokens / n_cache_tokens``.
    """
    result_path = os.path.join(trial_dir, "result.json")
    if not os.path.isfile(result_path):
        return None
    try:
        with open(result_path, encoding="utf-8") as f:
            data = json.load(f)
        agent_result = data.get("agent_result") or {}
        return UsageStats(
            input_tokens=agent_result.get("n_input_tokens") or 0,
            output_tokens=agent_result.get("n_output_tokens") or 0,
            cache_read_input_tokens=agent_result.get("n_cache_tokens") or 0,
        )
    except (json.JSONDecodeError, OSError, TypeError) as e:
        logger.warning(f"Failed to read usage stats from {result_path}: {e}")
        return None


def _read_exception_info(trial_dir: str) -> dict | None:
    """Read the exception from a Harbor trial's ``result.json``.

    Harbor writes ``exception_info`` (a dict with ``exception_type``,
    ``exception_message``, ``exception_traceback``) when a trial ends in an
    exception (AgentTimeoutError, AgentSetupError, …). On success the field
    is ``null``. Returns ``None`` when there was no exception or the file is
    missing/unreadable.
    """
    result_path = os.path.join(trial_dir, "result.json")
    if not os.path.isfile(result_path):
        return None
    try:
        with open(result_path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Failed to read exception_info from {result_path}: {e}")
        return None
    exc_info = data.get("exception_info")
    if not isinstance(exc_info, dict) or not exc_info:
        return None
    return exc_info


def _build_exception_span(trial_dir: str) -> Span | None:
    """Build a Span carrying the trial's terminal exception, if any.

    Appended to the trajectory's root span list so downstream consumers
    (proposer/loss) see both the agent's prior steps *and* the exception
    that ended the trial. ``output`` holds the structured type+message;
    ``metadata`` holds the full ``exception_traceback`` string.
    """
    exc_info = _read_exception_info(trial_dir)
    if exc_info is None:
        return None
    exc_type = exc_info.get("exception_type") or "Exception"
    exc_message = exc_info.get("exception_message") or ""
    traceback = exc_info.get("exception_traceback")
    return Span(
        name="exception",
        span_type="system",
        input=None,
        output={
            "exception_type": exc_type,
            "exception_message": exc_message,
        },
        metadata={"traceback": traceback} if traceback else {},
    )


def _find_trajectory_path(trial_dir: str) -> str | None:
    """tbtest writes trajectory.json at ``<trial>/agent/trajectory.json``.

    ``generate`` converts harbor's native Step-format ``agent/trajectory.json``
    in place (backing the original up to ``trajectory.harbor.json``).
    """
    path = os.path.join(trial_dir, "agent", "trajectory.json")
    return path if os.path.isfile(path) else None


class TerminalBenchSystem(System):
    """System that runs Terminal-Bench 2 tasks via the ``tbtest generate`` CLI.

    ``tbtest generate`` is a thin wrapper around ``harbor run`` that also
    rewrites the Harbor job config to mount ``skill/``, ``memory/``, and
    ``extension/`` from ``--artifact-dir`` — so per-rollout artifact swap is a
    single flag change (no per-task Dockerfile mutation needed, unlike the
    dp_text2sql pipeline).

    Trial output layout::

        <output_dir>/<job_name>/<task_name>__<suffix>/
        ├── agent/
        │   └── pi.txt              # Pi NDJSON stream
        ├── result.json             # Harbor TrialResult (verifier_result.rewards, agent_result.n_*_tokens)
        └── trajectory.json         # Already in antomnievo.model.trajectory shape
    """

    MAX_TOTAL_CONCURRENCY: int = 40
    _pool: ConcurrencyPool | None = None
    _pool_lock = asyncio.Lock()

    @classmethod
    def set_max_total_concurrency(cls, total: int) -> None:
        if cls._pool is not None:
            raise RuntimeError(
                "Cannot change MAX_TOTAL_CONCURRENCY after the pool has been created"
            )
        cls.MAX_TOTAL_CONCURRENCY = total

    @classmethod
    async def _get_pool(cls) -> ConcurrencyPool:
        async with cls._pool_lock:
            if cls._pool is None:
                cls._pool = ConcurrencyPool(cls.MAX_TOTAL_CONCURRENCY)
        return cls._pool

    def __init__(
        self,
        generate_bin: str,
        api_key: str,
        concurrency: int = 1,
        attempts: int = 1,
        base_url: str = "https://antchat.alipay.com/api/anthropic",
        model: str | None = None,
        provider: str | None = "anthropic",
        job_config_yaml: str | None = None,
        agent_import_path: str | None = "agent.kira_agent:AgentHarness",
        force_build: bool = False,
        debug: bool = False,
    ):
        """Initialize TerminalBenchSystem.

        Args:
            generate_bin: Path to the ``generate`` console script
                (e.g. ``~/work/terminalbench2/.venv/bin/generate``).
            api_key: API key injected as ``ANTHROPIC_API_KEY`` / ``THETA_API_KEY``.
            concurrency: Number of parallel trials (``-n`` flag).
            attempts: Number of attempts per task (``-k`` flag).
            base_url: Anthropic API base URL, injected as ``ANTHROPIC_BASE_URL``.
            model: Optional model override for ``-m``. Pass the bare name
                (e.g. ``"glm-5"``); the ``provider`` prefix is added
                automatically. If the value already contains ``/`` (e.g.
                ``"anthropic/glm-5"``) it is used as-is. If None, the yaml's
                model is used.
            provider: litellm provider prefix prepended to ``model`` (default
                ``"anthropic"``). litellm needs this to route via the
                anthropic adapter (/v1/messages) before forwarding the bare
                name to the antchat gateway. Ignored when ``model`` already
                carries a provider segment.
            job_config_yaml: Optional Harbor job-config yaml (``-c`` flag).
                If None, ``tbtest generate``'s built-in default is used.
            agent_import_path: Optional ``--agent`` override (agent import path).
                Defaults to ``agent.kira_agent:AgentHarness``, which resolves
                against the candidate tunable-artifact dir itself (laid out as
                ``<cand>/artifact/agent/kira_agent.py``) — ``generate`` puts the
                tunable-artifact dir on ``PYTHONPATH``. Pass ``artifact.kira.agent.kira_agent:
                AgentHarness`` to use the repo-root ``artifact/kira`` agent instead.
            force_build: Pass ``--force-build`` to rebuild task Docker images.
            debug: Pass ``--debug`` to enable Harbor debug logging.
        """
        super().__init__()
        self.generate_bin = os.path.abspath(generate_bin)
        self.api_key = api_key
        self.concurrency = concurrency
        self.attempts = attempts
        self.base_url = base_url
        # Prepend the litellm provider prefix (e.g. ``anthropic/glm-5``) so
        # litellm's ``get_llm_provider`` can route via the anthropic adapter.
        # A bare model name (``glm-5``) makes litellm raise
        # ``BadRequestError("LLM Provider NOT provided")``. Skip prefixing when
        # model already contains a provider segment or when no model override
        # is given (fall back to the job-config yaml's ``model_name``).
        if model and provider and "/" not in model:
            model = f"{provider}/{model}"
        self.model = model
        self.job_config_yaml = os.path.abspath(job_config_yaml) if job_config_yaml else None
        self.agent_import_path = agent_import_path
        self.force_build = force_build
        self.debug = debug

    async def _run(self, candidate_meta: CandidateMeta, data_inst: DataInst) -> SystemResult:
        pass  # Not used; run_batch is the real entry point.

    async def run_batch(
        self,
        candidate_meta: CandidateMeta,
        data_list: list[DataInst],
        *,
        job_name: str,
        dataset_dir: str,
        output_dir: str,
        **kwargs,
    ) -> list[SystemResult]:
        """Run multiple Terminal-Bench tasks via ``tbtest generate``.

        Args:
            candidate_meta: Candidate metadata (``artifact_dir`` becomes ``--artifact-dir``).
            data_list: Data instances to run.
            job_name: Harbor ``--job-name`` (also names the output subdir).
            dataset_dir: Terminal-Bench dataset root (``-p`` flag).
            output_dir: Harbor jobs directory (``-o`` flag). Trials land under
                ``<output_dir>/<job_name>/<task_name>__<suffix>/``.
        """
        job_dir = os.path.join(output_dir, job_name)
        task_ids = [d.id for d in data_list]

        env = {
            "THETA_API_KEY": self.api_key,
            "ANTHROPIC_AUTH_TOKEN": self.api_key,
            "ANTHROPIC_API_KEY": self.api_key,
            "ANTHROPIC_BASE_URL": self.base_url,
            # litellm fetches a remote model cost map from raw.githubusercontent.com
            # during its __init__ — under an offline/flaky network that times out
            # (6s+) and can destabilize harbor startup. Force the local backup so
            # the agent process never touches GitHub. Cost/usage is unaffected.
            "LITELLM_LOCAL_MODEL_COST_MAP": "True",
        }
        if self.model:
            env["ANTHROPIC_MODEL"] = self.model

        try:
            slots = min(self.concurrency, len(data_list), self.MAX_TOTAL_CONCURRENCY)
            pool = await self._get_pool()
            async with pool.slot(slots):
                await self._run_via_generate(
                    dataset_dir=dataset_dir,
                    output_dir=output_dir,
                    artifact_dir=candidate_meta.artifact_dir,
                    job_name=job_name,
                    include_tasks=task_ids,
                    env=env,
                )

            results: list[SystemResult] = []
            for data_inst in data_list:
                trial_dirs = _find_trial_dirs_for_task(job_dir, data_inst.id)
                if not trial_dirs:
                    logger.warning(f"No trial found for data_id={data_inst.id}")
                    results.append(SystemResult(
                        trajectory=Trajectory(root_span_list=[]),
                        output=RolloutResult(content=""),
                    ))
                    continue
                results.append(self._build_system_result(trial_dirs[0], data_inst.id))
            return results

        except Exception as e:
            logger.error(f"Batch run via tbtest generate failed: {e}")
            return [
                SystemResult(
                    trajectory=Trajectory(root_span_list=[]),
                    output=RolloutResult(content=""),
                )
                for _ in data_list
            ]

    def _build_system_result(self, trial_dir: str, data_id: str) -> SystemResult:
        trajectory = Trajectory(root_span_list=[])
        traj_path = _find_trajectory_path(trial_dir)
        if traj_path:
            try:
                trajectory = _parse_trajectory(traj_path)
            except Exception as e:
                logger.warning(f"Failed to parse trajectory for {data_id}: {e}")

        # If the trial ended in an exception, append a terminal Span carrying
        # the exception type/message (output) + full traceback (metadata), so
        # the trajectory holds both the agent's prior steps AND the failure.
        exception_span = _build_exception_span(trial_dir)
        if exception_span is not None:
            trajectory.root_span_list.append(exception_span)

        # Final agent output = last non-empty span output (walk in reverse).
        content = ""
        def _walk_reverse(spans: list[Span]) -> str:
            for s in reversed(spans):
                child_out = _walk_reverse(s.children)
                if child_out:
                    return child_out
                if s.output:
                    return str(s.output)
            return ""
        content = _walk_reverse(trajectory.root_span_list)

        usage = _read_usage_stats(trial_dir)

        return SystemResult(
            trajectory=trajectory,
            output=RolloutResult(content=content),
            usage=usage,
        )

    async def _run_via_generate(
        self,
        dataset_dir: str,
        output_dir: str,
        artifact_dir: str | None,
        job_name: str,
        include_tasks: list[str] | None = None,
        env: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Invoke the ``tbtest generate`` CLI as a subprocess."""
        cmd: list[str] = [
            self.generate_bin,
            "-p", dataset_dir,
            "-o", output_dir,
            "-j", job_name,
            "-n", str(self.concurrency),
            "-k", str(self.attempts),
        ]
        if artifact_dir:
            cmd.extend(["--artifact-dir", artifact_dir])
        if self.job_config_yaml:
            cmd.extend(["-c", self.job_config_yaml])
        if self.agent_import_path:
            cmd.extend(["--agent", self.agent_import_path])
        if self.model:
            cmd.extend(["-m", self.model])
        if self.force_build:
            cmd.append("--force-build")
        if self.debug:
            cmd.append("--debug")
        for task_id in (include_tasks or []):
            cmd.extend(["-i", task_id])

        sub_env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
        if env:
            sub_env.update(env)

        logger.info(f"Running tbtest generate: {' '.join(cmd)}")

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            lambda: subprocess.run(cmd, capture_output=True, env=sub_env),
        )

        if result.returncode != 0:
            logger.error(
                f"tbtest generate failed (rc={result.returncode}): "
                f"stdout={result.stdout.decode(errors='replace')[:5000]}, "
                f"stderr={result.stderr.decode(errors='replace')[:5000]}"
            )

        return {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
