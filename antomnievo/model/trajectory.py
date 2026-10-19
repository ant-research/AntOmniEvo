"""Execution trajectories: the span tree that records one system run end to end.

## What a trajectory is

A ``Trajectory`` is a list of root ``Span``s forming a tree: each span is one
unit of work (a model turn, a tool call, a thinking block — see
``Span.span_type``), with ``input`` / ``output``, start & end times, and links
via ``parent_span_id`` / ``children``.
It records *how the system actually behaved*, as opposed to the final
``RolloutResult.content``, which is only what came out.

## Why it matters

The evaluator scores the output; a score says *how good*, never *why*. The
trajectory is what makes AntOmniEvo white-box instead of black-box: the
coding-agent Proposer reads failure trajectories (persisted in every
``RunRecord`` in the CandidateStore) to attribute a low score to a concrete
cause — the wrong tool call, the missed retrieval, the hallucinated argument —
and then edits the tunable artifacts responsible. Without trajectories the
optimizer can only hill-climb on scores; with them it can diagnose. Trajectory
fidelity directly bounds optimization quality: capture what you would want a
human debugger to see.

``Trajectory.errors`` flags runs that produced no usable output. Callers
persist the trajectory first (the error spans are inside), then act on the
error.

## How to collect one

- **Agent CLIs / frameworks that emit event streams** — don't hand-build;
  parse with ``antomnievo.common.utils.trajectory_parser``:
  ``parse_stream_json`` (Claude Code stream-json), ``parse_pi_json_output``
  (Pi NDJSON), ``parse_eddy_trajectory`` (eddy). Add a new parser there for a
  new format instead of bolting a bespoke builder onto each ``System``.
- **In-process systems** — build spans directly; see ``TrajectoryCollector``
  in ``antomnievo/system/langgraph/react_agent.py``: one model span per LLM
  turn, tool calls as child spans with ``tool_call_id`` in ``metadata`` so
  results can be paired back.

Minimum useful shape: a model span per LLM turn with input/output, tool calls
as children, and fatal failures appended to ``errors``.

## If optimization is not improving, check collection first

Before blaming the optimizer, verify the trajectories are collected correctly:
open a few ``RunRecord`` files in the CandidateStore and confirm that spans
are non-empty, tool calls are paired with their results, ``errors`` is empty
on healthy runs, and inputs/outputs show the real intermediate behavior — not
just the final answer. A mis-collected trajectory (empty, truncated, or
missing tool detail) silently degrades every downstream analysis: the Proposer
cannot fix what it cannot see.

## Protocol reference

This model is a deliberately simplified subset of the OpenTelemetry trace data
model — ``Span`` ≈ an OTel Span (``trace_id`` / ``parent_span_id`` / name /
start & end times / attributes → ``metadata``), a ``Trajectory`` ≈ a trace.
If your system already emits OTel spans, map them field by field. See
https://opentelemetry.io/docs/concepts/signals/traces/
"""

import json
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class Span(BaseModel):
    """One unit of work in a trajectory's span tree — see the module docstring."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique span id (uuid4).")
    parent_span_id: str | None = Field(
        default=None,
        description="Enclosing span's id when the producer recorded it; None on roots. Nesting is expressed by children — treat this as advisory.",
    )
    name: str = Field(
        description="What ran: 'model', a tool name ('Edit'), a pipeline node ('node:recall_dense'), ..."
    )
    span_type: str = Field(
        description="Coarse kind: 'model' (an LLM turn), 'tool_call' (a tool/node invocation), 'thinking', or 'span' (grouping/phase)."
    )
    input: Any | None = Field(
        default=None, description="What this unit received — model messages, tool args, node input hits."
    )
    output: Any | None = Field(
        default=None, description="What it produced — model text, tool result, node output hits."
    )
    start_time: datetime = Field(default_factory=datetime.now, description="When the work started (set at creation).")
    end_time: datetime | None = Field(default=None, description="When the work finished; None while still running.")
    children: list["Span"] = Field(
        default_factory=list, description="Nested sub-spans, e.g. tool calls under a model turn."
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Producer extras: tool_call_id (pairs tool calls with their results), stop_reason/error_message on failed LLM turns, ...",
    )

    def add_child(self, child: "Span") -> None:
        """Attach a nested span (a tool call under its model turn, a node under its query)."""
        self.children.append(child)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to the shared on-disk span shape.

        Uses the ``parent_id`` / ``type`` keys (not ``parent_span_id`` /
        ``span_type``) — this is the interchange format external producers
        write and ``_span_from_dict`` readers map back.
        """
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
    """One system run's complete span tree plus run-level metadata.

    What a trajectory is, why optimization quality is bounded by its fidelity,
    and how to collect one: see the module docstring.
    """

    root_span_list: list[Span] = Field(
        default_factory=list,
        description="Top-level spans; one root per logical run (a query, an agent session).",
    )
    session_id: str | None = Field(
        default=None, description="Producer session id, when it has one (e.g. an agent CLI session)."
    )
    trace_id: str | None = Field(
        default=None,
        description="Groups the spans of one logical trace; producers often default it to the data/query id.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="In-process extras; intentionally NOT serialized — the on-disk envelope is {trajectory, session_id, trace_id, errors}.",
    )
    # Caller protocol: persist the trajectory BEFORE acting on errors (the
    # error spans are inside). Stored as a real field, not metadata, so it
    # serializes with the trajectory and is readable on disk.
    errors: list[str] = Field(
        default_factory=list,
        description="Fatal run-level failures — LLM-call errors (401/5xx/rate limit), agent-session aborts (max turns), degenerate/empty sessions; non-empty means the run produced no usable output.",
    )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to the on-disk envelope {trajectory, session_id, trace_id, errors}."""
        return {
            "trajectory": [span.to_dict() for span in self.root_span_list],
            "session_id": self.session_id,
            "trace_id": self.trace_id,
            "errors": self.errors,
        }

    def to_json(self, indent: int | None = 2) -> str:
        """Pretty-printed ``to_dict()``; ``ensure_ascii=False`` so CJK survives."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


def merge_trajectories(trajectories: list[Trajectory]) -> Trajectory:
    """Merge multiple trajectories into one.

    Spans and errors are flattened in order; ``session_id`` / ``trace_id`` /
    ``metadata`` are not merged — the result carries none of them.
    """
    all_spans: list[Span] = []
    all_errors: list[str] = []
    for t in trajectories:
        all_spans.extend(t.root_span_list)
        all_errors.extend(t.errors)
    return Trajectory(root_span_list=all_spans, errors=all_errors)


