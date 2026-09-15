import logging
import os
import random

from antomnievo.dataset.dp.text2sql_data_inst import Text2SQLDataInst

logger = logging.getLogger(__name__)


async def load_dataset(
    data_dir: str,
    max_samples: int = 0,
    shuffle: bool = False
) -> list[Text2SQLDataInst]:
    """Load a text2sql dataset from a directory of Harbor task directories.

    Scans ``data_dir`` for subdirectories named ``task_*``, reads each one's
    ``tests/test_data.json`` and ``environment/`` files, and returns a list of
    :class:`Text2SQLDataInst`.

    Args:
        data_dir: Path to the harbor tasks directory
            (e.g. ``/path/to/harbor_tasks_train``).
        max_samples: Maximum number of samples to load. 0 means load all.
        shuffle: Whether to shuffle the dataset.

    Returns:
        List of Text2SQLDataInst instances.
    """
    if not os.path.isdir(data_dir):
        raise FileNotFoundError(f"Data directory not found: {data_dir}")

    # Discover task directories
    task_dirs = sorted(
        entry
        for entry in os.listdir(data_dir)
        if entry.startswith("task_") and os.path.isdir(os.path.join(data_dir, entry))
    )

    if not task_dirs:
        raise ValueError(f"No task_* directories found in {data_dir}")

    if max_samples > 0:
        task_dirs = task_dirs[:max_samples]

    result: list[Text2SQLDataInst] = []
    for task_name in task_dirs:
        task_path = os.path.join(data_dir, task_name)
        try:
            inst = Text2SQLDataInst.from_task_dir(
                task_path,
            )
            result.append(inst)
        except Exception as e:
            logger.warning(f"Failed to load task {task_name}: {e}")
            continue

    if shuffle:
        random.shuffle(result)

    logger.info(f"Loaded {len(result)} text2sql tasks from {data_dir}")
    return result
