# Features

> **English** · [中文](./features.zh-CN.md)

## 1. Optimization target: tunable-artifact-as-genome

- What's optimized is **not** a constrained parameter set or a constrained DSL, but a **real directory of files**; mutation = a coding agent adding / deleting / editing files inside it.
- **Not limited to agents**: any "directory of tunable artifacts + repeatable evaluation" system is a legal target — an agent's skill/harness/memory, a workflow's `pipeline.json` + node scripts, a single-file algorithm (`.py`/`.ts` + its description). Whether the system-under-optimization contains an LLM doesn't matter; the `System` interface only requires "tunable artifacts + data → trajectory + output".
- Every change is structured as a `ArtifactAction{file, operation, artifact_issue, change, resolves[]}` that must cite the failed-trajectory observation it fixes, making mutations **traceable, contradiction-resolvable, and quality-gated**.
- Expressive power = whatever the filesystem can hold: edit a markdown rule, edit a python implementation, add a verification script, add a runtime extension hard-constraint — not limited to preset fields.

## 2. Evolution: concurrency + mara chain + micro-pareto

- **Multi-slot concurrent evolution**: up to `num_proposals` candidates evolve **simultaneously**, each occupying its own slot over a shared candidate pool + state machine; prior work (GEPA / ACE / AHE) is serial.
- **Mara-chain deep repair**: when a batch misses its threshold, it doesn't stop at one natural-language reflection. The failed chain's per-instance score history, attributed changelog, and prior analyses are **pre-loaded into the prompt**, forcing a five-method diagnosis (causal tracing / success extraction / oscillation detection / inconsistency discovery / evidence corroboration) to produce the next candidate — up to `max_reflection_iterations` rounds, accepting the best chain member that beats the original parent.
- **Micro-pareto selection**: per-instance Pareto weak-dominance pruning + top-N truncation fallback; `select` weights by "multi-dimension leadership count" to protect versatile candidates. (Pareto selection itself is adopted from GEPA, not an AntOmniEvo contribution; AntOmniEvo's algorithmic deltas are **concurrency** and **mara chains**.)

## 3. Infrastructure: memory, isolation, observability, pluggability

- **Two-phase proposer (analyze → mutate)**: Phase 1 distills a failed run into a structured `RunAnalysis` (raw runs never feed the mutator directly); Phase 2 deduplicates / resolves contradictions across data instances before landing edits. Independent quality gates: `validate-analysis` (self-check) + enforced `append-changelog` (lineage traceability).
- **Filesystem-as-memory + checkpoint resume**: append-only `changelog.jsonl` (a child inherits its parent's copy); a candidate state machine + `reset_evolving_to_pending` at startup means an interruption and restart anywhere will resume cleanly.
- **Multi-axis budget control**: `Budget` has four orthogonal hard caps (`max_iterations` slot occupations / `max_rollouts` total rollouts / `max_tokens` cumulative tokens / `max_elapsed_seconds` wall clock); any `None` = unlimited on that axis. Hitting any set limit stops opening new slots, and in-flight slots drain before exit (a soft stop + drain semantics, pairing with checkpoint resume for long runs that don't overspend).
- **Cloud-storage integration**: `CandidateStore` is an abstract ABC with a default `LocalCandidateStore` that persists the evolution memory to a local `workspace/`. To use cloud infra, implement a "local + transparent sync" subclass: fully transparent to the optimizer, it still runs locally, and on every write it also syncs artifacts (tunable-artifact tree, meta, changelog, best candidate) to object storage / a DB — pulling the initial tunable artifacts from the cloud before a run, and exposing the artifacts for downstream consumption after. The main loop and in-process multi-slot concurrency are unchanged.
- **Strict validation-set isolation**: `val_system_run/` is off-limits to the proposer (the Pi path adds a runtime extension that hard-blocks it); a training batch decides "is this mutation worth keeping," the val set decides "where this candidate sits in the population," preventing tunable-artifact overfitting to val.
- **Bundled visualizer**: a React + Flask front-end renders an evolution run from its workspace directory.
