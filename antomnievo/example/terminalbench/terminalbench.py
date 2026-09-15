#!/usr/bin/env python
"""
Terminal-Bench 2 Auto-Optimizer entry point.

Uses TerminalBenchSystem (tbtest generate + harbor) + TerminalBenchEvaluator
+ PiCodingAgentProposer + ParetoFrontierEvolutionAlgorithm to optimize the
Pi coding agent's spec (skill / memory / extension) against the Terminal-
Bench 2 dataset.

Train/val both read the full ``terminalbench2/dataset`` directly (no separate
symlink split). The loader loads every qualifying task directory (no default
exclusion). ``allow_empty=True`` is kept on the val load so pointing it at an
empty split (if you reintroduce one) stays a no-op.
"""
import asyncio
import logging
import os

import yaml

from antomnievo.common.config.config import setup_logging
from antomnievo.dataset.terminalbench.terminalbench_dataset_loader import load_dataset
from antomnievo.evaluator.terminalbench.terminalbench_evaluator import TerminalBenchEvaluator
from antomnievo.evolution_algorithm.pareto_frontier import ParetoFrontierEvolutionAlgorithm
from antomnievo.model.budget import Budget
from antomnievo.model.candidate_data_schema import CANDIDATE_DATA_SCHEMA
from antomnievo.model.spec_defs.terminalbench_kira_spec_def import TERMINALBENCH_KIRA_SPEC_SCHEMA
from antomnievo.optimizer.terminalbench.terminalbench_optimizer import TerminalBenchOptimizer
from antomnievo.proposer.pi_coding_agent_proposer import PiCodingAgentProposer
from antomnievo.store.candidate_store import LocalCandidateStore
from antomnievo.system.terminalbench.terminalbench_system import TerminalBenchSystem

# antchat creds (api_keys + base_url) live in <repo>/config/config.yaml (gitignored).
_CONFIG_FILE = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "config", "config.yaml")
)
with open(_CONFIG_FILE, encoding="utf-8") as _f:
    _antchat_cfg = yaml.safe_load(_f)
ANTCHAT_API_KEYS = _antchat_cfg["api_keys"]
ANTCHAT_BASE_URL = _antchat_cfg["base_url"]

logger = logging.getLogger(__name__)

# ── Paths (adjust to your environment) ──────────────────────────────────────
TERMINALBENCH_DIR = os.path.expanduser("~/work/terminalbench2")
GENERATE_BIN = os.path.join(TERMINALBENCH_DIR, ".venv", "bin", "generate")
JOB_CONFIG_YAML = os.path.join(TERMINALBENCH_DIR, "test", "job-config-kira.yaml")
INITIAL_SPEC_DIR = os.path.join(TERMINALBENCH_DIR, "spec", "kira")

# Model + litellm provider prefix. TerminalBenchSystem forwards ``model`` to
# ``tbtest generate``'s ``-m`` / ``ANTHROPIC_MODEL``; litellm needs the
# ``anthropic/`` prefix so it routes via the anthropic adapter (/v1/messages)
# and then forwards the bare name to the antchat gateway. A bare ``glm-5``
# makes litellm raise ``BadRequestError("LLM Provider NOT provided")``. See
# job-config-kira.yaml head comment. Do NOT use ``antchat/`` — the remote
# gateway 401s it.
PROVIDER = "anthropic"
SYSTEM_MODEL = "glm-5"      # tbtest rollout agent model (provider auto-prefixed)
PROPOSER_MODEL = "glm-5.1"  # proposer LLM (PiCodingAgentProposer has its own provider param)

# AntOmniEvo reads ``dataset2.1/`` directly — the loader loads every
# qualifying task directory (no default exclusion). No separate
# dataset-training/ symlink split is maintained. Train and val both point at
# the same dir; val uses allow_empty semantics only if pointed at an empty
# split.
DATASET_DIR = os.path.join(TERMINALBENCH_DIR, "dataset2.1")
TRAIN_DATA_DIR = DATASET_DIR
VAL_DATA_DIR = DATASET_DIR


async def main():
    setup_logging()
    logger.info("Starting Terminal-Bench 2 Auto-Optimizer")

    # ── Dataset ──────────────────────────────────────────────────────────
    # Both point at the full dataset/; the loader loads every task. Train is
    # sorted by ascending wall-clock duration (fastest first, unmeasured last)
    # so early batches run the cheapest tasks — see DEFAULT_DURATION_JSON.
    train_dataset = await load_dataset(
        TRAIN_DATA_DIR, shuffle=False, max_samples=89, sort_by_duration=True,
    )
    val_dataset = await load_dataset(VAL_DATA_DIR, shuffle=False, allow_empty=True, max_samples=0)
    logger.info(f"Dataset: train={len(train_dataset)}, val={len(val_dataset)}")

    # ── Workspace ────────────────────────────────────────────────────────
    #from datetime import datetime
    #workspace_dir = os.path.join(os.path.dirname(__file__), "workspace", "tbtest_wo_reflection_chain" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    #os.makedirs(workspace_dir, exist_ok=True)
    workspace_dir = '/Users/jacklv/work/antomnievo/antomnievo/example/terminalbench/workspace/tbtest_wo_reflection_chain20260726_013442'
    logger.info(f"Workspace: {workspace_dir}")

    # ── Components ───────────────────────────────────────────────────────
    candidate_store = LocalCandidateStore(workspace_dir, cleanup_unavailable=False)

    evolution_algorithm = ParetoFrontierEvolutionAlgorithm(
        candidate_store=candidate_store,
        max_candidate_num=1,
    )

    system = TerminalBenchSystem(
        generate_bin=GENERATE_BIN,
        api_key=ANTCHAT_API_KEYS[3],
        base_url=ANTCHAT_BASE_URL,
        concurrency=8,
        attempts=1,
        job_config_yaml=JOB_CONFIG_YAML,
        model=SYSTEM_MODEL,
        provider=PROVIDER,
        force_build=True,
    )

    evaluator = TerminalBenchEvaluator()

    proposer = PiCodingAgentProposer(
        api_key=ANTCHAT_API_KEYS[4],
        spec_schema=TERMINALBENCH_KIRA_SPEC_SCHEMA,
        candidate_store=candidate_store,
        evaluator=evaluator,
        data_schema=CANDIDATE_DATA_SCHEMA,
        model=PROPOSER_MODEL,
        provider=PROVIDER,
        max_turns=200,
        timeout=3600,
        concurrency=20,
        system=system,
        skip_perfect_score_runs=False,
        last_n_analysis=10,
    )

    # ── Optimizer ────────────────────────────────────────────────────────
    optimizer = TerminalBenchOptimizer(
        system=system,
        proposer=proposer,
        evaluator=evaluator,
        evolution_algorithm=evolution_algorithm,
        candidate_store=candidate_store,
        train_dataset=train_dataset,
        val_dataset=val_dataset,
        batch_size=4,
        budget=Budget(max_iterations=1000),
        num_proposals=1,
        #max_reflection_iterations=5,
        #min_improvement_per_batch=3.0,
        initial_spec_dir=INITIAL_SPEC_DIR,
    )

    await optimizer.optimize()


if __name__ == "__main__":
    try:
        asyncio.run(main())
        logger.info("Optimizer finished!")
    except KeyboardInterrupt:
        logger.info("User interrupted")
    except Exception as e:
        logger.error(f"Optimizer failed: {e}")
        import traceback
        traceback.print_exc()
