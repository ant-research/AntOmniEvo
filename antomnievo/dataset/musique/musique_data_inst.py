from __future__ import annotations

from pydantic import Field

from antomnievo.interface.data_inst import DataInst


class MusiqueDataInst(DataInst):
    """MuSiQue data instance with golden context paragraphs.

    Golden context is the concatenation of paragraphs whose is_supporting=True,
    i.e. the paragraphs referenced by question_decomposition[].paragraph_support_idx.
    """

    golden_context: str = Field(
        default="",
        description=(
            "Golden context paragraphs for the question (those with is_supporting=True), "
            "concatenated with '\\n\\n' separators. Used as reference for evaluation."
        ),
    )

    @classmethod
    def from_raw(cls, item: dict) -> MusiqueDataInst:
        """Build a MusiqueDataInst from a raw MuSiQue JSONL item.

        Extracts golden context by selecting paragraphs where is_supporting=True
        and joining their paragraph_text with double newlines.
        """
        supporting = [
            p["paragraph_text"]
            for p in item.get("paragraphs", [])
            if p.get("is_supporting")
        ]
        return cls(
            id=str(item["id"]),
            query=item["question"],
            golden_answer=item.get("answer", ""),
            golden_context="\n\n".join(supporting),
        )
