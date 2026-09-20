"""Tests for CandidateStore: lifecycle, analysis, changelog, cleanup."""

import os
import tempfile
import time

import pytest

from antomnievo.interface.candidate_store import CandidateStore
from antomnievo.model.candidate_data import (
    ArtifactAction,
    CandidateMeta,
    ChangeLogEntry,
    RunAnalysis,
)
from antomnievo.model.evaluation_result import EvaluationResult
from antomnievo.model.system_result import SystemResult
from antomnievo.model.trajectory import Span, Trajectory
from antomnievo.store.candidate_store import LocalCandidateStore


@pytest.fixture
def workspace():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield os.path.join(tmpdir, "workspace")


@pytest.fixture
def store(workspace):
    os.makedirs(workspace, exist_ok=True)
    return LocalCandidateStore(workspace)


@pytest.fixture
def root_candidate(store: CandidateStore):
    meta = store.create_root()
    store.set_available(meta.candidate_id, True)
    return meta


class TestCandidateStore:
    def test_create_root(self, store: CandidateStore):
        meta = store.create_root()
        assert meta.candidate_id
        assert meta.generation == 0
        assert meta.parent_id is None
        assert os.path.isdir(meta.artifact_dir)
        assert os.path.isdir(meta.data_dir)

    def test_create_child(self, store: CandidateStore, root_candidate: CandidateMeta):
        child = store.create_child(root_candidate.candidate_id)
        assert child is not None
        assert child.parent_id == root_candidate.candidate_id
        assert child.generation == 1
        assert child.candidate_id in root_candidate.children_ids

    def test_create_child_copies_artifact(self, store: CandidateStore, root_candidate: CandidateMeta):
        parent_file = os.path.join(root_candidate.artifact_dir, "SKILL.md")
        with open(parent_file, "w") as f:
            f.write("# Original artifact")

        child = store.create_child(root_candidate.candidate_id)
        child_file = os.path.join(child.artifact_dir, "SKILL.md")
        assert os.path.exists(child_file)
        with open(child_file) as f:
            assert f.read() == "# Original artifact"

    def test_create_child_copies_changelog(self, store: CandidateStore, root_candidate: CandidateMeta):
        entry = ChangeLogEntry(
            type="feat", subject="initial", body="test body that is long enough to pass validation", diff="test diff", files_modified=["SKILL.md"]
        )
        store.append_changelog(root_candidate.candidate_id, entry)

        child = store.create_child(root_candidate.candidate_id)
        child_changelog = store.read_changelog(child.candidate_id)
        assert len(child_changelog) == 1
        assert child_changelog[0].subject == "initial"

    def test_delete_candidate(self, store: CandidateStore, root_candidate: CandidateMeta):
        child = store.create_child(root_candidate.candidate_id)
        cid = child.candidate_id

        store.delete(cid)
        assert store.get_meta(cid) is None
        assert cid not in store.get_meta(root_candidate.candidate_id).children_ids
        assert not os.path.exists(store.candidate_dir(cid))

    def test_delete_removes_from_parent_children(self, store: CandidateStore, root_candidate: CandidateMeta):
        child1 = store.create_child(root_candidate.candidate_id)
        child2 = store.create_child(root_candidate.candidate_id)
        parent = store.get_meta(root_candidate.candidate_id)
        assert len(parent.children_ids) == 2

        store.delete(child1.candidate_id)
        parent = store.get_meta(root_candidate.candidate_id)
        assert child1.candidate_id not in parent.children_ids
        assert child2.candidate_id in parent.children_ids

    def test_set_available(self, store: CandidateStore, root_candidate: CandidateMeta):
        store.set_available(root_candidate.candidate_id, False)
        meta = store.get_meta(root_candidate.candidate_id)
        assert meta.is_available is False
        store.set_available(root_candidate.candidate_id, True)
        meta = store.get_meta(root_candidate.candidate_id)
        assert meta.is_available is True

    def test_get_available_meta_list(self, store: CandidateStore, root_candidate: CandidateMeta):
        child = store.create_child(root_candidate.candidate_id)
        store.set_available(root_candidate.candidate_id, True)
        store.set_available(child.candidate_id, False)

        available = store.get_available_meta_list()
        ids = [m.candidate_id for m in available]
        assert root_candidate.candidate_id in ids
        assert child.candidate_id not in ids

    def test_delete_unavailable_candidates(self, store: CandidateStore, root_candidate: CandidateMeta):
        child1 = store.create_child(root_candidate.candidate_id)
        child2 = store.create_child(root_candidate.candidate_id)
        store.set_available(root_candidate.candidate_id, True)
        store.set_available(child1.candidate_id, False)
        store.set_available(child2.candidate_id, False)

        deleted = store.delete_unavailable_candidates()
        assert len(deleted) == 2
        assert store.get_meta(child1.candidate_id) is None
        assert store.get_meta(child2.candidate_id) is None
        assert store.get_meta(root_candidate.candidate_id) is not None

    def test_analysis_crud(self, store: CandidateStore, root_candidate: CandidateMeta):
        entry = RunAnalysis(
            data_id="test_001",
            trajectory_analysis=[
                "System failed to decompose the question into sub-questions"
            ],
            actions=[
                ArtifactAction(
                    file="SKILL.md",
                    operation="add",
                    artifact_issue="No decomposition rule in the tunable artifacts",
                    change="Add a decomposition step that breaks the question into sub-questions",
                    resolves=[0],
                )
            ],
        )
        store.update_analysis(root_candidate.candidate_id, entry)

        analyses = list(store._read_analysis_dict_from_disk(root_candidate.candidate_id).values())
        assert len(analyses) == 1
        assert analyses[0].data_id == "test_001"
        assert len(analyses[0].actions) == 1
        assert analyses[0].actions[0].artifact_issue == "No decomposition rule in the tunable artifacts"

    def test_analysis_update_preserves_created_at(self, store: CandidateStore, root_candidate: CandidateMeta):
        entry1 = RunAnalysis(data_id="test_001")
        store.update_analysis(root_candidate.candidate_id, entry1)
        original_created = list(store._read_analysis_dict_from_disk(root_candidate.candidate_id).values())[0].created_at

        time.sleep(0.01)
        entry2 = RunAnalysis(
            data_id="test_001",
            trajectory_analysis=["updated observation"],
            actions=[
                ArtifactAction(
                    file="SKILL.md",
                    operation="modify",
                    artifact_issue="updated tunable artifacts",
                    change="BEFORE:\nold\nAFTER:\nnew",
                    resolves=[0],
                )
            ],
        )
        store.update_analysis(root_candidate.candidate_id, entry2)

        analyses = list(store._read_analysis_dict_from_disk(root_candidate.candidate_id).values())
        assert len(analyses) == 1
        assert analyses[0].trajectory_analysis[0] == "updated observation"
        assert analyses[0].created_at == original_created

    def test_find_unanalyzed_runs(self, store: CandidateStore, root_candidate: CandidateMeta):
        from datetime import datetime

        from antomnievo.interface.data_inst import DataInst
        from antomnievo.model.candidate_data import RunRecord
        from antomnievo.model.rollout_result import RolloutResult

        cid = root_candidate.candidate_id
        assert store.find_unanalyzed_runs(cid) == {}

        record = RunRecord(
            candidate_id=cid,
            timestamp=datetime.now(),
            data_inst=DataInst(id="q1", query="test", golden_answer="answer"),
            system_result=SystemResult(
                trajectory=Trajectory(root_span_list=[]),
                output=RolloutResult(content="out"),
            ),
            evaluation_result=EvaluationResult(data_id="q1", metric_name="atomic_fact", score=0.5, reason="test"),
        )
        store.save_run_record(cid, record)

        unanalyzed = store.find_unanalyzed_runs(cid)
        assert len(unanalyzed) == 1
        assert "q1" in unanalyzed

        analysis = RunAnalysis(data_id="q1")
        store.update_analysis(cid, analysis)
        assert store.find_unanalyzed_runs(cid) == {}

    def test_changelog(self, store: CandidateStore, root_candidate: CandidateMeta):
        cid = root_candidate.candidate_id
        entry1 = ChangeLogEntry(
            type="feat", subject="add rule", body="test body 1 that is long enough to pass validation", diff="diff1", files_modified=["SKILL.md"]
        )
        entry2 = ChangeLogEntry(
            type="fix", subject="fix bug", body="test body 2 that is long enough to pass validation", diff="diff2", files_modified=["SKILL.md"]
        )
        store.append_changelog(cid, entry1)
        store.append_changelog(cid, entry2)

        entries = store.read_changelog(cid)
        assert len(entries) == 2
        assert entries[0].type == "feat"
        assert entries[1].type == "fix"

    def test_save_and_read_trajectory(self, store: CandidateStore, root_candidate: CandidateMeta):
        cid = root_candidate.candidate_id
        child = store.create_child(cid)

        trajectory = Trajectory(
            root_span_list=[
                Span(name="model", span_type="model", input="hello", output="world"),
            ]
        )
        store.save_analysis_trajectory(cid, child.candidate_id, trajectory)
        store.save_propose_trajectory(cid, child.candidate_id, trajectory)

        analysis_dir = store.analysis_trajectory_dir(cid)
        mutation_dir = store.mutation_trajectory_dir(cid)
        assert os.path.exists(os.path.join(analysis_dir, f"{child.candidate_id}.json"))
        assert os.path.exists(os.path.join(mutation_dir, f"{child.candidate_id}.json"))

    def test_update_summary_scores(self, store: CandidateStore, root_candidate: CandidateMeta):
        cid = root_candidate.candidate_id
        evals = [
            EvaluationResult(data_id="q1", metric_name="atomic_fact", score=0.8, reason="good"),
            EvaluationResult(data_id="q2", metric_name="atomic_fact", score=0.4, reason="bad"),
        ]
        store.update_summary_scores(cid, evals)

        summary = store.get_summary(cid)
        assert summary.avg_score == pytest.approx(0.6)
        assert len(summary.score_list) == 2

    def test_get_best_candidate(self, store: CandidateStore, root_candidate: CandidateMeta):
        cid = root_candidate.candidate_id
        store.update_summary_scores(cid, [
            EvaluationResult(data_id="q1", metric_name="atomic_fact", score=0.5, reason=""),
        ])
        store.set_available(cid, True)

        best = store.get_best_candidate()
        assert best is not None
        assert best[1].candidate_id == cid

    def test_statistics_round_trip(self, store: CandidateStore):
        stats = store.get_statistics()
        stats.root_candidate_id = "test_root"
        stats.best_avg_score = 0.75
        store.save_statistics(stats)

        loaded = store.get_statistics()
        assert loaded.root_candidate_id == "test_root"
        assert loaded.best_avg_score == pytest.approx(0.75)


class TestStateAndProgress:
    def test_state_field_round_trip(self, store: CandidateStore, root_candidate: CandidateMeta):
        store.set_state(root_candidate.candidate_id, "evolving")
        meta = store.get_meta(root_candidate.candidate_id)
        assert meta.state == "evolving"
        assert meta.is_available is True  # evolving is also "available" (not unavailable)

        # Reload from disk
        fresh = LocalCandidateStore(store.workspace_dir)
        reloaded = fresh.get_meta(root_candidate.candidate_id)
        assert reloaded.state == "evolving"

    def test_set_state_canonical(self, store: CandidateStore, root_candidate: CandidateMeta):
        cid = root_candidate.candidate_id
        for state in ("pending", "evolving", "unavailable"):
            store.set_state(cid, state)
            assert store.get_meta(cid).state == state

    def test_set_state_missing_id_is_noop(self, store: CandidateStore):
        # Should not raise
        store.set_state("nonexistent_id", "pending")

    def test_set_progress(self, store: CandidateStore, root_candidate: CandidateMeta):
        cid = root_candidate.candidate_id
        store.set_progress(cid, epoch=3, dataset_index=12)
        meta = store.get_meta(cid)
        assert meta.epoch == 3
        assert meta.dataset_index == 12

        fresh = LocalCandidateStore(store.workspace_dir)
        reloaded = fresh.get_meta(cid)
        assert reloaded.epoch == 3
        assert reloaded.dataset_index == 12

    def test_reset_evolving_to_pending(self, store: CandidateStore, root_candidate: CandidateMeta):
        c1 = store.create_child(root_candidate.candidate_id, state="evolving")
        c2 = store.create_child(root_candidate.candidate_id, state="evolving")
        c3 = store.create_child(root_candidate.candidate_id, state="pending")
        c4 = store.create_child(root_candidate.candidate_id, state="unavailable")

        reset_ids = store.reset_evolving_to_pending()
        assert sorted(reset_ids) == sorted([c1.candidate_id, c2.candidate_id])
        assert store.get_meta(c1.candidate_id).state == "pending"
        assert store.get_meta(c2.candidate_id).state == "pending"
        assert store.get_meta(c3.candidate_id).state == "pending"
        assert store.get_meta(c4.candidate_id).state == "unavailable"

    def test_get_pool_by_state(self, store: CandidateStore, root_candidate: CandidateMeta):
        c_pending = store.create_child(root_candidate.candidate_id, state="pending")
        c_evolving = store.create_child(root_candidate.candidate_id, state="evolving")
        c_unavailable = store.create_child(root_candidate.candidate_id, state="unavailable")

        pending_ids = [m.candidate_id for m in store.get_pool_by_state("pending")]
        evolving_ids = [m.candidate_id for m in store.get_pool_by_state("evolving")]
        unavailable_ids = [m.candidate_id for m in store.get_pool_by_state("unavailable")]

        # root_candidate is set pending in the fixture
        assert root_candidate.candidate_id in pending_ids
        assert c_pending.candidate_id in pending_ids
        assert c_evolving.candidate_id in evolving_ids
        assert c_unavailable.candidate_id in unavailable_ids

    def test_get_available_meta_list_is_pending_only(self, store: CandidateStore, root_candidate: CandidateMeta):
        c_evolving = store.create_child(root_candidate.candidate_id, state="evolving")
        c_pending = store.create_child(root_candidate.candidate_id, state="pending")

        ids = [m.candidate_id for m in store.get_available_meta_list()]
        assert root_candidate.candidate_id in ids
        assert c_pending.candidate_id in ids
        assert c_evolving.candidate_id not in ids  # evolving is NOT selectable

    def test_legacy_is_available_migration(self, workspace):
        """A meta.json written with the old `is_available` schema should round-trip into `state`."""
        os.makedirs(workspace, exist_ok=True)
        store = LocalCandidateStore(workspace)
        root = store.create_root(state="pending")

        # Hand-write a legacy meta.json (no `state`, has `is_available`)
        cid = "legacy_cid_test1"
        cand_data_dir = os.path.join(store.candidate_dir(cid), "data")
        os.makedirs(cand_data_dir, exist_ok=True)
        os.makedirs(store.artifact_dir(cid), exist_ok=True)
        legacy = (
            '{"candidate_id": "%s", "artifact_dir": "", "data_dir": "", '
            '"parent_id": null, "children_ids": [], "is_available": true, '
            '"generation": 0, "reflection_depth": 0}'
        ) % cid
        with open(os.path.join(cand_data_dir, "meta.json"), "w") as f:
            f.write(legacy)

        # Reload — the validator should translate the legacy field.
        fresh = LocalCandidateStore(workspace)
        meta = fresh.get_meta(cid)
        assert meta is not None
        assert meta.state == "pending"
        assert meta.is_available is True

        # Also check is_available=False
        cid2 = "legacy_cid_test2"
        cand_data_dir2 = os.path.join(store.candidate_dir(cid2), "data")
        os.makedirs(cand_data_dir2, exist_ok=True)
        os.makedirs(store.artifact_dir(cid2), exist_ok=True)
        with open(os.path.join(cand_data_dir2, "meta.json"), "w") as f:
            f.write(legacy.replace('"is_available": true', '"is_available": false').replace(cid, cid2))

        fresh2 = LocalCandidateStore(workspace)
        meta2 = fresh2.get_meta(cid2)
        assert meta2.state == "unavailable"
        assert meta2.is_available is False

    def test_retire_with_cleanup_false_marks_unavailable(self, workspace):
        os.makedirs(workspace, exist_ok=True)
        store = LocalCandidateStore(workspace, cleanup_unavailable=False)
        root = store.create_root(state="pending")
        child = store.create_child(root.candidate_id, state="pending")

        store.retire(child.candidate_id)
        meta = store.get_meta(child.candidate_id)
        assert meta is not None
        assert meta.state == "unavailable"
        assert meta.is_available is False

    def test_retire_with_cleanup_true_deletes(self, workspace):
        os.makedirs(workspace, exist_ok=True)
        store = LocalCandidateStore(workspace, cleanup_unavailable=True)
        root = store.create_root(state="pending")
        child = store.create_child(root.candidate_id, state="pending")

        store.retire(child.candidate_id)
        assert store.get_meta(child.candidate_id) is None
        assert not os.path.exists(store.candidate_dir(child.candidate_id))
