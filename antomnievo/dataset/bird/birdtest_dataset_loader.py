from __future__ import annotations

import json
import logging
import random
from pathlib import Path

from antomnievo.dataset.bird.birdtest_data_inst import BirdTestDataInst

logger = logging.getLogger(__name__)


async def load_birdtest_dataset(
    contexts_path: str,
    max_samples: int = 0,
    shuffle: bool = False,
) -> list[BirdTestDataInst]:
    """Load a BirdTest dataset from contexts.jsonl.

    Each line in contexts.jsonl contains all fields including gold_sql.

    Args:
        contexts_path: Path to contexts.jsonl from birdtest preprocessing.
        max_samples: Maximum number of samples to load. 0 means load all.
        shuffle: Whether to shuffle the dataset.
    """
    ctx_path = Path(contexts_path)
    if not ctx_path.is_file():
        raise FileNotFoundError(f"Contexts file not found: {ctx_path}")

    contexts: list[dict] = []
    with ctx_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                contexts.append(json.loads(line))

    result: list[BirdTestDataInst] = []
    for ctx in contexts:
        result.append(BirdTestDataInst(
            id=str(ctx["question_id"]),
            query=ctx["question"],
            golden_answer=ctx["gold_sql"],
            db_id=ctx["db_id"],
            evidence=ctx.get("evidence", ""),
            difficulty=ctx.get("difficulty", ""),
            schema_text=ctx.get("schema", ""),
        ))

    if shuffle:
        random.shuffle(result)

    if max_samples > 0:
        result = result[:max_samples]

    logger.info(f"Loaded {len(result)} BirdTest data instances from {ctx_path}")
    return result
