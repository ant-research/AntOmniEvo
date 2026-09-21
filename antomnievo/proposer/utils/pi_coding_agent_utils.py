"""Utilities for working with Pi Coding Agent: invocation and configuration.

Provides:
- PiCodingAgentConfig: configuration for invoking the Pi Coding Agent CLI
- invoke_pi_coding_agent: async subprocess invocation of the Pi Coding Agent CLI
- classify_pi_error / RETRYABLE / log_retry_sleep: transient-failure retry
  policy (429/rate-limit/5xx retried; 401/403 and unknown surfaced immediately)
"""

import asyncio
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from tenacity import retry_if_exception

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG_DIR = str(Path(__file__).resolve().parent.parent / "config" / "pi")
_DEFAULT_EXTENSION_DIR = str(Path(__file__).resolve().parent.parent / "config" / "pi" / "extensions")

# Allowed values for the Pi CLI --thinking flag. None means "do not pass --thinking"
# (the model uses its provider/CLI default).
PiThinkingLevel = Literal["off", "minimal", "low", "medium", "high", "xhigh"]
_VALID_THINKING_LEVELS: frozenset[str] = frozenset(
    ("off", "minimal", "low", "medium", "high", "xhigh")
)

# Provider identifiers passed to the Pi CLI ``--provider`` flag. They map to
# the keys of ``config/pi/models.json``'s ``providers`` object, which selects
# the gateway endpoint/adapter (anthropic-messages vs openai) used to reach the
# litellm backend.
PROVIDER_ANTHROPIC = "anthropic"
PROVIDER_OPENAI = "openai"
# ``Literal`` requires literal strings; the constants above are for code that
# references the values at runtime (defaults, comparisons), not the type form.
Provider = Literal["anthropic", "openai"]


@dataclass
class PiCodingAgentConfig:
    """Configuration for invoking the Pi Coding Agent CLI."""

    pi_path: str = "pi"
    model: str = "kimi-k2.5"
    provider: Provider = PROVIDER_ANTHROPIC
    max_turns: int = 150
    timeout: int = 3600
    api_key: str | None = None
    base_url: str | None = None
    thinking: PiThinkingLevel | None = None

    def __post_init__(self) -> None:
        if self.thinking is not None and self.thinking not in _VALID_THINKING_LEVELS:
            raise ValueError(
                f"Invalid thinking level: {self.thinking!r}. "
                f"Must be one of {sorted(_VALID_THINKING_LEVELS)} or None."
            )


# --- Transient-failure retry support for Pi Coding Agent invocations ---
#
# Pi Coding Agent and its gateway (antchat/litellm) fail transiently: 429
# rate-limit, 5xx, "overloaded", "too many requests". These clear on their own
# after a short wait, so invoking Pi again is worth it. Auth/permission
# failures (401/403) are NOT transient — retrying wastes time and never
# succeeds — so they must surface immediately. Unknown errors are also not
# retried, to avoid masking real bugs (agent/import failures) with retries.
#
# Pi itself does no internal 429 retry (verified in @mariozechner/pi-coding-agent),
# so without this layer a single rate-limit hit aborts the whole propose phase.

MAX_RETRY_ATTEMPTS: int = 5

# Substrings (matched case-insensitively) that mark a transient, retryable
# gateway error. Matched against the Pi subprocess stderr (which surfaces in
# the RuntimeError message from invoke_pi_coding_agent) and against
# Trajectory.errors entries parsed from a clean Pi exit.
_RETRYABLE_MARKERS: tuple[str, ...] = (
    "429", "rate limit", "rate_limit", "ratelimit", "too many requests",
    "retry-after", "retry_after", "overloaded", "service unavailable",
    "temporarily unavailable", "try again", "502", "503", "504",
    "bad gateway", "gateway timeout",
)
# Substrings that mark a non-transient auth/permission failure. Checked first:
# if any is present the error is 'fatal' regardless of concurrent retryable
# markers (e.g. a "401" output bundled with "rate limit" text still stays
# fatal — retrying won't fix the auth problem).
_FATAL_MARKERS: tuple[str, ...] = (
    "401", "403", "unauthorized", "forbidden", "invalid api key",
    "invalid_api_key", "not authorized", "authentication",
)


class PiEmptyResponseError(RuntimeError):
    """Pi's model returned repeated empty responses (transient gateway overload).

    Distinct from message-based classification: an empty assistant message
    carries no error text, so nothing matches ``_RETRYABLE_MARKERS`` and the
    failure would slip past ``classify_pi_error`` as 'unknown' — never retried,
    never surfaced in ``trajectory.errors`` (Pi exits 0). Detected by shape via
    ``find_degenerate_ending`` and raised as this type so it joins the same
    retry path as 429s.
    """


def classify_pi_error(text: str) -> str:
    """Classify a Pi/gateway error string as ``'retryable'``, ``'fatal'``, or ``'unknown'``.

    ``'retryable'`` — transient (429 / rate-limit / 5xx / overloaded): wait + retry.
    ``'fatal'``     — auth/permission (401/403): surface immediately, do not retry.
    ``'unknown'``   — neither: surface immediately (don't mask real bugs with retries).
    """
    if not text:
        return "unknown"
    low = text.lower()
    if any(m in low for m in _FATAL_MARKERS):
        return "fatal"
    if any(m in low for m in _RETRYABLE_MARKERS):
        return "retryable"
    return "unknown"


def is_retryable_pi_exception(exc: BaseException) -> bool:
    """True for transient RuntimeErrors (429 / rate-limit / 5xx) and for
    ``PiEmptyResponseError`` (repeated empty model responses — transient
    gateway overload by shape, no error text to classify). Auth (401/403)
    and unknown errors return False — not retried (retrying auth is pointless,
    retrying unknowns masks bugs)."""
    if isinstance(exc, PiEmptyResponseError):
        return True
    return isinstance(exc, RuntimeError) and classify_pi_error(str(exc)) == "retryable"


# Retry only on transient exceptions. Callers that surface a transient result
# (e.g. a clean Pi exit whose parsed trajectory carries a rate-limit error) should
# raise a RuntimeError so it joins this single retry path — see
# ``PiCodingAgentProposer._invoke_pi_once``. Matches the repo's kira_agent
# retry-on-exception idiom.
RETRYABLE = retry_if_exception(is_retryable_pi_exception)


def log_retry_sleep(retry_state) -> None:
    """tenacity ``before_sleep`` hook: log one line before each backoff sleep."""
    wait = retry_state.next_action.sleep if retry_state.next_action else 0.0
    outcome = retry_state.outcome
    exc = outcome.exception() if outcome is not None else None
    cause = str(exc)[:200] if exc is not None else "transient error"
    logger.warning(
        f"Pi transient error (attempt {retry_state.attempt_number}/"
        f"{MAX_RETRY_ATTEMPTS}), retrying in {wait:.1f}s: {cause}"
    )


async def invoke_pi_coding_agent(
    prompt: str,
    cwd: str,
    config: PiCodingAgentConfig,
) -> str:
    """Invoke Pi Coding Agent CLI as a subprocess and return raw JSON output.

    Args:
        prompt: The prompt to send to Pi via -p flag.
        cwd: Working directory for the subprocess.
        config: Pi Coding Agent configuration (path, model, env vars, etc.).

    Returns:
        Raw stdout from Pi (NDJSON in --mode json format).

    Raises:
        RuntimeError: If Pi exits with a non-zero return code.
    """
    cmd = [
        config.pi_path,
        "--print",
        "--mode", "json",
        "--provider", config.provider,
        "--model", config.model,
        "--no-extensions",
        "--no-skills",
        "--no-context-files",
        "--no-session",
        # Explicitly load extensions:
        # - Block proposer from accessing val set trajectories
        "-e", str(Path(_DEFAULT_EXTENSION_DIR) / "block-val-system-run.ts"),
        # - Enforce using append-changelog CLI instead of direct writes to changelog.jsonl
        "-e", str(Path(_DEFAULT_EXTENSION_DIR) / "enforce-changelog-cli.ts"),
        "-p", prompt,
    ]
    if config.thinking:
        cmd.extend(["--thinking", config.thinking])

    env = os.environ.copy()
    venv_bin = os.path.dirname(sys.executable)
    if venv_bin not in env.get("PATH", "").split(os.pathsep):
        env["PATH"] = venv_bin + os.pathsep + env.get("PATH", "")
    env.pop("CLAUDECODE", None)
    env.pop("PI_CODING_AGENT_NESTED", None)
    env["PI_OFFLINE"] = "1"
    env["PI_CODING_AGENT_DIR"] = _DEFAULT_CONFIG_DIR
    if config.api_key:
        cmd.extend(["--api-key", config.api_key])
    process = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    stdout, stderr = await asyncio.wait_for(
        process.communicate(), timeout=config.timeout
    )
    if process.returncode != 0:
        stderr_msg = stderr.decode() if stderr else "(no stderr output)"
        stdout_msg = stdout.decode() if stdout else "(no stdout output)"
        logger.error(f"Pi Coding Agent stdout: {stdout_msg}")
        logger.error(f"Pi Coding Agent stderr: {stderr_msg}")
        raise RuntimeError(
            f"Pi Coding Agent exited with code {process.returncode}: "
            f"stderr={stderr_msg}, stdout={stdout_msg}"
        )

    return stdout.decode()
