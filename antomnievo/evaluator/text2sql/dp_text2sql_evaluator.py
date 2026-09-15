from __future__ import annotations

import json
import logging
import os

from antomnievo.dataset.dp.text2sql_data_inst import Text2SQLDataInst
from antomnievo.interface.data_inst import DataInst
from antomnievo.interface.evaluator import Evaluator
from antomnievo.model.evaluation_result import EvaluationResult
from antomnievo.model.system_result import SystemResult

logger = logging.getLogger(__name__)

_TEXT2SQL_SCORING_CRITERIA = """\
SQL correctness: average reward across all Harbor trial attempts for the same task.
- Each trial yields 1.0 (pass) or 0.0 (fail).
- Final score = mean of all trial rewards for the given data_id.
- No trials found → 0.0.

SQL extraction from trajectory:
- Read trajectory, walk steps in reverse order.
- Find the last step whose message field contains a ```sql``` code block.
- Extract all SQL from that step's message via regex matching ```sql ... ```, \
```SQL ... ```, ``` sql ... ``` (case-insensitive, dotall).
- All matched SQL strings from that single step are returned as model answers.
- If no step contains a SQL code block, the answer is empty → score 0.0.

IMPORTANT: The agent MUST wrap its final SQL in a ```sql code block. \
Without the code block, the extractor cannot find the SQL and the score will be 0.
"""

def _find_trial_dirs(jobs_dir: str, data_id: str) -> list[str]:
    """Find all trial directories for *data_id* under a Harbor job output directory.

    Scans ``jobs_dir`` for subdirectories named ``task_<id>__<suffix>``
    and matches ``<id>`` against *data_id* (which is the task directory name,
    e.g. ``task_1af22617``).  Returns all matching trial directories.

    When ``n_attempts > 1`` in the Harbor job config, the same task can
    produce multiple trial directories with different suffixes.
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

    return results


def _read_trial_reward(trial_dir: str) -> tuple[float | None, str]:
    """Read a single trial's reward and reason from its verifier output.

    Returns (reward, reason).  reward is None if no result found.
    """
    # Try verifier/eval.json first
    eval_path = os.path.join(trial_dir, "verifier", "eval.json")
    if os.path.isfile(eval_path):
        try:
            with open(eval_path, encoding="utf-8") as f:
                data = json.load(f)
            passed = data.get("pass", False)
            if isinstance(passed, str):
                passed = passed.strip().lower() == "true"
            reason = data.get("reason") or ""
            return (1.0 if bool(passed) else 0.0, reason)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to read eval.json: {e}")

    # Fallback to verifier/reward.txt
    reward_path = os.path.join(trial_dir, "verifier", "reward.txt")
    if os.path.isfile(reward_path):
        try:
            with open(reward_path, encoding="utf-8") as f:
                return (float(f.read().strip()), "")
        except (ValueError, OSError) as e:
            logger.warning(f"Failed to read reward.txt: {e}")

    return (None, "")


def _compute_avg_reward(jobs_dir: str, data_id: str) -> tuple[float, str]:
    """Compute the average reward across all trials for *data_id*.

    Returns (avg_score, reason_string).
    """
    trial_dirs = _find_trial_dirs(jobs_dir, data_id)

    if not trial_dirs:
        return (0.0, "No data found")

    rewards: list[float] = []
    trial_summaries: list[str] = []

    for trial_dir in trial_dirs:
        trial_name = os.path.basename(trial_dir)
        reward, reason = _read_trial_reward(trial_dir)
        if reward is not None:
            rewards.append(reward)
            summary = f"{trial_name}={reward:.1f}"
            if reason:
                summary += f"({reason})"
            trial_summaries.append(summary)
        else:
            # Trial with no result counts as 0.0
            rewards.append(0.0)
            trial_summaries.append(f"{trial_name}=0.0(no verifier result)")

    if not rewards:
        return (0.0, "No verifier results found in any trial")

    avg = sum(rewards) / len(rewards)
    reason = "avg(" + ", ".join(trial_summaries) + f")={avg:.2f}"

    return (avg, reason)


class DPText2SQLEvaluator(Evaluator):
    """Evaluator for text2sql tasks that reads results from Harbor job output.

    For each data_id, finds all matching trial directories under ``jobs_dir``
    and computes the **average reward** across trials.  This correctly handles
    ``n_attempts > 1`` where the same task is run multiple times.

    Harbor job output directory structure::

        jobs/<job_name>/
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

    Trial status determination:
    - SUCCESS:  exception_info is null AND reward == 1.0
    - FAIL:     exception_info is null AND reward == 0.0
    - ERROR:    exception_info is non-null
    - CANCELLED: exception_info.exception_type == "CancelledError"
    """

    def __init__(self):
        super().__init__()

    def scoring_criteria(self) -> str:
        return _TEXT2SQL_SCORING_CRITERIA

    async def _evaluate(
        self,
        data_inst: DataInst,
        _: SystemResult,
    ) -> EvaluationResult:
        pass  # Not used; we override evaluate_batch for efficiency

    async def evaluate_batch(
        self,
        data_list: list[DataInst],
        system_results: list[SystemResult],
        *,
        job_name: str | None = None,
        output_dir: str,
        **kwargs,
    ) -> list[EvaluationResult]:
        """Batch evaluation: compute scores for all data instances.

        Args:
            data_list: Data instances to evaluate.
            system_results: Corresponding system results (unused, scores come
                from the verifier output on disk).
            job_name: Harbor job name.
            output_dir: Directory containing Harbor job output.
        """
        if len(data_list) != len(system_results):
            raise ValueError(
                f"data_list length ({len(data_list)}) != "
                f"system_results length ({len(system_results)})"
            )

        scan_dir = os.path.join(output_dir, job_name)

        results: list[EvaluationResult] = []
        for data_inst in data_list:
            assert isinstance(data_inst, Text2SQLDataInst)
            avg_score, reason = _compute_avg_reward(scan_dir, data_inst.id)
            results.append(EvaluationResult(
                data_id=data_inst.id,
                metric_name="Text2SQLCorrectness",
                score=avg_score,
                reason=reason,
            ))

        return results
