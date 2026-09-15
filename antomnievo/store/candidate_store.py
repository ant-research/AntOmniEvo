import json
import logging
import os
import shutil
import uuid
from datetime import datetime

from antomnievo.interface.candidate_store import CandidateStore
from antomnievo.model.antomnievo_data import IterationRecord
from antomnievo.model.candidate_data import (
    CandidateMeta,
    CandidateState,
    CandidateSummary,
    ChangeLogEntry,
    RunAnalysis,
    RunRecord,
    RunSplit,
    ScoreEntry,
)
from antomnievo.model.evaluation_result import EvaluationResult
from antomnievo.model.statistics import OptimizationStatistics
from antomnievo.model.trajectory import Trajectory

logger = logging.getLogger(__name__)

_SYSTEM_RUN_DIR = "system_run"
_VAL_SYSTEM_RUN_DIR = "val_system_run"
_PROPOSER_RUN_DIR = "proposer_run"


def _gen_candidate_id() -> str:
    return uuid.uuid4().hex[:12]


class LocalCandidateStore(CandidateStore):
    """Filesystem-based storage for candidate specs and data, with in-memory cache.

    Concrete implementation of the :class:`antomnievo.interface.candidate_store.CandidateStore`
    contract, persisting to a local directory tree. See that interface's docstring
    for the contracts a different (e.g. remote / distributed) implementation must honor.

    Reads hit memory first; writes go to both memory and disk.

    Layout:
        workspace_dir/
        └── candidates/
            └── {candidate_id}/
                ├── spec/
                └── data/
                    ├── meta.json
                    ├── changelog.jsonl
                    ├── summary.json
                    ├── system_run/{data_id}/run_{timestamp}.json
                    ├── val_system_run/{data_id}/run_{timestamp}.json
                    └── proposer_run/
                        ├── analysis/
                        │   ├── trajectory/
                        │   │   └── {child_id}.json
                        │   └── result/
                        │       └── {data_id}.json
                        └── mutation/
                            └── {child_id}.json
    """

    def __init__(self, workspace_dir: str, cleanup_unavailable: bool = True):
        # 基类 __init__ 存 workspace_dir + cleanup_unavailable(optimizer 经
        # CandidateStore 接口回读的两个字段);此处再按需 hydrate 本地种群缓存。
        super().__init__(workspace_dir, cleanup_unavailable)
        self.candidates_dir = os.path.join(workspace_dir, "candidates")
        os.makedirs(self.candidates_dir, exist_ok=True)

        self._meta_cache: dict[str, CandidateMeta] = {}
        self._summary_cache: dict[str, CandidateSummary] = {}
        self._statistics_cache: OptimizationStatistics = OptimizationStatistics()
        self._load_all_from_disk()

    def _load_all_from_disk(self) -> None:
        for cid in self._list_candidate_dirs():
            meta = self._read_meta_from_disk(cid)
            if meta:
                self._meta_cache[cid] = meta
            summary = self._read_summary_from_disk(cid)
            if summary:
                self._summary_cache[cid] = summary
        self._statistics_cache = self._read_statistics_from_disk() or OptimizationStatistics()

    def _list_candidate_dirs(self) -> list[str]:
        if not os.path.isdir(self.candidates_dir):
            return []
        return [
            d
            for d in os.listdir(self.candidates_dir)
            if os.path.isdir(os.path.join(self.candidates_dir, d))
        ]

    def candidate_dir(self, candidate_id: str) -> str:
        return os.path.join(self.candidates_dir, candidate_id)

    def spec_dir(self, candidate_id: str) -> str:
        return os.path.join(self.candidate_dir(candidate_id), "spec")

    def data_dir(self, candidate_id: str) -> str:
        return os.path.join(self.candidate_dir(candidate_id), "data")

    def system_run_dir(self, candidate_id: str) -> str:
        return os.path.join(self.data_dir(candidate_id), _SYSTEM_RUN_DIR)

    def val_system_run_dir(self, candidate_id: str) -> str:
        return os.path.join(self.data_dir(candidate_id), _VAL_SYSTEM_RUN_DIR)

    def proposer_run_dir(self, candidate_id: str) -> str:
        return os.path.join(self.data_dir(candidate_id), _PROPOSER_RUN_DIR)

    def analysis_trajectory_dir(self, candidate_id: str) -> str:
        return os.path.join(self.proposer_run_dir(candidate_id), "analysis", "trajectory")

    def analysis_result_dir(self, candidate_id: str) -> str:
        return os.path.join(self.proposer_run_dir(candidate_id), "analysis", "result")

    def analysis_result_path(self, candidate_id: str, data_id: str) -> str:
        return os.path.join(self.analysis_result_dir(candidate_id), f"{data_id}.json")

    def mutation_trajectory_dir(self, candidate_id: str) -> str:
        return os.path.join(self.proposer_run_dir(candidate_id), "mutation")

    def run_data_dir(self, candidate_id: str, data_id: str) -> str:
        return os.path.join(self.system_run_dir(candidate_id), data_id)

    def val_run_data_dir(self, candidate_id: str, data_id: str) -> str:
        return os.path.join(self.val_system_run_dir(candidate_id), data_id)

    def exists(self, candidate_id: str) -> bool:
        return candidate_id in self._meta_cache

    # ---- Disk I/O (private) ----

    def _read_meta_from_disk(self, candidate_id: str) -> CandidateMeta | None:
        path = os.path.join(self.data_dir(candidate_id), "meta.json")
        if not os.path.exists(path):
            return None
        try:
            with open(path, encoding="utf-8") as f:
                meta = CandidateMeta.model_validate_json(f.read())
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"Failed to read meta.json for {candidate_id}: {e}")
            return None
        # spec_dir / data_dir are deliberately not persisted (they're a pure
        # function of candidates_dir + candidate_id); re-derive on load so the
        # in-memory object still carries them for consumers that read
        # ``candidate_meta.spec_dir`` / ``.data_dir``.
        meta.spec_dir = self.spec_dir(candidate_id)
        meta.data_dir = self.data_dir(candidate_id)
        return meta

    def _write_meta_to_disk(self, candidate_id: str, meta: CandidateMeta) -> None:
        path = os.path.join(self.data_dir(candidate_id), "meta.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            # spec_dir / data_dir are not persisted — re-derived on load.
            f.write(meta.model_dump_json(indent=2, exclude={"spec_dir", "data_dir"}))

    def _read_summary_from_disk(self, candidate_id: str) -> CandidateSummary | None:
        path = os.path.join(self.data_dir(candidate_id), "summary.json")
        if not os.path.exists(path):
            return None
        try:
            with open(path, encoding="utf-8") as f:
                return CandidateSummary.model_validate_json(f.read())
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"Failed to read summary.json for {candidate_id}: {e}")
            return None

    def _write_summary_to_disk(self, candidate_id: str, summary: CandidateSummary) -> None:
        path = os.path.join(self.data_dir(candidate_id), "summary.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write(summary.model_dump_json(indent=2))

    # ---- Candidate lifecycle ----

    def _init_candidate_data_dirs(self, candidate_id: str) -> None:
        os.makedirs(self.data_dir(candidate_id), exist_ok=True)
        os.makedirs(self.system_run_dir(candidate_id), exist_ok=True)
        os.makedirs(self.val_system_run_dir(candidate_id), exist_ok=True)
        os.makedirs(self.analysis_trajectory_dir(candidate_id), exist_ok=True)
        os.makedirs(self.analysis_result_dir(candidate_id), exist_ok=True)
        os.makedirs(self.mutation_trajectory_dir(candidate_id), exist_ok=True)

    def create_root(self, state: CandidateState = "unavailable", initial_spec_dir: str | None = None) -> CandidateMeta:
        candidate_id = _gen_candidate_id()
        if initial_spec_dir:
            shutil.copytree(initial_spec_dir, self.spec_dir(candidate_id))
        else:
            os.makedirs(self.spec_dir(candidate_id), exist_ok=True)
        self._init_candidate_data_dirs(candidate_id)

        meta = CandidateMeta(
            candidate_id=candidate_id,
            spec_dir=self.spec_dir(candidate_id),
            data_dir=self.data_dir(candidate_id),
            created_at=datetime.now(),
            generation=0,
            state=state,
        )
        self.save_meta(candidate_id, meta)
        summary = CandidateSummary(candidate_id=candidate_id)
        self.save_summary(candidate_id, summary)

        return meta

    def create_child(
        self,
        parent_id: str,
        state: CandidateState = "unavailable",
        reflection_depth: int = 0,
        epoch: int | None = None,
        dataset_index: int | None = None,
    ) -> CandidateMeta | None:
        if not self.exists(parent_id):
            return None

        child_id = _gen_candidate_id()
        shutil.copytree(self.spec_dir(parent_id), self.spec_dir(child_id))
        self._init_candidate_data_dirs(child_id)

        parent_changelog = self.changelog_path(parent_id)
        if os.path.exists(parent_changelog):
            shutil.copy2(parent_changelog, os.path.join(self.data_dir(child_id), "changelog.jsonl"))

        parent_meta = self.get_meta(parent_id)
        child_meta = CandidateMeta(
            candidate_id=child_id,
            spec_dir=self.spec_dir(child_id),
            data_dir=self.data_dir(child_id),
            parent_id=parent_id,
            created_at=datetime.now(),
            generation=parent_meta.generation + 1,
            state=state,
            reflection_depth=reflection_depth,
            epoch=parent_meta.epoch if epoch is None else epoch,
            dataset_index=parent_meta.dataset_index if dataset_index is None else dataset_index,
        )
        self.save_meta(child_id, child_meta)
        self.save_summary(child_id, CandidateSummary(candidate_id=child_id))

        parent_meta.children_ids.append(child_id)
        self.save_meta(parent_id, parent_meta)

        return child_meta

    def delete(self, candidate_id: str) -> None:
        meta = self.get_meta(candidate_id)
        if meta is None:
            return

        self._meta_cache.pop(candidate_id, None)
        self._summary_cache.pop(candidate_id, None)

        # Detach from parent: otherwise the parent's children_ids keeps a
        # dangling reference to a now-deleted candidate.
        if meta.parent_id is not None:
            parent = self.get_meta(meta.parent_id)
            if parent is not None and candidate_id in parent.children_ids:
                parent.children_ids = [cid for cid in parent.children_ids if cid != candidate_id]
                self.save_meta(parent.candidate_id, parent)

        candidate_dir = self.candidate_dir(candidate_id)
        if os.path.isdir(candidate_dir):
            shutil.rmtree(candidate_dir)

    def retire(self, candidate_id: str) -> None:
        if self.cleanup_unavailable:
            self.delete(candidate_id)
        else:
            self.set_state(candidate_id, "unavailable")

    # ---- Meta ----

    def get_meta(self, candidate_id: str) -> CandidateMeta | None:
        return self._meta_cache.get(candidate_id)

    def save_meta(self, candidate_id: str, meta: CandidateMeta) -> None:
        self._meta_cache[candidate_id] = meta
        if os.path.isdir(self.candidate_dir(candidate_id)):
            self._write_meta_to_disk(candidate_id, meta)

    def set_state(self, candidate_id: str, state: CandidateState) -> None:
        meta = self.get_meta(candidate_id)
        if meta is None:
            return
        if meta.state == state:
            return
        meta.state = state
        self.save_meta(candidate_id, meta)

    def set_available(self, candidate_id: str, is_available: bool) -> None:
        self.set_state(candidate_id, "pending" if is_available else "unavailable")

    def set_progress(self, candidate_id: str, epoch: int, dataset_index: int) -> None:
        meta = self.get_meta(candidate_id)
        if meta is None:
            return
        meta.epoch = epoch
        meta.dataset_index = dataset_index
        self.save_meta(candidate_id, meta)

    # ---- Summary ----

    def get_summary(self, candidate_id: str) -> CandidateSummary | None:
        cached = self._summary_cache.get(candidate_id)
        if cached is not None:
            return cached
        if not self.exists(candidate_id):
            return None
        return CandidateSummary(candidate_id=candidate_id)

    def save_summary(self, candidate_id: str, summary: CandidateSummary) -> None:
        self._summary_cache[candidate_id] = summary
        if os.path.isdir(self.candidate_dir(candidate_id)):
            self._write_summary_to_disk(candidate_id, summary)

    def update_summary_scores(self, candidate_id: str, eval_results: list[EvaluationResult]) -> None:
        summary = self.get_summary(candidate_id)
        if summary is None:
            return
        summary.score_list = [ScoreEntry(data_id=e.data_id, score=e.score) for e in eval_results]
        scores = [e.score for e in eval_results]
        summary.avg_score = sum(scores) / len(scores) if scores else 0.0
        summary.last_evaluated_at = datetime.now()
        self.save_summary(candidate_id, summary)

    # ---- Analysis ----

    @staticmethod
    def _analysis_result_filename(entry: RunAnalysis) -> str:
        return f"{entry.data_id}.json"

    def _read_analysis_dict_from_disk(self, candidate_id: str) -> dict[str, RunAnalysis]:
        """Read all analysis result files as a dict keyed by data_id."""
        if not self.exists(candidate_id):
            return {}
        result_dir = self.analysis_result_dir(candidate_id)
        if not os.path.isdir(result_dir):
            return {}

        result: dict[str, RunAnalysis] = {}
        for fname in os.listdir(result_dir):
            if not fname.endswith(".json"):
                continue
            fpath = os.path.join(result_dir, fname)
            try:
                with open(fpath, encoding="utf-8") as f:
                    raw = f.read()
                data = json.loads(raw)
                entry = RunAnalysis.model_validate(data)
                result[entry.data_id] = entry
            except json.JSONDecodeError:
                # json.load failed — try brace-tracking extraction as fallback
                entry = self._try_repair_analysis_json(raw, fpath)
                if entry:
                    result[entry.data_id] = entry
            except Exception as e:
                logger.warning(f"Failed to parse analysis result {fpath}: {e}")
        return result

    @staticmethod
    def _try_repair_analysis_json(raw: str, fpath: str) -> RunAnalysis | None:
        """Attempt to extract a valid RunAnalysis from malformed JSON text."""
        from antomnievo.common.utils.analysis_parser import (
            _extract_complete_json,
        )

        # Strategy 1: brace-tracking extraction for {"data_id": ...}
        start = raw.find('{"data_id"')
        if start == -1:
            start = raw.find('{\n  "data_id"')
        if start >= 0:
            complete = _extract_complete_json(raw, start)
            if complete:
                try:
                    data = json.loads(complete)
                    entry = RunAnalysis.model_validate(data)
                    # Overwrite the file with valid JSON for future reads
                    with open(fpath, "w", encoding="utf-8") as f:
                        f.write(entry.model_dump_json(indent=2))
                    logger.info(f"Repaired analysis result {fpath} via brace-tracking extraction")
                    return entry
                except Exception:
                    pass
        # Strategy 2: try markdown code fence extraction
        import re

        fence_match = re.search(r"```(?:json)?\s*\n(.*?)\n\s*```", raw, re.DOTALL)
        if fence_match:
            try:
                data = json.loads(fence_match.group(1).strip())
                entry = RunAnalysis.model_validate(data)
                with open(fpath, "w", encoding="utf-8") as f:
                    f.write(entry.model_dump_json(indent=2))
                logger.info(f"Repaired analysis result {fpath} via markdown fence extraction")
                return entry
            except Exception:
                pass
        logger.warning(f"Failed to repair analysis result {fpath}")
        return None

    def read_analysis_content(self, candidate_id: str, data_id: str) -> str | None:
        path = self.analysis_result_path(candidate_id, data_id)
        if not os.path.isfile(path):
            return None
        with open(path, encoding="utf-8") as f:
            return f.read()

    def read_all_analysis_json_content(
        self, candidate_id: str, max_chars: int = 100_000, last_n: int | None = None
    ) -> str:
        analysis_dict = self._read_analysis_dict_from_disk(candidate_id)
        if not analysis_dict:
            return "(no analysis results available)"

        # Filter out entries with no actions (they provide no actionable info to the proposer),
        # then sort by updated_at desc (newer first).
        entries = sorted(
            [e for e in analysis_dict.values() if e.actions],
            key=lambda e: e.updated_at,
            reverse=True,
        )

        if last_n is not None:
            entries = entries[:last_n]

        included: dict[str, object] = {}
        current_size = 0
        for entry in entries:
            serialized = json.dumps(
                json.loads(entry.model_dump_json()), indent=2, ensure_ascii=False
            )
            if current_size + len(serialized) > max_chars and included:
                break
            included[entry.data_id] = json.loads(entry.model_dump_json())
            current_size += len(serialized)

        if not included:
            return "(no analysis results available)"

        return json.dumps(included, indent=2, ensure_ascii=False)

    def update_analysis(self, candidate_id: str, entry: RunAnalysis) -> None:
        if not self.exists(candidate_id):
            return
        existing = self._read_analysis_dict_from_disk(candidate_id).get(entry.data_id)
        if existing:
            entry.created_at = existing.created_at
        result_dir = self.analysis_result_dir(candidate_id)
        os.makedirs(result_dir, exist_ok=True)
        path = os.path.join(result_dir, self._analysis_result_filename(entry))
        with open(path, "w", encoding="utf-8") as f:
            f.write(entry.model_dump_json(indent=2))

    def _split_run_dir(self, candidate_id: str, split: RunSplit) -> str:
        if split == "val":
            return self.val_system_run_dir(candidate_id)
        return self.system_run_dir(candidate_id)

    def _split_run_data_dir(self, candidate_id: str, data_id: str, split: RunSplit) -> str:
        if split == "val":
            return self.val_run_data_dir(candidate_id, data_id)
        return self.run_data_dir(candidate_id, data_id)

    def get_all_run_data_ids(self, candidate_id: str, split: RunSplit = "train") -> list[str]:
        run_dir = self._split_run_dir(candidate_id, split)
        if not os.path.isdir(run_dir):
            return []
        return sorted(
            entry for entry in os.listdir(run_dir)
            if os.path.isdir(os.path.join(run_dir, entry))
        )

    def find_unanalyzed_runs(self, candidate_id: str) -> dict[str, list[str]]:
        run_dir = self.system_run_dir(candidate_id)
        if not os.path.isdir(run_dir):
            return {}

        # Find the latest mtime across all analysis result files
        result_dir = self.analysis_result_dir(candidate_id)
        since_ts = 0.0
        if os.path.isdir(result_dir):
            for fname in os.listdir(result_dir):
                if fname.endswith(".json"):
                    since_ts = max(since_ts, os.path.getmtime(os.path.join(result_dir, fname)))

        result: dict[str, list[str]] = {}
        for data_id in os.listdir(run_dir):
            data_dir = os.path.join(run_dir, data_id)
            if not os.path.isdir(data_dir):
                continue
            for f in os.listdir(data_dir):
                if f.startswith("run_") and f.endswith(".json"):
                    fpath = os.path.join(data_dir, f)
                    if os.path.getmtime(fpath) > since_ts:
                        result.setdefault(data_id, []).append(f)
        return result

    # ---- Run records ----

    def list_run_files(self, candidate_id: str, data_id: str, split: RunSplit = "train") -> list[str]:
        data_dir = self._split_run_data_dir(candidate_id, data_id, split)
        if not os.path.isdir(data_dir):
            return []
        return sorted(
            os.path.join(data_dir, f)
            for f in os.listdir(data_dir)
            if f.startswith("run_") and f.endswith(".json")
        )

    def latest_run_file(self, candidate_id: str, data_id: str, split: RunSplit = "train") -> str | None:
        files = self.list_run_files(candidate_id, data_id, split)
        return files[-1] if files else None

    def run_file_path(self, candidate_id: str, data_id: str, run_name: str, split: RunSplit = "train") -> str:
        return os.path.join(self._split_run_data_dir(candidate_id, data_id, split), run_name)

    def get_run_score(self, candidate_id: str, data_id: str, run_name: str, split: RunSplit = "train") -> float | None:
        fpath = self.run_file_path(candidate_id, data_id, run_name, split)
        try:
            with open(fpath, encoding="utf-8") as f:
                data = json.loads(f.read())
            return data.get("evaluation_result", {}).get("score")
        except Exception:
            return None

    def save_run_record(self, candidate_id: str, record: RunRecord, split: RunSplit = "train") -> None:
        if not self.exists(candidate_id):
            return
        run_dir = self._split_run_data_dir(candidate_id, record.data_inst.id, split)
        os.makedirs(run_dir, exist_ok=True)
        ts = record.timestamp.strftime("%Y%m%d_%H%M%S")
        path = os.path.join(run_dir, f"run_{ts}.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write(record.model_dump_json(indent=2, serialize_as_any=True))

    # ---- Proposer trajectories ----

    def save_analysis_trajectory(self, parent_candidate_id: str, new_candidate_id: str, trajectory: Trajectory) -> None:
        if not self.exists(parent_candidate_id):
            return
        analysis_dir = self.analysis_trajectory_dir(parent_candidate_id)
        os.makedirs(analysis_dir, exist_ok=True)
        path = os.path.join(analysis_dir, f"{new_candidate_id}.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write(trajectory.to_json())
        logger.info(f"Saved analysis trajectory for candidate {parent_candidate_id} at {path}")

    def save_propose_trajectory(self, parent_candidate_id: str, new_candidate_id: str, trajectory: Trajectory) -> None:
        if not self.exists(parent_candidate_id):
            return
        mutation_dir = self.mutation_trajectory_dir(parent_candidate_id)
        os.makedirs(mutation_dir, exist_ok=True)
        path = os.path.join(mutation_dir, f"{new_candidate_id}.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write(trajectory.to_json())
        logger.info(f"Saved propose trajectory for candidate {parent_candidate_id} at {path}")
    # ---- Changelog ----

    def changelog_path(self, candidate_id: str) -> str:
        return os.path.join(self.data_dir(candidate_id), "changelog.jsonl")

    def append_changelog(self, candidate_id: str, entry: ChangeLogEntry) -> None:
        if not self.exists(candidate_id):
            return
        path = self.changelog_path(candidate_id)
        with open(path, "a", encoding="utf-8") as f:
            f.write(entry.model_dump_json() + "\n")

    def read_changelog(self, candidate_id: str) -> list[ChangeLogEntry] | None:
        if not self.exists(candidate_id):
            return []
        from antomnievo.model.candidate_data import ChangeLogEntry
        path = self.changelog_path(candidate_id)
        if not os.path.exists(path):
            return []
        entries: list[ChangeLogEntry] = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(ChangeLogEntry.model_validate_json(line))
                except Exception as e:
                    # Although the proposer agent has a changelog format validation step,
                    # it cannot guarantee 100% correct format (e.g. agent may produce
                    # invalid JSON or miss required fields). Return None so the caller
                    # knows the changelog needs repair.
                    logger.warning(f"Malformed changelog entry for {candidate_id}: {e}")
                    return None
        return entries

    # ---- Population queries ----

    def get_all_candidate_id_list(self) -> list[str]:
        return list(self._meta_cache.keys())

    def get_best_candidate(self) -> tuple[CandidateMeta, CandidateSummary] | None:
        """Return (meta, summary) of the best *alive* candidate by ``avg_score``.

        Only ``pending``/``evolving`` candidates are considered — the live,
        validated population. Retired/unavailable candidates (never-validated
        newborns plus eliminated/dominated/rejected ones) are excluded: their
        scores are stale or empty and must never be reported as "best".

        Tiebreak is (avg_score, generation, created_at) descending, so an
        all-zero tie resolves deterministically to the deepest-evolved
        candidate instead of dict-iteration order. Returns None when no alive
        candidate has been evaluated yet (the caller then keeps the prior best).
        """
        best_meta = None
        best_summary = None
        best_key: tuple | None = None
        for meta in self.get_pool_by_state("pending", "evolving"):
            summary = self._summary_cache.get(meta.candidate_id)
            if not summary:
                continue
            key = (summary.avg_score, meta.generation, meta.created_at)
            if best_key is None or key > best_key:
                best_key = key
                best_meta = meta
                best_summary = summary
        if best_meta and best_summary:
            return best_meta, best_summary
        return None

    def get_available_meta_list(self) -> list[CandidateMeta]:
        return self.get_pool_by_state("pending")

    def get_pool_by_state(self, *states: "CandidateState") -> list[CandidateMeta]:
        return [m for m in self._meta_cache.values() if m.state in states]

    def reset_evolving_to_pending(self) -> list[str]:
        reset_ids: list[str] = []
        for cid, meta in self._meta_cache.items():
            if meta.state == "evolving":
                meta.state = "pending"
                self.save_meta(cid, meta)
                reset_ids.append(cid)
        return reset_ids

    def delete_unavailable_candidates(self) -> list[str]:
        unavailable_ids = [cid for cid, meta in self._meta_cache.items() if meta.state == "unavailable"]
        if not unavailable_ids:
            return []
        logger.info(f"Deleting {len(unavailable_ids)} unavailable candidate(s): {unavailable_ids}")
        for cid in unavailable_ids:
            self.delete(cid)
        return unavailable_ids

    # ---- Statistics ----

    def _statistics_dir(self) -> str:
        return os.path.join(self.workspace_dir, "logs")

    def _read_statistics_from_disk(self) -> OptimizationStatistics | None:
        path = os.path.join(self._statistics_dir(), "statistics.json")
        if not os.path.exists(path):
            return None
        try:
            with open(path, encoding="utf-8") as f:
                return OptimizationStatistics.model_validate_json(f.read())
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"Failed to read statistics.json: {e}")
            return None

    def save_statistics(self, statistics: OptimizationStatistics) -> None:
        self._statistics_cache = statistics
        stats_dir = self._statistics_dir()
        os.makedirs(stats_dir, exist_ok=True)
        path = os.path.join(stats_dir, "statistics.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write(statistics.model_dump_json(indent=2))

    def get_statistics(self) -> OptimizationStatistics:
        return self._statistics_cache

    # ---- Iteration records (JSONL) ----

    def _iteration_records_path(self) -> str:
        return os.path.join(self._statistics_dir(), "iteration_records.jsonl")

    def append_iteration_record(self, record: IterationRecord) -> None:
        path = self._iteration_records_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(record.model_dump_json() + "\n")

    def read_iteration_records(self) -> list[IterationRecord]:
        path = self._iteration_records_path()
        if not os.path.exists(path):
            return []
        records: list[IterationRecord] = []
        with open(path, encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(IterationRecord.model_validate_json(line))
                except Exception as e:
                    logger.warning(f"Skipping malformed iteration record at line {line_no}: {e}")
        return records

    # ---- Parameters log (JSONL) ----

    def _parameters_path(self) -> str:
        return os.path.join(self._statistics_dir(), "parameters.jsonl")

    def append_parameters(self, params: dict) -> None:
        record = {**params}
        path = self._parameters_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
