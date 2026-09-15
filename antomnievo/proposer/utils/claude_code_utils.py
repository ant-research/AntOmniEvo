"""Utilities for working with Claude Code: invocation and configuration.

Provides:
- ClaudeCodeConfig: configuration for invoking the Claude Code CLI
- invoke_claude_code: async subprocess invocation of Claude Code CLI
"""

import asyncio
import logging
import os
import sys
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class ClaudeCodeConfig:
    """Configuration for invoking Claude Code CLI."""

    claude_code_path: str = "claude"
    model: str = "kimi-k2.5"
    max_turns: int = 150
    timeout: int = 3600
    api_key: str | None = None
    base_url: str | None = None
    max_context_tokens: int | None = None
    autocompact_pct: int | None = None
    config_dir: str | None = None


async def invoke_claude_code(
    prompt: str,
    cwd: str,
    config: ClaudeCodeConfig,
) -> str:
    """Invoke Claude Code CLI as a subprocess and return raw stream-json output.

    Args:
        prompt: The prompt to send to Claude Code via -p flag.
        cwd: Working directory for the subprocess.
        config: Claude Code configuration (path, model, env vars, etc.).

    Returns:
        Raw stdout from Claude Code (stream-json NDJSON).

    Raises:
        RuntimeError: If Claude Code exits with a non-zero return code.
    """
    cmd = [
        config.claude_code_path,
        "--print",
        "--output-format", "stream-json",
        "--verbose",
        "--model", config.model,
        "--dangerously-skip-permissions",
        "--max-turns", str(config.max_turns),
        "-p", prompt,
    ]
    # Env var reference: https://code.claude.com/docs/en/env-vars
    env = os.environ.copy()
    # Ensure the venv bin directory (where entry-point scripts like
    # validate-analysis live) is on PATH for the Claude Code subprocess.
    venv_bin = os.path.dirname(sys.executable)
    if venv_bin not in env.get("PATH", "").split(os.pathsep):
        env["PATH"] = venv_bin + os.pathsep + env.get("PATH", "")
    # CLAUDECODE: set to 1 in shells spawned by Claude Code. Strip it to prevent
    # the nesting guard from blocking programmatic subprocess usage.
    env.pop("CLAUDECODE", None)
    # CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC: equivalent of setting
    # DISABLE_AUTOUPDATER, DISABLE_FEEDBACK_COMMAND, DISABLE_ERROR_REPORTING,
    # and DISABLE_TELEMETRY. Reduces non-essential network traffic.
    env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"
    # ANTHROPIC_API_KEY: API key sent as X-Api-Key header. When set, this key
    # is used instead of the Claude subscription.
    if config.api_key:
        env["ANTHROPIC_API_KEY"] = config.api_key
    if config.base_url:
        env["ANTHROPIC_BASE_URL"] = config.base_url
    # CLAUDE_CODE_AUTO_COMPACT_WINDOW: set the context capacity in tokens used
    # for auto-compaction calculations. Defaults to the model's context window.
    # When set, CLAUDE_AUTOCOMPACT_PCT_OVERRIDE is applied as a percentage of
    # this value instead of the model's actual context window.
    if config.max_context_tokens:
        env["CLAUDE_CODE_AUTO_COMPACT_WINDOW"] = str(config.max_context_tokens)
    # CLAUDE_AUTOCOMPACT_PCT_OVERRIDE: trigger auto-compaction at this % of
    # CLAUDE_CODE_AUTO_COMPACT_WINDOW. Default ~93.5%; lower values compact
    # earlier to avoid hitting the token limit.
    if config.autocompact_pct:
        env["CLAUDE_AUTOCOMPACT_PCT_OVERRIDE"] = str(config.autocompact_pct)
    if config.config_dir:
        env["CLAUDE_CONFIG_DIR"] = config.config_dir

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
        logger.error(f"Claude Code stdout: {stdout_msg}")
        logger.error(f"Claude Code stderr: {stderr_msg}")
        raise RuntimeError(
            f"Claude Code exited with code {process.returncode}: "
            f"stderr={stderr_msg}, stdout={stdout_msg}"
        )

    return stdout.decode()
