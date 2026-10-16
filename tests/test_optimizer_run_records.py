"""Batch shape errors must be rejected before any run records are written."""

from pathlib import Path

import pytest

from antomnievo.interface.data_inst import DataInst
from antomnievo.model.candidate_data import RunRecord
from antomnievo.model.evaluation_result import EvaluationResult
from antomnievo.model.rollout_result import RolloutResult
from antomnievo.model.system_result import SystemResult
from antomnievo.model.trajectory import Trajectory
from antomnievo.optimizer.optimizer import Optimizer
from antomnievo.store.candidate_store import LocalCandidateStore


@pytest.fixture
def optimizer_and_candidate(tmp_path):
    # Exercise persistence without constructing unrelated runtime components.
    optimizer = Optimizer.__new__(Optimizer)
    optimizer.candidate_store = LocalCandidateStore(str(tmp_path))
    candidate = optimizer.candidate_store.create_root()
    return optimizer, candidate.candidate_id


def _batch(data_count, result_count, eval_count):
    data = [DataInst(id=f"q{i}", query=f"question {i}", golden_answer=f"answer {i}") for i in range(data_count)]
    results = [
        SystemResult(trajectory=Trajectory(), output=RolloutResult(content=f"answer {i}"))
        for i in range(result_count)
    ]
    evals = [
        EvaluationResult(data_id=f"q{i}", metric_name="accuracy", score=0.5, reason=f"reason {i}")
        for i in range(eval_count)
    ]
    return data, results, evals


@pytest.mark.parametrize("split", ["train", "val"])
@pytest.mark.parametrize("counts", [(1, 2, 2), (2, 1, 2), (2, 2, 1), (3, 2, 2), (2, 3, 2), (2, 2, 3), (1, 1, 0)])
def test_mismatched_lengths_fail_before_writing(optimizer_and_candidate, counts, split):
    optimizer, candidate_id = optimizer_and_candidate

    with pytest.raises(ValueError) as exc_info:
        optimizer._save_run_record_list(candidate_id, *_batch(*counts), split=split)

    message = str(exc_info.value)
    assert candidate_id in message
    for name, count in zip(("data_inst_list", "system_result_list", "eval_result_list"), counts, strict=True):
        assert f"{name}={count}" in message
    assert optimizer.candidate_store.get_all_run_data_ids(candidate_id, split=split) == []


@pytest.mark.parametrize("split", ["train", "val"])
def test_matching_batch_persists_every_record(optimizer_and_candidate, split):
    optimizer, candidate_id = optimizer_and_candidate
    data, results, evals = _batch(2, 2, 2)

    optimizer._save_run_record_list(candidate_id, data, results, evals, split=split)

    store = optimizer.candidate_store
    assert store.get_all_run_data_ids(candidate_id, split=split) == ["q0", "q1"]
    for inst, result, evaluation in zip(data, results, evals, strict=True):
        files = store.list_run_files(candidate_id, inst.id, split=split)
        assert len(files) == 1
        record = RunRecord.model_validate_json(Path(files[0]).read_text(encoding="utf-8"))
        assert record.candidate_id == candidate_id
        assert record.data_inst == inst
        assert record.system_result == result
        assert record.evaluation_result == evaluation
    other_split = "val" if split == "train" else "train"
    assert store.get_all_run_data_ids(candidate_id, split=other_split) == []


@pytest.mark.parametrize("split", ["train", "val"])
def test_empty_batch_remains_a_noop(optimizer_and_candidate, split):
    optimizer, candidate_id = optimizer_and_candidate

    optimizer._save_run_record_list(candidate_id, [], [], [], split=split)

    assert optimizer.candidate_store.get_all_run_data_ids(candidate_id, split=split) == []
