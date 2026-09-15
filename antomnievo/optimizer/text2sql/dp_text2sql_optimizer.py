import asyncio
import contextlib
import logging
import os
import shutil
import subprocess
import tempfile
from datetime import datetime

from antomnievo.dataset.dp.text2sql_data_inst import Text2SQLDataInst
from antomnievo.interface.data_inst import DataInst
from antomnievo.model.antomnievo_data import RolloutEvalResult
from antomnievo.optimizer.optimizer import Optimizer

logger = logging.getLogger(__name__)

_SKILL_NAME = "data-text2sql"
_SKILL_DIR = f"/root/.claude/skills/{_SKILL_NAME}"


def _generate_dockerfile() -> str:
    """Generate a Dockerfile that copies spec files from the build context."""
    lines = ["FROM harbor-dp-base:latest", ""]
    lines.append(f"RUN rm -rf {_SKILL_DIR} && mkdir -p {_SKILL_DIR}")
    lines.append(f"COPY spec/ {_SKILL_DIR}/")
    return "\n".join(lines) + "\n"


def _inject_spec_into_task_dir(task_dir: str, spec_dir: str) -> None:
    """Inject candidate spec into a task directory.

    Copies spec files into ``<task_dir>/environment/spec/`` so they are
    available in the Docker build context, then rewrites the Dockerfile
    to use a relative ``COPY spec/`` instruction.
    """
    env_dir = os.path.join(task_dir, "environment")
    spec_dest = os.path.join(env_dir, "spec")

    if os.path.isdir(spec_dest):
        shutil.rmtree(spec_dest)
    if os.path.isdir(spec_dir):
        shutil.copytree(spec_dir, spec_dest)

    dockerfile_path = os.path.join(env_dir, "Dockerfile")
    with open(dockerfile_path, "w", encoding="utf-8") as f:
        f.write(_generate_dockerfile())


def _cleanup_docker_for_tasks(task_ids: set[str]) -> None:
    """Remove Docker images and networks created by Harbor for the given task ids.

    Harbor names images as ``<trial_name>-main`` where trial_name starts with
    ``<task_id>__``.  Networks follow a similar ``<trial_name>_default`` pattern.
    """
    # 1. Find and remove matching images
    try:
        result = subprocess.run(
            ["docker", "images", "--format", "{{.Repository}}:{{.Tag}}"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            images_to_remove = []
            for line in result.stdout.splitlines():
                repo = line.split(":")[0]
                for task_id in task_ids:
                    if repo.startswith(f"{task_id}__"):
                        images_to_remove.append(line)
                        break
            if images_to_remove:
                subprocess.run(
                    ["docker", "rmi", "-f", *images_to_remove],
                    capture_output=True, timeout=60,
                )
                logger.info(f"Removed {len(images_to_remove)} Docker images for {len(task_ids)} tasks")
            else:
                logger.info("No Docker images to remove for tasks")
    except Exception as e:
        logger.warning(f"Failed to cleanup Docker images: {e}")

    # 2. Find and remove matching networks
    try:
        result = subprocess.run(
            ["docker", "network", "ls", "--format", "{{.Name}}"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            networks_to_remove = []
            for name in result.stdout.splitlines():
                for task_id in task_ids:
                    if name.startswith(f"{task_id}__"):
                        networks_to_remove.append(name)
                        break
            if networks_to_remove:
                subprocess.run(
                    ["docker", "network", "rm", *networks_to_remove],
                    capture_output=True, timeout=60,
                )
                logger.info(f"Removed {len(networks_to_remove)} Docker networks")
    except Exception as e:
        logger.warning(f"Failed to cleanup Docker networks: {e}")

    # 3. Prune dangling images
    with contextlib.suppress(Exception):
        subprocess.run(["docker", "image", "prune", "-f"], capture_output=True, timeout=60)


class DPText2SQLOptimizer(Optimizer):
    """Optimizer for Text2SQL.

    Creates a temporary directory per rollout containing dataset copies and
    job output.  The temp dir is auto-cleaned after each rollout cycle.
    Docker images and networks created by Harbor are cleaned up after each
    ``run_batch``.
    """

    async def _run_and_evaluate(
        self, candidate_id: str, data_list: list[DataInst],
    ) -> RolloutEvalResult:
        logger.info(f"Rolling out candidate {candidate_id} and evaluating...")
        meta = self.candidate_store.get_meta(candidate_id)

        job_name = f"{candidate_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        with tempfile.TemporaryDirectory(prefix=f"text2sql_{candidate_id}_", dir="/tmp") as tmp_dir:
            dataset_dir = os.path.join(tmp_dir, "dataset")
            output_dir = os.path.join(tmp_dir, "output")
            os.makedirs(dataset_dir)
            os.makedirs(output_dir)

            for data_inst in data_list:
                assert isinstance(data_inst, Text2SQLDataInst)
                dst = os.path.join(dataset_dir, data_inst.id)
                shutil.copytree(data_inst.task_dir, dst)
                _inject_spec_into_task_dir(dst, meta.spec_dir)

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
