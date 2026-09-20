from __future__ import annotations

import logging
import os
import tempfile
import time

from antomnievo.interface.data_inst import DataInst
from antomnievo.model.antomnievo_data import RolloutEvalResult
from antomnievo.optimizer.optimizer import Optimizer

logger = logging.getLogger(__name__)


class RagPipelineOptimizer(Optimizer):
    """Optimizer for retrieval-pipeline (MuSiQue) optimization.

    Mirrors AppWorldOptimizer: overrides ``_run_and_evaluate`` to thread
    scenario-specific state (per-rollout temp working dirs + the candidate's
    artifact_dir + the predictions path) through ``RagPipelineSystem.run_batch`` and
    ``RagPipelineEvaluator.evaluate_batch``. The temp dir both isolates this
    rollout's generate.py/evaluate.py outputs and shares the predictions file
    from the run to the eval (the evaluator reuses it instead of re-running the
    pipeline).

    The corpus is split-specific and lives on each data inst
    (``RagPipelineDataInst.corpus_path`` — train queries point at the train
    corpus, val at the val corpus); the system/evaluator read it per batch, so
    the optimizer does not touch corpus selection here.
    """

    async def _run_and_evaluate(
        self, candidate_id: str, data_list: list[DataInst],
    ) -> RolloutEvalResult:
        """Run generate.py over the batch, then evaluate.py over its predictions."""
        logger.info(
            "Rolling out candidate %s and evaluating %d queries...",
            candidate_id, len(data_list),
        )
        meta = self.candidate_store.get_meta(candidate_id)

        short_id = candidate_id[:8]
        t_start = time.monotonic()

        # One temp working dir per rollout: generate.py writes predictions +
        # trajectories under run/, evaluate.py writes eval.json + details under
        # eval/. Cleaned up automatically when the block exits.
        with tempfile.TemporaryDirectory(prefix=f"ragopt_{short_id}_") as tmp_dir:
            run_output_dir = os.path.join(tmp_dir, "run")
            eval_output_dir = os.path.join(tmp_dir, "eval")
            os.makedirs(run_output_dir, exist_ok=True)
            os.makedirs(eval_output_dir, exist_ok=True)

            t0 = time.monotonic()
            results = await self.system.run_batch(
                meta, data_list, run_output_dir=run_output_dir,
            )
            t1 = time.monotonic()
            logger.info(
                "system run_batch done in %.1fs (candidate=%s, %d queries)",
                t1 - t0, candidate_id, len(data_list),
            )

            # Reuse the predictions the system just produced — do NOT re-run the
            # pipeline. The evaluator scores nDCG@k / Recall@k against them.
            predictions_path = os.path.join(run_output_dir, "predictions.jsonl")
            evals = await self.evaluator.evaluate_batch(
                data_list,
                results,
                eval_output_dir=eval_output_dir,
                predictions_path=predictions_path,
                artifact_dir=meta.artifact_dir,
            )
            t2 = time.monotonic()
            avg_score = sum(e.score for e in evals) / len(evals) if evals else 0.0
            logger.info(
                "evaluate done in %.1fs (candidate=%s, %d queries, mean nDCG=%.4f)",
                t2 - t1, candidate_id, len(data_list), avg_score,
            )

            logger.info(
                "rollout+evaluate total %.1fs for candidate %s",
                t2 - t_start, candidate_id,
            )
            return RolloutEvalResult(results=results, evals=evals)
