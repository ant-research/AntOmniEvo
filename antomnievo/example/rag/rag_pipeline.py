#!/usr/bin/env python
"""
Retrieval-Pipeline Auto-Optimizer entry point.

Mirrors appworld.py: optimizes the retrieval-pipeline DAG tunable artifacts
(``RAG_PIPELINE_TUNABLE_ARTIFACT_SCHEMA``) on MuSiQue. The "system" is retrieval-test's
``generate.py`` (runs the artifact_dir pipeline over queries) and the evaluator is
retrieval-test's ``evaluate.py`` (nDCG@k / Recall@k vs golden_doc_ids). Both run
in the retrieval-test venv as subprocesses, so the antomnievo environment does not
need retrieval_test / rank_bm25 / numpy installed.

The Proposer (PiCodingAgentProposer) mutates pipeline.json + nodes/*.py +
prompt/*.md to improve mean nDCG@k; the evolution loop is Pareto-frontier EA.
"""
import asyncio
import logging
import os

import yaml

from antomnievo.common.config.config import setup_logging
from antomnievo.dataset.rag_pipeline.rag_pipeline_dataset_loader import load_dataset
from antomnievo.evaluator.rag_pipeline.rag_pipeline_evaluator import RagPipelineEvaluator
from antomnievo.evolution_algorithm.pareto_frontier import (
    ParetoFrontierEvolutionAlgorithm,
)
from antomnievo.model.budget import Budget
from antomnievo.model.candidate_data_schema import CANDIDATE_DATA_SCHEMA
from antomnievo.model.tunable_artifact_defs.rag_pipeline_tunable_artifact_def import (
    RAG_PIPELINE_TUNABLE_ARTIFACT_SCHEMA,
)
from antomnievo.optimizer.rag_pipeline.rag_pipeline_optimizer import (
    RagPipelineOptimizer,
)
from antomnievo.proposer.pi_coding_agent_proposer import PiCodingAgentProposer
from antomnievo.store.candidate_store import LocalCandidateStore
from antomnievo.system.rag_pipeline.rag_pipeline_system import RagPipelineSystem

logger = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────
# retrieval-test hosts generate.py / evaluate.py, the baseline tunable artifacts, AND the
# pre-built MuSiQue dataset (train/val corpus + queries). Its venv (with
# retrieval_test + rank_bm25 + numpy + the API clients) runs the subprocesses.
RETRIEVAL_TEST_DIR = os.path.expanduser("~/work/retrieval-test")
RETRIEVAL_TEST_PYTHON = os.path.join(RETRIEVAL_TEST_DIR, ".venv", "bin", "python")
INITIAL_ARTIFACTS_DIR = os.path.join(RETRIEVAL_TEST_DIR, "specs", "default")
MUSIQUE_DATASET_DIR = os.path.join(RETRIEVAL_TEST_DIR, "datasets", "musique")
TRAIN_SPLIT_DIR = os.path.join(MUSIQUE_DATASET_DIR, "train")
VAL_SPLIT_DIR = os.path.join(MUSIQUE_DATASET_DIR, "val")

_API_KEYS_FILE = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "config", "config.yaml")
)
with open(_API_KEYS_FILE, encoding="utf-8") as _f:
    ANTCHAT_API_KEY = yaml.safe_load(_f)["api_keys"][0]


async def main():
    """Main function."""
    setup_logging()
    logger.info("Starting Retrieval-Pipeline Auto-Optimizer")

    # ── Dataset (pre-built MuSiQue, loaded per split — train and val separate) ─
    # Each instance carries its split's corpus_path; the system/evaluator read
    # it per batch (train queries -> train corpus, val -> val corpus).
    train_dataset = await load_dataset(TRAIN_SPLIT_DIR, max_samples=102)
    val_dataset = await load_dataset(VAL_SPLIT_DIR, max_samples=100)
    logger.info(
        "Dataset: train=%d (corpus=%s), val=%d (corpus=%s)",
        len(train_dataset), train_dataset[0].corpus_path,
        len(val_dataset), val_dataset[0].corpus_path,
    )

    # ── Workspace ────────────────────────────────────────────────────────────
    #from datetime import datetime
    #workspace_dir = os.path.join(os.path.dirname(__file__), "workspace", "rag_pipeline_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    #os.makedirs(workspace_dir, exist_ok=True)
    workspace_dir = '/Users/jacklv/work/antomnievo/antomnievo/example/rag/workspace/rag_pipeline_20260729_210306'
    logger.info("Workspace: %s", workspace_dir)

    # ── Components ───────────────────────────────────────────────────────────
    candidate_store = LocalCandidateStore(workspace_dir, cleanup_unavailable=False)

    evolution_algorithm = ParetoFrontierEvolutionAlgorithm(
        candidate_store=candidate_store, max_candidate_num=3,
    )

    system = RagPipelineSystem(
        retrieval_test_python=RETRIEVAL_TEST_PYTHON,
        retrieval_test_dir=RETRIEVAL_TEST_DIR,
        concurrency=20,
    )

    evaluator = RagPipelineEvaluator(
        retrieval_test_python=RETRIEVAL_TEST_PYTHON,
        retrieval_test_dir=RETRIEVAL_TEST_DIR,
        k=10,
        concurrency=8,
    )

    proposer = PiCodingAgentProposer(
        api_key=ANTCHAT_API_KEY,
        tunable_artifact_schema=RAG_PIPELINE_TUNABLE_ARTIFACT_SCHEMA,
        candidate_store=candidate_store,
        evaluator=evaluator,
        data_schema=CANDIDATE_DATA_SCHEMA,
        model="glm-5.1",
        max_turns=200,
        timeout=3600,
        concurrency=10,
        system=system,
        skip_perfect_score_runs=False,
        last_n_analysis=10,
    )

    # ── Optimizer ────────────────────────────────────────────────────────────
    optimizer = RagPipelineOptimizer(
        system=system,
        proposer=proposer,
        evaluator=evaluator,
        evolution_algorithm=evolution_algorithm,
        candidate_store=candidate_store,
        train_dataset=train_dataset,
        val_dataset=val_dataset,
        batch_size=6,
        budget=Budget(max_iterations=1000),
        num_proposals=2,
        initial_artifacts_dir=INITIAL_ARTIFACTS_DIR,
        max_reflection_iterations=3,
        min_improvement_per_batch=2.0,
    )

    # ── Run ──────────────────────────────────────────────────────────────────
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
