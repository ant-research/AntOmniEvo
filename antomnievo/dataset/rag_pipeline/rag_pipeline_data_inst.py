from __future__ import annotations

from pydantic import Field

from antomnievo.interface.data_inst import DataInst


class RagPipelineDataInst(DataInst):
    """Data instance for retrieval-pipeline optimization on MuSiQue.

    The optimization target is the retrieval DAG tunable artifacts (``RAG_PIPELINE_TUNABLE_ARTIFACT_SCHEMA``):
    the system runs ``generate.py`` over a batch of queries and the evaluator
    scores nDCG@k / Recall@k of the retrieved docs against the doc ids of
    ``golden_docs`` (the supporting passages).

    Fields:
        id              : the MuSiQue item id — used as ``query_id`` by
                          generate.py / evaluate.py.
        query           : the MuSiQue question.
        golden_answer   : the MuSiQue answer (reference only; the retrieval
                          metric does not use it).
        golden_docs     : the supporting passages [{doc_id, title, text}]. The
                          doc_ids here ARE the gold set evaluated against; the
                          passage text lets the proposer reason about evidence.
    """

    golden_docs: list[dict] = Field(
        default_factory=list,
        description=(
            "The supporting passages themselves: [{doc_id, title, text}] for each "
            "is_supporting paragraph."
        ),
    )

    corpus_path: str = Field(
        default="",
        description=(
            "Path to THIS query's split corpus.jsonl (train query -> train corpus, "
            "val query -> val corpus). MuSiQue ships train/val as two separate "
            "corpora, so the corpus is split-specific. The system/evaluator read "
            "this to run generate.py / evaluate.py against the right retrieval pool."
        ),
    )
