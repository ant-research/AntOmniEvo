#!/usr/bin/env python3
"""Validate a changelog.jsonl file.

Usage:
    python -m antomnievo.proposer.scripts.validate_changelog <changelog.jsonl>
    python optimization/demo/v2/proposer/scripts/validate_changelog.py <changelog.jsonl>

Checks:
    1. changelog.jsonl is valid JSONL (each line is valid JSON)
    2. Each entry conforms to ChangeLogEntry schema
    3. type field is one of the allowed values
    4. subject length <= 72 characters
    5. body quality heuristics
    6. files_modified is a non-empty list of strings
    7. diff is a non-empty string
"""

import argparse
import json
import os
import sys

# Allow running as a script or as a module
if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", ".."))
    __package__ = "antomnievo.proposer.scripts"

from antomnievo.model.candidate_data import ChangeLogEntry

VALID_TYPES = {"feat", "fix", "refactor", "perf", "docs", "style", "chore"}


def validate_changelog_file(path: str) -> list[str]:
    """Validate a changelog.jsonl file. Returns list of error messages."""
    errors: list[str] = []

    if not os.path.exists(path):
        return [f"File not found: {path}"]

    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    if not lines:
        return []

    for line_num, line in enumerate(lines, start=1):
        line = line.strip()
        if not line:
            continue

        prefix = f"line {line_num}"

        # 1. Valid JSON
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as e:
            errors.append(f"{prefix}: invalid JSON: {e}")
            continue

        # 2. Must be a dict
        if not isinstance(entry, dict):
            errors.append(f"{prefix}: expected a JSON object, got {type(entry).__name__}")
            continue

        # 3. Schema validation via Pydantic
        try:
            ChangeLogEntry.model_validate(entry)
        except Exception as e:
            errors.append(f"{prefix}: schema validation failed: {e}")
            continue

        # 4. type is valid
        entry_type = entry.get("type", "")
        if entry_type not in VALID_TYPES:
            errors.append(f"{prefix}: type={entry_type!r} is not one of {VALID_TYPES}")

        # 5. subject length
        subject = entry.get("subject", "")
        if len(subject) > 72:
            errors.append(f"{prefix}: subject is {len(subject)} chars, max 72")

        # 6. body quality heuristics
        body = entry.get("body", "")
        if not body:
            errors.append(f"{prefix}: body is empty — must describe the failure pattern, change, and hypothesis")
        elif len(body) < 50:
            errors.append(f"{prefix}: body is too short ({len(body)} chars) — expected a detailed 3-part explanation")
        else:
            low = body.lower()
            vague = ["be more careful", "try harder", "improve accuracy", "do better"]
            for v in vague:
                if v in low and len(body) < len(v) + 30:
                    errors.append(f"{prefix}: body is too vague: contains '{v}' without specifics")
                    break

        # 7. files_modified is non-empty
        files_modified = entry.get("files_modified", [])
        if not files_modified:
            errors.append(f"{prefix}: files_modified is empty — must list which files were changed")
        elif not all(isinstance(f, str) and f for f in files_modified):
            errors.append(f"{prefix}: files_modified must be a list of non-empty strings")

        # 8. diff is non-empty
        diff = entry.get("diff", "")
        if not diff:
            errors.append(f"{prefix}: diff is empty — must include the unified diff of changes")

    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a changelog.jsonl file")
    parser.add_argument("file", help="Path to changelog.jsonl")
    args = parser.parse_args()

    errors = validate_changelog_file(args.file)
    if errors:
        for err in errors:
            print(f"  - {err}")
        print(f"\n{len(errors)} error(s) found.")
        sys.exit(1)
    else:
        line_count = 0
        try:
            with open(args.file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        line_count += 1
        except Exception:
            pass
        print(f"OK  {args.file} ({line_count} entries)")
        sys.exit(0)


if __name__ == "__main__":
    main()
