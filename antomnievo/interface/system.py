from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from antomnievo.interface.data_inst import DataInst
    from antomnievo.model.candidate_data import CandidateMeta
    from antomnievo.model.system_result import SystemResult


class System(ABC):
    """Generic system interface.

    Takes a candidate meta and a data instance, returns trajectory + output.
    Corresponds to: τ, output ← System(o, B_t)

    Supports concurrency control via the `concurrency` parameter, which limits
    how many parallel `run()` calls can execute simultaneously.
    """

    def __init__(self, concurrency: int = 8):
        self.concurrency = concurrency
        self._sem = asyncio.Semaphore(concurrency)

    @property
    def name(self) -> str:
        return self.__class__.__name__

    def system_description(self) -> str:
        """Return a human-readable description of the system's behavior.

        This description is injected into the analysis prompt so the analyzer
        understands what the system does, how it processes inputs, and what
        kind of outputs it produces. Helps the analyzer correctly attribute
        issues to the tunable artifacts vs. the system itself.

        Returns empty string by default; subclasses may override.
        """
        return ""

    @abstractmethod
    async def _run(self, candidate_meta: CandidateMeta, data_inst: DataInst) -> SystemResult:
        """Subclass implements the actual system run logic here."""
        ...

    async def run(self, candidate_meta: CandidateMeta, data_inst: DataInst) -> SystemResult:
        """Run the system on a single data instance with concurrency control.

        For batch execution, prefer ``run_batch``.
        """
        async with self._sem:
            return await self._run(candidate_meta, data_inst)

    async def run_batch(
        self,
        candidate_meta: CandidateMeta,
        data_list: list[DataInst],
        **kwargs,
    ) -> list[SystemResult]:
        """Run the system on multiple data instances with concurrency control.

        Internally fans out via asyncio.gather; concurrency is capped by the
        semaphore set at construction time.

        Subclasses can accept additional keyword arguments for scenario-specific
        customization (e.g. ``job_name``, ``dataset_dir``).
        """
        return list(
            await asyncio.gather(*(self.run(candidate_meta, d) for d in data_list))
        )
