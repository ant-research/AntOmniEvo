"""Scheduler must re-check the token budget after waiting on the slot semaphore.

The budget check sits *after* ``slot_sem.acquire()`` on purpose: with
``num_proposals > 1`` a loop iteration can wait on the semaphore while a
running slot exhausts the budget, and a pre-acquire check would miss that
and open new work anyway. These tests pin that behavior so the check cannot
silently move back above the acquire.
"""

import tempfile
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from antomnievo.evolution_algorithm.pareto_frontier import ParetoFrontierEvolutionAlgorithm
from antomnievo.interface.data_inst import DataInst
from antomnievo.model.antomnievo_data import ProposalResult, RolloutEvalResult
from antomnievo.model.budget import Budget
from antomnievo.model.evaluation_result import EvaluationResult
from antomnievo.model.rollout_result import RolloutResult
from antomnievo.model.system_result import SystemResult
from antomnievo.model.trajectory import Trajectory
from antomnievo.model.usage_stats import UsageStats
from antomnievo.optimizer.optimizer import Optimizer
from antomnievo.store.candidate_store import LocalCandidateStore


def _rollout(system_tokens: int) -> RolloutEvalResult:
    return RolloutEvalResult(
        results=[SystemResult(
            trajectory=Trajectory(), output=RolloutResult(content="answer"),
            usage=UsageStats(input_tokens=system_tokens),
        )],
        evals=[EvaluationResult(data_id="q", metric_name="correctness", score=0.5, reason="test")],
    )


def _optimizer(store: LocalCandidateStore, budget: Budget, **kwargs) -> Optimizer:
    data = [DataInst(id="q", query="question", golden_answer="answer")]
    proposer = SimpleNamespace(
        name="fake proposer",
        propose=AsyncMock(return_value=ProposalResult(success=True)),
        reflect=AsyncMock(return_value=ProposalResult()),
    )
    return Optimizer(
        system=SimpleNamespace(name="fake system"), proposer=proposer,
        evaluator=SimpleNamespace(name="fake evaluator"),
        evolution_algorithm=ParetoFrontierEvolutionAlgorithm(store), candidate_store=store,
        train_dataset=data, val_dataset=data, budget=budget, **kwargs,
    )


def _seed_scored_candidates(store: LocalCandidateStore, count: int) -> None:
    """Create ``count`` extra scored pending candidates so select() has enough to pick."""
    for _ in range(count):
        meta = store.create_root(state="pending")
        store.update_summary_scores(meta.candidate_id, [
            EvaluationResult(data_id="q", metric_name="correctness", score=0.5, reason="test")
        ])


@pytest.mark.asyncio
async def test_waiting_slot_rechecks_budget_after_acquire():
    # 3 selectable candidates (root baseline + 2 seeded), 2 permits: iteration 3
    # blocks on the semaphore while slots A and B run. Each slot accumulates its
    # rollouts' usage (>= 2 x 60 = 120 >= max_tokens) at slot end, so whichever
    # finishes first exhausts the budget; iteration 3 must then abort instead of
    # opening a third slot. Propose count == 2 proves no third slot opened.
    tmp = tempfile.mkdtemp()
    store = LocalCandidateStore(tmp)
    opt = _optimizer(store, Budget(max_tokens=100, max_iterations=10), num_proposals=2)
    opt._run_and_evaluate = AsyncMock(return_value=_rollout(system_tokens=60))
    _seed_scored_candidates(store, count=2)

    await opt.optimize()

    assert opt.proposer.propose.await_count == 2
    assert opt.statistics.current_iteration == 2
