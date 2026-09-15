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


class Text2SQLOptimizer(Optimizer):
    """Optimizer for text2sql (BirdTest / Spider2Snow).

    Creates a temporary directory for each rollout-and-evaluate cycle.
    Prepares dataset_batch.jsonl and passes it to both system and evaluator.
    """

    async def _run_and_evaluate(
        self, candidate_id: str, data_list: list[DataInst],
    ) -> RolloutEvalResult:
        logger.info(f"Rolling out candidate {candidate_id} and evaluating...")
        meta = self.candidate_store.get_meta(candidate_id)

        with tempfile.TemporaryDirectory(prefix=f"text2sql_{candidate_id}_") as tmp_dir:
            gen_dir = os.path.join(tmp_dir, "generate")
            eval_dir = os.path.join(tmp_dir, "evaluate")
            os.makedirs(gen_dir)
            os.makedirs(eval_dir)

            batch_path = os.path.join(tmp_dir, "dataset_batch.jsonl")
            self._write_dataset_batch(data_list, batch_path)

            t0 = time.monotonic()
            results = await self.system.run_batch(
                meta, data_list,
                output_dir=gen_dir,
                contexts_path=batch_path,
            )
            t1 = time.monotonic()
            logger.info(f"System run_batch completed in {t1 - t0:.1f}s for candidate {candidate_id}")

            predicted_sql_path = os.path.join(gen_dir, "predictions.json")
            evals = await self.evaluator.evaluate_batch(
                data_list, results,
                output_dir=eval_dir,
                predicted_sql_path=predicted_sql_path,
                contexts_path=batch_path,
            )
            t2 = time.monotonic()
            logger.info(f"Evaluate completed in {t2 - t1:.1f}s for candidate {candidate_id}")

        return RolloutEvalResult(results=results, evals=evals)

    @staticmethod
    def _write_dataset_batch(data_list: list[DataInst], batch_path: str) -> None:
        sorted_list = sorted(data_list, key=lambda d: d.id)
        with open(batch_path, "w", encoding="utf-8") as f:
            for data_inst in sorted_list:
                f.write(json.dumps(data_inst.to_context_dict(), ensure_ascii=False) + "\n")
