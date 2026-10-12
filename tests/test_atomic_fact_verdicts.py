"""Invalid judge output must not improve an agent's factuality score."""

from unittest.mock import AsyncMock, Mock

import pytest


@pytest.fixture(params=["atomic_fact", "atomic_fact_evaluator"])
def atomic_fact(request):
    return pytest.importorskip(f"antomnievo.evaluator.rag.{request.param}")


@pytest.mark.parametrize(
    ("content", "score"),
    [
        ("", 0.0),
        ("I cannot determine whether the answer is correct.", 0.0),
        ("The candidate is not CORRECT.", 0.0),
        ("<judgement>CORRECT", 0.0),
        ("CORRECT", 1.0),
        ("The facts match.\nCORRECT", 1.0),
        ("INCORRECT", 0.0),
        ("Matches. <judgement>CORRECT</judgement>", 1.0),
        ("Wrong fact. <judgement>INCORRECT</judgement>", 0.0),
    ],
)
def test_short_verdict_requires_an_explicit_judgement(atomic_fact, content, score):
    metric = atomic_fact.AtomicFact(llm=Mock())
    assert metric._parse_verdict(content).score == score


def test_binary_verdicts_are_not_scored_by_string_truthiness(atomic_fact):
    metric = atomic_fact.AtomicFact(llm=Mock())
    verdicts = [{"verdict": value} for value in (0, "0", False, "unknown", 2, 1, "1", True)]
    assert metric._calculate_average_precision(verdicts) == 3 / 8


@pytest.mark.asyncio
async def test_unknown_short_judgement_has_no_correctness_credit(atomic_fact, monkeypatch):
    judge = AsyncMock(return_value="Unable to evaluate this response.")
    monkeypatch.setattr(atomic_fact, "areq_llm", judge)
    metric = atomic_fact.AtomicFact(llm=Mock())
    result = await metric.do_score("What is the capital of France?", "London", "Paris")
    assert result.score == 0.0
    judge.assert_awaited_once()


@pytest.mark.asyncio
async def test_long_answer_uses_binary_verdict_values(atomic_fact, monkeypatch):
    monkeypatch.setattr(
        atomic_fact,
        "areq_llm",
        AsyncMock(return_value='{"verification": [{"verdict": "0"}, {"verdict": "1"}]}'),
    )
    metric = atomic_fact.AtomicFact(llm=Mock())
    monkeypatch.setattr(metric, "_create_simplified_statements", Mock(return_value=["fact A", "fact B"]))
    result = await metric.do_score("question", "answer", "long reference " * 40)
    assert result.score == 0.5
