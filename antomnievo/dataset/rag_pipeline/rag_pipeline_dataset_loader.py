"""Per-split dataset loader for retrieval-pipeline optimization on MuSiQue.

Reads ONE split of the pre-built MuSiQue dataset shipped with retrieval-test:

    <split_dir>/corpus.jsonl   — one ``{_id, title, text}`` per passage; ``_id``
                                 is ``<query_id>__<paragraph_idx>``.
    <split_dir>/queries.jsonl  — one ``{query_id, query, golden_doc_ids}`` per
                                 question; golden_doc_ids reference corpus ``_id``s.

Mirrors the repo convention (text2sql / terminalbench): a single ``load_dataset``
that loads one split from a directory, called twice in the entry (train split,
val split). Each instance carries its split's ``corpus_path`` so the runtime
selects the right retrieval pool per batch (train vs val are separate corpora).

The corpus is PER-SPLIT (a question's supporting passages live only in its own
split's corpus), so train and val MUST be loaded from their respective dirs.
"""

from __future__ import annotations

import json
import logging
import os
import random

from antomnievo.dataset.rag_pipeline.rag_pipeline_data_inst import RagPipelineDataInst

logger = logging.getLogger(__name__)


def _load_corpus_lookup(corpus_path: str) -> dict[str, dict]:
    """Read corpus.jsonl into {doc_id: {doc_id, title, text}}.

    Handles both retrieval-test's ``_id`` key and a BEIR-style ``doc_id`` key.
    """
    lookup: dict[str, dict] = {}
    if not os.path.isfile(corpus_path):
        logger.warning("corpus not found: %s", corpus_path)
        return lookup
    with open(corpus_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            did = str(rec.get("doc_id") or rec.get("_id"))
            lookup[did] = {
                "doc_id": did,
                "title": rec.get("title", ""),
                "text": rec.get("text") or rec.get("contents") or "",
            }
    return lookup


async def load_dataset(
    split_dir: str,
    max_samples: int | None = None,
    shuffle: bool = False,
) -> list[RagPipelineDataInst]:
    """Load one MuSiQue split (queries + its corpus) into RagPipelineDataInst.

    Args:
        split_dir: path to the split dir (contains ``corpus.jsonl`` +
            ``queries.jsonl``), e.g. ``datasets/musique/train`` or ``.../val``.
        max_samples: cap the number of queries loaded (None = all).
        shuffle: shuffle the loaded instances (default False, matches the
            text2sql/terminalbench examples' determinism).

    Each instance's ``golden_docs`` are enriched from this split's corpus, and
    ``corpus_path`` is stamped on the instance (train queries -> train corpus,
    val queries -> val corpus) so the system/evaluator select the right
    retrieval pool per batch — MuSiQue ships train/val as two separate corpora.
    """
    corpus_path = os.path.join(split_dir, "corpus.jsonl")
    queries_path = os.path.join(split_dir, "queries.jsonl")
    corpus_lookup = _load_corpus_lookup(corpus_path)

    insts: list[RagPipelineDataInst] = []
    if not os.path.isfile(queries_path):
        logger.warning("queries not found: %s", queries_path)
        return insts
    with open(queries_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            golden_ids = [str(d) for d in rec.get("golden_doc_ids", [])]
            insts.append(RagPipelineDataInst(
                id=str(rec["query_id"]),
                query=rec["query"],
                golden_answer="",
                golden_docs=[corpus_lookup[d] for d in golden_ids if d in corpus_lookup],
                corpus_path=corpus_path,
            ))
            if max_samples is not None and len(insts) >= max_samples:
                break

    if shuffle:
        random.shuffle(insts)
    logger.info("loaded %d instances from %s (corpus=%s)", len(insts), split_dir, corpus_path)
    return insts
