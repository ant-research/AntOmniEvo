#!/usr/bin/env python3
"""Append a changelog entry by computing diff and files_modified automatically.

Usage:
    # Recommended: use --body - with heredoc to avoid shell escaping issues
    append-changelog <old_dir> <new_dir> <changelog_jsonl> \\
        --type feat --subject 'add multi-hop decomposition' --body - << 'EOF'
    Run analysis showed failures...
    EOF

    # Alternative: --body with a short string (safe for simple text without special chars)
    append-changelog <old_dir> <new_dir> <changelog_jsonl> \\
        --type feat --subject 'add feature' --body 'simple description'

Computes the unified diff between old_dir and new_dir, determines which files
were modified, and appends a valid ChangeLogEntry to changelog_jsonl.
"""

import argparse
import os
import sys

if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", ".."))
    __package__ = "antomnievo.proposer.scripts"

from antomnievo.model.candidate_data import ChangeLogEntry
from antomnievo.proposer.scripts.diff_dirs import compare_dirs

VALID_TYPES = {"feat", "fix", "refactor", "perf", "docs", "style", "chore"}


_MAX_DIFF_LINES = 200


def append_changelog(
    old_dir: str,
    new_dir: str,
    changelog_path: str,
    entry_type: str,
    subject: str,
    body: str,
    author: str = "claude_code",
    max_diff_lines: int = _MAX_DIFF_LINES,
) -> None:
    diff_result = compare_dirs(old_dir, new_dir, max_lines=max_diff_lines)

    if not diff_result.files_modified:
        print("Error: no differences found between directories", file=sys.stderr)
        sys.exit(1)

    entry = ChangeLogEntry(
        type=entry_type,
        subject=subject,
        body=body,
        diff=diff_result.diff_text,
        files_modified=diff_result.files_modified,
        author=author,
    )

    os.makedirs(os.path.dirname(changelog_path) or ".", exist_ok=True)
    with open(changelog_path, "a", encoding="utf-8") as f:
        f.write(entry.model_dump_json() + "\n")

    print(f"Appended changelog entry: type={entry_type}, subject={subject}")
    print(f"  files_modified: {diff_result.files_modified}")
    print(f"  diff_lines: {diff_result.diff_text.count(chr(10)) + 1}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Append a changelog entry with auto-computed diff and files_modified"
    )
    parser.add_argument("old_dir", help="Original (parent) spec directory")
    parser.add_argument("new_dir", help="Modified (new) spec directory")
    parser.add_argument("changelog_jsonl", help="Path to changelog.jsonl file")
    parser.add_argument("--type", required=True, choices=sorted(VALID_TYPES),
                        help="Change type")
    parser.add_argument("--subject", required=True,
                        help="Short imperative summary (max 72 chars)")
    parser.add_argument("--body", help="Detailed explanation of the mutation. Use --body - to read from stdin (recommended for long text with special characters)")
    parser.add_argument("--author", default="claude_code",
                        help="Author identity (default=claude_code)")
    parser.add_argument("--max-diff-lines", type=int, default=_MAX_DIFF_LINES,
                        help=f"Max diff output lines (0=unlimited, default={_MAX_DIFF_LINES})")
    args = parser.parse_args()

    if not args.body:
        parser.error("--body is required")

    if args.body == "-":
        body = sys.stdin.read()
    else:
        body = args.body

    if len(args.subject) > 72:
        print(f"Error: subject is {len(args.subject)} chars, max 72", file=sys.stderr)
        sys.exit(1)

    if len(body) < 50:
        print(f"Error: body is too short ({len(body)} chars), expected at least 50",
              file=sys.stderr)
        sys.exit(1)

    append_changelog(
        old_dir=args.old_dir,
        new_dir=args.new_dir,
        changelog_path=args.changelog_jsonl,
        entry_type=args.type,
        subject=args.subject,
        body=body,
        author=args.author,
        max_diff_lines=args.max_diff_lines,
    )


if __name__ == "__main__":
    main()
