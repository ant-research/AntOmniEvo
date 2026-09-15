#!/usr/bin/env python3
"""Validate an analysis result JSON file.

Usage:
    python3 optimization/demo/v2/proposer/scripts/validate_analysis.py <file>

Checks:
    1. File is valid JSON
    2. JSON conforms to RunAnalysis schema (includes resolves index range)
    3. created_at / updated_at are valid ISO datetimes
    4. trajectory_analysis items and action fields are non-empty and non-vague
"""

import argparse
import json
import os
import sys

if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", ".."))
    __package__ = "antomnievo.proposer.scripts"

from antomnievo.model.candidate_data import RunAnalysis

_VAGUE_PHRASES = [
    "the answer was wrong",
    "the answer was correct",
    "the system made a mistake",
    "the system performed well",
    "the system performed poorly",
    "failed to answer correctly",
]

_REQUIRED_ACTION_FIELDS = ("file", "operation", "spec_issue", "change", "resolves")


def _is_vague(value: str) -> str | None:
    low = value.lower()
    for vague in _VAGUE_PHRASES:
        if vague in low and len(value) < len(vague) + 20:
            return vague
    return None


def validate_analysis_file(path: str) -> list[str]:
    """Validate a single analysis result JSON file. Returns list of error messages."""
    if not os.path.exists(path):
        return [f"File not found: {path}"]

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return [f"Invalid JSON: {e}"]

    if not isinstance(data, dict):
        return [f"Expected a JSON object, got {type(data).__name__}"]

    errors: list[str] = []
    prefix = f"data_id={data.get('data_id', '?')!r}"

    try:
        RunAnalysis.model_validate(data)
    except Exception as e:
        errors.append(f"{prefix}: schema validation failed: {e}")

    for field_name in ("created_at", "updated_at"):
        if data.get(field_name) is None:
            errors.append(f"{prefix}: {field_name} is missing or null")

    trajectory = data.get("trajectory_analysis", [])
    if isinstance(trajectory, list):
        for i, item in enumerate(trajectory):
            if not isinstance(item, str) or not item.strip():
                errors.append(f"{prefix}: trajectory_analysis[{i}] is empty")
                continue
            if (vague := _is_vague(item)) is not None:
                errors.append(f"{prefix}: trajectory_analysis[{i}] is too vague (matched {vague!r}): {item!r}")

    actions = data.get("actions", [])
    if isinstance(actions, list):
        traj_len = len(trajectory) if isinstance(trajectory, list) else 0
        for j, action in enumerate(actions):
            if not isinstance(action, dict):
                continue
            for action_field in _REQUIRED_ACTION_FIELDS:
                value = action.get(action_field)
                if not value and value != 0:
                    errors.append(f"{prefix}: actions[{j}].{action_field} is empty")
                    continue
                if isinstance(value, str) and (vague := _is_vague(value)) is not None:
                    errors.append(f"{prefix}: actions[{j}].{action_field} is too vague (matched {vague!r}): {value!r}")

            resolves = action.get("resolves", [])
            if isinstance(resolves, list) and traj_len > 0:
                for idx in resolves:
                    if isinstance(idx, int) and not (0 <= idx < traj_len):
                        errors.append(
                            f"{prefix}: actions[{j}].resolves contains {idx}, out of range [0, {traj_len - 1}]"
                        )

    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate an analysis result JSON file")
    parser.add_argument("file", help="Path to analysis result JSON file")
    args = parser.parse_args()

    errors = validate_analysis_file(args.file)
    if errors:
        for err in errors:
            print(f"  - {err}")
        print(f"\n{len(errors)} error(s) found.")
        sys.exit(1)
    else:
        print(f"OK  {args.file}")
        sys.exit(0)


if __name__ == "__main__":
    main()
