from __future__ import annotations

import asyncio
import json
import logging
import os
import time

from antomnievo.common.utils.concurrency_pool import ConcurrencyPool
from antomnievo.interface.data_inst import DataInst
from antomnievo.interface.system import System
from antomnievo.model.candidate_data import CandidateMeta
from antomnievo.model.rollout_result import RolloutResult
from antomnievo.model.system_result import SystemResult
from antomnievo.model.trajectory import Span, Trajectory
from antomnievo.model.usage_stats import UsageStats

logger = logging.getLogger(__name__)


_APPWORLD_SYSTEM_DESCRIPTION = """\
AppWorld Coding Agent System:

A ReAct-style agent that writes Python code to complete day-to-day tasks in the
AppWorld environment. Each task involves interacting with apps (e.g. spotify,
venmo, gmail) through their Python APIs.

## Agent Input Format

The agent receives:
- A **system prompt** combining a fixed AGENT_CONSTRAINT (environment rules)
  and an optimized SKILL.md (task strategies, error patterns, API patterns).
- A **user prompt** containing the task instruction, API documentation (YAML),
  supervisor info, and available imports.

## Agent Tools

The agent writes Python code which is executed in a sandboxed REPL. Available
APIs include:
- `apis.<app_name>.<api_name>(**kwargs)` — call an app API
- `apis.supervisor.complete_task(answer=..., status=...)` — mark task done
- `apis.api_docs.show_app_descriptions()` — list available apps
- `apis.api_docs.show_api_descriptions(app_name=...)` — list APIs for an app
- `apis.api_docs.show_api_doc(app_name=..., api_name=...)` — get API spec
- Standard library: datetime, json, math, re, collections, etc.

## Output

The task is complete when the agent calls `apis.supervisor.complete_task()`.
Evaluation checks the resulting database state against ground truth.
"""

# Default path to the AppWorld venv Python interpreter.
_DEFAULT_APPWORLD_PYTHON = os.path.expanduser(
    "~/work/appworld/.venv/bin/python"
)


class AppWorldSystem(System):
    """System that runs AppWorld tasks via subprocess calling appworld-run-batch.

    Uses the AppWorld venv Python to run ``appworld-run-batch`` as a
    subprocess, which internally uses ``SimplifiedSkillReActCodeAgent``.
    All AppWorld I/O happens inside the ``tmp_dir`` which acts as
    ``APPWORLD_ROOT`` for the subprocess.
    """

    MAX_TOTAL_CONCURRENCY: int = 60
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
        appworld_python: str = _DEFAULT_APPWORLD_PYTHON,
        appworld_root: str | None = None,
        model: str = "anthropic/glm-5",
        api_key: str | None = None,
        base_url: str | None = None,
        max_steps: int = 40,
        max_prompt_length: int | None = None,
        max_output_length: int | None = None,
        concurrency: int = 1,
    ):
        super().__init__()
        self.appworld_python = appworld_python
        self.appworld_root = appworld_root or os.path.expanduser("~/work/appworld")
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.max_steps = max_steps
        self.max_prompt_length = max_prompt_length
        self.max_output_length = max_output_length
        self.run_batch_concurrency = concurrency

    def system_description(self) -> str:
        return _APPWORLD_SYSTEM_DESCRIPTION

    async def _run(self, candidate_meta: CandidateMeta, data_inst: DataInst) -> SystemResult:
        """Not used — all execution goes through run_batch via subprocess."""
        raise NotImplementedError(
            "AppWorldSystem._run is not used; "
            "call run_batch instead, which uses subprocess appworld-run-batch"
        )

    @staticmethod
    def _build_run_batch_cmd(
        *,
        appworld_python: str,
        task_ids: list[str],
        experiment_name: str,
        skill_dir: str,
        model: str,
        api_key: str | None,
        base_url: str | None,
        max_steps: int,
        max_prompt_length: int | None,
        max_output_length: int | None,
        concurrency: int,
        skip_if_finished: bool,
        result_file: str,
    ) -> list[str]:
        """Build the command line for appworld-run-batch CLI."""
        bin_dir = os.path.dirname(appworld_python)
        run_batch_cli = os.path.join(bin_dir, "appworld-run-batch")

        cmd = [
            run_batch_cli,
            "--task-ids", *task_ids,
            "--experiment-name", experiment_name,
            "--skill-dir", skill_dir,
            "--model", model,
            "--max-steps", str(max_steps),
            "--concurrency", str(concurrency),
            "--result-file", result_file,
        ]
        if skip_if_finished:
            cmd.append("--skip-if-finished")
        if api_key:
            cmd.extend(["--api-key", api_key])
        if base_url:
            cmd.extend(["--base-url", base_url])
        if max_prompt_length is not None:
            cmd.extend(["--max-prompt-length", str(max_prompt_length)])
        if max_output_length is not None:
            cmd.extend(["--max-output-length", str(max_output_length)])
        return cmd

    async def run_batch(
        self,
        candidate_meta: CandidateMeta,
        data_list: list[DataInst],
        **kwargs,
    ) -> list[SystemResult]:
        """Run tasks via subprocess calling appworld-run-batch.

        Keyword args:
            experiment_name: Unique experiment name for this rollout.
            tmp_dir: The temporary directory serving as APPWORLD_ROOT for
                the subprocess.
        """
        experiment_name = kwargs.get("experiment_name")
        if not experiment_name:
            raise ValueError("experiment_name is required for AppWorldSystem.run_batch")
        tmp_dir = kwargs.get("tmp_dir")
        if not tmp_dir:
            raise ValueError("tmp_dir is required for AppWorldSystem.run_batch")

        skill_dir = os.path.join(candidate_meta.spec_dir, "skill")
        if not os.path.isdir(skill_dir):
            raise FileNotFoundError(f"Skill directory not found: {skill_dir}")

        task_ids = [d.id for d in data_list]
        result_file = os.path.join(tmp_dir, "run_result.json")

        cmd = self._build_run_batch_cmd(
            appworld_python=self.appworld_python,
            task_ids=task_ids,
            experiment_name=experiment_name,
            skill_dir=skill_dir,
            model=self.model,
            api_key=self.api_key,
            base_url=self.base_url,
            max_steps=self.max_steps,
            max_prompt_length=self.max_prompt_length,
            max_output_length=self.max_output_length,
            concurrency=self.run_batch_concurrency,
            skip_if_finished=False,
            result_file=result_file,
        )

        env = os.environ.copy()
        env["APPWORLD_ROOT"] = tmp_dir

        logger.info(
            "Running appworld-run-batch: %d tasks, experiment=%s, "
            "model=%s, concurrency=%d, max_steps=%d",
            len(task_ids), experiment_name,
            self.model, self.run_batch_concurrency, self.max_steps,
        )

        slots = min(self.run_batch_concurrency, len(data_list), self.MAX_TOTAL_CONCURRENCY)
        pool = await self._get_pool()

        # Run the subprocess
        t0 = time.monotonic()
        async with pool.slot(slots):
            process = await asyncio.create_subprocess_exec(
                *cmd,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()
        elapsed = time.monotonic() - t0

        if process.returncode != 0:
            logger.error(
                "appworld-run-batch failed (exit code %d) in %.1fs:\n"
                "stdout: %s\nstderr: %s",
                process.returncode, elapsed,
                stdout.decode("utf-8", errors="replace")[:2000],
                stderr.decode("utf-8", errors="replace")[:2000],
            )
        else:
            # Print subprocess stderr summary (contains progress info)
            stderr_text = stderr.decode("utf-8", errors="replace").strip()
            # Grab last few lines which contain the summary
            summary_lines = stderr_text.splitlines()[-3:] if stderr_text else []
            summary = " | ".join(line.strip() for line in summary_lines if line.strip())
            logger.info(
                "appworld-run-batch completed in %.1fs for experiment=%s: %s",
                elapsed, experiment_name, summary,
            )

        # Parse results
        task_results = self._read_run_result(result_file, task_ids)

        # Log per-task status summary
        completed_ids = [
            tid for tid, info in task_results.items()
            if info.get("status") == "completed"
        ]
        failed_ids = [
            tid for tid, info in task_results.items()
            if info.get("status") != "completed"
        ]
        logger.info(
            "Run results: %d completed, %d failed out of %d tasks "
            "(experiment=%s, %.1fs)",
            len(completed_ids), len(failed_ids), len(task_ids),
            experiment_name, elapsed,
        )
        if failed_ids:
            logger.warning(
                "Failed tasks: %s", ", ".join(failed_ids[:20]),
            )

        # Build SystemResult for each task
        results: list[SystemResult] = []
        for data_inst in data_list:
            task_id = data_inst.id
            task_info = task_results.get(task_id, {})

            # Read trajectory and usage from the experiment output directory
            trajectory = self._read_trajectory_from_tmp(
                tmp_dir, experiment_name, task_id,
            )
            usage = self._read_usage_from_tmp(
                tmp_dir, experiment_name, task_id,
            )

            status = task_info.get("status", "unknown")
            output_content = "completed" if status == "completed" else f"failed: {task_info.get('error', 'unknown')}"

            results.append(SystemResult(
                trajectory=trajectory,
                output=RolloutResult(content=output_content),
                usage=usage,
            ))

        return results

    @staticmethod
    def _read_run_result(
        result_file: str, task_ids: list[str],
    ) -> dict[str, dict]:
        """Read and parse run_result.json."""
        if not os.path.isfile(result_file):
            logger.warning("run_result.json not found at %s", result_file)
            return {}

        try:
            with open(result_file, encoding="utf-8") as f:
                data = json.load(f)
            return data.get("tasks", {})
        except Exception as e:
            logger.warning("Failed to parse run_result.json: %s", e)
            return {}

    @staticmethod
    def _read_trajectory_from_tmp(
        tmp_dir: str, experiment_name: str, task_id: str,
    ) -> Trajectory:
        """Read trajectory.json from the temporary APPWORLD_ROOT directory."""
        traj_path = os.path.join(
            tmp_dir, "experiments", "outputs", experiment_name,
            "tasks", task_id, "misc", "trajectory.json",
        )

        if not os.path.isfile(traj_path):
            # Trajectory is optional — may not exist if task failed early
            return Trajectory(root_span_list=[], trace_id=task_id)

        try:
            with open(traj_path, encoding="utf-8") as f:
                data = json.load(f)

            spans: list[Span] = []
            for span_dict in data.get("trajectory", []):
                spans.append(
                    Span(
                        name=span_dict.get("name", ""),
                        span_type=span_dict.get("type", "agent_step"),
                        input=span_dict.get("input"),
                        output=span_dict.get("output"),
                        start_time=span_dict.get("start_time"),
                        end_time=span_dict.get("end_time"),
                    )
                )
            return Trajectory(
                root_span_list=spans,
                trace_id=data.get("trace_id") or task_id,
            )
        except Exception as e:
            logger.warning("Failed to read trajectory.json for %s: %s", task_id, e)
            return Trajectory(root_span_list=[], trace_id=task_id)

    @staticmethod
    def _read_usage_from_tmp(
        tmp_dir: str, experiment_name: str, task_id: str,
    ) -> UsageStats | None:
        """Read usage.json from the temporary APPWORLD_ROOT directory."""
        usage_path = os.path.join(
            tmp_dir, "experiments", "outputs", experiment_name,
            "tasks", task_id, "misc", "usage.json",
        )

        if not os.path.isfile(usage_path):
            return None

        try:
            with open(usage_path, encoding="utf-8") as f:
                data = json.load(f)

            # usage.json structure: {"<task_id>": {"tokens": {...}, ...}}
            task_usage = data.get(task_id, data) if isinstance(data, dict) else {}
            tokens = task_usage.get("tokens", {})

            return UsageStats(
                input_tokens=tokens.get("input_cache_miss", 0),
                output_tokens=tokens.get("output", 0),
                cache_creation_input_tokens=tokens.get("input_cache_write", 0),
                cache_read_input_tokens=tokens.get("input_cache_hit", 0),
            )
        except Exception as e:
            logger.warning("Failed to read usage.json for %s: %s", task_id, e)
            return None
