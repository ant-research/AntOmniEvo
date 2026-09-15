# When to use it

> **English** · [中文](./when-to-use.zh-CN.md)

If two conditions hold — **(1) the thing under optimization can be expressed as an editable file directory, (2) its evaluation is repeatable and reasonably cheap** — AntOmniEvo fits. The system-under-optimization is **not limited to LLM agents**; common shapes by "the editable file directory":

- **AI agents** (skill / harness / memory / extension directories): NL2SQL skills, Terminal-Bench / SWE-bench coding-agent skills+harness, AppWorld agentic-API skills, ReAct+RAG system prompts + strategy docs.
- **Workflows / pipelines** (config + node code): a retrieval DAG's `pipeline.json` + `nodes/*.py` + `extensions/*.json` + `skill/STRATEGY.md`; the coding agent can edit DAG topology, node implementations, invariants. Whether the system contains an LLM is irrelevant — the `System` interface only sees "spec + data → trajectory + output".
- **Single-file algorithms** (a `.py` / `.ts` + its spec description): for cases where the algorithm itself is editable and has an eval set; the `SpecSchema` degenerates to "one main algorithm file + optional helpers".

Other common premises: you want **white-box, attributable** optimization (seeing "why this was changed, which instances improved, what the lineage is"), and a **long, interruptible** optimization with resume.

Not suitable / caveats: **systems with no editable spec** (only a few scalar params → use black-box tuning), **non-repeatable / extremely expensive evaluation**, **strict compliance output** (the proposer edits files in a sandbox — audit sandbox permissions yourself), **Proposer must be an LLM coding agent** (editable-spec evolution requires coding capability; but whether the system-under-optimization contains an LLM is irrelevant).
