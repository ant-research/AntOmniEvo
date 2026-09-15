from __future__ import annotations

import logging
import os
import tempfile
import time

from antomnievo.interface.data_inst import DataInst
from antomnievo.model.antomnievo_data import RolloutEvalResult
from antomnievo.optimizer.optimizer import Optimizer

logger = logging.getLogger(__name__)


class AppWorldOptimizer(Optimizer):
    """Optimizer for AppWorld tasks.

    Creates a unique experiment name per rollout+evaluate cycle so that
    AppWorld task outputs don't collide across candidates.  Each
    ``_run_and_evaluate`` call creates a temporary directory that
    serves as ``APPWORLD_ROOT`` for all subprocesses — containing a
    ``data`` symlink to the real data and an ``experiments/outputs``
    directory for task outputs.  The temp directory is automatically
    cleaned up when the rollout finishes.

    Delegates to ``AppWorldSystem`` for rollout (via subprocess) and
    ``AppWorldEvaluator`` for evaluation (via subprocess).
    """

    def __init__(self, appworld_data_dir: str | None = None, **kwargs):
        super().__init__(**kwargs)
        self.appworld_data_dir = appworld_data_dir or os.path.expanduser(
            "~/work/appworld/data"
        )

    async def _run_and_evaluate(
        self, candidate_id: str, data_list: list[DataInst],
    ) -> RolloutEvalResult:
        """Run the system on a batch of tasks, then evaluate the outputs.

        Creates a temporary directory to isolate this rollout's AppWorld
        I/O.  The temp dir acts as ``APPWORLD_ROOT`` for all subprocesses
        (appworld-run-batch, appworld-eval-batch), with ``data/`` symlinked
        to the real AppWorld data directory.

        The experiment name is unique per call (format:
        ``antomnievo_{short_id}_{timestamp}``) to prevent output collisions.
        """
        logger.info(
            "Rolling out candidate %s and evaluating %d tasks...",
            candidate_id, len(data_list),
        )
        meta = self.candidate_store.get_meta(candidate_id)

        # Create a unique experiment name for this rollout
        short_id = candidate_id[:8]
        ts = int(time.monotonic() * 1000) % (10**8)
        experiment_name = f"antomnievo_{short_id}_{ts}"
        logger.info(
            "Experiment name: %s (candidate=%s)", experiment_name, candidate_id,
        )

        t_start = time.monotonic()

        # Create a temporary directory to serve as APPWORLD_ROOT
        with tempfile.TemporaryDirectory(prefix=f"appopt_{short_id}_") as tmp_dir:
            logger.info("APPWORLD_ROOT tmp_dir: %s", tmp_dir)

            # Set up the directory structure expected by AppWorld
            self._setup_tmp_dir(tmp_dir)

            # Run the system
            t0 = time.monotonic()
            results = await self.system.run_batch(
                meta,
                data_list,
                experiment_name=experiment_name,
                tmp_dir=tmp_dir,
            )
            t1 = time.monotonic()
            logger.info(
                "System run_batch completed in %.1fs for candidate %s "
                "(experiment=%s, %d tasks)",
                t1 - t0, candidate_id, experiment_name, len(data_list),
            )

            # Evaluate the outputs
            evals = await self.evaluator.evaluate_batch(
                data_list,
                results,
                experiment_name=experiment_name,
                tmp_dir=tmp_dir,
            )
            t2 = time.monotonic()
            logger.info(
                "Evaluate completed in %.1fs for candidate %s "
                "(experiment=%s, %d tasks)",
                t2 - t1, candidate_id, experiment_name, len(data_list),
            )

            # Log score summary
            passed = sum(1 for e in evals if e.score > 0)
            avg_score = sum(e.score for e in evals) / len(evals) if evals else 0.0
            logger.info(
                "Rollout+evaluate total %.1fs: %d/%d passed, avg_score=%.2f "
                "(candidate=%s, experiment=%s)",
                t2 - t_start, passed, len(data_list), avg_score,
                candidate_id, experiment_name,
            )

            return RolloutEvalResult(results=results, evals=evals)

    def _setup_tmp_dir(self, tmp_dir: str) -> None:
        """Set up the temporary directory as a valid APPWORLD_ROOT.

        Creates:
            tmp_dir/data -> real AppWorld data directory (symlink)
            tmp_dir/experiments/outputs/  (directory)
        """
        data_link = os.path.join(tmp_dir, "data")
        if not os.path.exists(data_link):
            os.symlink(self.appworld_data_dir, data_link)
            logger.info(
                "Symlinked %s -> %s", data_link, self.appworld_data_dir,
            )

        outputs_dir = os.path.join(tmp_dir, "experiments", "outputs")
        os.makedirs(outputs_dir, exist_ok=True)
