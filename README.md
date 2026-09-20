# AntOmniEvo

**An auto-evolution framework: optimize anything — your 7×24 algorithm engineers.**

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](./LICENSE) [![arXiv](https://img.shields.io/badge/Paper-coming_soon-lightgrey.svg)](#paper)

> **English** · [中文](./README.zh-CN.md)

---

**AntOmniEvo** is an auto-evolution framework with a strict division of labor: **you define your system's tunable artifacts and what "good" means — the framework controls the loop, AI agents do the work — and it delivers optimized tunable artifacts.**

Your system's tunable parts are abstracted as **tunable artifacts** — a real directory of files: an agent's `SKILL.md` + references + scripts, a workflow's `pipeline.json` + node scripts, a single-file algorithm + its description. Anything so representable, and repeatably evaluatable, AntOmniEvo can optimize — optimization becomes plain file editing. The system-under-optimization need not contain an LLM; the proposer must be agents.

## 🚀 What it is

AntOmniEvo is an auto-evolution framework for AI agent systems. It treats your system's **tunable artifacts** (skills, prompts, workflow configs, pipeline code) as the genome, and runs a concurrent evolution loop where a coding-agent `Proposer` reads failure trajectories and rewrites those artifacts — the way a human would edit code.

It works for any system that can be expressed as a directory of tunable files and has a repeatable, reasonably-cheap evaluation:

- **AI agents** — skill / harness / memory / extension directories (NL2SQL skills, coding-agent skills+harness, agentic-API skills, system prompts + strategy docs, etc).
- **Workflows / pipelines** — config + node code (a retrieval DAG's `pipeline.json` + `nodes/*.py`).
- **Single-file algorithms** — a `.py` / `.ts` + its description.

## 🧩 How it works

**Division of labor: you define, framework controls, AI works.**

**You define** — five things, once:

| You provide | Role |
| --- | --- |
| `System` | how to **run** your system on one eval instance |
| `Evaluator` | how to **score** its output (0–1) — its scoring criteria *is* the optimization objective |
| eval **data** | the train/val instances that define "good" |
| `TunableArtifactSchema` | maps your system's tunable artifacts onto a directory: the file tree + what each file is for |
| **initial tunable artifacts** | the starting point |

**The framework controls** — it runs the evolution loop, and all the control and engineering work inside it: scheduling, budgets, selection / elimination, persistence — deterministic machinery you don't write, keeping the strongest candidates in the population. Every candidate, run, analysis, and changelog is persisted to a `CandidateStore` — interruptible and resumable.

**The AI works** — the changing itself is done by a coding-agent `Proposer`: it reads failure trajectories, locates which file to edit, and lands a structured change as a new candidate's tunable artifacts — the way a human would edit code.

**It delivers** — the best candidate's **tunable artifacts**: a real directory of files you can diff, review, and deploy, with a change lineage attributing every edit to the failure evidence that motivated it.

## 📚 Documentation

| Topic | English | 中文 |
| --- | --- | --- |
| Install & quick start | [docs/quickstart.md](./docs/quickstart.md) | [docs/quickstart.zh-CN.md](./docs/quickstart.zh-CN.md) |
| Features | [docs/features.md](./docs/features.md) | [docs/features.zh-CN.md](./docs/features.zh-CN.md) |
| Extensibility | [docs/extensibility.md](./docs/extensibility.md) | [docs/extensibility.zh-CN.md](./docs/extensibility.zh-CN.md) |
| When to use it | [docs/when-to-use.md](./docs/when-to-use.md) | [docs/when-to-use.zh-CN.md](./docs/when-to-use.zh-CN.md) |
| System design | [docs/system-design.md](./docs/system-design.md) | [docs/system-design.zh-CN.md](./docs/system-design.zh-CN.md) |
| Workspace artifacts & attribution | [docs/workspace-artifacts.md](./docs/workspace-artifacts.md) | [docs/workspace-artifacts.zh-CN.md](./docs/workspace-artifacts.zh-CN.md) |
| Checkpoint resume & crash recovery | [docs/checkpoint-resume.md](./docs/checkpoint-resume.md) | [docs/checkpoint-resume.zh-CN.md](./docs/checkpoint-resume.zh-CN.md) |
| Visualizer | [docs/visualizer.md](./docs/visualizer.md) | [docs/visualizer.zh-CN.md](./docs/visualizer.zh-CN.md) |

## 📄 Paper

**Coming soon.** We will link the paper here once it is released.

## ⭐ Star History

[![Star History Chart](https://api.star-history.com/svg?repos=ant-research/AntOmniEvo&type=Date)](https://star-history.com/#ant-research/AntOmniEvo&Date)

## License

Licensed under the [Apache License 2.0](./LICENSE). Legal disclaimer: see [`LEGAL.md`](./LEGAL.md).
