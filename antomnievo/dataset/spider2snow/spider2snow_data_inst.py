from __future__ import annotations

from typing import Any

from pydantic import Field

from antomnievo.interface.data_inst import DataInst


class Spider2SnowDataInst(DataInst):
    """Data instance for Spider2-Snow text2sql evaluation.

    Supports two modes:

    1. **Filesystem mode** (``spider2_root`` provided): lazily reads schema
       DDL and knowledge documents from the spider2-snow dataset directory.
    2. **Inline mode** (``schema_data`` / ``evidence`` provided): carries all
       context inline, e.g. when loaded from a pre-processed contexts.jsonl.

    Inline fields take precedence — if ``schema_data`` is non-empty it is
    used directly; otherwise the filesystem is consulted via ``spider2_root``.
    """

    db_id: str = Field(description="Snowflake database identifier")
    external_knowledge: str = Field(
        default="", description="External knowledge document filename", exclude=True
    )
    spider2_root: str = Field(default="", description="Root path of spider2-snow dataset", exclude=True)

    # ── Inline mode fields (populated when loading from contexts.jsonl) ──
    evidence: str = Field(default="", description="External knowledge text (inline)", exclude=True)
    evidence_ref: str = Field(default="", description="Evidence document reference", exclude=True)
    schema_data: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Schema as list of {table, description, ddl} dicts (inline)", exclude=True
    )

    # ── Filesystem-derived properties (used only in filesystem mode) ─────

    def to_context_dict(self) -> dict:
        """Serialize to contexts.jsonl format consumed by generate and evaluate.

        Includes gold_sql so that training pipelines can access it after
        deserialization.
        """
        # Use structured schema_data when available, otherwise fall back to text
        d: dict[str, Any] = {
            "question_id": self.id,
            "db_id": self.db_id,
            "question": self.query,
            "schema": self.schema_data,
        }
        if self.evidence:
            d["evidence"] = self.evidence
        if self.evidence_ref:
            d["evidence_ref"] = self.evidence_ref
        if self.golden_answer:
            d["gold_sql"] = self.golden_answer
        return d
