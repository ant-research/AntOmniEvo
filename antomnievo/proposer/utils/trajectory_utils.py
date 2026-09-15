"""Generic trajectory utilities shared across coding agent implementations."""

import logging

from antomnievo.model.trajectory import Trajectory

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
