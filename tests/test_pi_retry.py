"""Tests for Pi Coding Agent invocation retry on transient gateway errors.

Covers the pure decision helpers (``classify_pi_error``, ``retry_backoff_seconds``)
and the retry loop inside ``PiCodingAgentProposer.invoke_agent``. The loop is
exercised in isolation via ``__new__`` + the two attributes the method reads
(``self._sem``, ``self._config``), with ``invoke_pi_coding_agent`` and
``parse_pi_json_output`` stubbed — no TunableArtifactSchema/CandidateStore/Evaluator needed.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import antomnievo.proposer.pi_coding_agent_proposer as mod
from antomnievo.model.trajectory import Trajectory
from antomnievo.model.usage_stats import UsageStats
from antomnievo.proposer.utils.pi_coding_agent_utils import (
    MAX_RETRY_ATTEMPTS,
    classify_pi_error,
)


def _make_proposer():
    """A proposer with only the attrs ``invoke_agent`` touches — bypasses the
    heavy BaseProposer construction (TunableArtifactSchema/store/evaluator)."""
    p = mod.PiCodingAgentProposer.__new__(mod.PiCodingAgentProposer)
    p._sem = asyncio.Semaphore(2)
    p._config = MagicMock()
    return p


# ---- pure helpers ----

@pytest.mark.parametrize(
    "text,want",
    [
        ("HTTP 429 Too Many Requests", "retryable"),
        ("rate limit exceeded for kimi-k2.5", "retryable"),
        ("Error: 503 Service Unavailable", "retryable"),
        ("overloaded. Please retry.", "retryable"),
        ("gateway timeout from upstream", "retryable"),
        ("antchat 401 服务未授权", "fatal"),
        ("403 Forbidden: invalid api key", "fatal"),
        ("NameError: name '_x' is not defined", "unknown"),
        ("", "unknown"),
        # fatal wins over a concurrent retryable marker
        ("429 rate limit but really 401 unauthorized", "fatal"),
    ],
)
def test_classify_pi_error(text, want):
    assert classify_pi_error(text) == want


# ---- loop behavior (tenacity-decorated _invoke_pi_once) ----

def _patch_sleep():
    """Replace asyncio.sleep with a no-await AsyncMock so tests don't really wait."""
    return patch.object(asyncio, "sleep", new=AsyncMock())


def test_retries_transient_runtime_error_then_succeeds():
    p = _make_proposer()
    calls = {"n": 0}

    async def fake_invoke(prompt, cwd, config):
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("HTTP 429 Too Many Requests")
        return "raw-ok"

    def fake_parse(raw):
        return Trajectory(root_span_list=[], errors=[]), UsageStats()

    with patch.object(mod, "invoke_pi_coding_agent", fake_invoke), \
         patch.object(mod, "parse_pi_json_output", fake_parse), \
         _patch_sleep() as sleep_mock:
        traj, stats = asyncio.run(p.invoke_agent("p", "/tmp"))

    assert calls["n"] == 3          # 2 failed + 1 success
    assert sleep_mock.await_count == 2
    assert traj.errors == []


def test_no_retry_on_fatal_auth_error():
    p = _make_proposer()

    async def fake_invoke(prompt, cwd, config):
        raise RuntimeError("antchat 401 unauthorized")

    with patch.object(mod, "invoke_pi_coding_agent", fake_invoke), \
         _patch_sleep() as sleep_mock:
        with pytest.raises(RuntimeError):
            asyncio.run(p.invoke_agent("p", "/tmp"))

    assert sleep_mock.await_count == 0   # 401 is fatal — surface immediately


def test_unknown_error_not_retried():
    p = _make_proposer()

    async def fake_invoke(prompt, cwd, config):
        raise RuntimeError("ModuleNotFoundError: no module named 'foo'")

    with patch.object(mod, "invoke_pi_coding_agent", fake_invoke), \
         _patch_sleep() as sleep_mock:
        with pytest.raises(RuntimeError):
            asyncio.run(p.invoke_agent("p", "/tmp"))

    assert sleep_mock.await_count == 0


def test_retries_trajectory_rate_limit_then_succeeds():
    p = _make_proposer()
    state = {"n": 0}

    async def fake_invoke(prompt, cwd, config):
        state["n"] += 1
        return "raw"

    def fake_parse(raw):
        if state["n"] < 2:
            return Trajectory(root_span_list=[], errors=["429 rate limit exceeded"]), UsageStats()
        return Trajectory(root_span_list=[], errors=[]), UsageStats()

    with patch.object(mod, "invoke_pi_coding_agent", fake_invoke), \
         patch.object(mod, "parse_pi_json_output", fake_parse), \
         _patch_sleep() as sleep_mock:
        traj, stats = asyncio.run(p.invoke_agent("p", "/tmp"))

    assert state["n"] == 2
    assert sleep_mock.await_count == 1
    assert traj.errors == []


def test_no_retry_when_trajectory_error_is_fatal():
    p = _make_proposer()
    state = {"n": 0}

    async def fake_invoke(prompt, cwd, config):
        state["n"] += 1
        return "raw"

    def fake_parse(raw):
        return Trajectory(root_span_list=[], errors=["401 unauthorized"]), UsageStats()

    with patch.object(mod, "invoke_pi_coding_agent", fake_invoke), \
         patch.object(mod, "parse_pi_json_output", fake_parse), \
         _patch_sleep() as sleep_mock:
        traj, stats = asyncio.run(p.invoke_agent("p", "/tmp"))

    assert state["n"] == 1
    assert sleep_mock.await_count == 0
    assert "401" in traj.errors[0]


def test_exhausts_retries_on_runtime_error_then_reraises():
    p = _make_proposer()

    async def fake_invoke(prompt, cwd, config):
        raise RuntimeError("429 Too Many Requests")

    with patch.object(mod, "invoke_pi_coding_agent", fake_invoke), \
         _patch_sleep() as sleep_mock:
        with pytest.raises(RuntimeError):
            asyncio.run(p.invoke_agent("p", "/tmp"))

    # 5 attempts → sleeps after attempts 1..4
    assert sleep_mock.await_count == MAX_RETRY_ATTEMPTS - 1


def test_exhausts_trajectory_rate_limit_reraises():
    """When retries are exhausted on the trajectory-error path the original
    RuntimeError is re-raised (``reraise=True``) — the phase is marked failed
    via the exception path, same as exhausting on a non-zero Pi exit."""
    p = _make_proposer()

    async def fake_invoke(prompt, cwd, config):
        return "raw"

    def fake_parse(raw):
        return Trajectory(root_span_list=[], errors=["429 rate limit"]), UsageStats()

    with patch.object(mod, "invoke_pi_coding_agent", fake_invoke), \
         patch.object(mod, "parse_pi_json_output", fake_parse), \
         _patch_sleep() as sleep_mock:
        with pytest.raises(RuntimeError):
            asyncio.run(p.invoke_agent("p", "/tmp"))

    assert sleep_mock.await_count == MAX_RETRY_ATTEMPTS - 1
