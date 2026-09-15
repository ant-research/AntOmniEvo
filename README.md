# AntOmniEvo

> **English** · [中文](./README.zh-CN.md)

**AntOmniEvo** is an auto optimization framework with a strict division of labor: **you define your system's editable parts and what "good" means — the framework controls the loop, AI agents do the work — and it delivers an optimized spec.**

The editable part of your system is abstracted as a **spec** — a real directory of files: an agent's `SKILL.md` + references + scripts, a workflow's `pipeline.json` + node scripts, a single-file algorithm + its description. Anything so representable, and repeatably evaluatable, AntOmniEvo can optimize — optimization becomes plain file editing. The system-under-optimization need not contain an LLM; the proposer must be agents.

## Division of labor: you define, framework controls, AI works

**You define** — five things, once:

| You provide | Role |
|---|---|
| `System` | how to **run** your system on one eval instance |
| `Evaluator` | how to **score** its output (0–1) — its scoring criteria *is* the optimization objective |
| eval **data** | the train/val instances that define "good" |
| `SpecSchema` | maps your system's editable parts onto a directory: the file tree + what each file is for |
| an **initial spec** | the starting point |

**The framework controls** — it runs the evolution loop, and all the control and engineering work inside it: scheduling, budgets, selection / elimination, persistence — deterministic machinery you don't write, keeping the strongest candidates in the population. Every candidate, run, analysis, and changelog is persisted to a `CandidateStore` — interruptible and resumable.

**The AI works** — the changing itself is done by a coding-agent `Proposer`: it reads failure trajectories, locates which spec file to edit, and lands a structured change as a new candidate's spec — the way a human would edit code.

**It delivers** — the best candidate's **spec**: a real directory of files you can diff, review, and deploy, with a change lineage attributing every edit to the failure evidence that motivated it.

---

## Documentation

| Topic | English | 中文 |
|---|---|---|
| Install & quick start | [docs/quickstart.md](./docs/quickstart.md) | [docs/quickstart.zh-CN.md](./docs/quickstart.zh-CN.md) |
| Features | [docs/features.md](./docs/features.md) | [docs/features.zh-CN.md](./docs/features.zh-CN.md) |
| Extensibility | [docs/extensibility.md](./docs/extensibility.md) | [docs/extensibility.zh-CN.md](./docs/extensibility.zh-CN.md) |
| When to use it | [docs/when-to-use.md](./docs/when-to-use.md) | [docs/when-to-use.zh-CN.md](./docs/when-to-use.zh-CN.md) |
| System design | [docs/system-design.md](./docs/system-design.md) | [docs/system-design.zh-CN.md](./docs/system-design.zh-CN.md) |
| Workspace artifacts & attribution | [docs/workspace-artifacts.md](./docs/workspace-artifacts.md) | [docs/workspace-artifacts.zh-CN.md](./docs/workspace-artifacts.zh-CN.md) |
| Checkpoint resume & crash recovery | [docs/checkpoint-resume.md](./docs/checkpoint-resume.md) | [docs/checkpoint-resume.zh-CN.md](./docs/checkpoint-resume.zh-CN.md) |
| Visualizer | [docs/visualizer.md](./docs/visualizer.md) | [docs/visualizer.zh-CN.md](./docs/visualizer.zh-CN.md) |

## License

Licensed under the [Apache License 2.0](./LICENSE). Legal disclaimer: see [`LEGAL.md`](./LEGAL.md).
