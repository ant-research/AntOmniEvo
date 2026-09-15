# Checkpoint resume & crash recovery

> **English** · [中文](./checkpoint-resume.zh-CN.md)

AntOmniEvo is interruptible and resumable by design:

- **Same `workspace_dir` re-run**: on startup it checks `statistics.root_candidate_id`; present → resume (skip root baseline); absent → start from scratch.
- **Candidates left `evolving` from a crash**: `__init__` calls `reset_evolving_to_pending()` to flip them all back to `pending`.
- **Stale `unavailable` candidates**: swept at startup if `cleanup_unavailable=True`.
- **Durable artifacts**: run records, analyses, changelogs, and trajectories are append-only or atomic; even an LLM error mid-mutation persists its trajectory before reporting failure.

**In practice**: resume by running the same entry script with the same `workspace_dir`; to start fresh, timestamp a new `workspace_dir`. That's the only thing to get right.
