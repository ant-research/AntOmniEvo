# Tests

```bash
pytest tests/
```

Most tests are fast and hermetic. One test exercises the real process killer by
spawning actual subprocesses; it carries the `slow` marker:

```bash
pytest tests/ -m "not slow"   # skip the real-process test
pytest tests/ -m slow         # only the real-process test
pytest tests/                 # everything
```

The marker is registered in `pyproject.toml` under `[tool.pytest.ini_options]`.
Mark any new test that spawns real processes `@pytest.mark.slow`.

## Process-lifecycle tests

`TestTimeoutKillsProcessTree` (in `test_agent_lifecycle.py`) is split so that
only the part which genuinely needs real processes pays for them:

- **`test_kill_process_tree_kills_children`** — real processes, no timeout:
  spawns a stand-in agent that forks a child and hangs, calls
  `kill_process_tree` directly, and asserts both pids die. No timing is
  involved, so there is nothing to race.
- **`test_timeout_kills_the_tree_and_raises`** and the two backend tests
  (`invoke_claude_code` / `invoke_pi_coding_agent`) use a **stub process** whose
  `communicate()` never returns. No fork/exec means no cold-start latency can
  race the timeout, so they are instant and deterministic. They cover the
  timeout path (kill + raise) and that each backend routes through
  `communicate_with_timeout`.
