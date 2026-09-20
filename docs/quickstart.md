# Install & quick start

> **English** · [中文](./quickstart.zh-CN.md)

Requires Python ≥ 3.10.

```bash
cd antomnievo
pip install -e .                       # core framework (pydantic, httpx, tenacity)
pip install -e ".[rag]"                # optional: LangGraph / RAG scenarios
pip install -e ./visualizer && cd visualizer && npm install   # optional: visualizer
npm install -g @mariozechner/pi-coding-agent   # optional: `pi` CLI, needed only if you use PiCodingAgentProposer
```

If your `System` / `Evaluator` shells out to your own runtime / scoring harness, install those separately; AntOmniEvo does not manage them. The two built-in proposers likewise drive external CLIs — `PiCodingAgentProposer` needs the `pi` command (install above), `ClaudeCodeProposer` needs the `claude` command; pick the one whose CLI you have.

## Writing your own optimizer entry point

AntOmniEvo is a framework: you write an entry-point script that wires the 7 pluggable components + your `TunableArtifactSchema` together and calls `await optimizer.optimize()`. The scripts under `antomnievo/example/` are **reference implementations** (each wires the components for a different system shape) — copy the one matching your system, then swap in your own `System` / `Evaluator` / `DataInst` / `TunableArtifactSchema` / initial tunable artifacts.

Entry-point shape: load train/val data → build a timestamped `workspace/` → construct the components → `await optimizer.optimize()`. For the concrete wiring:

- [`antomnievo/example/rag/agentic_rag.py`](../antomnievo/example/rag/agentic_rag.py) — the simplest end-to-end reference (in-process system, base `Optimizer`); start here.
- [`antomnievo/example/text2sql/birdtest_text2sql.py`](../antomnievo/example/text2sql/birdtest_text2sql.py) — a batch-subprocess `System` + a scenario `Optimizer` subclass.

```python
import asyncio, os
from datetime import datetime
from antomnievo.common.config.config import setup_logging
from antomnievo.evolution_algorithm.pareto_frontier import ParetoFrontierEvolutionAlgorithm
from antomnievo.model.budget import Budget
from antomnievo.model.candidate_data_schema import CANDIDATE_DATA_SCHEMA
# Replace these four with your own:
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

The `example/` scripts each depend on their own external runtime and dataset (e.g. the separate `terminalbench2`, `appworld`, `birdtest` codebases) and **are not runnable out of the box** — they're for learning the structure, not reproducing an environment; ignore their hardcoded paths.
