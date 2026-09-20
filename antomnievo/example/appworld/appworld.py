#!/usr/bin/env python
"""
AppWorld Auto-Optimizer entry point.

Uses AppWorldSystem + AppWorldEvaluator + PiCodingAgentProposer +
ParetoFrontierEvolutionAlgorithm to optimize the AppWorld coding agent's skill.

All AppWorld subprocess calls use the AppWorld venv Python and a per-rollout
temporary directory as APPWORLD_ROOT, so the antomnievo environment does not
need to install the appworld package.
"""
import asyncio
import logging
import os

import yaml

from antomnievo.common.config.config import setup_logging
from antomnievo.dataset.appworld.appworld_dataset_loader import load_appworld_split
from antomnievo.evaluator.appworld.appworld_evaluator import AppWorldEvaluator
from antomnievo.evolution_algorithm.pareto_frontier import ParetoFrontierEvolutionAlgorithm
from antomnievo.model.budget import Budget
from antomnievo.model.candidate_data_schema import CANDIDATE_DATA_SCHEMA
from antomnievo.model.tunable_artifact_defs.appworld_tunable_artifact_def import APPWORLD_SKILL_TUNABLE_ARTIFACT_SCHEMA
from antomnievo.optimizer.appworld.appworld_optimizer import AppWorldOptimizer
from antomnievo.proposer.pi_coding_agent_proposer import PiCodingAgentProposer
from antomnievo.store.candidate_store import LocalCandidateStore
from antomnievo.system.appworld.appworld_system import AppWorldSystem

# antchat creds (api_keys + base_url) live in <repo>/config/config.yaml (gitignored).
_CONFIG_FILE = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "config", "config.yaml")
)
with open(_CONFIG_FILE, encoding="utf-8") as _f:
    _antchat_cfg = yaml.safe_load(_f)
ANTCHAT_API_KEYS = _antchat_cfg["api_keys"]
ANTCHAT_BASE_URL = _antchat_cfg["base_url"]

logger = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────
APPWORLD_ROOT = os.path.expanduser("~/work/appworld")
APPWORLD_PYTHON = os.path.join(APPWORLD_ROOT, ".venv", "bin", "python")
APPWORLD_DATA_DIR = os.path.join(APPWORLD_ROOT, "data")
SPLIT_FILE = os.path.join(APPWORLD_ROOT, "experiments", "data_splits", "train_val_split.json")
INITIAL_ARTIFACTS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "tasks", "appworld-base"))


async def main():
    """Main function."""
    setup_logging()
    logger.info("Starting AppWorld Auto-Optimizer")

    # ── Dataset ──────────────────────────────────────────────────────────
    train_dataset, val_dataset = await load_appworld_split(
        split_file=SPLIT_FILE,
        appworld_python=APPWORLD_PYTHON,
        appworld_root=APPWORLD_ROOT,
    )
    logger.info(f"Dataset: train={len(train_dataset)}, val={len(val_dataset)}")
    train_dataset = train_dataset[:8]
    val_dataset = val_dataset[:4]

    # ── Workspace ────────────────────────────────────────────────────────
    workspace_dir = os.path.join(os.path.dirname(__file__), "workspace","appworld_multi_slots_1_with_mc-" + __import__("datetime").datetime.now().strftime("%Y%m%d_%H%M%S"))
    os.makedirs(workspace_dir, exist_ok=True)
    #workspace_dir = '/Users/jacklv/work/antomnievo/antomnievo/example/appworld/workspace/appworld_multi_slots_2-20260723_113741'
    logger.info(f"Workspace: {workspace_dir}")

    # ── Components ───────────────────────────────────────────────────────
    candidate_store = LocalCandidateStore(workspace_dir, cleanup_unavailable=False)

    evolution_algorithm = ParetoFrontierEvolutionAlgorithm(
        candidate_store=candidate_store,
        max_candidate_num=3,
    )

    system = AppWorldSystem(
        appworld_python=APPWORLD_PYTHON,
        appworld_root=APPWORLD_ROOT,
        model="glm-5.2",
        max_steps=50,
        concurrency=25,
        api_key=ANTCHAT_API_KEYS[1],
        base_url=ANTCHAT_BASE_URL,
    )

    evaluator = AppWorldEvaluator(
        appworld_python=APPWORLD_PYTHON,
        appworld_root=APPWORLD_ROOT,
        concurrency=20,
    )

    proposer = PiCodingAgentProposer(
        api_key=ANTCHAT_API_KEYS[1],
        #api_key=ANTCHAT_API_KEYS[0],
        tunable_artifact_schema=APPWORLD_SKILL_TUNABLE_ARTIFACT_SCHEMA,
        #tunable_artifact_schema=APPWORLD_SKILL_ONLY_TUNABLE_ARTIFACT_SCHEMA,
        candidate_store=candidate_store,
        evaluator=evaluator,
        data_schema=CANDIDATE_DATA_SCHEMA,
        model="glm-5.2",
        max_turns=200,
        timeout=3600,
        concurrency=10,
        system=system,
        skip_perfect_score_runs=False,
        last_n_analysis=10,
    )

    # ── Optimizer ────────────────────────────────────────────────────────
    optimizer = AppWorldOptimizer(
        system=system,
        proposer=proposer,
        evaluator=evaluator,
        evolution_algorithm=evolution_algorithm,
        candidate_store=candidate_store,
        train_dataset=train_dataset,
        val_dataset=val_dataset,
        batch_size=4,
        budget=Budget(max_iterations=1000, max_elapsed_seconds=40 * 3600),
        num_proposals=1,
        max_reflection_iterations=2,
        min_improvement_per_batch=3.0,
        initial_artifacts_dir=INITIAL_ARTIFACTS_DIR,
        appworld_data_dir=APPWORLD_DATA_DIR,
    )

    # ── Run ──────────────────────────────────────────────────────────────
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
