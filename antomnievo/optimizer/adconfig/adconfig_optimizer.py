from __future__ import annotations

import json
import logging
import os
import tempfile
import time

from antomnievo.interface.data_inst import DataInst
from antomnievo.model.antomnievo_data import RolloutEvalResult
from antomnievo.optimizer.optimizer import Optimizer

logger = logging.getLogger(__name__)


class AdConfigOptimizer(Optimizer):
    """Optimizer for ad-config.

    Per-batch gen + eval artifacts go to a temporary directory, auto-cleaned on
    exit. The optimizer loop doesn't keep gen/eval intermediate files — only the
    RunRecord (trajectory + score + reason) is persisted to the candidate store
    via `Optimizer._save_run_record_list`.

    If you later want a full multi-stage eval report for a specific candidate,
    re-run `evaluate.py --eval-stage all` manually OUTSIDE the optimizer loop on
    that candidate's predictions (snapshot predictions.jsonl yourself if needed).
    """

    async def _run_and_evaluate(
        self,
        candidate_id: str,
        data_list: list[DataInst],
    ) -> RolloutEvalResult:
        logger.info("Rolling out candidate %s and evaluating...", candidate_id)
        meta = self.candidate_store.get_meta(candidate_id)

        with tempfile.TemporaryDirectory(prefix=f"adconfig_{candidate_id}_") as tmp_dir:
            gen_dir = os.path.join(tmp_dir, "generate")
            eval_dir = os.path.join(tmp_dir, "evaluate")
            os.makedirs(gen_dir)
            os.makedirs(eval_dir)

            batch_path = os.path.join(tmp_dir, "cases_batch.jsonl")
            self._write_batch_cases(data_list, batch_path)

            t0 = time.monotonic()
            results = await self.system.run_batch(
                meta, data_list, output_dir=gen_dir, cases_path=batch_path,
            )
            t1 = time.monotonic()
            logger.info("System run_batch done in %.1fs for candidate %s", t1 - t0, candidate_id)

            predictions_path = os.path.join(gen_dir, "predictions.jsonl")
            evals = await self.evaluator.evaluate_batch(
                data_list, results,
                output_dir=eval_dir,
                predictions_path=predictions_path,
                cases_path=batch_path,
            )
            t2 = time.monotonic()
            logger.info("Evaluate done in %.1fs", t2 - t1)

        return RolloutEvalResult(results=results, evals=evals)

    @staticmethod
    def _write_batch_cases(data_list: list[DataInst], batch_path: str) -> None:
        """Write the batch cases jsonl = FULL case rows (with gold), so generate.py
        can read app/env/base_config_version + code_version and evaluate.py the
        `expected.artifact.changes` gold."""
        sorted_list = sorted(data_list, key=lambda d: d.id)
        with open(batch_path, "w", encoding="utf-8") as f:
            for data_inst in sorted_list:
                f.write(json.dumps(data_inst.to_case_dict(), ensure_ascii=False) + "\n")
