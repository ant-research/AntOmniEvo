from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import subprocess
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


def _extract_text_content(message: str) -> str:
    """Extract displayable text from a possibly structured message.

    ATIF user messages may be JSON objects like ``{"type": "text", "text": "..."}``
    or plain strings.  Returns the inner ``text`` field when present, otherwise
    the original message.
    """
    try:
        parsed = json.loads(message)
    except json.JSONDecodeError:
        # Outer JSON deserialization turns escaped \n into literal newlines,
        # making the inner JSON invalid.  Re-escape and retry.
        try:
            normalized = message.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
            parsed = json.loads(normalized)
        except (json.JSONDecodeError, TypeError):
            return message
    except TypeError:
        return message

    if isinstance(parsed, dict) and parsed.get("type") == "text" and "text" in parsed:
        return parsed["text"]
    return message


def _parse_trajectory(trajectory_path: str) -> Trajectory:
    """Parse Harbor's ATIF trajectory.json into antomnievo Trajectory.

    Produces a root ``agent`` span with child spans for each step:
    - ``model`` spans for LLM reasoning/generation (``message`` or
      ``reasoning_content``)
    - ``tool`` spans for tool invocations (``tool_calls`` + ``observation``)
    - ``user`` spans for user messages beyond the initial input
      (e.g. skill content injection)

    ATIF step fields used:
    - ``source``: ``"user"`` | ``"agent"``
    - ``message``: visible output (may be empty for reasoning-only steps)
    - ``reasoning_content``: chain-of-thought (fallback when message is empty)
    - ``tool_calls``: list of ``{tool_call_id, function_name, arguments}``
    - ``observation.results``: list of ``{source_call_id, content}``
    - ``extra.stop_reason``: ``"tool_use"`` | ``"end_turn"`` | etc.
    """
    with open(trajectory_path, encoding="utf-8") as f:
        data = json.load(f)

    session_id = data.get("session_id")
    steps = data.get("steps", [])

    user_input = ""
    child_spans: list[Span] = []
    # Map tool_call_id -> Span so we can attach results later
    pending_tool_calls: dict[str, Span] = {}

    for step in steps:
        source = step.get("source", "unknown")
        message = step.get("message", "")
        reasoning_content = step.get("reasoning_content") or ""
        timestamp = step.get("timestamp")
        tool_calls = step.get("tool_calls", [])
        observation = step.get("observation", {})
        model_name = step.get("model_name", "unknown")
        extra = step.get("extra", {})
        stop_reason = extra.get("stop_reason", "")

        start_time = datetime.now()
        if timestamp:
            with contextlib.suppress(ValueError, TypeError):
                start_time = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

        if source == "user":
            if not user_input:
                user_input = message
            else:
                # Tool result delivered as a user turn — attach to pending tool_call
                results = observation.get("results", [])
                for result in results:
                    call_id = result.get("source_call_id", "")
                    if call_id in pending_tool_calls:
                        pending_tool_calls[call_id].output = result.get("content", "")

                # Capture user message content that isn't a tool result
                # (e.g., skill content injection, system messages)
                if message and not results:
                    content = _extract_text_content(message)
                    child_spans.append(Span(
                        name="user_message",
                        span_type="user",
                        input=None,
                        output=content,
                        start_time=start_time,
                        end_time=start_time,
                    ))
            continue

        # source == "agent"
        if stop_reason == "tool_use" and tool_calls:
            # Capture any text message alongside tool calls
            if message:
                child_spans.append(Span(
                    name=f"{model_name}_call",
                    span_type="model",
                    input=None,
                    output=message,
                    start_time=start_time,
                    end_time=start_time,
                ))

            # One or more tool calls in this step
            for tc in tool_calls:
                call_id = tc.get("tool_call_id", "")
                func_name = tc.get("function_name", "unknown")
                arguments = tc.get("arguments", {})

                span = Span(
                    name=f"tool_call_{func_name}",
                    span_type="tool",
                    input=json.dumps({func_name: arguments}, ensure_ascii=False)
                    if isinstance(arguments, dict) else str(arguments),
                    output="",
                    start_time=start_time,
                    end_time=start_time,
                )
                child_spans.append(span)
                if call_id:
                    pending_tool_calls[call_id] = span

            # Also check if observation results are inline (same step)
            for result in observation.get("results", []):
                call_id = result.get("source_call_id", "")
                if call_id in pending_tool_calls:
                    pending_tool_calls[call_id].output = result.get("content", "")
        else:
            # Model step — use message, fall back to reasoning_content
            output = message or reasoning_content
            if not output:
                continue

            span = Span(
                name=f"{model_name}_call",
                span_type="model",
                input=None,
                output=output,
                start_time=start_time,
                end_time=start_time,
            )
            child_spans.append(span)

    # Final agent output = last model span's output
    final_output = ""
    for span in reversed(child_spans):
        if span.span_type == "model" and span.output:
            final_output = span.output
            break

    root_span = Span(
        name="agent",
        span_type="agent",
        input=user_input,
        output=final_output,
        start_time=child_spans[0].start_time if child_spans else datetime.now(),
        end_time=child_spans[-1].end_time if child_spans else datetime.now(),
        children=child_spans,
    )

    return Trajectory(
        root_span_list=[root_span],
        session_id=session_id,
        trace_id=session_id,
    )

def _find_trial_dirs_for_task(jobs_dir: str, data_id: str) -> list[str]:
    """Find all trial directories for *data_id* under the Harbor job output directory.

    Scans ``jobs_dir`` for subdirectories named ``task_<id>__<suffix>``
    and matches ``<id>`` against *data_id*.  Returns all matching trial
    directories sorted by name.
    """
    if not os.path.isdir(jobs_dir):
        return []

    prefix = f"{data_id}__"
    results: list[str] = []

    for entry in os.listdir(jobs_dir):
        if not entry.startswith(prefix):
            continue
        trial_path = os.path.join(jobs_dir, entry)
        if os.path.isdir(trial_path):
            results.append(trial_path)

    return sorted(results)


def _read_usage_stats(trial_dir: str) -> UsageStats | None:
    """Read token usage from a Harbor trial's result.json."""
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


def _find_trajectory_path(trial_dir: str) -> str | None:
    """Find trajectory.json in a Harbor trial directory."""
    traj_path = os.path.join(trial_dir, "agent", "trajectory.json")
    return traj_path if os.path.isfile(traj_path) else None


class DPText2SQLSystem(System):
    """System implementation that runs text2sql tasks via Harbor's run.sh script.

    Uses pre-prepared Harbor task directories (``harbor_tasks_train/`` etc.).
    For each data instance, injects the current candidate spec into the task
    directory as the ``data-text2sql`` skill, runs ``run.sh`` to
    execute Harbor, and parses the results from the jobs output directory.

    Harbor job output directory structure::

        <script_dir>/jobs/<job_name>/
        ├── config.json              # Job config snapshot
        ├── lock.json                # Trial input hashes for dedup/replay
        ├── job.log                  # Job-level logs
        ├── result.json              # Summary: completed/errored counts, scores
        └── task_<id>__<suffix>/     # Trial directory (one per task run)
            ├── config.json          # Trial config snapshot
            ├── result.json          # Trial result (reward, exception, timing, tokens)
            ├── trial.log            # Trial-level logs
            ├── exception.txt        # Only on error
            ├── agent/
            │   ├── trajectory.json  # ATIF-format interaction trace
            │   ├── claude-code.txt  # Raw Claude Code stream-json output
            │   └── sessions/        # Claude Code session state
            └── verifier/
                ├── reward.txt       # "1" = pass, "0" = fail
                ├── eval.json        # {"pass": true/false, "reason": "..."}
                └── test-stdout.txt  # Test script stdout

    run.sh behavior:

    - Always ``cd``\\s to its own script directory before running
    - Clears ``./jobs/*`` at the start of each run
    - Uses ``job-config.yaml`` in the script directory for configuration
    - Job name is set in the config (default: ``nl2sql-bench``)
    """

    MAX_TOTAL_CONCURRENCY: int = 40
    _pool: ConcurrencyPool | None = None
    _pool_lock = asyncio.Lock()

    @classmethod
    def set_max_total_concurrency(cls, total: int) -> None:
        """Set the global concurrency cap shared across all instances.

        Must be called before the first ``run_batch`` — once the pool is
        created it cannot be resized.
        """
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
        run_sh_path: str,
        api_key: str,
        concurrency: int = 1,
        base_url: str = "https://antchat.alipay.com/api/anthropic",
        model: str = "kimi-k2.5",
    ):
        """Initialize DPText2SQLSystem.

        Args:
            run_sh_path: Path to the ``run.sh`` script
                (e.g. ``/path/to/harbor_dp/test/run.sh``).
            api_key: API key for LLM authentication, injected as environment
                variables (``THETA_API_KEY``, ``ANTHROPIC_AUTH_TOKEN``,
                ``ANTHROPIC_API_KEY``) when running the script.
            concurrency: Number of parallel tasks to run via ``run.sh -c``.
            base_url: Anthropic API base URL, injected as ``ANTHROPIC_BASE_URL``.
            model: Model name, injected as ``ANTHROPIC_MODEL``.
        """
        super().__init__()
        self.run_sh_path = os.path.abspath(run_sh_path)
        self.api_key = api_key
        self.concurrency = concurrency
        self.base_url = base_url
        self.model = model

    async def _run(self, candidate_meta: CandidateMeta, data_inst: DataInst) -> SystemResult:
        pass # Not used; we override run_batch instead for efficiency

    async def run_batch(
        self,
        candidate_meta: CandidateMeta,
        data_list: list[DataInst],
        *,
        job_name: str | None = None,
        dataset_dir: str,
        output_dir: str,
        **kwargs,
    ) -> list[SystemResult]:
        """Run multiple text2sql tasks via run.sh.

        Args:
            candidate_meta: Candidate metadata.
            data_list: Data instances to run.
            job_name: Optional job name for the Harbor run (``-j`` flag).
            dataset_dir: Directory containing prepared task directories
                (with spec already injected by the caller).
            output_dir: Directory for Harbor job output (``-o`` flag).
        """
        batch_job_dir = os.path.join(output_dir, job_name)

        env = {
            "THETA_API_KEY": self.api_key,
            "ANTHROPIC_AUTH_TOKEN": self.api_key,
            "ANTHROPIC_API_KEY": self.api_key,
            "ANTHROPIC_BASE_URL": self.base_url,
            "ANTHROPIC_MODEL": self.model,
        }
        try:
            slots = min(self.concurrency, len(data_list), self.MAX_TOTAL_CONCURRENCY)
            pool = await self._get_pool()
            async with pool.slot(slots):
                await self._run_via_script(
                    dataset_dir=dataset_dir,
                    output_dir=output_dir,
                    env=env,
                    concurrency=self.concurrency,
                    job_name=job_name,
                )

            # Parse results for each task
            results: list[SystemResult] = []
            for data_inst in data_list:
                trial_dirs = _find_trial_dirs_for_task(batch_job_dir, data_inst.id)
                if not trial_dirs:
                    logger.warning(f"No trial found for data_id={data_inst.id}")
                    results.append(SystemResult(
                        trajectory=Trajectory(root_span_list=[]),
                        output=RolloutResult(content=""),
                    ))
                    continue
                # trial times = 1
                results.append(self._build_system_result(trial_dirs[0], data_inst.id))

            return results

        except Exception as e:
            logger.error(f"Batch run via run.sh failed: {e}")
            return [
                SystemResult(
                    trajectory=Trajectory(root_span_list=[]),
                    output=RolloutResult(content=""),
                )
                for _ in data_list
            ]

    def _build_system_result(self, trial_dir: str, data_id: str) -> SystemResult:
        """Build a SystemResult from a Harbor trial directory."""
        trajectory_path = _find_trajectory_path(trial_dir)

        # Build trajectory
        trajectory = Trajectory(root_span_list=[])
        if trajectory_path:
            try:
                trajectory = _parse_trajectory(trajectory_path)
            except Exception as e:
                logger.warning(f"Failed to parse trajectory for {data_id}: {e}")

        # Root span's output holds the final agent response
        content = ""
        if trajectory.root_span_list:
            root = trajectory.root_span_list[0]
            if root.output:
                content = root.output

        # Read token usage from trial result.json
        usage = _read_usage_stats(trial_dir)

        return SystemResult(
            trajectory=trajectory,
            output=RolloutResult(content=content),
            usage=usage,
        )

    async def _run_via_script(
        self,
        dataset_dir: str,
        output_dir: str,
        n_tasks: int | None = None,
        include_tasks: list[str] | None = None,
        env: dict[str, str] | None = None,
        concurrency: int = 1,
        job_name: str | None = None,
    ) -> dict[str, Any]:
        """Run ``run.sh`` to execute Harbor tasks.

        Calls the ``run.sh`` script with the given dataset directory.
        The script handles Harbor invocation, including job cleanup,
        config loading, and parallel execution.

        Args:
            dataset_dir: Path to the directory containing prepared task
                directories (each task is a ``task_<id>/`` subdirectory).
            n_tasks: Maximum number of tasks to run.  None means run all.
            include_tasks: Optional list of task name globs to include.
            env: Extra environment variables to inject into the subprocess.
                Merged on top of the current process environment.
            concurrency: Number of parallel tasks to run (``-c`` flag).
            job_name: Optional job name for the script (``-j`` flag).

        Returns:
            Dict with returncode, stdout, and stderr from the script.
        """
        cmd: list[str] = ["bash", self.run_sh_path, "-d", dataset_dir]
        cmd.extend(["-o", output_dir])

        if n_tasks is not None:
            cmd.extend(["-n", str(n_tasks)])

        if concurrency > 1:
            cmd.extend(["-c", str(concurrency)])

        for task_name in (include_tasks or []):
            cmd.extend(["-i", task_name])

        if job_name is not None:
            cmd.extend(["-j", job_name])

        sub_env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
        if env:
            sub_env.update(env)

        logger.info(f"Running run.sh: {' '.join(cmd)}")

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                cmd,
                capture_output=True,
                env=sub_env,
            ),
        )

        if result.returncode != 0:
            logger.error(
                f"run.sh failed (rc={result.returncode}): "
                f"stdout={result.stdout.decode(errors='replace')[:5000]}, "
                f"stderr={result.stderr.decode(errors='replace')[:5000]}"
            )

        return {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }


