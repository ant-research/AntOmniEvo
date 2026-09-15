#!/usr/bin/env python
"""
Text2SQL Auto-Optimizer entry point for Spider2-Snow.

Uses Text2SQLSystem (spidertest.generate) + Text2SQLEvaluator (spidertest.evaluate)
+ PiCodingAgentProposer + ParetoFrontierEvolutionAlgorithm to optimize the NL2SQL skill.
"""
import asyncio
import logging
import os

import yaml

from antomnievo.common.config.config import setup_logging
from antomnievo.dataset.spider2snow.spider2snow_dataset_loader import (
    load_spider2snow_from_contexts,
)
from antomnievo.evaluator.text2sql.text2sql_evaluator import Text2SQLEvaluator
from antomnievo.evolution_algorithm.pareto_frontier import ParetoFrontierEvolutionAlgorithm
from antomnievo.model.budget import Budget
from antomnievo.model.candidate_data_schema import CANDIDATE_DATA_SCHEMA
from antomnievo.model.spec_defs.text2sql_spec_def import TEXT2SQL_SKILL_SPEC_SCHEMA
from antomnievo.optimizer.text2sql.text2sql_optimizer import Text2SQLOptimizer
from antomnievo.proposer.pi_coding_agent_proposer import PiCodingAgentProposer
from antomnievo.store.candidate_store import LocalCandidateStore
from antomnievo.system.text2sql.text2sql_system import Text2SQLSystem

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
SPIDERTEST_DIR = os.path.expanduser("~/work/spidertest")
SPIDER2_ROOT = os.path.join(SPIDERTEST_DIR, "datasets", "spider2-snow")
OUTPUT_DIR = os.path.join(SPIDERTEST_DIR, "output")
INDEX_DIR = os.path.join(OUTPUT_DIR, "spider2-snow", "retrieval")
EVALUATE_SCRIPT = os.path.join(SPIDERTEST_DIR, "src", "spidertest", "evaluate.py")
GENERATE_SCRIPT = os.path.join(SPIDERTEST_DIR, "src", "spidertest", "generate.py")
SPIDERTEST_PYTHON = os.path.join(SPIDERTEST_DIR, ".venv", "bin", "python")

# Sampled dataset paths (pre-processed)
SAMPLED_TRAIN = os.path.join(OUTPUT_DIR, "sampled_train", "contexts.jsonl")
SAMPLED_VAL = os.path.join(OUTPUT_DIR, "sampled_val", "contexts.jsonl")


async def main():
    """Main function."""
    setup_logging()
    logger.info("Starting Spider2-Snow Text2SQL Auto-Optimizer")

    # ── Dataset ──────────────────────────────────────────────────────────
    train_dataset = await load_spider2snow_from_contexts(SAMPLED_TRAIN, shuffle=False)
    val_dataset = await load_spider2snow_from_contexts(SAMPLED_VAL, shuffle=False)
    logger.info(f"Dataset: train={len(train_dataset)}, val={len(val_dataset)}")

    # ── Workspace ────────────────────────────────────────────────────────
    #workspace_dir = os.path.join(os.path.dirname(__file__), "workspace",
    #                             "spider2snow_" + __import__("datetime").datetime.now().strftime("%Y%m%d_%H%M%S"))
    workspace_dir = '/Users/jacklv/work/antomnievo/antomnievo/example/text2sql/workspace/spider2snow_20260629_004307'
    os.makedirs(workspace_dir, exist_ok=True)
    logger.info(f"Workspace: {workspace_dir}")

    # ── Components ───────────────────────────────────────────────────────
    candidate_store = LocalCandidateStore(workspace_dir, cleanup_unavailable=False)

    evolution_algorithm = ParetoFrontierEvolutionAlgorithm(
        candidate_store=candidate_store,
        max_candidate_num=3,
    )

    system = Text2SQLSystem(
        generate_script=GENERATE_SCRIPT,
        python_path=SPIDERTEST_PYTHON,
        model="glm-5",
        timeout=3000,
        concurrency=30,
        api_key=ANTCHAT_API_KEYS[0],
        base_url=ANTCHAT_BASE_URL,
        extra_args=["--index-dir", INDEX_DIR],
    )

    evaluator = Text2SQLEvaluator(
        evaluate_script=EVALUATE_SCRIPT,
        python_path=SPIDERTEST_PYTHON,
        score_parser="spider2snow",
        extra_args=["--spider2_root", SPIDER2_ROOT],
    )

    proposer = PiCodingAgentProposer(
        #api_key=ANTCHAT_API_KEYS[0],
        api_key=ANTCHAT_API_KEYS[2],
        spec_schema=TEXT2SQL_SKILL_SPEC_SCHEMA,
        candidate_store=candidate_store,
        evaluator=evaluator,
        data_schema=CANDIDATE_DATA_SCHEMA,
        model="glm-5.1",
        thinking="low",
        max_turns=200,
        timeout=3600,
        concurrency=20,
        system=system,
        skip_perfect_score_runs=False,
        last_n_analysis=10,
    )

    # ── Optimizer ────────────────────────────────────────────────────────
    optimizer = Text2SQLOptimizer(
        system=system,
        proposer=proposer,
        evaluator=evaluator,
        evolution_algorithm=evolution_algorithm,
        candidate_store=candidate_store,
        train_dataset=train_dataset,
        val_dataset=val_dataset,
        batch_size=4,
        budget=Budget(max_iterations=1000),
        num_proposals=3,
        max_reflection_iterations=2,
        min_improvement_per_batch=2.0,
        initial_spec_dir='/Users/jacklv/work/antomnievo/tasks/spider-base-2',
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
