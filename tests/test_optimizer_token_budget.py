"""Token budgets include unsuccessful proposals and every evaluation phase."""

import asyncio
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


def rollout(score=0.4, system_tokens=0, eval_tokens=0):
    return RolloutEvalResult(
        results=[SystemResult(
            trajectory=Trajectory(), output=RolloutResult(content="answer"),
            usage=UsageStats(input_tokens=system_tokens),
        )],
        evals=[EvaluationResult(
            data_id="q", metric_name="correctness", score=score, reason="test",
            usage=UsageStats(output_tokens=eval_tokens),
        )],
    )


def optimizer(tmp_path, budget, **kwargs):
    store = LocalCandidateStore(str(tmp_path))
    data = [DataInst(id="q", query="question", golden_answer="answer")]
    proposer = SimpleNamespace(
        name="fake proposer", propose=AsyncMock(return_value=ProposalResult(success=False)),
        reflect=AsyncMock(return_value=ProposalResult()),
    )
    return Optimizer(
        system=SimpleNamespace(name="fake system"), proposer=proposer,
        evaluator=SimpleNamespace(name="fake evaluator"),
        evolution_algorithm=ParetoFrontierEvolutionAlgorithm(store), candidate_store=store,
        train_dataset=data, val_dataset=data, budget=budget, **kwargs,
    )


@pytest.mark.asyncio
async def test_baseline_usage_can_exhaust_budget_before_first_proposal(tmp_path):
    opt = optimizer(tmp_path, Budget(max_tokens=100, max_iterations=3))
    opt._run_and_evaluate = AsyncMock(return_value=rollout(system_tokens=70, eval_tokens=30))

    await opt.optimize()

    assert opt.statistics.current_iteration == 0
    assert opt.statistics.system_usage.input_tokens == 70
    assert opt.statistics.eval_usage.output_tokens == 30
    opt.proposer.propose.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_proposal_exhausts_budget_while_scheduler_waits_for_slot(tmp_path):
    opt = optimizer(tmp_path, Budget(max_tokens=100, max_iterations=3))
    opt._run_and_evaluate = AsyncMock(return_value=rollout())

    async def fail_after_using_tokens(parent_id, new_id):
        await asyncio.sleep(0)
        return ProposalResult(success=False, stats=UsageStats(input_tokens=60, output_tokens=40))

    opt.proposer.propose.side_effect = fail_after_using_tokens

    await opt.optimize()

    assert opt.statistics.current_iteration == 1
    opt.proposer.propose.assert_awaited_once()
    assert opt.statistics.proposer_usage.input_tokens == 60
    assert opt.statistics.proposer_usage.output_tokens == 40


@pytest.mark.asyncio
async def test_reflection_and_validation_usage_count_once(tmp_path):
    opt = optimizer(tmp_path, Budget(max_iterations=1), max_reflection_iterations=1)
    # Baseline, parent batch, unsuccessful child, reflection child, validation.
    opt._run_and_evaluate = AsyncMock(
        side_effect=[rollout(score, system_tokens=3, eval_tokens=2) for score in (0.4, 0.4, 0.3, 0.8, 0.8)]
    )
    opt.proposer.propose.return_value = ProposalResult(stats=UsageStats(input_tokens=7))
    opt.proposer.reflect.return_value = ProposalResult(stats=UsageStats(input_tokens=11))

    await opt.optimize()

    assert opt._run_and_evaluate.await_count == 5
    assert opt.statistics.system_usage.input_tokens == 15
    assert opt.statistics.eval_usage.output_tokens == 10
    assert opt.statistics.proposer_usage.input_tokens == 18
    assert opt.statistics.best_avg_score == 0.8


@pytest.mark.asyncio
async def test_reflection_usage_survives_later_evaluation_failure(tmp_path):
    opt = optimizer(tmp_path, Budget(max_iterations=1), max_reflection_iterations=1)
    opt._run_and_evaluate = AsyncMock(side_effect=[
        rollout(0.4, system_tokens=3), rollout(0.4, system_tokens=3),
        rollout(0.3, system_tokens=3), RuntimeError("evaluation failed"),
    ])
    opt.proposer.propose.return_value = ProposalResult(stats=UsageStats(input_tokens=7))
    opt.proposer.reflect.return_value = ProposalResult(stats=UsageStats(input_tokens=11))

    await opt.optimize()

    assert opt.statistics.system_usage.input_tokens == 9
    assert opt.statistics.proposer_usage.input_tokens == 18
