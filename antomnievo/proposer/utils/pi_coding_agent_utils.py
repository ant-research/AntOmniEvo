"""Utilities for working with Pi Coding Agent: invocation and configuration.

Provides:
- PiCodingAgentConfig: configuration for invoking the Pi Coding Agent CLI
- invoke_pi_coding_agent: async subprocess invocation of the Pi Coding Agent CLI

The transient-failure retry policy (classify_agent_error / RETRYABLE /
log_retry_sleep) lives in ``antomnievo.common.utils.errors``.
"""

import asyncio
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from antomnievo.common.utils.subprocess_utils import communicate_with_timeout

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
        AgentTimeoutError: If Pi exceeds ``config.timeout``; the process and
            its children are killed before raising. Not retried by
            ``RETRYABLE`` — a hung session is not a transient gateway error.
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
    stdout, stderr = await communicate_with_timeout(process, config.timeout, "Pi Coding Agent")
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
