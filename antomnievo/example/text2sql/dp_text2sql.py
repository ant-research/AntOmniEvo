#!/usr/bin/env python
"""
Text2SQL Auto-Optimizer entry point.

Uses Text2SQLSystem (Harbor-based) + Text2SQLEvaluator + ClaudeCodeProposer
+ ParetoFrontierEvolutionAlgorithm to optimize the NL2SQL agent tunable artifacts.
"""
import asyncio
import logging
import os

import yaml

from antomnievo.common.config.config import setup_logging
from antomnievo.dataset.dp.text2sql_dataset_loader import load_dataset
from antomnievo.evaluator.text2sql.dp_text2sql_evaluator import DPText2SQLEvaluator
from antomnievo.evolution_algorithm.pareto_frontier import ParetoFrontierEvolutionAlgorithm
from antomnievo.model.budget import Budget
from antomnievo.model.candidate_data_schema import CANDIDATE_DATA_SCHEMA
from antomnievo.model.tunable_artifact_defs.dp_text2sql_skill_tunable_artifact_def import (
    TEXT2SQL_SKILL_TUNABLE_ARTIFACT_SCHEMA,
)
from antomnievo.optimizer.text2sql.dp_text2sql_optimizer import DPText2SQLOptimizer
from antomnievo.proposer.pi_coding_agent_proposer import PiCodingAgentProposer
from antomnievo.store.candidate_store import LocalCandidateStore
from antomnievo.system.text2sql.dp_text2sql_system import DPText2SQLSystem

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
HARBOR_DP_DIR = os.path.expanduser("~/work/harbor_dp")
TRAIN_DATA_DIR = os.path.join(HARBOR_DP_DIR, "output", "harbor_tasks_train_v2")
VAL_DATA_DIR = os.path.join(HARBOR_DP_DIR, "output", "harbor_tasks_val_v2")

async def main():
    """Main function."""
    setup_logging()
    logger.info("Starting Text2SQL Auto-Optimizer")

    # ── Dataset ──────────────────────────────────────────────────────────
    train_dataset = await load_dataset(TRAIN_DATA_DIR, shuffle=False)
    val_dataset = await load_dataset(VAL_DATA_DIR, shuffle=False)
    logger.info(f"Dataset: train={len(train_dataset)}, val={len(val_dataset)}")

    # ── Workspace ────────────────────────────────────────────────────────
    workspace_dir = os.path.join(os.path.dirname(__file__), "workspace", "dptest_" + __import__("datetime").datetime.now().strftime("%Y%m%d_%H%M%S"))
    #workspace_dir = '/Users/jacklv/work/antomnievo/antomnievo/example/text2sql/workspace/dptest_20260610_124754'
    os.makedirs(workspace_dir, exist_ok=True)
    logger.info(f"Workspace: {workspace_dir}")

    # ── Components ───────────────────────────────────────────────────────
    candidate_store = LocalCandidateStore(workspace_dir, cleanup_unavailable=False)

    evolution_algorithm = ParetoFrontierEvolutionAlgorithm(
        candidate_store=candidate_store,
        max_candidate_num=4,
    )

    system = DPText2SQLSystem(
        run_sh_path=os.path.join(HARBOR_DP_DIR, "test", "run.sh"),
        api_key=ANTCHAT_API_KEYS[0],
        concurrency=25,
        model="kimi-k2.5"
    )

    evaluator = DPText2SQLEvaluator()


    proposer = PiCodingAgentProposer(
        api_key=ANTCHAT_API_KEYS[0],
        tunable_artifact_schema=TEXT2SQL_SKILL_TUNABLE_ARTIFACT_SCHEMA,
        candidate_store=candidate_store,
        evaluator=evaluator,
        data_schema=CANDIDATE_DATA_SCHEMA,
        model="glm-5",
        max_turns=200,
        timeout=3600,
        concurrency=20,
        system=system,
        skip_perfect_score_runs=False,
        last_n_analysis=10,
    )

    # ── Optimizer ────────────────────────────────────────────────────────
    optimizer = DPText2SQLOptimizer(
        system=system,
        proposer=proposer,
        evaluator=evaluator,
        evolution_algorithm=evolution_algorithm,
        candidate_store=candidate_store,
        train_dataset=train_dataset,
        val_dataset=val_dataset,
        batch_size=5,
        budget=Budget(max_iterations=1000),
        num_proposals=3,
        max_reflection_iterations=1,
        min_improvement_per_batch=2.0,
        initial_artifacts_dir="/Users/jacklv/work/antomnievo/tasks/dp-base",
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
