from __future__ import annotations

import json
import logging
import random
from pathlib import Path

from antomnievo.dataset.spider2snow.spider2snow_data_inst import Spider2SnowDataInst

logger = logging.getLogger(__name__)


async def load_spider2snow_dataset(
    spider2_root: str,
    max_samples: int = 0,
    shuffle: bool = False,
) -> list[Spider2SnowDataInst]:
    """Load the Spider2-Snow dataset from the raw dataset directory.

    Args:
        spider2_root: Root directory of spider2-snow dataset containing
            spider2-snow.jsonl and resource/ directory.
        max_samples: Maximum number of samples to load. 0 means load all.
        shuffle: Whether to shuffle the dataset.
    """
    root = Path(spider2_root)
    questions_path = root / "spider2-snow.jsonl"
    gold_sql_dir = root / "evaluation_suite" / "gold" / "sql"

    if not questions_path.is_file():
        raise FileNotFoundError(f"Questions file not found: {questions_path}")

    instances: list[dict] = []
    with questions_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                instances.append(json.loads(line))

    result: list[Spider2SnowDataInst] = []
    for inst in instances:
        instance_id = inst["instance_id"]

        gold_sql = ""
        gold_sql_path = gold_sql_dir / f"{instance_id}.sql"
        if gold_sql_path.is_file():
            gold_sql = gold_sql_path.read_text(encoding="utf-8").strip()

        result.append(Spider2SnowDataInst(
            id=instance_id,
            query=inst["instruction"],
            golden_answer=gold_sql,
            db_id=inst["db_id"],
            external_knowledge=inst.get("external_knowledge", ""),
            spider2_root=str(root),
        ))

    if shuffle:
        random.shuffle(result)

    if max_samples > 0:
        result = result[:max_samples]

    logger.info(f"Loaded {len(result)} Spider2-Snow instances from {root}")
    return result


async def load_spider2snow_from_contexts(
    contexts_path: str,
    max_samples: int = 0,
    shuffle: bool = False,
) -> list[Spider2SnowDataInst]:
    """Load a Spider2-Snow dataset from a pre-processed contexts.jsonl file.

    Each line in the JSONL file is expected to have the format produced by
    the spider2-snow preprocessing pipeline::

        {
          "question_id": "...",
          "db_id": "...",
          "question": "...",
          "evidence": "...",
          "evidence_ref": "...",
          "schema": [{"table": "...", "description": "...", "ddl": "..."}, ...],
          "gold_sql": "..."
        }

    Args:
        contexts_path: Path to the contexts.jsonl file.
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

    result: list[Spider2SnowDataInst] = []
    for ctx in contexts:
        # schema: list of {table, description, ddl} or string (fallback)
        schema_raw = ctx.get("schema", [])
        schema_data: list[dict] = schema_raw if isinstance(schema_raw, list) else []

        result.append(Spider2SnowDataInst(
            id=str(ctx["question_id"]),
            query=ctx["question"],
            golden_answer=ctx.get("gold_sql", ""),
            db_id=ctx["db_id"],
            evidence=ctx.get("evidence", ""),
            evidence_ref=ctx.get("evidence_ref", "") or "",
            schema_data=schema_data,
        ))

    if shuffle:
        random.shuffle(result)

    if max_samples > 0:
        result = result[:max_samples]

    logger.info(f"Loaded {len(result)} Spider2-Snow data instances from {ctx_path}")
    return result
