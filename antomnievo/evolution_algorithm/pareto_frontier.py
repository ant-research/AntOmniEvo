import logging
import random

from antomnievo.interface.candidate_store import CandidateStore
from antomnievo.interface.evolution_algorithm import EvolutionAlgorithm

logger = logging.getLogger(__name__)

SCORE_EPS = 1e-8

class ParetoFrontierEvolutionAlgorithm(EvolutionAlgorithm):
    """EA implementation using Pareto frontier + top-n greedy.

    """

    def __init__(self, candidate_store: CandidateStore, max_candidate_num: int = 10):
        super().__init__(candidate_store)
        # add top-n greedy
        self.max_candidate_num = max_candidate_num

    def select(self, num: int = 1) -> list[str]:
        """Select candidates to improve.

        Args:
            num: Number of candidates to select.

        Returns:
            List of unique candidate_ids, length <= num. Empty when nothing is eligible —
            the scheduler treats `[]` as "no work right now, wait for in-flight slots".
        """
        store = self.candidate_store

        # Only pending candidates are selectable. 'evolving' parents are already busy,
        # 'unavailable' children are either pre-validation or retired.
        available_meta_list = store.get_pool_by_state("pending")
        if not available_meta_list:
            return []

        available_id_list = [m.candidate_id for m in available_meta_list]
        all_summaries = {cid: store.get_summary(cid) for cid in available_id_list}

        score_lists = {
            cid: [s.score for s in all_summaries[cid].score_list]
            for cid in available_id_list
            if all_summaries[cid].score_list
        }
        if not score_lists:
            # Candidates exist but none have been scored yet — pick uniformly at random.
            k = min(num, len(available_id_list))
            return random.sample(available_id_list, k)

        max_score_counts = self._get_max_score_count_dict(score_lists)
        k = min(num, len(max_score_counts))
        selected: list[str] = []
        remaining = dict(max_score_counts)  # copy for mutation during selection

        for _ in range(k):
            if not remaining:
                break
            cid = random.choices(list(remaining.keys()), weights=list(remaining.values()), k=1)[0]
            selected.append(cid)
            del remaining[cid]

        for cid in selected:
            avg = all_summaries[cid].avg_score
            logger.info(
                f"selected={cid} (avg_score={avg:.4f}, max_score_dims={max_score_counts[cid]}, all_count={len(available_meta_list)})"
            )
        return selected

    def eliminate(self) -> list[tuple[str, str]]:
        store = self.candidate_store
        # Both pending and evolving participate in comparison, but only pending
        # candidates can be retired. This lets a weak evolving candidate finish
        # its run and then get eliminated on the next call, while strong pending
        # candidates are not blocked by the max_candidate_num cap.
        all_available_meta_list = store.get_pool_by_state("pending", "evolving")
        if len(all_available_meta_list) <= 1:
            return []

        # Sort by generation desc (tiebreak: created_at desc) so deeper-evolved
        # candidates dominate first — Phase 1 uses `>=`, so when two candidates
        # tie on every score the one ordered first survives.
        all_available_meta_list.sort(key=lambda m: (m.generation, m.created_at), reverse=True)
        all_id_list = [m.candidate_id for m in all_available_meta_list]
        metas = {m.candidate_id: m for m in all_available_meta_list}
        summaries = {cid: store.get_summary(cid) for cid in all_id_list}

        alive: dict[str, bool] = {cid: True for cid in all_id_list}
        reasons: dict[str, str] = {}

        evolving_ids = {m.candidate_id for m in all_available_meta_list if m.state == "evolving"}

        # Phase 1: Pareto dominance elimination — all candidates (including
        # evolving) participate in domination checks normally.
        for cid_a in all_id_list:
            if not alive[cid_a]:
                continue
            for cid_b in all_id_list:
                if cid_a == cid_b or not alive[cid_b]:
                    continue
                if self._is_dominated(
                    [s.score for s in summaries[cid_a].score_list],
                    [s.score for s in summaries[cid_b].score_list],
                ):
                    alive[cid_b] = False
                    reasons[cid_b] = f"dominated by {cid_a}"

        # Phase 2: Top-N truncation, keep top N by avg_score when the number of frontiers is too large.
        # Tiebreak: prefer larger generation, then newer created_at — same rule as Phase 1's pre-sort.
        frontier = [cid for cid in all_id_list if alive[cid]]
        if len(frontier) > self.max_candidate_num:
            frontier.sort(
                key=lambda c: (summaries[c].avg_score, metas[c].generation, metas[c].created_at),
                reverse=True,
            )
            for cid in frontier[self.max_candidate_num:]:
                alive[cid] = False
                reasons[cid] = f"top-{self.max_candidate_num} cutoff (avg_score={summaries[cid].avg_score:.4f})"

        # Only retire pending candidates — evolving ones will be retired on a
        # future call after they finish and transition back to pending.
        eliminated: list[tuple[str, str]] = []
        for cid, is_alive in alive.items():
            if not is_alive and cid not in evolving_ids and store.exists(cid):
                reason = reasons[cid]
                logger.info(f"eliminate {cid} ({reason})")
                store.retire(cid)
                eliminated.append((cid, reason))

        return eliminated

    @staticmethod
    def _is_dominated(scores_a: list[float], scores_b: list[float]) -> bool:
        """Check if a dominates b (a >= b on all dimensions)."""
        return all(a + SCORE_EPS >= b for a, b in zip(scores_a, scores_b, strict=False))

    @staticmethod
    def _get_max_score_count_dict(
        score_list_dict: dict[str, list[float]],
    ) -> dict[str, int]:
        """Compute max-score count for each candidate.

        Args:
            score_list_dict: Dict mapping candidate_id to scores list.

        Returns:
            Dict mapping candidate_id to count, where count is the number of
            dimensions on which this candidate achieves the highest score.
        """
        if not score_list_dict:
            return {}
        num_dims = len(next(iter(score_list_dict.values())))
        dim_maxes = [
            max(scores[dim_idx] for scores in score_list_dict.values())
            for dim_idx in range(num_dims)
        ]
        result: dict[str, int] = {}
        for cid, scores in score_list_dict.items():
            result[cid] = sum(
                1 for dim_idx in range(num_dims)
                if scores[dim_idx] + SCORE_EPS >= dim_maxes[dim_idx]
            )
        return result
