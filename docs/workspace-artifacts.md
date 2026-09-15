# Workspace artifacts & attribution

> **English** · [中文](./workspace-artifacts.zh-CN.md)

## 1. Did the run improve?

1. `logs/statistics.json`: compare `baseline_avg_score` with `best_avg_score`; `avg_score_history` is monotonic non-decreasing per slot.
2. `logs/iteration_records.jsonl`: per-slot `accepted`, `old_batch_score_sum → new_batch_score_sum`, `reflection_depth` (>0 = rescued by reflection), `proposer_duration_seconds`.
3. `candidates/{best_id}/data/summary.json`: per-validation-instance scores of the best candidate.

## 2. Why is the spec the way it is now?

1. Read `candidates/{id}/data/meta.json` → `parent_id`; walk up to the root for the full lineage.
2. Read `candidates/{id}/data/changelog.jsonl` — every mutation is one `ChangeLogEntry` with `subject`/`body`/`diff`/`files_modified`. **This is the human-readable history of why the spec looks the way it does.**
3. Read `candidates/{id}/data/proposer_run/analysis/result/{data_id}.json` — the `RunAnalysis` that drove each mutation: what was diagnosed (`trajectory_analysis`), what was prescribed (`actions`, each `resolves` linking back to the trajectory item it fixes).

## 3. Analyzing a candidate by ID

For a parent `4df3c...` / child `db062...` example, read (all under the same `workspace_dir`):

| What | Path | Look for |
|---|---|---|
| parent's analysis basis | `candidates/<parent>/data/proposer_run/analysis/result/*.json` | what trajectory problems were diagnosed, what `actions` were prescribed |
| child's actual runs | `candidates/<child>/data/system_run/{data_id}/run_*.json` | what the child actually did per instance (trajectory) |
| what changed | `candidates/<child>/data/changelog.jsonl` (last entry) | diff, `subject`, `body` (failure → change → expected impact) |
| analysis prompt | `antomnievo/proposer/template/analysis_prompt.py` (+`reflection_analysis_prompt.py`) | what the analysis agent was asked to do |
| mutation prompt | `antomnievo/proposer/template/mutation_prompt.py` | how actions were to be applied to the spec |
| spec conventions | `antomnievo/model/spec_defs/<your>_spec_def.py` | what files the spec may have and what each means |

Common failure modes: analysis diagnosed a problem but no `action` covered it; mutation fixed some instances but broke others (compare per-instance deltas); the spec says the right thing but the system didn't follow it (read the child trajectory).
