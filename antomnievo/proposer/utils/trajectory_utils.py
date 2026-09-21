"""Generic trajectory utilities shared across coding agent implementations."""

import logging

from antomnievo.model.trajectory import Span, Trajectory

logger = logging.getLogger(__name__)

_ISSUE_PATTERNS: list[tuple[str, str]] = [
    ("requested permissions to", "Permission denied"),
    ("haven't granted it yet", "Permission not granted"),
    ("context window is full", "Context window full"),
    ("context length exceeded", "Context length exceeded"),
    ("input length exceeds maximum", "Input length exceeds maximum"),
    ("prompt is too long", "Prompt too long"),
    ("rate limit", "Rate limited"),
    ("server error", "Server error"),
]


def check_trajectory_issues(trajectory: Trajectory, phase: str = "") -> None:
    """Inspect a trajectory for operational issues and log warnings.

    Scans tool call results and model output text for patterns that indicate
    the agent encountered problems during execution, such as permission denials,
    context overflow, or other runtime errors. Issues are logged as warnings.
    """
    seen: set[str] = set()
    prefix = f"[{phase}] " if phase else ""

    def _scan_text(text: str, source: str) -> None:
        text_lower = text.lower()
        for pattern, label in _ISSUE_PATTERNS:
            if pattern.lower() in text_lower:
                issue = f"{prefix}{label} in {source}: {text[:200]}"
                if issue not in seen:
                    seen.add(issue)
                    logger.warning(issue)

    for span in trajectory.root_span_list:
        if span.output is not None:
            _scan_text(str(span.output), "model output")

        for child in span.children:
            if child.span_type != "tool_call":
                continue
            result_text = ""
            if isinstance(child.output, dict):
                result_text = str(child.output.get("result", ""))
            elif child.output is not None:
                result_text = str(child.output)

            if result_text:
                _scan_text(result_text, f"tool '{child.name}'")


def _model_span_is_empty(span: Span) -> bool:
    """An empty model span carries no text output and no children (thinking /
    tool calls) — the model returned a completely empty assistant message."""
    return not span.children and not (span.output and str(span.output).strip())


def find_degenerate_ending(trajectory: Trajectory, min_trailing_empty: int = 2) -> str | None:
    """Return a description if the session ended degenerately, else ``None``.

    A healthy agent session ends with a final assistant message carrying text
    (the model span's ``output``) or a tool call. Under gateway overload / rate
    limiting the model can instead return completely empty assistant messages
    (no text, no thinking, no tool calls); the agent CLI retries internally a
    few times and then exits with code 0, so nothing lands in
    ``trajectory.errors`` and the caller mistakes an aborted session for
    success. Observed pattern: 1-6 productive turns followed by 4-5 consecutive
    empty model spans.

    Degenerate shapes:
    - no model spans at all (the CLI produced nothing parseable);
    - >= ``min_trailing_empty`` consecutive empty model spans at the end
      (one trailing empty span is tolerated: a final content-free message
      right after the last tool call is harmless when the work is done);
    - zero tool calls AND zero text output across the whole session.
    """
    model_spans = [s for s in trajectory.root_span_list if s.span_type == "model"]
    if not model_spans:
        return "no model spans in trajectory"

    trailing_empty = 0
    for span in reversed(model_spans):
        if _model_span_is_empty(span):
            trailing_empty += 1
        else:
            break
    if trailing_empty >= min_trailing_empty:
        return f"{trailing_empty} consecutive empty model responses at session end"

    has_tool_call = any(
        child.span_type == "tool_call" for s in model_spans for child in s.children
    )
    has_text = any(s.output and str(s.output).strip() for s in model_spans)
    if not has_tool_call and not has_text:
        return f"no tool calls and no text output across {len(model_spans)} model response(s)"
    return None
