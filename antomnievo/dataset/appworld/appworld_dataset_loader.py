from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
from collections.abc import Sequence

from antomnievo.dataset.appworld.appworld_data_inst import AppWorldDataInst

logger = logging.getLogger(__name__)

# Default path to the AppWorld venv Python interpreter.
_DEFAULT_APPWORLD_PYTHON = os.path.expanduser(
    "~/work/appworld/.venv/bin/python"
)

# Default path to the AppWorld project root.
_DEFAULT_APPWORLD_ROOT = os.path.expanduser("~/work/appworld")

# Default path to the train/val split file.
_DEFAULT_SPLIT_FILE = os.path.expanduser(
    "~/work/appworld/experiments/data_splits/train_val_split.json"
)


async def load_appworld_dataset(
    dataset_name: str = "dev",
    appworld_python: str = _DEFAULT_APPWORLD_PYTHON,
    appworld_root: str = _DEFAULT_APPWORLD_ROOT,
    task_ids: Sequence[str] | None = None,
) -> list[AppWorldDataInst]:
    """Load an AppWorld dataset as a list of :class:`AppWorldDataInst`.

    Uses the ``experiments.list_tasks`` subprocess to fetch task IDs and
    instructions from the AppWorld project, avoiding direct import of
    the ``appworld`` package.

    Args:
        dataset_name: Name of the AppWorld dataset split
            (e.g. ``"dev"``, ``"test_normal"``, ``"test_challenge"``).
            Ignored if ``task_ids`` is provided.
        appworld_python: Path to the AppWorld venv Python interpreter.
        appworld_root: Path to the AppWorld project root (used to set
            ``APPWORLD_ROOT`` for the subprocess).
        task_ids: Optional explicit list of task IDs to load. When provided,
            only these task IDs will be included in the result. This allows
            loading a custom subset (e.g. from a train/val split file) without
            being limited to a single named dataset.

    Returns:
        A list of :class:`AppWorldDataInst` instances sorted by task_id.
    """
    with tempfile.TemporaryDirectory(prefix="appworld_tasks_") as tmp_dir:
        output_path = os.path.join(tmp_dir, "tasks.json")

        bin_dir = os.path.dirname(appworld_python)
        list_tasks_cli = os.path.join(bin_dir, "appworld-list-tasks")
        cmd = [
            list_tasks_cli,
            "--dataset", dataset_name,
            "--output", output_path,
        ]

        env = os.environ.copy()
        env["APPWORLD_ROOT"] = appworld_root

        process = await asyncio.create_subprocess_exec(
            *cmd,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        stderr_text = stderr.decode("utf-8", errors="replace")

        if process.returncode != 0:
            raise RuntimeError(
                f"list_tasks.py failed (exit code {process.returncode}):\n"
                f"stdout: {stdout.decode('utf-8', errors='replace')[:2000]}\n"
                f"stderr: {stderr_text[:2000]}"
            )

        if not os.path.isfile(output_path):
            raise RuntimeError(
                f"list_tasks.py did not produce output file {output_path}\n"
                f"stderr: {stderr_text[:2000]}"
            )

        # Read and parse the output
        with open(output_path, encoding="utf-8") as f:
            tasks_data = json.load(f)

        # If task_ids specified, filter to only those IDs
        if task_ids is not None:
            id_set = set(task_ids)
            tasks_data = [t for t in tasks_data if t["task_id"] in id_set]
            # Warn about missing IDs
            found_ids = {t["task_id"] for t in tasks_data}
            missing = id_set - found_ids
            if missing:
                logger.warning(
                    f"{len(missing)} task IDs not found in dataset '{dataset_name}': "
                    f"{sorted(missing)[:5]}{'...' if len(missing) > 5 else ''}"
                )

        instances: list[AppWorldDataInst] = []
        for task in tasks_data:
            instances.append(
                AppWorldDataInst(
                    id=task["task_id"],
                    query=task["instruction"],
                    golden_answer=task.get("golden_answer", ""),
                    task_id=task["task_id"],
                    scenario_id=task["scenario_id"],
                )
            )

        instances.sort(key=lambda x: x.id)
        logger.info(f"Prepared {len(instances)} AppWorldDataInst instances from dataset '{dataset_name}'")
        return instances


def load_split_task_ids(
    split_file: str = _DEFAULT_SPLIT_FILE,
) -> dict[str, list[str]]:
    """Load task IDs from a train/val split JSON file.

    The split file should have the structure::

        {
          "train": { "task_ids": [...] },
          "validation": {
            "test_normal": { "task_ids": [...] },
            "test_challenge": { "task_ids": [...] }
          }
        }

    Args:
        split_file: Path to the split JSON file.

    Returns:
        A dict with keys ``"train"``, ``"val_test_normal"``,
        ``"val_test_challenge"``, and ``"val_all"``, each mapping to
        a list of task ID strings.
    """
    with open(split_file, encoding="utf-8") as f:
        data = json.load(f)

    train_ids = data["train"]["task_ids"]
    val_normal_ids = data["validation"]["test_normal"]["task_ids"]
    val_challenge_ids = data["validation"]["test_challenge"]["task_ids"]

    return {
        "train": train_ids,
        "val_test_normal": val_normal_ids,
        "val_test_challenge": val_challenge_ids,
        "val_all": val_normal_ids + val_challenge_ids,
    }


async def load_appworld_split(
    split_file: str = _DEFAULT_SPLIT_FILE,
    appworld_python: str = _DEFAULT_APPWORLD_PYTHON,
    appworld_root: str = _DEFAULT_APPWORLD_ROOT,
) -> tuple[list[AppWorldDataInst], list[AppWorldDataInst]]:
    """Load train and validation datasets from a split file.

    Convenience function that reads a split JSON file and loads the
    corresponding task data from AppWorld.

    Training data comes from the ``train`` + ``dev`` datasets.
    Validation data comes from ``test_normal`` + ``test_challenge`` datasets.

    Args:
        split_file: Path to the split JSON file.
        appworld_python: Path to the AppWorld venv Python interpreter.
        appworld_root: Path to the AppWorld project root.

    Returns:
        A tuple of ``(train_instances, val_instances)``.
    """
    splits = load_split_task_ids(split_file)
    train_ids = splits["train"]
    val_ids = splits["val_all"]

    logger.info(
        f"Loading split: {len(train_ids)} train, {len(val_ids)} val "
        f"from {split_file}"
    )

    # Train IDs are spread across "train" and "dev" datasets.
    # Load both fully, then filter by the split's train_ids.
    train_dataset = await load_appworld_dataset(
        dataset_name="train",
        appworld_python=appworld_python,
        appworld_root=appworld_root,
    )
    dev_dataset = await load_appworld_dataset(
        dataset_name="dev",
        appworld_python=appworld_python,
        appworld_root=appworld_root,
    )
    train_id_set = set(train_ids)
    all_train = [
        inst for inst in train_dataset + dev_dataset
        if inst.id in train_id_set
    ]

    # Validation IDs come from test_normal + test_challenge.
    # Load both fully, then filter by the split's val IDs.
    val_normal = await load_appworld_dataset(
        dataset_name="test_normal",
        appworld_python=appworld_python,
        appworld_root=appworld_root,
    )
    val_challenge = await load_appworld_dataset(
        dataset_name="test_challenge",
        appworld_python=appworld_python,
        appworld_root=appworld_root,
    )
    val_id_set = set(val_ids)
    all_val = [
        inst for inst in val_normal + val_challenge
        if inst.id in val_id_set
    ]

    all_val.sort(key=lambda x: x.id)

    logger.info(
        f"Loaded split: train={len(all_train)}, val={len(all_val)} "
        f"(normal={len(val_normal)}, challenge={len(val_challenge)})"
    )

    return all_train, all_val
