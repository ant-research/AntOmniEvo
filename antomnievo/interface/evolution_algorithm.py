from __future__ import annotations

from abc import ABC, abstractmethod

from antomnievo.interface.candidate_store import CandidateStore


class EvolutionAlgorithm(ABC):
    """Evolutionary algorithm for candidate population management.

    Holds a CandidateStore for population state. Other modules may also
    access the same store directly — the store is shared infrastructure,
    not private to the EA.
    """

    def __init__(self, candidate_store: CandidateStore):
        self.candidate_store = candidate_store

    @property
    def name(self) -> str:
        return self.__class__.__name__

    @abstractmethod
    def select(self, num: int = 1) -> list[str]:
        """Select candidate_ids from the current population for improvement.

        Args:
            num: Number of candidates to select.

        Returns:
            List of candidate_ids, length <= num. Empty if no candidate is currently
            eligible — the scheduler treats `[]` as "no work right now, wait for
            in-flight slots".
        """
        ...

    @abstractmethod
    def eliminate(self) -> list[tuple[str, str]]:
        """Eliminate weak candidates from the population.

        Synchronous. Callers are responsible for serializing concurrent invocations
        (e.g. behind an external lock) when running multiple evolution slots in
        parallel — the EA itself does NOT lock.

        Returns:
            List of (candidate_id, reason) for each eliminated candidate.
        """
        ...
