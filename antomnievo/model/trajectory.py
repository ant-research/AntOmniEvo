import json
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class Span(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    parent_span_id: str | None = None
    name: str
    span_type: str
    input: Any | None = None
    output: Any | None = None
    start_time: datetime = Field(default_factory=datetime.now)
    end_time: datetime | None = None
    children: list["Span"] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def add_child(self, child: "Span") -> None:
        self.children.append(child)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "parent_id": self.parent_span_id,
            "name": self.name,
            "type": self.span_type,
            "input": self.input,
            "output": self.output,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "children": [child.to_dict() for child in self.children],
        }


class Trajectory(BaseModel):
    root_span_list: list[Span] = Field(default_factory=list)
    session_id: str | None = None
    trace_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    # Fatal LLM-call errors (e.g. antchat 401, 5xx, rate limit). Parsers
    # populate this when the run produced no usable output. Non-empty means the
    # agent never ran successfully; callers should still persist the trajectory
    # (the error spans are inside) before acting on it. Stored as a real field
    # so it serializes with the trajectory and is readable on disk.
    errors: list[str] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trajectory": [span.to_dict() for span in self.root_span_list],
            "session_id": self.session_id,
            "trace_id": self.trace_id,
            "errors": self.errors,
        }

    def to_json(self, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


def merge_trajectories(trajectories: list[Trajectory]) -> Trajectory:
    """Merge multiple trajectories into one."""
    all_spans: list[Span] = []
    all_errors: list[str] = []
    for t in trajectories:
        all_spans.extend(t.root_span_list)
        all_errors.extend(t.errors)
    return Trajectory(root_span_list=all_spans, errors=all_errors)


