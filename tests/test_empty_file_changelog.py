"""Empty artifact additions/deletions still need mutation attribution."""

import json

import pytest

from antomnievo.proposer.scripts.append_changelog import append_changelog
from antomnievo.proposer.scripts.diff_dirs import compare_dirs
from antomnievo.proposer.scripts.validate_changelog import validate_changelog_file


@pytest.mark.parametrize("operation", ["add", "delete"])
@pytest.mark.parametrize("max_lines", [0, 1])
def test_empty_file_mutation_can_be_recorded(tmp_path, operation, max_lines):
    old = tmp_path / "old"
    new = tmp_path / "new"
    old.mkdir()
    new.mkdir()
    changed_dir = new if operation == "add" else old
    (changed_dir / "package").mkdir()
    (changed_dir / "package" / "__init__.py").touch()

    result = compare_dirs(str(old), str(new), max_lines=max_lines)
    assert result.files_modified == ["package/__init__.py"]
    assert "package/__init__.py" in result.diff_text
    if max_lines == 0:
        if operation == "add":
            assert "--- /dev/null\n+++ b/package/__init__.py" in result.diff_text
        else:
            assert "--- a/package/__init__.py\n+++ /dev/null" in result.diff_text

    changelog = tmp_path / "changelog.jsonl"
    append_changelog(
        str(old),
        str(new),
        str(changelog),
        entry_type="fix",
        subject=f"{operation} package marker",
        body=(
            "Analysis of data q1 found the wrong package discovery behavior. "
            "Change the empty package marker to correct how the agent imports "
            "the artifact modules, without changing their source text."
        ),
        max_diff_lines=max_lines,
    )
    assert validate_changelog_file(str(changelog)) == []
    entry = json.loads(changelog.read_text())
    assert entry["files_modified"] == ["package/__init__.py"]
    assert entry["diff"] == result.diff_text


def test_unchanged_empty_file_is_not_a_mutation(tmp_path):
    old = tmp_path / "old"
    new = tmp_path / "new"
    for directory in (old, new):
        directory.mkdir()
        (directory / "__init__.py").touch()

    result = compare_dirs(str(old), str(new))
    assert result.files_modified == []
    assert result.diff_text == ""


def test_empty_mutations_survive_diff_budget_exhaustion(tmp_path):
    old = tmp_path / "old"
    new = tmp_path / "new"
    for directory in (old, new):
        directory.mkdir()
    (old / "a.txt").write_text("before\n")
    (new / "a.txt").write_text("after\n")
    (new / "z_empty.py").touch()

    result = compare_dirs(str(old), str(new), max_lines=1)
    assert result.files_modified == ["a.txt", "z_empty.py"]
    assert "z_empty.py" in result.diff_text
    assert "truncated" in result.diff_text
