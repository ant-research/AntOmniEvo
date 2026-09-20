# 安装与快速开始

> [English](./quickstart.md) · **中文**

需要 Python ≥ 3.10。

```bash
cd antomnievo
pip install -e .                       # 核心框架(pydantic / httpx / tenacity)
pip install -e ".[rag]"                # 可选:LangGraph / RAG 场景
pip install -e ./visualizer && cd visualizer && npm install   # 可选:可视化器
npm install -g @mariozechner/pi-coding-agent   # 可选:`pi` CLI,仅当你用 PiCodingAgentProposer 时需要
```

若 `System` / `Evaluator` 会调你自己的运行时 / 打分工具,自行安装,AntOmniEvo 不管理它们。两个内置 proposer 同理:`PiCodingAgentProposer` 依赖 `pi` 命令(见上方安装),`ClaudeCodeProposer` 依赖 `claude` 命令,按你手上有的 CLI 二选一。

## 写你自己的 optimizer 入口

AntOmniEvo 是框架:你写一个入口脚本,把 7 个可插拔组件 + 一份 `TunableArtifactSchema` 串起来并调 `await optimizer.optimize()`。`antomnievo/example/` 下的脚本是参照实现(每个都针对一种系统形态把组件拼好),挑一个和你系统形态对得上的,把里面的 `System` / `Evaluator` / `DataInst` / `TunableArtifactSchema` / 初始可调产物换成你自己的。

入口脚本形状:加载 train/val 数据 → 建带时间戳的 `workspace/` → 构造各组件 → `await optimizer.optimize()`。具体拼法看:

- [`antomnievo/example/rag/agentic_rag.py`](../antomnievo/example/rag/agentic_rag.py) —— 最简单的端到端参照(进程内系统、基类 `Optimizer`),先看这个。
- [`antomnievo/example/text2sql/birdtest_text2sql.py`](../antomnievo/example/text2sql/birdtest_text2sql.py) —— 整批子进程 `System` + 场景 `Optimizer` 子类。

```python
import asyncio, os
from datetime import datetime
from antomnievo.common.config.config import setup_logging
from antomnievo.evolution_algorithm.pareto_frontier import ParetoFrontierEvolutionAlgorithm
from antomnievo.model.budget import Budget
from antomnievo.model.candidate_data_schema import CANDIDATE_DATA_SCHEMA
# 下面四个换成你自己的:
from antomnievo.model.tunable_artifact_defs.myagent_tunable_artifact_def import MY_TUNABLE_ARTIFACT_SCHEMA
from antomnievo.system.myagent.myagent_system import MySystem
from antomnievo.evaluator.myagent.myagent_evaluator import MyEvaluator
from antomnievo.dataset.myagent.myagent_dataset_loader import load_dataset
# ──
from antomnievo.optimizer.optimizer import Optimizer
from antomnievo.proposer.pi_coding_agent_proposer import PiCodingAgentProposer
from antomnievo.store.candidate_store import LocalCandidateStore

async def main():
    setup_logging()
    train = await load_dataset("…train…")
    val   = await load_dataset("…val…")
    workspace = os.path.join(os.path.dirname(__file__), "workspace",
                             "myagent_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    os.makedirs(workspace, exist_ok=True)

    store = LocalCandidateStore(workspace, cleanup_unavailable=False)
    ea    = ParetoFrontierEvolutionAlgorithm(store, max_candidate_num=3)
    system    = MySystem(concurrency=8, api_key="…", base_url="…")
    evaluator = MyEvaluator()
    proposer  = PiCodingAgentProposer(
        api_key="…", tunable_artifact_schema=MY_TUNABLE_ARTIFACT_SCHEMA, candidate_store=store,
        evaluator=evaluator, data_schema=CANDIDATE_DATA_SCHEMA,
        model="…", provider="anthropic", concurrency=20, max_turns=200, timeout=3600,
        system=system, skip_perfect_score_runs=False, last_n_analysis=10,
    )
    optimizer = Optimizer(
        system=system, proposer=proposer, evaluator=evaluator,
        evolution_algorithm=ea, candidate_store=store,
        train_dataset=train, val_dataset=val,
        batch_size=3, budget=Budget(max_iterations=1000),
        num_proposals=1, max_reflection_iterations=2, min_improvement_per_batch=2.0,
        initial_artifacts_dir="/path/to/tasks/myagent-base",
    )
    await optimizer.optimize()

if __name__ == "__main__":
    asyncio.run(main())
```

`example/` 里的脚本各自依赖外部运行时和数据集(如 `terminalbench2`、`appworld`、`birdtest` 等另外的代码仓),**开箱不能直接跑**;它们用来学结构,不是复刻环境,忽略其中硬编码路径即可。
