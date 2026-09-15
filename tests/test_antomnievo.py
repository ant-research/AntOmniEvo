"""Tests for CandidateStore.retire and cleanup_unavailable behavior."""

import os
import tempfile

import pytest

from antomnievo.interface.candidate_store import CandidateStore
from antomnievo.model.candidate_data import CandidateMeta
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


class TestRejectCandidate:
    def test_cleanup_unavailable_true_deletes(self, store: CandidateStore, root_candidate: CandidateMeta):
        child = store.create_child(root_candidate.candidate_id)
        cid = child.candidate_id
        assert os.path.exists(store.candidate_dir(cid))

        store.cleanup_unavailable = True
        store.retire(cid)
        assert store.get_meta(cid) is None
        assert not os.path.exists(store.candidate_dir(cid))

    def test_cleanup_unavailable_false_marks_unavailable(self, store: CandidateStore, root_candidate: CandidateMeta):
        child = store.create_child(root_candidate.candidate_id)
        cid = child.candidate_id
        store.set_available(cid, True)

        store.cleanup_unavailable = False
        store.retire(cid)
        assert store.get_meta(cid) is not None
        assert os.path.exists(store.candidate_dir(cid))
        assert store.get_meta(cid).state == "unavailable"

    def test_cleanup_unavailable_true_at_init(self, store: CandidateStore, root_candidate: CandidateMeta):
        """When cleanup_unavailable=True, deleting unavailable candidates removes them."""
        child1 = store.create_child(root_candidate.candidate_id)
        child2 = store.create_child(root_candidate.candidate_id)
        store.set_available(child1.candidate_id, False)
        store.set_available(child2.candidate_id, False)

        store.cleanup_unavailable = True
        deleted = store.delete_unavailable_candidates()
        assert len(deleted) == 2
        assert store.get_meta(child1.candidate_id) is None
        assert store.get_meta(child2.candidate_id) is None

    def test_reject_nonexistent_candidate(self, store: CandidateStore, root_candidate: CandidateMeta):
        """Retiring a non-existent candidate should not raise."""
        store.cleanup_unavailable = True
        # Should not raise
        store.retire("nonexistent_id")
