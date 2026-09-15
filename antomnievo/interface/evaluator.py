import asyncio
from abc import ABC, abstractmethod

from antomnievo.interface.data_inst import DataInst
from antomnievo.model.evaluation_result import EvaluationResult
from antomnievo.model.system_result import SystemResult


class Evaluator(ABC):
    """Evaluates system output against criteria.

    Corresponds to: (s, r) ← Evaluator(output, τ, c)

    Supports concurrency control via the `concurrency` parameter, which limits
    how many parallel `evaluate()` calls can execute simultaneously.
    """

    def __init__(self, concurrency: int = 8):
        self.concurrency = concurrency
        self._sem = asyncio.Semaphore(concurrency)

    @property
    def name(self) -> str:
        return self.__class__.__name__

    @abstractmethod
    def scoring_criteria(self) -> str:
        """Return a human-readable description of the scoring criteria.

        This description is injected into the proposer prompt so the proposer
        understands what the evaluator measures and how to optimize for it.
        Should cover: what is scored, the scoring scale, and key rules that
        determine a high vs. low score.
        remain empty if there are no specific criteria or if the proposer should not rely on specific criteria.
        """
        ...

    @abstractmethod
    async def _evaluate(
        self,
        data_inst: DataInst,
        system_result: SystemResult,
    ) -> EvaluationResult:
        """Subclass implements the actual evaluation logic here."""
        ...

    async def evaluate(
        self,
        data_inst: DataInst,
        system_result: SystemResult,
    ) -> EvaluationResult:
        """Evaluate a single system output with concurrency control.

        For batch evaluation, prefer ``evaluate_batch``.
        """
        async with self._sem:
            return await self._evaluate(data_inst, system_result)

    async def evaluate_batch(
        self,
        data_list: list[DataInst],
        system_results: list[SystemResult],
        **kwargs,
    ) -> list[EvaluationResult]:
        """Evaluate multiple system outputs with concurrency control.

        Internally fans out via asyncio.gather; concurrency is capped by the
        semaphore set at construction time.

        Subclasses can accept additional keyword arguments for scenario-specific
        customization (e.g. ``jobs_dir``).
        """
        if len(data_list) != len(system_results):
            raise ValueError(
                f"data_list length ({len(data_list)}) != "
                f"system_results length ({len(system_results)})"
            )
        return list(
            await asyncio.gather(
                *(self.evaluate(d, r) for d, r in zip(data_list, system_results, strict=False))
            )
        )
