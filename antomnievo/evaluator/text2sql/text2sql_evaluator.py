from __future__ import annotations

import asyncio
import json
import logging
import subprocess
from pathlib import Path
from typing import Literal

from antomnievo.interface.data_inst import DataInst
from antomnievo.interface.evaluator import Evaluator
from antomnievo.model.evaluation_result import EvaluationResult
from antomnievo.model.system_result import SystemResult

logger = logging.getLogger(__name__)

_BIRDTEST_SCORING_CRITERIA = """\
Combined SQL Score (EX + VES efficiency penalty):

1. Execution Accuracy (EX): whether the predicted SQL produces the same result set
   as the gold SQL when executed against the SQLite database.
   - set(predicted_rows) == set(gold_rows) → EX=1, else EX=0.
   - If the predicted SQL fails to execute, EX=0.

2. Valid Efficiency Score (VES): measures execution efficiency when EX=1.
   - VES = min(sqrt(gold_time / pred_time), 1.0) if EX=1, else VES=0.
   - Predicted SQL faster or equal to gold → VES=1.0 (no penalty).
   - Predicted SQL slower → VES < 1.0 (efficiency penalty).

3. Combined Score = EX * (0.7 + 0.3 * VES)
   - Correctness dominates: incorrect SQL always scores 0.0.
   - Efficiency penalty: a correct but slow SQL scores between 0.7 and 1.0.
   - Perfect score (1.0) requires both correct results and efficient execution.
"""

_SPIDER2SNOW_SCORING_CRITERIA = """\
Execution Accuracy (EX):

Whether the predicted SQL produces the same result set as the gold SQL
when executed against the Snowflake database.
- Result matches gold → score=1, else score=0.
- If the predicted SQL fails to execute, score=0.
"""


def _parse_bird_detail(detail: dict) -> tuple[float, str]:
    """Parse a BirdTest details.jsonl entry into (score, reason)."""
    ex = float(detail.get("ex", 0))
    ves = float(detail.get("ves", 0))
    score = ex * (0.7 + 0.3 * ves)
    reason = detail.get("ex_reason", "")
    if ex == 1:
        reason += f" | VES={ves:.4f}, combined={score:.4f}"
    return score, reason


def _parse_spider2snow_detail(detail: dict) -> tuple[float, str]:
    """Parse a Spider2Snow details.jsonl entry into (score, reason)."""
    score = float(detail.get("score", 0))
    reason = detail.get("reason", "") or ""
    error_info = detail.get("error_info")
    if error_info and score == 0:
        reason = f"{reason} | error: {error_info}" if reason else f"error: {error_info}"
    return score, reason


_SCORE_PARSERS = {
    "bird": _parse_bird_detail,
    "spider2snow": _parse_spider2snow_detail,
}


class Text2SQLEvaluator(Evaluator):
    """Evaluator for text2sql that calls an evaluate subprocess.

    Works with both BirdTest and Spider2Snow backends by configuring
    extra_args and score_parser.
    """

    def __init__(
        self,
        evaluate_script: str,
        python_path: str,
        score_parser: Literal["bird", "spider2snow"] = "bird",
        extra_args: list[str] | None = None,
    ):
        """
        Args:
            evaluate_script: Path to evaluate.py script.
            python_path: Path to venv python executable.
            score_parser: How to parse details.jsonl. "bird" or "spider2snow".
            extra_args: Additional CLI args (e.g. ["--spider2_root", "/path"]).
        """
        super().__init__()
        self.evaluate_script = evaluate_script
        self.python_path = python_path
        self.score_parser = score_parser
        self.extra_args = extra_args or []

    def scoring_criteria(self) -> str:
        if self.score_parser == "spider2snow":
            return _SPIDER2SNOW_SCORING_CRITERIA
        return _BIRDTEST_SCORING_CRITERIA

    async def _evaluate(
        self,
        data_inst: DataInst,
        system_result: SystemResult,
    ) -> EvaluationResult:
        pass

    async def evaluate_batch(
        self,
        data_list: list[DataInst],
        system_results: list[SystemResult],
        *,
        output_dir: str,
        predicted_sql_path: str,
        contexts_path: str,
        **kwargs,
    ) -> list[EvaluationResult]:
        """Call evaluate.py and read per-question scores from output."""
        cmd = [
            self.python_path, self.evaluate_script,
            "--contexts", contexts_path,
            "--predicted_sql_path", predicted_sql_path,
            "--output", output_dir,
        ]
        cmd.extend(self.extra_args)

        logger.info(f"Running text2sql evaluate: {' '.join(cmd)}")

        loop = asyncio.get_running_loop()
        proc = await loop.run_in_executor(
            None,
            lambda: subprocess.run(cmd, capture_output=True),
        )

        if proc.returncode != 0:
            stderr_msg = proc.stderr.decode(errors="replace")[:3000] if proc.stderr else ""
            logger.error(f"text2sql evaluate failed (rc={proc.returncode}): {stderr_msg}")

        details = self._read_details(Path(output_dir) / "details.jsonl")
        detail_by_qid: dict[str, dict] = {}
        for detail in details:
            qid = str(detail.get("question_id", ""))
            detail_by_qid[qid] = detail

        parse_fn = _SCORE_PARSERS.get(self.score_parser, _parse_bird_detail)
        metric_name = "Spider2SnowEX" if self.score_parser == "spider2snow" else "BirdTestEX"

        results: list[EvaluationResult] = []
        for data_inst in data_list:
            score = 0.0
            reason = "No evaluation detail"
            detail = detail_by_qid.get(str(data_inst.id))
            if detail is not None:
                score, reason = parse_fn(detail)

            results.append(EvaluationResult(
                data_id=data_inst.id,
                metric_name=metric_name,
                score=score,
                reason=reason,
            ))

        return results

    @staticmethod
    def _read_details(details_path: Path) -> list[dict]:
        if not details_path.is_file():
            return []
        results = []
        with details_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    results.append(json.loads(line))
        return results
