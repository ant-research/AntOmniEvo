"""Tests for agent subprocess lifecycle and mid-run failure detection.

Covers:
- communicate_with_timeout kills the agent AND its child processes on timeout
  (both backends route through it);
- Claude Code's ``is_error`` / ``error_*`` result events land in
  ``trajectory.errors``;
- the pi parser flags a session that ends on an error even if it produced
  output earlier, and tolerates errors it recovered from;
- Phase 2 rejects an aborted session that already edited files.
"""

import asyncio
import json
import os
import stat
import tempfile
import time
from unittest.mock import MagicMock

import pytest

from antomnievo.common.utils.subprocess_utils import (
    AgentTimeoutError,
    communicate_with_timeout,
)
from antomnievo.common.utils.trajectory_parser import _collect_agent_errors, parse_stream_json
from antomnievo.interface.evaluator import Evaluator
from antomnievo.model.trajectory import Span, Trajectory
from antomnievo.model.tunable_artifact_schema import FileSchema, FolderSchema
from antomnievo.model.usage_stats import UsageStats
from antomnievo.proposer.claude_code_proposer import ClaudeCodeProposer
from antomnievo.proposer.utils.claude_code_utils import ClaudeCodeConfig, invoke_claude_code
from antomnievo.proposer.utils.pi_coding_agent_utils import (
    PiCodingAgentConfig,
    invoke_pi_coding_agent,
    is_retryable_pi_exception,
)
from antomnievo.store.candidate_store import LocalCandidateStore

# A stand-in agent: spawns a child, records both pids, then hangs. Any CLI
# flags the backends pass are ignored.
_FAKE_AGENT = """#!/bin/sh
echo "$$" > "$AGENT_PIDFILE"
sleep 60 &
echo "$!" >> "$AGENT_PIDFILE"
wait
"""

_TIMEOUT_S = 1.0


@pytest.fixture
def fake_agent(tmp_path, monkeypatch):
    script = tmp_path / "fake_agent.sh"
    script.write_text(_FAKE_AGENT)
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    pidfile = tmp_path / "pids"
    monkeypatch.setenv("AGENT_PIDFILE", str(pidfile))
    return str(script), pidfile


def _is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    # Still exists; a zombie that is about to be reaped counts as dead.
    try:
        with open(f"/proc/{pid}/stat") as f:  # Linux
            return f.read().split(")")[-1].split()[0] != "Z"
    except OSError:
        return True


def _assert_all_dead(pidfile, timeout_s: float = 3.0) -> None:
    # Own pid first, then the child's; on a slow cold start the agent may have
    # been killed before it spawned the child, which is fine for this check.
    pids = [int(p) for p in pidfile.read_text().split()]
    assert pids, "fake agent never started"
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if not any(_is_alive(p) for p in pids):
            return
        time.sleep(0.05)
    alive = [p for p in pids if _is_alive(p)]
    for p in alive:  # don't leak processes out of the test run
        os.kill(p, 9)
    raise AssertionError(f"processes still alive after timeout kill: {alive}")


class TestTimeoutKillsProcessTree:
    def test_helper_kills_agent_and_children(self, fake_agent):
        script, pidfile = fake_agent

        async def run():
            proc = await asyncio.create_subprocess_exec(
                script, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            with pytest.raises(AgentTimeoutError):
                await communicate_with_timeout(proc, _TIMEOUT_S, "fake agent")
            assert proc.returncode is not None  # reaped, not left as a zombie

        asyncio.run(run())
        _assert_all_dead(pidfile)

    def test_helper_passes_output_through_when_in_time(self):
        async def run():
            proc = await asyncio.create_subprocess_exec(
                "sh", "-c", "echo out; echo err >&2",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            return await communicate_with_timeout(proc, 5, "fake agent")

        out, err = asyncio.run(run())
        assert out.strip() == b"out"
        assert err.strip() == b"err"

    def test_invoke_claude_code_timeout_kills_agent(self, fake_agent, tmp_path):
        script, pidfile = fake_agent
        config = ClaudeCodeConfig(claude_code_path=script, timeout=_TIMEOUT_S)
        with pytest.raises(AgentTimeoutError):
            asyncio.run(invoke_claude_code("prompt", str(tmp_path), config))
        _assert_all_dead(pidfile)

    def test_invoke_pi_timeout_kills_agent(self, fake_agent, tmp_path):
        script, pidfile = fake_agent
        config = PiCodingAgentConfig(pi_path=script, timeout=_TIMEOUT_S)
        with pytest.raises(AgentTimeoutError):
            asyncio.run(invoke_pi_coding_agent("prompt", str(tmp_path), config))
        _assert_all_dead(pidfile)

    def test_timeout_is_not_retried_by_pi_policy(self):
        """A hung session is not a transient gateway error — retrying it would
        multiply an already hour-long wait."""
        exc = AgentTimeoutError("Pi Coding Agent timed out after 3600s")
        assert isinstance(exc, asyncio.TimeoutError)
        assert not is_retryable_pi_exception(exc)


def _claude_events(result_event: dict) -> str:
    events = [
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "t1", "name": "Edit", "input": {"file_path": "SKILL.md"}},
        ]}},
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": "edited"},
        ]}},
        result_event,
    ]
    return "\n".join(json.dumps(e) for e in events)


class TestClaudeCodeResultErrors:
    def test_is_error_result_is_recorded(self):
        raw = _claude_events({
            "type": "result", "subtype": "error_max_turns", "is_error": True,
            "result": "", "usage": {"input_tokens": 1000, "output_tokens": 500},
        })
        trajectory, stats = parse_stream_json(raw)
        assert len(trajectory.errors) == 1
        assert "error_max_turns" in trajectory.errors[0]
        assert stats.output_tokens == 500  # usage is still parsed

    def test_error_subtype_without_flag_is_recorded(self):
        raw = _claude_events({
            "type": "result", "subtype": "error_during_execution",
            "result": "API Error: 401 unauthorized",
        })
        trajectory, _ = parse_stream_json(raw)
        assert trajectory.errors == [
            "Claude Code session ended with error_during_execution: API Error: 401 unauthorized"
        ]

    def test_successful_result_has_no_errors(self):
        raw = _claude_events({"type": "result", "subtype": "success", "is_error": False, "result": "Done"})
        trajectory, _ = parse_stream_json(raw)
        assert trajectory.errors == []


def _model_span(stop_reason: str | None = None, error: str | None = None, text: str = "ok") -> Span:
    meta = {}
    if stop_reason:
        meta["stop_reason"] = stop_reason
    if error:
        meta["error_message"] = error
    return Span(name="model", span_type="model", output=text, metadata=meta)


class TestPiSessionEndErrors:
    def test_session_ending_on_error_is_flagged_even_with_prior_output(self):
        trajectory = Trajectory(root_span_list=[
            _model_span(text="edited SKILL.md"),
            _model_span(stop_reason="error", error="429 rate limit", text=""),
        ])
        _collect_agent_errors(trajectory, UsageStats(output_tokens=800))
        assert trajectory.errors == ["agent session ended with an error: 429 rate limit"]

    def test_recovered_mid_session_error_is_tolerated(self):
        trajectory = Trajectory(root_span_list=[
            _model_span(stop_reason="error", error="502 bad gateway", text=""),
            _model_span(text="recovered and finished"),
        ])
        _collect_agent_errors(trajectory, UsageStats(output_tokens=300))
        assert trajectory.errors == []

    def test_zero_output_all_error_session_is_flagged(self):
        trajectory = Trajectory(root_span_list=[
            _model_span(stop_reason="error", error="401 unauthorized", text=""),
        ])
        _collect_agent_errors(trajectory, UsageStats(output_tokens=0))
        assert trajectory.errors == ["agent session ended with an error: 401 unauthorized"]


class TestMutationRejectsAbortedSession:
    def test_aborted_session_with_edits_fails_phase_2(self):
        """An aborted agent that already edited files must not become a candidate."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = LocalCandidateStore(os.path.join(tmpdir, "ws"))
            evaluator = MagicMock(spec=Evaluator)
            evaluator.scoring_criteria.return_value = "criteria"
            proposer = ClaudeCodeProposer(
                tunable_artifact_schema=FolderSchema(
                    name="artifact", description="d", files=[FileSchema(name="SKILL.md", description="d")],
                ),
                candidate_store=store, evaluator=evaluator, claude_code_path="echo", api_key=None,
            )
            root = store.create_root()
            with open(os.path.join(root.artifact_dir, "SKILL.md"), "w") as f:
                f.write("v1")
            child = store.create_child(root.candidate_id)

            async def aborted_agent(prompt, cwd):
                with open(os.path.join(cwd, "SKILL.md"), "w") as f:
                    f.write("half-finished edit")
                raw = _claude_events({"type": "result", "subtype": "error_max_turns", "is_error": True, "result": ""})
                return parse_stream_json(raw)

            proposer.invoke_agent = aborted_agent
            result = asyncio.run(proposer._run_mutation_pipeline(
                root.candidate_id, child.candidate_id, prompt="p", phase_label="Propose",
            ))
            assert not result.success
            assert "Agent session failed" in result.error_message
            assert "error_max_turns" in result.error_message
