import json
import logging
import re
from dataclasses import dataclass

from langchain_openai import ChatOpenAI

from antomnievo.common.theta_llm import areq_llm, req_llm
from antomnievo.evaluator.rag.prompts import (
    ANSWER_RESPONSE_VERDICT_PROMPT,
    ATOMIC_FACT_PROMPT,
    STATEMENT_GENERATOR_PROMPT,
)
from antomnievo.interface.data_inst import DataInst
from antomnievo.interface.evaluator import Evaluator
from antomnievo.model.evaluation_result import EvaluationResult
from antomnievo.model.system_result import SystemResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Scoring criteria
# ---------------------------------------------------------------------------

_ATOMIC_FACT_SCORING_CRITERIA = """\
Fact-point correctness: the ground truth answer is decomposed into discrete factual points, \
and the score is the fraction of points correctly addressed by the system output.
- Score range: 0.0 to 1.0. All points correct → 1.0; some correct → proportional partial credit; none → 0.0.
- Each factual point is checked by an LLM judge against the system output; \
score = (correctly addressed points) / (total points).
- Empty system output or empty ground truth → 0.0."""

# ---------------------------------------------------------------------------
# AtomicFactResult
# ---------------------------------------------------------------------------


@dataclass
class AtomicFactResult:
    """Result from AtomicFact scoring."""

    score: float
    detail: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _segment(text: str) -> list[str]:
    """Simple word segmentation: split on whitespace and CJK characters."""
    tokens: list[str] = []
    for token in re.findall(r"[一-鿿]|[a-zA-Z0-9]+|[^\s一-鿿]", text):
        token = token.strip()
        if token:
            tokens.append(token)
    return tokens


def _load_json(text: str | None) -> dict | list | None:
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return json.loads(text.replace("\n", "\\n"))


# ---------------------------------------------------------------------------
# AtomicFact
# ---------------------------------------------------------------------------


class AtomicFact:
    """Evaluates factual correctness of generated answers against ground truth.

    For short ground-truth answers (<=400 chars), first tries word-bag overlap;
    if that fails, falls back to an LLM judge. For longer answers, uses the
    statement decomposition + verification approach.
    """

    def __init__(self, model: str = "kimi-k2.5", llm: ChatOpenAI | None = None):
        from antomnievo.common.theta_llm import ThetaLLM

        self.model_name = model
        self.llm = llm or ThetaLLM(model=model)

    def _string_judge(self, true_answer: str, real_answer: str) -> AtomicFactResult | None:
        """Word-bag overlap check for short answers."""
        gt_tokens = set(_segment(true_answer.strip().lower()))
        ans_tokens = set(_segment(real_answer.strip().lower()))
        common = gt_tokens & ans_tokens
        if len(gt_tokens) > 0 and len(common) / max(1.0, len(gt_tokens)) > 0.8:
            return AtomicFactResult(score=1.0, detail="word-bag overlap > 0.8")
        return None

    def _parse_verdict(self, content: str) -> AtomicFactResult:
        """Parse LLM judge output with <judgement> tags."""
        if "<judgement>" in content and "</judgement>" in content:
            start = content.find("<judgement>") + len("<judgement>")
            end = content.find("</judgement>")
            judgement = content[start:end].strip()
            reasoning = content[: content.find("<judgement>")].strip()
        else:
            reasoning = content
            judgement = "INCORRECT" if "INCORRECT" in content else "CORRECT"
        score = 1 if judgement == "CORRECT" else 0
        return AtomicFactResult(score=score, detail=reasoning)

    def _calculate_average_precision(self, verdicts: list[dict]) -> float:
        scores = [1 if v.get("verdict") else 0 for v in verdicts]
        return sum(scores) / len(scores) if scores else 0.0

    async def do_score(self, query: str, real_answer: str, true_answer: str) -> AtomicFactResult:
        """Score a single (query, real_answer, true_answer) triple."""
        if not real_answer:
            return AtomicFactResult(score=0.0, detail="real_answer is empty")
        if not true_answer:
            return AtomicFactResult(score=0.0, detail="true_answer is empty")

        # Short answer: word-bag overlap first, then LLM judge
        if len(true_answer) <= 400:
            result = self._string_judge(true_answer, real_answer)
            if result:
                return result

            prompt_kwargs = {
                "question": query,
                "ground_truth_answer": true_answer,
                "gen_answer": real_answer,
            }
            content = await areq_llm(self.llm, ANSWER_RESPONSE_VERDICT_PROMPT, prompt_kwargs)
            return self._parse_verdict(content)
        else:
            logger.info(f"true answer too long ({len(true_answer)} > 400), using statement decomposition")

        # Long answer: statement decomposition + verification
        statements = self._create_simplified_statements(query, true_answer)
        if not statements:
            return AtomicFactResult(score=0.0, detail="failed to decompose ground truth")

        prompt_kwargs = {
            "user_input": query,
            "reference": json.dumps(statements, ensure_ascii=False),
            "response": real_answer,
        }
        content = await areq_llm(self.llm, ATOMIC_FACT_PROMPT, prompt_kwargs)
        prediction = _load_json(content) or {}
        verdicts = prediction.get("verification", [])
        if not verdicts:
            return AtomicFactResult(score=0.0, detail="no verification results from LLM")
        score = self._calculate_average_precision(verdicts)
        return AtomicFactResult(score=score, detail=json.dumps(verdicts, ensure_ascii=False))

    def _create_simplified_statements(self, question: str, text: str) -> list[str]:
        """Decompose ground truth into atomic statements via LLM."""
        prompt_kwargs = {"user_input": question, "response": text}
        result = req_llm(self.llm, STATEMENT_GENERATOR_PROMPT, prompt_kwargs)
        parsed = _load_json(result) or {}
        return parsed.get("statements", [])


# ---------------------------------------------------------------------------
# AtomicFactEvaluator
# ---------------------------------------------------------------------------


class AtomicFactEvaluator(Evaluator):
    """Evaluator implementation using the AtomicFact metric.

    Compares system output against the ground truth label using
    word-bag overlap + LLM-based judgement.
    """

    def __init__(self, model: str = "kimi-k2.5", concurrency: int = 16):
        super().__init__(concurrency=concurrency)
        self.metric = AtomicFact(model=model)

    def scoring_criteria(self) -> str:
        return _ATOMIC_FACT_SCORING_CRITERIA

    async def _evaluate(
        self,
        data_inst: DataInst,
        system_result: SystemResult,
    ) -> EvaluationResult:
        try:
            result = await self.metric.do_score(
                query=data_inst.query,
                real_answer=system_result.output.content,
                true_answer=data_inst.golden_answer,
            )
            return EvaluationResult(
                data_id=data_inst.id,
                metric_name="AtomicFactCorrectness",
                score=result.score,
                reason=result.detail or "")
        except Exception as e:
            logger.error(f"AtomicFactEvaluator failed for data_id={data_inst.id}: {e}")
            return EvaluationResult(
                data_id=data_inst.id,
                metric_name="AtomicFactCorrectness",
                score=0.0,
                reason=f"Evaluation failed: {e}")
