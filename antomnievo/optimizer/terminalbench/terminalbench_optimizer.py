import asyncio
import contextlib
import logging
import os
import subprocess
import tempfile
from datetime import datetime

from antomnievo.dataset.terminalbench.terminalbench_data_inst import TerminalBenchDataInst
from antomnievo.interface.data_inst import DataInst
from antomnievo.model.antomnievo_data import RolloutEvalResult
from antomnievo.optimizer.optimizer import Optimizer

logger = logging.getLogger(__name__)


def _cleanup_docker_for_tasks(task_ids: set[str]) -> None:
    """Remove Docker containers/images/networks created by Harbor for *task_ids*.

    Harbor names containers/images/networks with a ``<task_id>__<hash>`` prefix
    (per terminalbench2/cleanup.sh). We match by that prefix.
    """
    # 1. Containers
    try:
        result = subprocess.run(
            ["docker", "ps", "-a", "--format", "{{.Names}}"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            to_remove = [
                name for name in result.stdout.splitlines()
                if any(name.startswith(f"{tid}__") for tid in task_ids)
            ]
            if to_remove:
                subprocess.run(
                    ["docker", "rm", "-f", *to_remove],
                    capture_output=True, timeout=60,
                )
                logger.info(f"Removed {len(to_remove)} Docker containers for {len(task_ids)} tasks")
    except Exception as e:
        logger.warning(f"Failed to cleanup Docker containers: {e}")

    # 2. Images
    try:
        result = subprocess.run(
            ["docker", "images", "--format", "{{.Repository}}:{{.Tag}}"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            to_remove = []
            for line in result.stdout.splitlines():
                repo = line.split(":")[0]
                if any(repo.startswith(f"{tid}__") for tid in task_ids):
                    to_remove.append(line)
            if to_remove:
                subprocess.run(
                    ["docker", "rmi", "-f", *to_remove],
                    capture_output=True, timeout=60,
                )
                logger.info(f"Removed {len(to_remove)} Docker images")
    except Exception as e:
        logger.warning(f"Failed to cleanup Docker images: {e}")

    # 3. Networks
    try:
        result = subprocess.run(
            ["docker", "network", "ls", "--format", "{{.Name}}"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            to_remove = [
                name for name in result.stdout.splitlines()
                if any(name.startswith(f"{tid}__") for tid in task_ids)
            ]
            if to_remove:
                subprocess.run(
                    ["docker", "network", "rm", *to_remove],
                    capture_output=True, timeout=60,
                )
                logger.info(f"Removed {len(to_remove)} Docker networks")
    except Exception as e:
        logger.warning(f"Failed to cleanup Docker networks: {e}")

    # 4. Prune dangling images
    with contextlib.suppress(Exception):
        subprocess.run(["docker", "image", "prune", "-f"], capture_output=True, timeout=60)


class TerminalBenchOptimizer(Optimizer):
    """Optimizer for Terminal-Bench 2.

    Simpler than the dp_text2sql optimizer: because ``tbtest generate`` mounts
    the spec via ``--spec-dir`` (yaml mount rewrite), there is no need to copy
    task directories or rewrite Dockerfiles per rollout. Each rollout just
    points at the shared dataset dir and passes ``candidate_meta.spec_dir``.

    Only a tmp output dir is created per rollout so Harbor artifacts don't
    accumulate on disk; Docker containers/images/networks matching
    ``<task_id>__*`` are cleaned up after each ``run_batch``.
    """

    async def _run_and_evaluate(
        self, candidate_id: str, data_list: list[DataInst],
    ) -> RolloutEvalResult:
        # Empty batch = nothing to do. This is the supported way to skip a
        # split (e.g. an empty val set): the base optimizer guards the score
        # aggregate, and `_evaluate_first`/`_step_validate` call this with an
        # empty list, so short-circuit here rather than failing the dataset-dir
        # check below.
        if not data_list:
            logger.info(f"No data instances to evaluate for candidate {candidate_id}; skipping")
            return RolloutEvalResult(results=[], evals=[])

        logger.info(f"Rolling out candidate {candidate_id} and evaluating...")
        meta = self.candidate_store.get_meta(candidate_id)

        job_name = f"{candidate_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # All data instances must share a dataset dir (tbtest -p accepts one).
        dataset_dirs = {d.get_dataset_dir() for d in data_list if isinstance(d, TerminalBenchDataInst)}
        if len(dataset_dirs) != 1:
            raise ValueError(
                f"All data instances must share a single dataset dir "
                f"(got {len(dataset_dirs)}: {dataset_dirs})"
            )
        dataset_dir = next(iter(dataset_dirs))

        with tempfile.TemporaryDirectory(
            prefix=f"terminalbench_{candidate_id}_", dir="/tmp",
        ) as tmp_dir:
            output_dir = os.path.join(tmp_dir, "output")
            os.makedirs(output_dir)

            results = await self.system.run_batch(
                meta, data_list,
                job_name=job_name,
                dataset_dir=dataset_dir,
                output_dir=output_dir,
            )

            task_ids = {d.id for d in data_list}
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, _cleanup_docker_for_tasks, task_ids)

            evals = await self.evaluator.evaluate_batch(
                data_list, results,
                job_name=job_name,
                output_dir=output_dir,
            )
            logger.info(f"Completed rollout and evaluation for candidate {candidate_id}")

        return RolloutEvalResult(results=results, evals=evals)
