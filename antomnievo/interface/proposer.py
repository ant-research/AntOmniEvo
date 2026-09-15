from __future__ import annotations

from abc import ABC, abstractmethod

from antomnievo.model.antomnievo_data import MaraChain, ProposalResult


class Proposer(ABC):
    """Generates a new candidate spec by modifying an existing one.

    Pure abstract interface. Implementation details belong in concrete subclasses.
    """

    @property
    def name(self) -> str:
        return self.__class__.__name__

    @abstractmethod
    async def propose(
        self,
        parent_candidate_id: str,
        new_candidate_id: str,
    ) -> ProposalResult:
        """Subclass implements the actual proposal logic here."""
        ...

    @abstractmethod
    async def analyze(
        self,
        parent_candidate_id: str,
        new_candidate_id: str,
    ) -> ProposalResult:
        """Analysis phase only: analyze the parent's unanalyzed runs and write analysis results.

        Public entry point for business callers that want to run the analysis
        phase standalone (without mutating the spec). ``BaseProposer`` provides
        the default implementation.

        Depended on by:
            - ``propose``: runs this as Phase 1 of its two-phase
              (analyze → mutate) flow, then mutates the spec based on the
              analysis results written here.
        """
        ...

    @abstractmethod
    async def reflect(
        self,
        chain: MaraChain,
        new_candidate_id: str,
    ) -> ProposalResult:
        """Reflection variant of propose: produce ``new_candidate_id`` (v_k), learning from every prior failed attempt in the chain.

        ``chain`` is the full mara chain of already-evaluated nodes
        (see ``MaraChain`` for layout):

            chain.root  — root (original parent's evals)
            chain[1]    — v0, the first failed child
            chain[2..]  — v1..v_{k-1}, prior failed reflection attempts

        Reflection depth is ``chain.depth`` (number of failed attempts so far,
        i.e. k). ``chain.last`` is the immediately preceding failed child whose
        spec serves as the starting point for v_k. ``new_candidate_id`` is the
        candidate whose spec will be produced — its spec_dir already contains a
        copy of ``chain.last``'s spec, ready to be edited in place.

        Seeing the FULL per-data score trajectory across the chain — root → v0 →
        v1 → ... → v_{k-1} — lets the agent detect oscillation (a data_id that
        was fixed then broken again), suppression (a fix that always regresses
        another data_id), and exhausted directions (a class of edits the chain
        has already tried and none of them lifted the relevant data_ids).
        """
        ...
