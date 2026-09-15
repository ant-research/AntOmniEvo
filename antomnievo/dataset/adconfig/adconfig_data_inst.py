from __future__ import annotations

import json
from typing import Any

from pydantic import Field

from antomnievo.interface.data_inst import DataInst


class AdConfigDataInst(DataInst):
    """Data instance for ad-config change eval (schema ``ad_config_change_eval_case/v1``).

    One case = a natural-language config-change request (with offline-replay
    baselines: a config base version + a source-code revision) whose gold is a
    structured ``expected.artifact.changes[0]`` (config_name / base_config_version /
    target_type / target_config).

    The full original case row is kept in ``raw`` (excluded from the RunRecord)
    so :meth:`to_case_dict` writes it back verbatim: the generate/evaluate
    subprocesses need the original full fields (``input.user_request`` +
    ``input.extra_context`` + ``expected.artifact.changes`` gold), not a flattened
    subset. Light stratification fields are exposed for the proposer/analysis.
    """

    # Light analysis/stratification fields (excluded from RunRecord). The heavy
    # gold (target_config) stays in `raw` only.
    category: str = Field(default="", description="Case category (创意/行业/粗排/…)", exclude=True)
    difficulty: str = Field(default="", description="简单/中等/困难", exclude=True)
    config_name: str = Field(default="", description="Gold config_name (main gold identifier)", exclude=True)
    tags: list[str] = Field(default_factory=list, description="Case tags", exclude=True)

    raw: dict[str, Any] = Field(default_factory=dict, exclude=True)

    def to_case_dict(self) -> dict[str, Any]:
        """Return the original case row verbatim.

        Written to the batch cases jsonl so generate.py (builds the prompt +
        run-context from the case) and evaluate.py (reads
        ``expected.artifact.changes`` gold) both see the full original fields.
        """
        return self.raw

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> AdConfigDataInst:
        case_id = str(raw.get("case_id") or raw.get("id") or "")
        inp = raw.get("input") or {}
        query = str(inp.get("user_request") or inp.get("query") or "")
        expected = raw.get("expected") or {}
        changes = (expected.get("artifact") or {}).get("changes") or []
        first = changes[0] if changes else {}
        golden_answer = json.dumps(expected, ensure_ascii=False, default=str)
        return cls(
            id=case_id,
            query=query,
            golden_answer=golden_answer,
            category=str(raw.get("category") or ""),
            difficulty=str(raw.get("difficulty") or ""),
            config_name=str(first.get("config_name") or ""),
            tags=list(raw.get("tags") or []),
            raw=raw,
        )
