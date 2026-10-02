"""Subprocess helpers shared by the coding-agent backends."""

import asyncio
import contextlib
import logging
import os
import signal
import subprocess

logger = logging.getLogger(__name__)

_REAP_GRACE_SECONDS = 5.0


class AgentTimeoutError(asyncio.TimeoutError):
    """An agent subprocess exceeded its timeout and was killed."""


def _descendant_pids(pid: int) -> list[int]:
    """Return every descendant pid of ``pid`` (children, grandchildren, ...).

    Uses ``ps`` so no extra dependency is needed; returns an empty list when
    ``ps`` is unavailable, in which case only the direct child is killed.
    """
    try:
        out = subprocess.run(
            ["ps", "-eo", "pid=,ppid="], capture_output=True, text=True, check=False,
        ).stdout
    except OSError:
        return []
    children: dict[int, list[int]] = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) != 2 or not all(p.isdigit() for p in parts):
            continue
        children.setdefault(int(parts[1]), []).append(int(parts[0]))
    found: list[int] = []
    stack = [pid]
    while stack:
        for child in children.get(stack.pop(), []):
            found.append(child)
            stack.append(child)
    return found


def kill_process_tree(process: asyncio.subprocess.Process) -> None:
    """SIGKILL ``process`` and every process it spawned.

    Coding agents run tools in their own child processes (shells, node, python);
    killing only the agent would leave those running. The agent stays in our
    process group on purpose, so Ctrl+C in the terminal still reaches it.
    """
    if process.returncode is not None:
        return
    for pid in _descendant_pids(process.pid):
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.kill(pid, signal.SIGKILL)
    with contextlib.suppress(ProcessLookupError):
        process.kill()


async def communicate_with_timeout(
    process: asyncio.subprocess.Process, timeout: float, label: str,
) -> tuple[bytes, bytes]:
    """``process.communicate()`` bounded by ``timeout``; kills the process tree on expiry.

    ``asyncio.wait_for`` alone only cancels the *await* — the subprocess keeps
    running (and, for a coding agent, keeps consuming tokens and editing files
    after the caller has already given up on it).

    Raises:
        AgentTimeoutError: the process did not finish within ``timeout`` seconds.
    """
    try:
        return await asyncio.wait_for(process.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        logger.error(f"{label} exceeded its {timeout}s timeout; killing pid {process.pid} and its children")
        kill_process_tree(process)
        try:
            await asyncio.wait_for(process.wait(), timeout=_REAP_GRACE_SECONDS)
        except asyncio.TimeoutError:
            logger.warning(f"{label} pid {process.pid} did not exit within {_REAP_GRACE_SECONDS}s of SIGKILL")
        raise AgentTimeoutError(
            f"{label} timed out after {timeout}s; pid {process.pid} and its children were killed"
        ) from None
