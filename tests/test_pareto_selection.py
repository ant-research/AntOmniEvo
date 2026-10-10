"""Parent selection should not sample candidates whose weight is zero."""

import pytest

from antomnievo.evolution_algorithm.pareto_frontier import ParetoFrontierEvolutionAlgorithm
from antomnievo.model.evaluation_result import EvaluationResult
from antomnievo.store.candidate_store import LocalCandidateStore


@pytest.mark.parametrize(
    "scores,expected_indices",
    [([[1.0, 1.0], [0.0, 0.0]], {0}),
     ([[1.0, 0.0], [0.0, 1.0], [0.5, 0.5]], {0, 1}),
     ([[1.0], [1.0]], {0, 1})],
)
def test_select_up_to_num_positive_weight_candidates(tmp_path, scores, expected_indices):
    store = LocalCandidateStore(str(tmp_path))
    candidate_ids = []
    for candidate_scores in scores:
        meta = store.create_root(state="pending")
        candidate_ids.append(meta.candidate_id)
        store.update_summary_scores(meta.candidate_id, [
            EvaluationResult(data_id=str(i), metric_name="test", score=score, reason="test")
            for i, score in enumerate(candidate_scores)
        ])
    algorithm = ParetoFrontierEvolutionAlgorithm(store)

    selected = algorithm.select(num=len(candidate_ids) + 1)

    assert set(selected) == {candidate_ids[i] for i in expected_indices}
    assert len(selected) == len(set(selected))


def test_unscored_candidates_still_use_uniform_sampling(tmp_path):
    store = LocalCandidateStore(str(tmp_path))
    candidate_ids = {store.create_root(state="pending").candidate_id for _ in range(3)}

    selected = ParetoFrontierEvolutionAlgorithm(store).select(num=2)

    assert len(selected) == len(set(selected)) == 2
    assert set(selected) <= candidate_ids
