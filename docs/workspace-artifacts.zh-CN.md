# workspace 产物与归因

> [English](./workspace-artifacts.md) · **中文**

## 1. 看一次运行有没有进步

1. `logs/statistics.json`:对比 `baseline_avg_score` 与 `best_avg_score`;`avg_score_history` 每 slot 单调不降。
2. `logs/iteration_records.jsonl`:逐 slot 看 `accepted`、`old_batch_score_sum → new_batch_score_sum`、`reflection_depth`(>0 = 反思救回)、`proposer_duration_seconds`。
3. `candidates/{best_id}/data/summary.json`:最佳候选在 val 上的逐题分数。

## 2. 为什么 spec 现在长这样

1. 读 `candidates/{id}/data/meta.json` → `parent_id`,顺到 root 得完整 lineage。
2. 读 `candidates/{id}/data/changelog.jsonl` —— 每次变异一条 `ChangeLogEntry`,带 `subject`/`body`/`diff`/`files_modified`,**这就是 spec 演化史的可读叙述**。
3. 读 `candidates/{id}/data/proposer_run/analysis/result/{data_id}.json` —— 驱动每次变异的 `RunAnalysis`:诊断了什么(`trajectory_analysis`)、开了哪些处方(`actions`,每个 `resolves` 回指它修的 trajectory 项)。

## 3. 给定候选 id 做归因分析

以 parent `4df3c...` / child `db062...` 为例,看下面这些(都在同一 `workspace_dir`):

| 看什么 | 路径 | 找什么 |
|---|---|---|
| parent 的分析依据 | `candidates/<parent>/data/proposer_run/analysis/result/*.json` | 诊断了哪些 trajectory 问题、开了哪些 `actions` |
| child 的实际运行 | `candidates/<child>/data/system_run/{data_id}/run_*.json` | child 在每条数据上到底做了啥(trajectory) |
| 变了什么 | `candidates/<child>/data/changelog.jsonl`(最后一条) | diff、`subject`、`body`(失败→改动→预期) |
| 分析 prompt | `antomnievo/proposer/template/analysis_prompt.py`(+`reflection_analysis_prompt.py`) | 分析阶段让 agent 干什么 |
| 变异 prompt | `antomnievo/proposer/template/mutation_prompt.py` | actions 该怎么落到 spec 上 |
| spec 约定 | `antomnievo/model/spec_defs/<your>_spec_def.py` | spec 允许哪些文件、每个文件什么含义 |

常见失效模式:analysis 诊断了问题但没覆盖它的 `action`;变异在部分题上修好但别的题改坏了(对比逐题 delta);spec 写对了但系统没照着做(看 child 的 trajectory)。
