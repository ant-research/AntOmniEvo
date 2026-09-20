from __future__ import annotations

import asyncio
import json
import logging
import subprocess
from pathlib import Path

from antomnievo.interface.data_inst import DataInst
from antomnievo.interface.evaluator import Evaluator
from antomnievo.model.evaluation_result import EvaluationResult
from antomnievo.model.system_result import SystemResult

logger = logging.getLogger(__name__)


_ADCONFIG_SCORING_CRITERIA = """\
Ad-Config Change Deterministic Score — delegated to the business project's
`scripts/evaluate.py`, which shells out to the project's own eval pipeline
(run_offline.py). The deterministic stage scores with NO LLM.

## What's compared
The predicted `textproto_edit_result` (config_name / base_config_version /
target_config / edit_descriptions) vs the gold `expected.artifact.changes[0]`.
Both are parsed as protobuf (via a pre-built schema manifest's descriptors) and
compared field-by-field — strict equality (different_paths / missing_paths /
unexpected_paths all empty ⇒ equal).

## Score (per case, ∈ [0,1])
- 1.0 = the produced config matches the gold exactly (correct config_name,
  base_version, app/env, target_type, AND the edited target_config).
- 0.0 = no artifact produced (漏改 — agent blocked / baseline unreadable /
  MCP unavailable) OR a wrong/extra edit (错改 / 多改).

## reason
From the project evaluator's per-case detail:
- success: "all N expected change(s) produced and match (M predicted)".
- failure: names which field is missing / wrong-value / unexpected.
- ("轨迹为空" reason ⇒ a harness bug, not a real 0.)

## Mechanism notes (for the proposer)
- Deterministic stage = `nl_config_accuracy` (strict protobuf equality); fast, no
  model key / MCP needed.
- A pre-built schema manifest is a FIXED input (the cases carry `code_version`
  only in replay context, not as a structured change field; without the manifest
  the schema-source stage fails). It's not something the agent/tunable-artifacts control.
- The full `all` stage (LLM process-judge + semantic + runtime) exists but is too
  slow for the optimization loop; its `runtime` dimension is low because the agent
  correctly does NOT push the release offline — that's expected, not a defect.
"""


class AdConfigEvaluator(Evaluator):
    """Evaluator for ad-config that shells out to the business project's
    ``scripts/evaluate.py`` (which delegates to the project's own eval pipeline).

    Overrides ``evaluate_batch`` to run ONE ``evaluate.py`` subprocess per batch
    (reads ``--predictions`` predictions.jsonl + ``--cases`` gold cases, writes
    ``eval.json`` / ``details.jsonl``), then reads ``details.jsonl`` back and builds
    an :class:`EvaluationResult` per data_id. Default stage is ``deterministic``
    (no LLM) — fast enough for the optimization loop; ``all`` (LLM judges + runtime)
    is available but expensive.
    """

    def __init__(
        self,
        *,
        evaluate_script: str,
        python_path: str,
        schema_manifest: str | None = None,
        adrtbcore_repo: str | None = None,
        eval_stage: str = "deterministic",
        accuracy_threshold: float | None = None,
        timeout: int = 1800,
        extra_args: list[str] | None = None,
    ):
        """
        Args:
            evaluate_script: abs path to the business project's ``scripts/evaluate.py``.
            python_path: abs path to the business project's venv python
                (``.venv/bin/python``); evaluate.py + its deps run there.
            schema_manifest: pre-built schema manifest jsonl (covering the cases the
                optimizer will evaluate) passed via ``--schema-manifest`` — needed to
                SKIP the schema-source stage: this project's cases carry `code_version`
                only in replay context, not as a structured change field, so without a
                pre-built manifest the schema-source stage fails with "missing
                code_version". ``None`` → evaluate.py runs that stage (fails on this
                project's cases shape).
            adrtbcore_repo: project source repo for ``--adrtbcore-repo`` (schema source
                autofill / fallback). ``None`` → omit.
            eval_stage: ``deterministic`` (default, no LLM) or ``all`` (LLM process-judge
                + semantic + runtime; expensive). The optimization loop uses deterministic.
            accuracy_threshold: optional ``--accuracy-threshold`` override.
            timeout: subprocess timeout seconds (deterministic is usually fast; budget
                generously for ``all``).
            extra_args: extra CLI args appended to the evaluate.py command.
        """
        super().__init__()
        self.evaluate_script = evaluate_script
        self.python_path = python_path
        self.schema_manifest = schema_manifest
        self.adrtbcore_repo = adrtbcore_repo
        self.eval_stage = eval_stage
        self.accuracy_threshold = accuracy_threshold
        self.timeout = timeout
        self.extra_args = list(extra_args or [])

    def scoring_criteria(self) -> str:
        return _ADCONFIG_SCORING_CRITERIA

    async def _evaluate(self, data_inst: DataInst, system_result: SystemResult) -> EvaluationResult:
        # Batch-subprocess path: the optimizer calls evaluate_batch with output_dir +
        # predictions_path + cases_path. Per-instance _evaluate is intentionally unsupported.
        raise NotImplementedError(
            "AdConfigEvaluator runs via evaluate_batch (one evaluate.py subprocess per batch). "
            "Per-instance _evaluate is not supported — use an Optimizer subclass that threads "
            "output_dir + predictions_path + cases_path through evaluate_batch."
        )

    async def evaluate_batch(
        self,
        data_list: list[DataInst],
        system_results: list[SystemResult],
        *,
        output_dir: str,
        predictions_path: str,
        cases_path: str,
        **kwargs,
    ) -> list[EvaluationResult]:
        """Run evaluate.py for the batch under one subprocess, then read details.jsonl.

        The caller (an ``Optimizer`` subclass) passes ``predictions_path`` (the
        System's ``<gen_dir>/predictions.jsonl``), ``cases_path`` (the batch cases
        jsonl with FULL rows + gold), and ``output_dir`` (isolated per candidate per
        batch). ``system_results`` is NOT consumed — scoring reads the predictions
        file (authoritative).
        """
        if not data_list:
            return []

        cmd = [
            self.python_path, self.evaluate_script,
            "--predictions", predictions_path,
            "--cases", cases_path,
            "--output", output_dir,
            "--eval-stage", self.eval_stage,
        ]
        if self.schema_manifest:
            cmd.extend(["--schema-manifest", self.schema_manifest])
        if self.adrtbcore_repo:
            cmd.extend(["--adrtbcore-repo", self.adrtbcore_repo])
        if self.accuracy_threshold is not None:
            cmd.extend(["--accuracy-threshold", str(self.accuracy_threshold)])
        cmd.extend(self.extra_args)

        logger.info("Running ad-config evaluate: %s", " ".join(cmd))

        loop = asyncio.get_running_loop()
        proc: subprocess.CompletedProcess | None = None
        try:
            proc = await loop.run_in_executor(
                None,
                lambda: subprocess.run(cmd, capture_output=True, timeout=self.timeout),
            )
        except subprocess.TimeoutExpired:
            logger.error("ad-config evaluate timed out after %ss", self.timeout)

        if proc is not None and proc.returncode != 0:
            stderr = proc.stderr.decode(errors="replace")[:3000] if proc.stderr else ""
            logger.error("ad-config evaluate failed rc=%s: %s", proc.returncode, stderr)

        details_by_id = self._read_details(Path(output_dir) / "details.jsonl")
        metric_name = "ad_config_deterministic" if self.eval_stage == "deterministic" else f"ad_config_{self.eval_stage}"

        results: list[EvaluationResult] = []
        for data_inst in data_list:
            case_id = str(data_inst.id)
            d = details_by_id.get(case_id)
            if d is not None:
                score = float(d.get("score", 0.0))
                if score < 0.0:
                    score = 0.0
                elif score > 1.0:
                    score = 1.0
                reason = str(d.get("reason") or "")
                if not reason and d.get("nl_config_correct") is True:
                    reason = "nl_config_correct (no detail reason)"
            else:
                score = 0.0
                reason = "no evaluation detail for this case_id"
            results.append(EvaluationResult(
                data_id=case_id,
                metric_name=metric_name,
                score=score,
                reason=reason,
            ))
        return results

    @staticmethod
    def _read_details(details_path: Path) -> dict[str, dict]:
        if not details_path.is_file():
            return {}
        out: dict[str, dict] = {}
        with details_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(rec, dict):
                    cid = rec.get("case_id") or rec.get("data_id")
                    if cid is not None:
                        out[str(cid)] = rec
        return out
