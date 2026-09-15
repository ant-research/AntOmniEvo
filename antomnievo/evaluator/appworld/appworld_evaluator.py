from __future__ import annotations

import asyncio
import json
import logging
import os
import time

from antomnievo.interface.data_inst import DataInst
from antomnievo.interface.evaluator import Evaluator
from antomnievo.model.evaluation_result import EvaluationResult
from antomnievo.model.system_result import SystemResult

logger = logging.getLogger(__name__)


_APPWORLD_SCORING_CRITERIA = """\
AppWorld Goal Completion (strict pass/fail):

Whether the agent's code execution produced the correct final state
compared to the ground truth, as judged by per-task test suites.

- Each task has multiple test requirements (assertions on database state,
  answer correctness, etc.).
- A task passes (score=1.0) ONLY if ALL test requirements pass.
- A task fails (score=0.0) if ANY test requirement fails.
- The test suite is deterministic: time is frozen, and DB state is compared
  exactly.
- Common failure modes: wrong answer, missing API call, extra side effects,
  missing pagination, incorrect date/time handling.
"""

# Default path to the AppWorld venv Python interpreter.
_DEFAULT_APPWORLD_PYTHON = os.path.expanduser(
    "~/work/appworld/.venv/bin/python"
)


class AppWorldEvaluator(Evaluator):
    """Evaluator for AppWorld tasks using subprocess calling appworld-eval-batch.

    Uses the AppWorld venv Python to run ``appworld-eval-batch`` as a
    subprocess, which internally uses ``appworld.evaluator.evaluate_tasks``.
    All AppWorld I/O happens inside the ``tmp_dir`` which acts as
    ``APPWORLD_ROOT`` for the subprocess.
    """

    def __init__(
        self,
        appworld_python: str = _DEFAULT_APPWORLD_PYTHON,
        appworld_root: str | None = None,
        concurrency: int = 1,
    ):
        super().__init__()
        self.appworld_python = appworld_python
        self.appworld_root = appworld_root or os.path.expanduser("~/work/appworld")
        self.concurrency = concurrency

    def scoring_criteria(self) -> str:
        return _APPWORLD_SCORING_CRITERIA

    async def _evaluate(
        self,
        data_inst: DataInst,
        system_result: SystemResult,
    ) -> EvaluationResult:
        """Not used — all evaluation goes through evaluate_batch via subprocess."""
        raise NotImplementedError(
            "AppWorldEvaluator._evaluate is not used; "
            "call evaluate_batch instead, which uses subprocess appworld-eval-batch"
        )

    @staticmethod
    def _build_eval_batch_cmd(
        *,
        appworld_python: str,
        appworld_root: str,
        task_ids: list[str],
        experiment_name: str,
        result_file: str,
        save_reports: bool = True,
        concurrency: int = 1,
    ) -> list[str]:
        """Build the command line for appworld-eval-batch CLI."""
        bin_dir = os.path.dirname(appworld_python)
        eval_batch_cli = os.path.join(bin_dir, "appworld-eval-batch")

        cmd = [
            eval_batch_cli,
            "--task-ids", *task_ids,
            "--experiment-name", experiment_name,
            "--result-file", result_file,
            "--concurrency", str(concurrency),
        ]
        if save_reports:
            cmd.append("--save-reports")
        return cmd

    async def evaluate_batch(
        self,
        data_list: list[DataInst],
        system_results: list[SystemResult],
        **kwargs,
    ) -> list[EvaluationResult]:
        """Evaluate all tasks via subprocess calling appworld-eval-batch.

        Keyword args:
            experiment_name: The experiment name for this evaluation.
            tmp_dir: The temporary directory serving as APPWORLD_ROOT for
                the subprocess.
        """
        if len(data_list) != len(system_results):
            raise ValueError(
                f"data_list length ({len(data_list)}) != "
                f"system_results length ({len(system_results)})"
            )

        experiment_name = kwargs.get("experiment_name")
        if not experiment_name:
            raise ValueError("experiment_name is required for AppWorldEvaluator.evaluate_batch")
        tmp_dir = kwargs.get("tmp_dir")
        if not tmp_dir:
            raise ValueError("tmp_dir is required for AppWorldEvaluator.evaluate_batch")

        task_ids = [d.id for d in data_list]
        result_file = os.path.join(tmp_dir, "eval_result.json")

        cmd = self._build_eval_batch_cmd(
            appworld_python=self.appworld_python,
            appworld_root=self.appworld_root,
            task_ids=task_ids,
            experiment_name=experiment_name,
            result_file=result_file,
            save_reports=True,
            concurrency=self.concurrency,
        )

        env = os.environ.copy()
        env["APPWORLD_ROOT"] = tmp_dir

        logger.info(
            "Running appworld-eval-batch: %d tasks, experiment=%s, concurrency=%d",
            len(task_ids), experiment_name, self.concurrency,
        )

        # Run the subprocess
        t0 = time.monotonic()
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
                "appworld-eval-batch failed (exit code %d) in %.1fs:\n"
                "stdout: %s\nstderr: %s",
                process.returncode, elapsed,
                stdout.decode("utf-8", errors="replace")[:2000],
                stderr.decode("utf-8", errors="replace")[:2000],
            )
        else:
            stderr_text = stderr.decode("utf-8", errors="replace").strip()
            summary_lines = stderr_text.splitlines()[-3:] if stderr_text else []
            summary = " | ".join(l_.strip() for l_ in summary_lines if l_.strip())
            logger.info(
                "appworld-eval-batch completed in %.1fs for experiment=%s: %s",
                elapsed, experiment_name, summary,
            )

        # Parse eval results
        eval_data = self._read_eval_result(result_file)

        # Log aggregate metrics
        aggregate = eval_data.get("aggregate", {})
        if aggregate:
            logger.info(
                "Eval aggregate: task_goal_completion=%.1f%%, scenario_goal_completion=%.1f%% "
                "(experiment=%s, %.1fs)",
                aggregate.get("task_goal_completion", 0),
                aggregate.get("scenario_goal_completion", 0),
                experiment_name, elapsed,
            )

        # Build EvaluationResult for each task
        task_eval_map: dict[str, dict] = {}
        for task_eval in eval_data.get("tasks", []):
            task_eval_map[task_eval["task_id"]] = task_eval

        passed_ids = []
        failed_ids = []
        results: list[EvaluationResult] = []
        for data_inst in data_list:
            task_id = data_inst.id
            task_eval = task_eval_map.get(task_id, {})

            success = task_eval.get("success", False)
            score = 1.0 if success else 0.0
            num_tests = task_eval.get("num_tests", 0)
            pass_count = task_eval.get("pass_count", 0)

            reason = f"{pass_count}/{num_tests} tests passed"

            # Add failure details
            failures = task_eval.get("failures", [])
            if not success and failures:
                first_failure = failures[0]
                failure_req = first_failure.get("requirement", "unknown")
                failure_trace = first_failure.get("trace", "")[:200]
                reason += f"; first failure: {failure_req} — {failure_trace}"

                if len(failures) > 1:
                    all_failures = []
                    for f in failures:
                        all_failures.append(
                            f"- {f.get('requirement', 'unknown')}: "
                            f"{f.get('trace', '')[:150]}"
                        )
                    reason += "\nAll failures:\n" + "\n".join(all_failures)

            # Append evaluation report if available
            report_md = task_eval.get("report_md", "")
            if report_md:
                reason += f"\n\n--- Evaluation Report ---\n{report_md}"

            if success:
                passed_ids.append(task_id)
            else:
                failed_ids.append(task_id)

            results.append(EvaluationResult(
                data_id=task_id,
                metric_name="AppWorldGoalCompletion",
                score=score,
                reason=reason,
            ))

        logger.info(
            "Eval results: %d passed, %d failed out of %d tasks "
            "(experiment=%s, %.1fs)",
            len(passed_ids), len(failed_ids), len(task_ids),
            experiment_name, elapsed,
        )
        if failed_ids:
            logger.warning(
                "Failed evaluations: %s", ", ".join(failed_ids[:20]),
            )

        return results

    @staticmethod
    def _read_eval_result(result_file: str) -> dict:
        """Read and parse eval_result.json."""
        if not os.path.isfile(result_file):
            logger.warning("eval_result.json not found at %s", result_file)
            return {"tasks": []}

        try:
            with open(result_file, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("Failed to parse eval_result.json: %s", e)
            return {"tasks": []}
