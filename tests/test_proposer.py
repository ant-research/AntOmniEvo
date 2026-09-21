"""Tests for ClaudeCodeProposer: prompt building, stream-json parsing,
mtime detection, CLI command construction, pre-flight checks, and permission configuration."""

import asyncio
import json
import logging
import os
import tempfile
import time
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from antomnievo.common.utils.fs_utils import get_latest_mtime
from antomnievo.common.utils.trajectory_parser import parse_stream_json
from antomnievo.interface.candidate_store import CandidateStore
from antomnievo.interface.evaluator import Evaluator
from antomnievo.model.trajectory import Span, Trajectory
from antomnievo.model.tunable_artifact_schema import FileSchema, FolderSchema, TunableArtifactSchema
from antomnievo.model.usage_stats import UsageStats
from antomnievo.proposer.claude_code_proposer import ClaudeCodeProposer
from antomnievo.proposer.utils.claude_code_utils import (
    ClaudeCodeConfig,
    invoke_claude_code,
)
from antomnievo.proposer.utils.trajectory_utils import check_trajectory_issues
from antomnievo.store.candidate_store import LocalCandidateStore


@pytest.fixture
def workspace():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield os.path.join(tmpdir, "workspace")


@pytest.fixture
def store(workspace):
    os.makedirs(workspace, exist_ok=True)
    return LocalCandidateStore(workspace)


@pytest.fixture
def tunable_artifact_schema() -> TunableArtifactSchema:
    return FolderSchema(
        name="artifact",
        description="Test tunable-artifact directory",
        files=[
            FileSchema(name="SKILL.md", description="Main instructions"),
        ],
    )


@pytest.fixture
def proposer(tunable_artifact_schema: TunableArtifactSchema, store: CandidateStore):
    evaluator = MagicMock(spec=Evaluator)
    evaluator.scoring_criteria.return_value = "test criteria"
    return ClaudeCodeProposer(
        tunable_artifact_schema=tunable_artifact_schema,
        candidate_store=store,
        evaluator=evaluator,
        claude_code_path="echo",
        model="test-model",
        api_key=None,
    )


class TestPromptBuilding:
    def test_build_analysis_prompt(self, proposer: ClaudeCodeProposer, store: CandidateStore):
        root = store.create_root()
        child = store.create_child(root.candidate_id)

        prompt = proposer._build_analysis_prompt(
            data_id="q1",
            run_file_paths=["/path/to/run1.json", "/path/to/run2.json"],
            candidate_id=root.candidate_id,
        )
        assert root.data_dir in prompt
        assert "/path/to/run1.json" in prompt
        assert "/path/to/run2.json" in prompt

    def test_build_propose_prompt(self, proposer: ClaudeCodeProposer, store: CandidateStore):
        root = store.create_root()
        child = store.create_child(root.candidate_id)

        prompt = proposer._build_propose_prompt(root, child)
        assert root.data_dir in prompt
        assert child.artifact_dir in prompt
        assert child.data_dir in prompt
        assert root.artifact_dir in prompt


class TestStreamJsonParsing:
    def test_parse_stream_json(self):
        raw = json.dumps({
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "text", "text": "Hello"},
                    {"type": "tool_use", "id": "tu_1", "name": "Read", "input": {"file_path": "/tmp/test.txt"}},
                ]
            }
        }) + "\n" + json.dumps({
            "type": "user",
            "message": {
                "content": [
                    {"type": "tool_result", "tool_use_id": "tu_1", "content": "file contents here"}
                ]
            }
        }) + "\n" + json.dumps({
            "type": "result",
            "result": "Done"
        })

        trajectory, stats = parse_stream_json(raw)
        assert len(trajectory.root_span_list) == 1
        model_span = trajectory.root_span_list[0]
        assert model_span.name == "model"
        assert model_span.input == "Hello"
        assert model_span.output == "Done"
        assert len(model_span.children) == 1
        tool_span = model_span.children[0]
        assert tool_span.name == "Read"
        assert tool_span.output == {"result": "file contents here"}

    def test_parse_stream_json_empty(self):
        trajectory, stats = parse_stream_json("")
        assert len(trajectory.root_span_list) == 0

    def test_parse_stream_json_malformed_line(self):
        raw = "not json\n" + json.dumps({"type": "result", "result": "ok"})
        trajectory, stats = parse_stream_json(raw)
        assert len(trajectory.root_span_list) == 0

    def test_parse_stream_json_multiple_assistant_messages(self):
        raw = (
            json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "Step 1"}]}}) + "\n"
            + json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "Step 2"}]}}) + "\n"
            + json.dumps({"type": "result", "result": "All done"})
        )
        trajectory, stats = parse_stream_json(raw)
        assert len(trajectory.root_span_list) == 2
        assert trajectory.root_span_list[0].input == "Step 1"
        assert trajectory.root_span_list[1].input == "Step 2"

    def test_parse_stream_json_tool_result_before_assistant(self):
        """Tool result arriving before the next assistant message should be cached."""
        raw = (
            json.dumps({"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": "tu_1", "name": "Read", "input": {"file_path": "/tmp/a"}},
            ]}}) + "\n"
            + json.dumps({"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "tu_1", "content": "file a"},
            ]}}) + "\n"
            + json.dumps({"type": "assistant", "message": {"content": [
                {"type": "text", "text": "Now I know"},
            ]}}) + "\n"
            + json.dumps({"type": "result", "result": "Done"})
        )
        trajectory, stats = parse_stream_json(raw)
        assert len(trajectory.root_span_list) == 2
        # First assistant has a tool call with result attached
        first_tool = trajectory.root_span_list[0].children[0]
        assert first_tool.name == "Read"
        assert first_tool.output == {"result": "file a"}

    def test_parse_stream_json_extracts_usage(self):
        """Usage stats should be extracted from the result event."""
        raw = (
            json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "Hi"}]}}) + "\n"
            + json.dumps({
                "type": "result",
                "result": "Done",
                "usage": {
                    "input_tokens": 5000,
                    "output_tokens": 2000,
                    "cache_creation_input_tokens": 1000,
                    "cache_read_input_tokens": 3000,
                },
            })
        )
        trajectory, stats = parse_stream_json(raw)
        assert stats.input_tokens == 5000
        assert stats.output_tokens == 2000
        assert stats.cache_creation_input_tokens == 1000
        assert stats.cache_read_input_tokens == 3000

    def test_parse_stream_json_no_usage_defaults_zero(self):
        """When result event has no usage, stats should default to zero."""
        raw = json.dumps({"type": "result", "result": "ok"})
        trajectory, stats = parse_stream_json(raw)
        assert stats.input_tokens == 0
        assert stats.output_tokens == 0


class TestMtimeDetection:
    def test_get_latest_mtime(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            f1 = os.path.join(tmpdir, "a.txt")
            f2 = os.path.join(tmpdir, "b.txt")
            with open(f1, "w") as f:
                f.write("a")
            time.sleep(0.05)
            with open(f2, "w") as f:
                f.write("b")

            mtime = get_latest_mtime(tmpdir)
            assert mtime > 0
            assert mtime >= os.path.getmtime(f2) - 1e-3

    def test_get_latest_mtime_empty_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            empty_dir = os.path.join(tmpdir, "empty")
            os.makedirs(empty_dir)
            mtime = get_latest_mtime(empty_dir)
            assert mtime == 0.0

    def test_get_latest_mtime_nested(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sub = os.path.join(tmpdir, "sub")
            os.makedirs(sub)
            with open(os.path.join(tmpdir, "a.txt"), "w") as f:
                f.write("a")
            time.sleep(0.05)
            with open(os.path.join(sub, "b.txt"), "w") as f:
                f.write("b")

            mtime = get_latest_mtime(tmpdir)
            assert mtime >= os.path.getmtime(os.path.join(sub, "b.txt")) - 1e-3


class TestPermissionConfiguration:
    """Verify that invoke_claude_code configures Claude Code CLI to avoid
    permission-related failures."""

    @staticmethod
    async def _invoke_with_mock(config: ClaudeCodeConfig):
        """Helper: invoke invoke_claude_code with a mock subprocess, return (cmd, env)."""
        captured_cmd = None
        captured_env = None

        async def mock_exec(*args, **kwargs):
            nonlocal captured_cmd, captured_env
            captured_cmd = list(args)
            captured_env = kwargs.get("env", {})
            proc = MagicMock()
            proc.communicate = AsyncMock(return_value=(b'{"type":"result","result":"ok"}', b""))
            proc.returncode = 0
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=mock_exec):
            await invoke_claude_code("test prompt", cwd="/tmp", config=config)

        return captured_cmd, captured_env

    def test_cli_command_includes_skip_permissions(self):
        """--dangerously-skip-permissions must be in the CLI command."""
        config = ClaudeCodeConfig(claude_code_path="claude", model="test-model")
        cmd, _ = asyncio.run(self._invoke_with_mock(config))
        assert "--dangerously-skip-permissions" in cmd

    def test_cli_command_does_not_use_allowed_tools(self):
        """--allowedTools should NOT be in the command since we use
        --dangerously-skip-permissions instead."""
        config = ClaudeCodeConfig(claude_code_path="claude", model="test-model")
        cmd, _ = asyncio.run(self._invoke_with_mock(config))
        assert "--allowedTools" not in cmd

    def test_env_sets_autocompact(self):
        """CLAUDE_AUTOCOMPACT_PCT_OVERRIDE must be set to trigger early compaction."""
        config = ClaudeCodeConfig(claude_code_path="claude", model="test-model", autocompact_pct=50)
        _, env = asyncio.run(self._invoke_with_mock(config))
        assert env.get("CLAUDE_AUTOCOMPACT_PCT_OVERRIDE") == "50"

    def test_env_sets_blocking_limit(self):
        """CLAUDE_CODE_AUTO_COMPACT_WINDOW must be set to prevent token overflow."""
        config = ClaudeCodeConfig(claude_code_path="claude", model="test-model", max_context_tokens=140000)
        _, env = asyncio.run(self._invoke_with_mock(config))
        assert env.get("CLAUDE_CODE_AUTO_COMPACT_WINDOW") == "140000"

    def test_env_sets_api_key(self):
        """ANTHROPIC_API_KEY must be forwarded to the subprocess."""
        config = ClaudeCodeConfig(claude_code_path="claude", model="test-model", api_key="test-key-123")
        _, env = asyncio.run(self._invoke_with_mock(config))
        assert env.get("ANTHROPIC_API_KEY") == "test-key-123"

    def test_no_env_vars_when_not_configured(self):
        """When max_context_tokens and autocompact_pct are None, their env vars
        should NOT be set."""
        config = ClaudeCodeConfig(claude_code_path="claude", model="test-model", api_key=None)
        _, env = asyncio.run(self._invoke_with_mock(config))
        assert "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE" not in env
        assert "CLAUDE_CODE_AUTO_COMPACT_WINDOW" not in env
        assert "ANTHROPIC_API_KEY" not in env

    def test_env_strips_claudecode(self):
        """CLAUDECODE must be stripped from subprocess env to prevent the
        nesting guard from blocking programmatic subprocess usage."""
        config = ClaudeCodeConfig(claude_code_path="claude", model="test-model")

        async def _invoke():
            captured_env = None

            async def mock_exec(*args, **kwargs):
                nonlocal captured_env
                captured_env = kwargs.get("env", {})
                proc = MagicMock()
                proc.communicate = AsyncMock(return_value=(b'{"type":"result","result":"ok"}', b""))
                proc.returncode = 0
                return proc

            with patch.dict(os.environ, {"CLAUDECODE": "1"}):
                with patch("asyncio.create_subprocess_exec", side_effect=mock_exec):
                    await invoke_claude_code("test prompt", cwd="/tmp", config=config)

            return captured_env

        env = asyncio.run(_invoke())
        assert "CLAUDECODE" not in env

    def test_env_sets_disable_nonessential_traffic(self):
        """CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC must be set to reduce
        telemetry, autoupdater, and other non-essential network traffic."""
        config = ClaudeCodeConfig(claude_code_path="claude", model="test-model")
        _, env = asyncio.run(self._invoke_with_mock(config))
        assert env.get("CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC") == "1"

    def test_cli_command_format(self):
        """Verify the full CLI command has the correct structure."""
        config = ClaudeCodeConfig(claude_code_path="claude", model="kimi-k2.5", max_turns=100)
        cmd, _ = asyncio.run(self._invoke_with_mock(config))
        assert cmd[0] == "claude"
        assert "--print" in cmd
        assert "--output-format" in cmd
        assert "stream-json" in cmd
        assert "--model" in cmd
        assert "kimi-k2.5" in cmd
        assert "--max-turns" in cmd
        assert "100" in cmd
        assert "-p" in cmd
        assert "test prompt" in cmd


class TestCheckTrajectoryIssues:
    """Verify that check_trajectory_issues detects operational problems
    in Claude Code output, such as permission denials and context overflow.

    The function logs warnings (returns None); we assert via ``caplog`` on the
    ``antomnievo.proposer.utils.trajectory_utils`` logger.
    """

    ISSUE_LOGGER = "antomnievo.proposer.utils.trajectory_utils"

    @staticmethod
    def _make_trajectory_with_tool_result(tool_name: str, result_text: str) -> Trajectory:
        """Helper: build a Trajectory with one model span containing one tool call."""
        tool_span = Span(
            name=tool_name,
            span_type="tool_call",
            input={"file_path": "/tmp/test.txt"},
            output={"result": result_text},
            start_time=datetime.now(),
            end_time=datetime.now(),
        )
        model_span = Span(
            name="model",
            span_type="model",
            input="Do something",
            start_time=datetime.now(),
            end_time=datetime.now(),
            children=[tool_span],
        )
        return Trajectory(root_span_list=[model_span])

    def _warnings(self, caplog) -> list[str]:
        return [r.message for r in caplog.records if r.name == self.ISSUE_LOGGER]

    def test_no_issues(self, proposer: ClaudeCodeProposer, caplog):
        """No issues when tool results are clean."""
        with caplog.at_level(logging.WARNING, logger=self.ISSUE_LOGGER):
            traj = self._make_trajectory_with_tool_result("Read", "file contents here")
            check_trajectory_issues(traj)
        assert self._warnings(caplog) == []

    def test_permission_denied_read(self, proposer: ClaudeCodeProposer, caplog):
        """Detect 'requested permissions to read' in tool result."""
        traj = self._make_trajectory_with_tool_result(
            "Read",
            "Claude requested permissions to read from /path/to/file, but you haven't granted it yet.",
        )
        with caplog.at_level(logging.WARNING, logger=self.ISSUE_LOGGER):
            check_trajectory_issues(traj)
        warnings = self._warnings(caplog)
        assert len(warnings) > 0
        assert any("Permission denied" in w or "Permission not granted" in w for w in warnings)

    def test_permission_denied_write(self, proposer: ClaudeCodeProposer, caplog):
        """Detect 'requested permissions to write' in tool result."""
        traj = self._make_trajectory_with_tool_result(
            "Write",
            "Claude requested permissions to write to /path/to/file, but you haven't granted it yet.",
        )
        with caplog.at_level(logging.WARNING, logger=self.ISSUE_LOGGER):
            check_trajectory_issues(traj)
        assert any("Permission" in w for w in self._warnings(caplog))

    def test_context_length_exceeded(self, proposer: ClaudeCodeProposer, caplog):
        """Detect context length exceeded in tool result."""
        traj = self._make_trajectory_with_tool_result(
            "model",
            "Error: context length exceeded the maximum allowed length",
        )
        with caplog.at_level(logging.WARNING, logger=self.ISSUE_LOGGER):
            check_trajectory_issues(traj)
        assert any("Context length exceeded" in w for w in self._warnings(caplog))

    def test_input_length_exceeds_maximum(self, proposer: ClaudeCodeProposer, caplog):
        """Detect input length exceeds maximum in tool result."""
        traj = self._make_trajectory_with_tool_result(
            "model",
            "API Error: 400 Bad Request - input length exceeds maximum allowed length",
        )
        with caplog.at_level(logging.WARNING, logger=self.ISSUE_LOGGER):
            check_trajectory_issues(traj)
        assert any("Input length exceeds maximum" in w for w in self._warnings(caplog))

    def test_multiple_issues_in_different_spans(self, proposer: ClaudeCodeProposer, caplog):
        """Detect multiple issues across different tool calls."""
        tool1 = Span(
            name="Read",
            span_type="tool_call",
            input={"file_path": "/tmp/a"},
            output={"result": "Claude requested permissions to read from /tmp/a, but you haven't granted it yet."},
            start_time=datetime.now(),
            end_time=datetime.now(),
        )
        tool2 = Span(
            name="Write",
            span_type="tool_call",
            input={"file_path": "/tmp/b"},
            output={"result": "Claude requested permissions to write to /tmp/b, but you haven't granted it yet."},
            start_time=datetime.now(),
            end_time=datetime.now(),
        )
        model_span = Span(
            name="model",
            span_type="model",
            input="Do things",
            start_time=datetime.now(),
            end_time=datetime.now(),
            children=[tool1, tool2],
        )
        traj = Trajectory(root_span_list=[model_span])
        with caplog.at_level(logging.WARNING, logger=self.ISSUE_LOGGER):
            check_trajectory_issues(traj)
        assert len(self._warnings(caplog)) >= 2

    def test_empty_trajectory(self, proposer: ClaudeCodeProposer, caplog):
        """No issues in an empty trajectory."""
        with caplog.at_level(logging.WARNING, logger=self.ISSUE_LOGGER):
            check_trajectory_issues(Trajectory(root_span_list=[]))
        assert self._warnings(caplog) == []

    def test_non_tool_spans_ignored(self, proposer: ClaudeCodeProposer, caplog):
        """Model span input should not be scanned for issues (only output is scanned)."""
        model_span = Span(
            name="model",
            span_type="model",
            input="Claude requested permissions to read from /tmp/a",
            start_time=datetime.now(),
            end_time=datetime.now(),
        )
        traj = Trajectory(root_span_list=[model_span])
        with caplog.at_level(logging.WARNING, logger=self.ISSUE_LOGGER):
            check_trajectory_issues(traj)
        assert self._warnings(caplog) == []

    def test_model_output_scanned_for_issues(self, proposer: ClaudeCodeProposer, caplog):
        """Model span output text should be scanned for API errors like 'Prompt is too long'."""
        model_span = Span(
            name="model",
            span_type="model",
            input="Analyze runs",
            output="Prompt is too long",
            start_time=datetime.now(),
            end_time=datetime.now(),
        )
        traj = Trajectory(root_span_list=[model_span])
        with caplog.at_level(logging.WARNING, logger=self.ISSUE_LOGGER):
            check_trajectory_issues(traj)
        assert any("Prompt too long" in w for w in self._warnings(caplog))

    def test_phase_prefix_in_issues(self, proposer: ClaudeCodeProposer, caplog):
        """Issues include the phase prefix when provided."""
        traj = self._make_trajectory_with_tool_result(
            "Read",
            "Claude requested permissions to read from /tmp/a, but you haven't granted it yet.",
        )
        with caplog.at_level(logging.WARNING, logger=self.ISSUE_LOGGER):
            check_trajectory_issues(traj, phase="Analysis")
        assert any("[Analysis]" in w for w in self._warnings(caplog))

    def test_duplicate_issues_deduplicated(self, proposer: ClaudeCodeProposer, caplog):
        """Same issue message appearing in multiple tool calls is deduplicated."""
        result = "Claude requested permissions to read from /tmp/a, but you haven't granted it yet."
        tool1 = Span(
            name="Read",
            span_type="tool_call",
            input={"file_path": "/tmp/a"},
            output={"result": result},
            start_time=datetime.now(),
            end_time=datetime.now(),
        )
        tool2 = Span(
            name="Read",
            span_type="tool_call",
            input={"file_path": "/tmp/b"},
            output={"result": result},
            start_time=datetime.now(),
            end_time=datetime.now(),
        )
        model_span = Span(
            name="model",
            span_type="model",
            input="Do things",
            start_time=datetime.now(),
            end_time=datetime.now(),
            children=[tool1, tool2],
        )
        traj = Trajectory(root_span_list=[model_span])
        with caplog.at_level(logging.WARNING, logger=self.ISSUE_LOGGER):
            check_trajectory_issues(traj)
        # The same message (label + text + source) appearing in two tool calls is
        # deduped to a single warning per distinct label, not one per span.
        warnings = self._warnings(caplog)
        assert len(warnings) == len(set(warnings))  # no exact-duplicate warnings
        assert any("Permission denied" in w for w in warnings)

    def test_result_text_truncated(self, proposer: ClaudeCodeProposer, caplog):
        """Long result text should be truncated in the issue description."""
        long_result = "Claude requested permissions to read from /tmp/a, but you haven't granted it yet. " + "x" * 500
        traj = self._make_trajectory_with_tool_result("Read", long_result)
        with caplog.at_level(logging.WARNING, logger=self.ISSUE_LOGGER):
            check_trajectory_issues(traj)
        warnings = self._warnings(caplog)
        assert len(warnings) > 0
        for warning in warnings:
            if "Permission denied" in warning:
                # message format: "<label> in <source>: <text[0:200]>"
                assert len(warning.split(": ", 1)[1]) <= 200

    def test_string_output_instead_of_dict(self, proposer: ClaudeCodeProposer, caplog):
        """Handle tool output that is a plain string instead of dict."""
        tool_span = Span(
            name="Read",
            span_type="tool_call",
            input={"file_path": "/tmp/a"},
            output="Claude requested permissions to read from /tmp/a, but you haven't granted it yet.",
            start_time=datetime.now(),
            end_time=datetime.now(),
        )
        model_span = Span(
            name="model",
            span_type="model",
            input="Read file",
            start_time=datetime.now(),
            end_time=datetime.now(),
            children=[tool_span],
        )
        traj = Trajectory(root_span_list=[model_span])
        with caplog.at_level(logging.WARNING, logger=self.ISSUE_LOGGER):
            check_trajectory_issues(traj)
        assert len(self._warnings(caplog)) > 0


class TestAnalysisResultVerification:
    """Phase 1 must not count a clean-exit session as success when the agent
    never (re)wrote its analysis result file — e.g. the model died on empty
    gateway responses mid-run. Otherwise Phase 2 builds on empty analysis and
    reliably ends with "no files modified"."""

    def _run_analyze(self, proposer, store, parent_meta, fake_invoke):
        proposer.invoke_agent = fake_invoke
        return asyncio.run(proposer._analyze_single_data_id(
            parent_meta=parent_meta,
            data_id="q1",
            run_names=["r1"],
            prompt_builder=lambda data_id, paths, candidate_id: "prompt",
            phase_label="Analysis",
        ))

    def test_missing_result_file_fails(self, proposer, store):
        root = store.create_root()
        parent_meta = store.get_meta(root.candidate_id)

        async def fake_invoke(prompt, cwd):
            return Trajectory(
                root_span_list=[Span(name="model", span_type="model", output="ok")]
            ), UsageStats()

        with pytest.raises(RuntimeError, match="analysis result file was not written"):
            self._run_analyze(proposer, store, parent_meta, fake_invoke)

    def test_written_result_file_passes(self, proposer, store):
        root = store.create_root()
        parent_meta = store.get_meta(root.candidate_id)
        result_path = store.analysis_result_path(root.candidate_id, "q1")

        async def fake_invoke(prompt, cwd):
            os.makedirs(os.path.dirname(result_path), exist_ok=True)
            with open(result_path, "w") as f:
                f.write("{}")
            return Trajectory(
                root_span_list=[Span(name="model", span_type="model", output="ok")]
            ), UsageStats()

        traj, _ = self._run_analyze(proposer, store, parent_meta, fake_invoke)
        assert traj.errors == []

    def test_stale_result_file_fails(self, proposer, store):
        """A result file left over from a previous analysis (older mtime) must
        not count as written by this run."""
        root = store.create_root()
        parent_meta = store.get_meta(root.candidate_id)
        result_path = store.analysis_result_path(root.candidate_id, "q1")
        os.makedirs(os.path.dirname(result_path), exist_ok=True)
        with open(result_path, "w") as f:
            f.write("{}")
        old = time.time() - 3600
        os.utime(result_path, (old, old))

        async def fake_invoke(prompt, cwd):
            return Trajectory(
                root_span_list=[Span(name="model", span_type="model", output="ok")]
            ), UsageStats()

        with pytest.raises(RuntimeError, match="analysis result file was not written"):
            self._run_analyze(proposer, store, parent_meta, fake_invoke)


class TestProposeGate:
    def test_mutate_fails_fast_without_analysis(self, proposer, store):
        """Phase 2 with zero usable analyses must fail fast instead of burning
        an agent run on a prompt whose Pre-loaded Data section is empty."""
        root = store.create_root()
        child = store.create_child(root.candidate_id)

        async def fake_invoke(prompt, cwd):  # must never be reached
            raise AssertionError("invoke_agent should not be called")

        proposer.invoke_agent = fake_invoke
        result = asyncio.run(proposer._mutate(root.candidate_id, child.candidate_id))
        assert not result.success
        assert "No analysis results" in result.error_message
