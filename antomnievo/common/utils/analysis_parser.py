"""Parse RunAnalysis JSON from Claude Code raw output and validate entries.

Extracts the RunAnalysis JSON that the model produces from the stream-json
output, using multiple extraction strategies for robustness.
"""

import json
import re

from antomnievo.model.candidate_data import RunAnalysis

_VAGUE_PHRASES = [
    "the answer was wrong",
    "the answer was correct",
    "the system made a mistake",
    "the system performed well",
    "the system performed poorly",
    "failed to answer correctly",
]


def parse_analysis_from_output(raw_output: str, expected_data_id: str) -> RunAnalysis:
    """Extract RunAnalysis JSON from Claude Code stream-json output.

    Scans the raw output for a JSON object containing the expected data_id.
    Tries multiple extraction strategies:
    1. Search for JSON in markdown code fences
    2. Find a JSON object containing "data_id" by brace tracking
    3. Direct JSON parse of the final result event text

    Raises ValueError if no valid JSON can be extracted.
    """
    # Extract text content from stream-json events
    texts = _extract_texts_from_stream_json(raw_output)
    # Process in reverse order — the final result is most likely to contain the JSON
    for text in reversed(texts):
        result = _try_extract_json(text, expected_data_id)
        if result:
            return result

    raise ValueError(
        f"Could not extract RunAnalysis JSON for data_id={expected_data_id} "
        f"from output ({len(raw_output)} chars)"
    )


def _extract_texts_from_stream_json(raw_output: str) -> list[str]:
    """Extract all text content from stream-json output lines.

    Collects text from:
    - assistant events (model text content blocks)
    - result events (final result text)
    """
    texts: list[str] = []
    for line in raw_output.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        event_type = event.get("type")

        if event_type == "assistant":
            message = event.get("message", {})
            for block in message.get("content", []):
                if block.get("type") == "text":
                    text = block.get("text", "")
                    if text:
                        texts.append(text)

        elif event_type == "result":
            result_text = event.get("result", "")
            if result_text:
                texts.append(result_text)

    return texts


def _try_extract_json(text: str, expected_data_id: str) -> RunAnalysis | None:
    """Try to extract a RunAnalysis from a text string using multiple strategies."""
    # Try 1: Direct parse
    try:
        data = json.loads(text.strip())
        if isinstance(data, dict) and data.get("data_id") == expected_data_id:
            return RunAnalysis.model_validate(data)
    except (json.JSONDecodeError, Exception):
        pass

    # Try 2: Extract from markdown code fence
    fence_match = re.search(r"```(?:json)?\s*\n(.*?)\n\s*```", text, re.DOTALL)
    if fence_match:
        try:
            data = json.loads(fence_match.group(1).strip())
            if isinstance(data, dict) and data.get("data_id") == expected_data_id:
                return RunAnalysis.model_validate(data)
        except (json.JSONDecodeError, Exception):
            pass

    # Try 3: Find a JSON object containing "data_id" by brace tracking
    start = text.find('{"data_id"')
    if start == -1:
        start = text.find('{\n  "data_id"')
    if start == -1:
        start = text.find('{"data_id"'.replace('"', '“'))
    if start >= 0:
        complete = _extract_complete_json(text, start)
        if complete:
            try:
                data = json.loads(complete)
                if isinstance(data, dict) and data.get("data_id") == expected_data_id:
                    return RunAnalysis.model_validate(data)
            except (json.JSONDecodeError, Exception):
                pass

    return None


def _extract_complete_json(text: str, start: int) -> str | None:
    """Extract a complete JSON object starting at position start by tracking braces."""
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        c = text[i]
        if escape:
            escape = False
            continue
        if c == "\\" and in_string:
            escape = True
            continue
        if c == '"' and not escape:
            in_string = not in_string
            continue
        if in_string:
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def validate_analysis_entry(analysis: RunAnalysis) -> list[str]:
    """Validate a RunAnalysis entry. Returns list of error messages (empty if valid)."""
    errors: list[str] = []
    prefix = f"data_id={analysis.data_id!r}"

    for i, item in enumerate(analysis.trajectory_analysis):
        if not item or not item.strip():
            errors.append(f"{prefix}: trajectory_analysis[{i}] is empty")
            continue
        low = item.lower()
        for vague in _VAGUE_PHRASES:
            if vague in low and len(item) < len(vague) + 20:
                errors.append(f"{prefix}: trajectory_analysis[{i}] is too vague: {item!r}")
                break

    for j, action in enumerate(analysis.actions):
        for action_field in ("file", "operation", "spec_issue", "change", "resolves"):
            value = getattr(action, action_field, "")
            if not value:
                errors.append(f"{prefix}: actions[{j}].{action_field} is empty")
                continue
            if not isinstance(value, str):
                continue
            low = value.lower()
            for vague in _VAGUE_PHRASES:
                if vague in low and len(value) < len(vague) + 20:
                    errors.append(f"{prefix}: actions[{j}].{action_field} is too vague: {value!r}")
                    break

    return errors
