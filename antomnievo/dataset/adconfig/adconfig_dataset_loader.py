from __future__ import annotations

import json
import logging
import random
from pathlib import Path

from antomnievo.dataset.adconfig.adconfig_data_inst import AdConfigDataInst

logger = logging.getLogger(__name__)


async def load_adconfig_dataset(
    cases_jsonl: str,
    max_samples: int = 0,
    shuffle: bool = False,
) -> list[AdConfigDataInst]:
    """Load ad-config eval cases from a cases jsonl (schema ``ad_config_change_eval_case/v1``).

    Each line is one case carrying ``input`` (user_request + extra_context) and
    ``expected.artifact.changes`` gold. Lines without a case_id or with malformed
    JSON are skipped. The full case row is retained on each instance (``raw``)
    so ``to_case_dict()`` can write it back verbatim for the subprocesses.

    Args:
        cases_jsonl: path to the cases jsonl (gold).
        max_samples: load only the first N (0 = all).
        shuffle: shuffle the loaded instances.
    """
    path = Path(cases_jsonl)
    if not path.is_file():
        raise FileNotFoundError(f"cases file not found: {path}")

    result: list[AdConfigDataInst] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                logger.warning("skip malformed case line: %s", exc)
                continue
            if not isinstance(raw, dict):
                continue
            if not (raw.get("case_id") or raw.get("id")):
                logger.warning("skip case with no id")
                continue
            result.append(AdConfigDataInst.from_raw(raw))

    if shuffle:
        random.shuffle(result)
    if max_samples > 0:
        result = result[:max_samples]

    logger.info("loaded %d ad-config cases from %s", len(result), path)
    return result
