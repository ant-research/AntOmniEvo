from __future__ import annotations

from pydantic import Field

from antomnievo.interface.data_inst import DataInst


class BirdTestDataInst(DataInst):
    """Data instance for BirdTest text2sql evaluation.

    Each instance corresponds to one row from a preprocessed contexts.jsonl,
    paired with a gold SQL from the corresponding gold SQL file.
    """

    db_id: str = Field(description="Database identifier", exclude=True)
    evidence: str = Field(default="", description="Domain knowledge / evidence hint", exclude=True)
    difficulty: str = Field(default="", description="Difficulty level: simple/moderate/challenging", exclude=True)
    schema_text: str = Field(default="", description="DDL schema text for the database", exclude=True)

    def to_context_dict(self) -> dict:
        """Convert to a dict matching the contexts.jsonl format."""
        return {
            "question_id": int(self.id),
            "db_id": self.db_id,
            "question": self.query,
            "evidence": self.evidence,
            "difficulty": self.difficulty,
            "schema": self.schema_text,
            "gold_sql": self.golden_answer,
        }
