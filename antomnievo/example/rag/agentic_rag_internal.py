#!/usr/bin/env python
"""
V2 Optimizer entry point

Uses ReactAgentSystem + AtomicFactEvaluator + ClaudeCodeProposer + ParetoFrontierEA
Based on v1's langgraph_react_optimizer.py, but using v2's modular framework
"""
import asyncio
import logging
import os

import httpx
import yaml

from antomnievo.common.config.config import setup_logging
from antomnievo.common.theta_llm import ThetaLLM
from antomnievo.common.tool.rag.rag_search import build_rag_tool
from antomnievo.dataset.musique.musique_dataset_loader import load_dataset
from antomnievo.evaluator.rag.atomic_fact_evaluator import AtomicFactEvaluator
from antomnievo.evolution_algorithm.pareto_frontier import ParetoFrontierEvolutionAlgorithm
from antomnievo.model.budget import Budget
from antomnievo.model.candidate_data_schema import CANDIDATE_DATA_SCHEMA
from antomnievo.model.spec_defs.agent_skill_spec_def import AGENT_SKILL_SPEC_SCHEMA
from antomnievo.optimizer.optimizer import Optimizer
from antomnievo.proposer.claude_code_proposer import ClaudeCodeProposer
from antomnievo.store.candidate_store import LocalCandidateStore
from antomnievo.system.langgraph.react_agent_system import ReactAgentSystem

# antchat creds (api_keys + base_url) live in <repo>/config/config.yaml (gitignored).
_CONFIG_FILE = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "config", "config.yaml")
)
with open(_CONFIG_FILE, encoding="utf-8") as _f:
    _antchat_cfg = yaml.safe_load(_f)
ANTCHAT_API_KEYS = _antchat_cfg["api_keys"]
ANTCHAT_BASE_URL = _antchat_cfg["base_url"]

logger = logging.getLogger(__name__)

async def main():
    """Main function"""
    setup_logging()
    logger.info("Starting V2 Optimizer")
    # ---- HTTP Client ----
    timeout = httpx.Timeout(1200.0, connect=1200.0, read=1200.0, write=1200.0, pool=100.0)
    limits = httpx.Limits(max_keepalive_connections=50, max_connections=200)

    # ---- LLM ----
    http_client = httpx.Client(
        timeout=timeout,
        limits=limits,
        follow_redirects=True,
    )
    async_http_client = httpx.AsyncClient(
        timeout=timeout,
        limits=limits,
        follow_redirects=True,
    )

    task_llm = ThetaLLM(
        model="Kimi-K2.5",
        api_key=ANTCHAT_API_KEYS[0],
        base_url=ANTCHAT_BASE_URL,
        temperature=1,
        max_retries=10,
        http_client=http_client,
        http_async_client=async_http_client,
        request_timeout=1200,
    )

    # ---- RAG Tool ----
    rag_search_tool = build_rag_tool(
        tenant="duanyuedekongjian_3d6c",
        library_id_list=[68600736],
    )

    # ---- Dataset ----
    '''
    dataset_path = "/Users/jacklv/work/files/rag-dataset/musique/data/filtered/musique_full_v1.0_train_4hop_300.jsonl"
    data = await load_dataset(dataset_path, max_samples=300, shuffle=False)

    split_idx = int(len(data) * 0.8)
    train_dataset = data[:split_idx]
    val_dataset = data[split_idx:]
    logger.info(f"Dataset split: train={len(train_dataset)}, val={len(val_dataset)}")
    '''
    train_dataset_path = "/Users/jacklv/work/files/rag-dataset/musique/data/filtered/musique_full_v1.0_train_4hop_300.jsonl"
    train_dataset = await load_dataset(train_dataset_path, max_samples=300, shuffle=True)
    val_dataset_path = "/Users/jacklv/work/writingspace/musique_dev_100.jsonl"
    val_dataset = await load_dataset(val_dataset_path, max_samples=100, shuffle=False)

    # ---- Initial Prompt (same as v1) ----
    initial_prompt = """你是一个智能知识库问答助手。你绝对不能使用自己的知识来回答问题，所有的答案必须基于你从知识库中检索到的信息。
你的任务是准确回答用户的问题，确保答案基于知识库中的信息。"""  # noqa: RUF001

    # ---- Workspace ----
    from datetime import datetime
    workspace_dir = os.path.join(os.path.dirname(__file__), "workspace", datetime.now().strftime("%Y%m%d_%H%M%S"))
    #workspace_dir = '/Users/jacklv/work/agenticapp/python/packages/evolution/src/optimization/demo/v2/example/workspace/20260517_224801'
    #os.makedirs(workspace_dir, exist_ok=True)
    logger.info(f"Workspace: {workspace_dir}")

    # ---- Components ----
    candidate_store = LocalCandidateStore(workspace_dir)

    evolution_algorithm = ParetoFrontierEvolutionAlgorithm(
        candidate_store=candidate_store, max_candidate_num=5
    )

    system = ReactAgentSystem(
        system_prompt=initial_prompt,
        llm=task_llm,
        tools=[rag_search_tool],
        max_assistant_turns=30,
        concurrency=25,
    )

    evaluator = AtomicFactEvaluator(
        concurrency=16
    )

    proposer = ClaudeCodeProposer(
        api_key=ANTCHAT_API_KEYS[0],
        spec_schema=AGENT_SKILL_SPEC_SCHEMA,
        candidate_store=candidate_store,
        evaluator=evaluator,
        data_schema=CANDIDATE_DATA_SCHEMA,
        claude_code_path="claude",
        model="kimi-k2.5",
        max_turns=200,
        timeout=3600,
        concurrency=20,
        max_context_tokens=170000,
        autocompact_pct=80,
    )

    # ---- Optimizer ----
    optimizer = Optimizer(
        system=system,
        proposer=proposer,
        evaluator=evaluator,
        evolution_algorithm=evolution_algorithm,
        candidate_store=candidate_store,
        train_dataset=train_dataset,
        val_dataset=val_dataset,
        batch_size=10,
        budget=Budget(max_iterations=1000),
        num_proposals=2,
    )

    # ---- Run ----
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
