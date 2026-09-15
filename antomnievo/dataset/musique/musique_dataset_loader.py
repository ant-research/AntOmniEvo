import os
import random

from antomnievo.common.utils.json_utils import parse_jsonl_file
from antomnievo.dataset.musique.musique_data_inst import MusiqueDataInst


async def load_dataset(
    file_path: str,
    max_samples: int = 300,
    shuffle: bool = True,
) -> list[MusiqueDataInst]:
    """Load a MuSiQue JSONL dataset and convert to MusiqueDataInst list."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Dataset file not found: {file_path}")

    data = parse_jsonl_file(file_path)
    result = []
    for item in data[:max_samples]:
        if "question" in item and "answer" in item:
            result.append(MusiqueDataInst.from_raw(item))

    if shuffle:
        random.shuffle(result)
    return result
