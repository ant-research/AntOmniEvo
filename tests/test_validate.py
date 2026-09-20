"""Tests for validate_analysis and validate_changelog scripts."""

import json
import os
import tempfile

from antomnievo.proposer.scripts.validate_analysis import validate_analysis_file
from antomnievo.proposer.scripts.validate_changelog import validate_changelog_file


class TestValidateAnalysis:
    def test_valid_analysis(self):
        data = {
            "data_id": "q1",
            "trajectory_analysis": [
                "Agent failed to retrieve the correct document, causing the wrong answer"
            ],
            "actions": [
                {
                    "file": "SKILL.md",
                    "operation": "add",
                    "artifact_issue": "No decomposition rule for multi-hop questions",
                    "change": "Add a step-by-step decomposition rule in the Procedure section",
                    "resolves": [0],
                }
            ],
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00",
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "analysis.json")
            with open(path, "w") as f:
                json.dump(data, f)

            errors = validate_analysis_file(path)
            assert errors == []

    def test_missing_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            errors = validate_analysis_file(os.path.join(tmpdir, "nonexistent.json"))
            assert len(errors) > 0
            assert "not found" in errors[0].lower() or "File not found" in errors[0]

    def test_invalid_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "analysis.json")
            with open(path, "w") as f:
                f.write("{invalid json")

            errors = validate_analysis_file(path)
            assert len(errors) > 0

    def test_vague_issue_analysis(self):
        data = {
            "data_id": "q1",
            "trajectory_analysis": ["the answer was wrong"],
            "actions": [],
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00",
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "analysis.json")
            with open(path, "w") as f:
                json.dump(data, f)

            errors = validate_analysis_file(path)
            assert any("vague" in e.lower() for e in errors)

    def test_empty_trajectory_and_actions(self):
        """An analysis with no trajectory observations and no actions is valid."""
        data = {
            "data_id": "q1",
            "trajectory_analysis": [],
            "actions": [],
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00",
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "analysis.json")
            with open(path, "w") as f:
                json.dump(data, f)

            errors = validate_analysis_file(path)
            assert errors == []

    def test_empty_analysis(self):
        """Empty JSON object should report missing required fields like data_id."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "analysis.json")
            with open(path, "w") as f:
                f.write("{}")

            errors = validate_analysis_file(path)
            # data_id is required by RunAnalysis schema
            assert any("data_id" in e for e in errors)

    def test_empty_action_fields(self):
        data = {
            "data_id": "q1",
            "trajectory_analysis": ["Agent failed to decompose the multi-hop question"],
            "actions": [
                {
                    "file": "",
                    "operation": "add",
                    "artifact_issue": "Missing decomposition strategy",
                    "change": "Add decomposition rule",
                    "resolves": [0],
                }
            ],
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00",
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "analysis.json")
            with open(path, "w") as f:
                json.dump(data, f)

            errors = validate_analysis_file(path)
            assert any("actions[0].file" in e for e in errors)


class TestValidateChangelog:
    def _make_entry(self, **overrides):
        entry = {
            "type": "feat",
            "subject": "add multi-hop decomposition strategy",
            "body": (
                "Data q1 (score 0.0) failed to decompose multi-hop questions. "
                "Added step-by-step decomposition rule in SKILL.md. "
                "Hypothesis: explicit decomposition will improve chained question scores."
            ),
            "diff": "--- a/SKILL.md\n+++ b/SKILL.md\n@@ +1 @@\n+New rule",
            "files_modified": ["SKILL.md"],
        }
        entry.update(overrides)
        return entry

    def test_valid_changelog(self):
        entry = self._make_entry()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "changelog.jsonl")
            with open(path, "w") as f:
                f.write(json.dumps(entry) + "\n")

            errors = validate_changelog_file(path)
            assert errors == []

    def test_invalid_type(self):
        entry = self._make_entry(type="breaking")
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "changelog.jsonl")
            with open(path, "w") as f:
                f.write(json.dumps(entry) + "\n")

            errors = validate_changelog_file(path)
            assert any("type" in e.lower() for e in errors)

    def test_subject_too_long(self):
        entry = self._make_entry(subject="x" * 100)
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "changelog.jsonl")
            with open(path, "w") as f:
                f.write(json.dumps(entry) + "\n")

            errors = validate_changelog_file(path)
            assert any("subject" in e.lower() and "72" in e for e in errors)

    def test_empty_body(self):
        entry = self._make_entry(body="")
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "changelog.jsonl")
            with open(path, "w") as f:
                f.write(json.dumps(entry) + "\n")

            errors = validate_changelog_file(path)
            assert any("body" in e.lower() for e in errors)

    def test_body_too_short(self):
        entry = self._make_entry(body="try harder with this change")
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "changelog.jsonl")
            with open(path, "w") as f:
                f.write(json.dumps(entry) + "\n")

            errors = validate_changelog_file(path)
            assert any("body" in e.lower() for e in errors)

    def test_empty_diff(self):
        entry = self._make_entry(diff="")
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "changelog.jsonl")
            with open(path, "w") as f:
                f.write(json.dumps(entry) + "\n")

            errors = validate_changelog_file(path)
            assert any("diff" in e.lower() for e in errors)

    def test_empty_files_modified(self):
        entry = self._make_entry(files_modified=[])
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "changelog.jsonl")
            with open(path, "w") as f:
                f.write(json.dumps(entry) + "\n")

            errors = validate_changelog_file(path)
            assert any("files_modified" in e.lower() for e in errors)

    def test_multiple_entries(self):
        e1 = self._make_entry(subject="first change")
        e2 = self._make_entry(type="fix", subject="fix retrieval bug")
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "changelog.jsonl")
            with open(path, "w") as f:
                f.write(json.dumps(e1) + "\n" + json.dumps(e2) + "\n")

            errors = validate_changelog_file(path)
            assert errors == []

    def test_missing_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            errors = validate_changelog_file(os.path.join(tmpdir, "nonexistent.jsonl"))
            assert len(errors) > 0

    def test_invalid_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "changelog.jsonl")
            with open(path, "w") as f:
                f.write("not json\n")

            errors = validate_changelog_file(path)
            assert len(errors) > 0