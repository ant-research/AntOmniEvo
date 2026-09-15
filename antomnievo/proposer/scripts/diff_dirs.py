#!/usr/bin/env python3
"""Compute unified diff between two directories.

Usage: python diff_dirs.py <old_dir> <new_dir> [--max-lines N]
"""

import argparse
import difflib
import os
from dataclasses import dataclass, field

_DEFAULT_MAX_LINES = 1000


@dataclass
class DiffResult:
    """Result of comparing two directories."""
    diff_text: str
    files_modified: list[str] = field(default_factory=list)


def compare_dirs(old_dir: str, new_dir: str, max_lines: int = 0) -> DiffResult:
    """Compare two directories and return unified diff plus list of modified files.

    Args:
        old_dir: Original directory.
        new_dir: Modified directory.
        max_lines: Max diff output lines (0 = unlimited).

    Returns:
        DiffResult with diff_text and files_modified (relative paths).
    """
    all_rel_paths: set[str] = set()
    for d in (old_dir, new_dir):
        for root, _, files in os.walk(d):
            for fname in files:
                all_rel_paths.add(os.path.relpath(os.path.join(root, fname), d))

    parts: list[str] = []
    total_lines = 0
    skipped_files: list[str] = []
    files_modified: list[str] = []

    for rel_path in sorted(all_rel_paths):
        old_path = os.path.join(old_dir, rel_path)
        new_path = os.path.join(new_dir, rel_path)

        old_lines = []
        if os.path.exists(old_path):
            with open(old_path, "r", encoding="utf-8", errors="replace") as f:
                old_lines = f.readlines()

        new_lines = []
        if os.path.exists(new_path):
            with open(new_path, "r", encoding="utf-8", errors="replace") as f:
                new_lines = f.readlines()

        if old_lines == new_lines:
            continue

        files_modified.append(rel_path)

        diff = difflib.unified_diff(
            old_lines, new_lines,
            fromfile=f"a/{rel_path}", tofile=f"b/{rel_path}",
        )
        diff_text = "".join(diff)
        diff_lines = diff_text.count("\n") + (1 if diff_text and not diff_text.endswith("\n") else 0)

        if max_lines > 0 and total_lines + diff_lines > max_lines:
            remaining = max_lines - total_lines
            if remaining > 0:
                truncated = diff_text.split("\n")
                parts.append("\n".join(truncated[:remaining]))
                parts.append(f"... ({diff_lines - remaining} more lines truncated)")
            skipped_files.append(rel_path)
            total_lines = max_lines
            continue

        parts.append(diff_text)
        total_lines += diff_lines

    if skipped_files:
        parts.append(f"\n... {len(skipped_files)} file(s) truncated: {', '.join(skipped_files)}")

    return DiffResult(
        diff_text="\n".join(parts),
        files_modified=files_modified,
    )


def diff_dirs(old_dir: str, new_dir: str, max_lines: int = _DEFAULT_MAX_LINES) -> str:
    """Compare two directories and return unified diff as text (backward-compatible wrapper)."""
    return compare_dirs(old_dir, new_dir, max_lines=max_lines).diff_text


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute unified diff between two directories")
    parser.add_argument("old_dir", help="Original directory")
    parser.add_argument("new_dir", help="Modified directory")
    parser.add_argument("--max-lines", type=int, default=_DEFAULT_MAX_LINES,
                        help=f"Max diff output lines (0=unlimited, default={_DEFAULT_MAX_LINES})")
    args = parser.parse_args()
    result = diff_dirs(args.old_dir, args.new_dir, max_lines=args.max_lines)
    if result:
        print(result)
    else:
        print("No differences found.")


if __name__ == "__main__":
    main()
