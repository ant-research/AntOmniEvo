from __future__ import annotations

from abc import ABC, abstractmethod

from antomnievo.model.antomnievo_data import IterationRecord
from antomnievo.model.candidate_data import (
    CandidateMeta,
    CandidateState,
    CandidateSummary,
    ChangeLogEntry,
    RunAnalysis,
    RunRecord,
    RunSplit,
)
from antomnievo.model.evaluation_result import EvaluationResult
from antomnievo.model.statistics import OptimizationStatistics
from antomnievo.model.trajectory import Trajectory

# Sentinel returned by ``read_all_analysis_json_content`` when no usable
# analysis results exist (nothing on disk, or every entry has empty actions).
# Callers can compare against this to fail fast instead of proposing on an
# empty evidence base.
NO_ANALYSIS_RESULTS = "(no analysis results available)"


class CandidateStore(ABC):
    """Abstract storage contract for optimization candidate persistence.

    The concrete ``LocalCandidateStore`` (``antomnievo/store/candidate_store.py``)
    persists everything to a local filesystem directory tree. This interface
    exists so a future implementation can back the same surface by a remote /
    distributed store (object storage, database, shared filesystem, …) without
    changing any caller — ``optimizer`` / ``proposer`` / ``system`` /
    ``evolution_algorithm`` program against this interface.

    Implementation contracts a distributed backend MUST honor
    ---------------------------------------------------------
    These follow from how callers use the store today; a remote implementation
    that violates them breaks the optimization loop in ways the callers cannot
    detect:

    1. **``artifact_dir`` / ``data_dir`` MUST return real, locally-writable
       directories.** They are passed as ``cwd`` to proposer-agent subprocesses
       (pi / claude code) which edit files in place, as ``--artifact-dir`` /
       ``--skill-dir`` to system subprocesses (tbtest generate, appworld, …)
       which mount them into containers, and to in-process code that ``open()``s
       them. A remote backend cannot hand out a remote URI here — it must
       materialize the tree to a local path on demand and sync changes back
       after the subprocess exits. Callers treat these paths as a mutable
       working directory, not a key.

    2. **mtime-equivalent ordering.** ``find_unanalyzed_runs`` computes which
       run records are newer than the most recent analysis result, using file
       modification timestamps. A remote backend must expose a last-modified
       timestamp (or equivalent monotonic ordering) per object so this
       freshness-diff semantics keeps working.

    3. **Append semantics + concurrent writers.** ``changelog.jsonl``, the
       analysis-result files, and the tunable-artifact tree are written by **external CLI
       subprocesses** (``append-changelog``, ``validate-analysis``, the
       proposer agent), not solely by this object's methods. A remote backend
       must support safe append (and tolerate concurrent writers from agent
       sandboxes) for the JSONL streams and atomic overwrite for the JSON blobs.

    4. **Directory-tree enumeration.** Several methods enumerate "files under a
       prefix and distinguish files from sub-dirs" (e.g. listing run files per
       data_id). A remote backend needs prefix listing + object-type
       discrimination, not just key-value get/put.

    Constructors take a storage root (a local path for the FS impl; a URI /
    bucket / connection for remote impls) plus implementation-specific options.
    The base :meth:`__init__` is concrete (not abstract): it stores the two
    cross-impl knobs every store carries — ``workspace_dir`` (the storage-root
    identifier callers read back via ``candidate_store.workspace_dir``) and
    ``cleanup_unavailable`` (the retire policy callers read via
    ``candidate_store.cleanup_unavailable``). Implementations extend
    construction by calling ``super().__init__(...)`` and then hydrating their
    own state (e.g. ``LocalCandidateStore`` loads the population cache from
    disk). Other impls may accept extra kwargs in addition to these two.
    """

    # -- construction ---------------------------------------------------------

    def __init__(self, workspace_dir: str, cleanup_unavailable: bool = True) -> None:
        """Set up storage rooted at ``workspace_dir``.

        **Default implementation** — stores the two cross-impl configuration
        knobs so callers that program against this interface can read them
        back without reaching into a concrete subclass:

        - ``self.workspace_dir`` — the storage-root identifier (a local path
          for the FS impl; a URI/bucket prefix for remote impls). Recorded
          into launch logs, etc.
        - ``self.cleanup_unavailable`` — the retire policy. If True,
          :meth:`retire` physically deletes a candidate; if False, it only
          flips state to ``"unavailable"`` and keeps the data for debugging.
          Callers (e.g. startup recovery) branch on this to decide whether
          to purge physically-retired candidates.

        Subclasses MUST call ``super().__init__(workspace_dir, cleanup_unavailable)``
        first, then do their own hydration (``LocalCandidateStore`` hydrates
        the in-memory population cache from disk here). Remote impls may
        reinterpret ``workspace_dir`` (e.g. as a bucket prefix) and accept
        extra kwargs.

        Args:
            workspace_dir: Storage root (local dir for the FS impl; URI/prefix
                for remote impls).
            cleanup_unavailable: If True, ``retire`` physically deletes a
                candidate; if False, it only flips state to ``"unavailable"``
                and keeps the data for debugging.
        """
        self.workspace_dir = workspace_dir
        self.cleanup_unavailable = cleanup_unavailable

    # -- path helpers (return STRINGS; artifact_dir/data_dir see contract #1) ----

    @abstractmethod
    def candidate_dir(self, candidate_id: str) -> str:
        """Absolute path/key of a candidate's root (tunable artifacts + data live under it).

        Args:
            candidate_id: The 12-hex candidate id.
        """

    @abstractmethod
    def artifact_dir(self, candidate_id: str) -> str:
        """Path/key of the candidate's tunable-artifact tree.

        MUST be a real, locally-writable directory (contract #1): it is passed
        as ``cwd`` to proposer-agent subprocesses and as ``--artifact-dir`` /
        ``--skill-dir`` to system subprocesses. Remote impls must materialize
        it on demand.

        Args:
            candidate_id: The 12-hex candidate id.
        """

    @abstractmethod
    def data_dir(self, candidate_id: str) -> str:
        """Path/key of the candidate's data dir (run records, analysis, logs).

        Like ``artifact_dir`` this may be passed as ``cwd`` to the analysis agent,
        and external CLIs write into ``analysis/result/`` and
        ``changelog.jsonl`` here — so it must be locally writable (contract #1)
        and tolerate append-style concurrent writers (contract #3).

        Args:
            candidate_id: The 12-hex candidate id.
        """

    @abstractmethod
    def system_run_dir(self, candidate_id: str) -> str:
        """Path/key of the directory holding train-split run records.

        Args:
            candidate_id: The 12-hex candidate id.
        """

    @abstractmethod
    def val_system_run_dir(self, candidate_id: str) -> str:
        """Path/key of the directory holding val-split run records.

        Args:
            candidate_id: The 12-hex candidate id.
        """

    @abstractmethod
    def proposer_run_dir(self, candidate_id: str) -> str:
        """Path/key of the proposer-run directory (analysis + mutation trees).

        Args:
            candidate_id: The 12-hex candidate id.
        """

    @abstractmethod
    def analysis_trajectory_dir(self, candidate_id: str) -> str:
        """Path/key of the dir holding per-child analysis-trajectory JSON files.

        Args:
            candidate_id: The 12-hex candidate id.
        """

    @abstractmethod
    def analysis_result_dir(self, candidate_id: str) -> str:
        """Path/key of the dir holding per-data_id analysis-result JSON files.

        These files are written by the proposer agent / ``validate-analysis``
        CLI, not solely by this store — respect contract #3 (concurrent writers).

        Args:
            candidate_id: The 12-hex candidate id.
        """

    @abstractmethod
    def analysis_result_path(self, candidate_id: str, data_id: str) -> str:
        """Full path/key of one analysis-result file for a (candidate, data_id).

        Args:
            candidate_id: The 12-hex candidate id.
            data_id: The data instance id this analysis concerns.
        """

    @abstractmethod
    def mutation_trajectory_dir(self, candidate_id: str) -> str:
        """Path/key of the dir holding per-child mutation-trajectory JSON files.

        Args:
            candidate_id: The 12-hex candidate id.
        """

    @abstractmethod
    def run_data_dir(self, candidate_id: str, data_id: str) -> str:
        """Path/key of a candidate's train-split run-records subdir for one data_id.

        Args:
            candidate_id: The 12-hex candidate id.
            data_id: The data instance id whose run records to locate.
        """

    @abstractmethod
    def val_run_data_dir(self, candidate_id: str, data_id: str) -> str:
        """Path/key of a candidate's val-split run-records subdir for one data_id.

        Args:
            candidate_id: The 12-hex candidate id.
            data_id: The data instance id whose run records to locate.
        """

    # -- candidate lifecycle --------------------------------------------------

    @abstractmethod
    def create_root(
        self, state: CandidateState = "unavailable", initial_artifacts_dir: str | None = None
    ) -> CandidateMeta:
        """Create the root (generation-0) candidate and return its meta.

        Seeds the artifact tree from ``initial_artifacts_dir`` (copytree / remote copy).
        A remote impl must materialize an initially-writable tunable-artifact dir here
        (contract #1).

        Args:
            state: Initial ``CandidateState`` (default ``"unavailable"``).
            initial_artifacts_dir: Local source artifact dir to copy in. If None, an
                empty tunable-artifact dir is created.

        Returns:
            The new root candidate's ``CandidateMeta``.
        """

    @abstractmethod
    def create_child(
        self,
        parent_id: str,
        state: CandidateState = "unavailable",
        reflection_depth: int = 0,
        epoch: int | None = None,
        dataset_index: int | None = None,
    ) -> CandidateMeta | None:
        """Create a child candidate by copying the parent's tunable-artifact tree.

        Bumps generation, links ``children_ids`` on the parent.

        Args:
            parent_id: Id of the parent candidate to derive from.
            state: Initial ``CandidateState`` (default ``"unavailable"``).
            reflection_depth: Mara-chain depth for this child (0 for a
                normal propose).
            epoch: Optional epoch to stamp on the child meta.
            dataset_index: Optional dataset index to stamp on the child meta.

        Returns:
            The new child's ``CandidateMeta``, or None if the parent doesn't
            exist.
        """

    @abstractmethod
    def delete(self, candidate_id: str) -> None:
        """Permanently remove a candidate and all its data (recursive delete).

        Args:
            candidate_id: The candidate id to delete.
        """

    @abstractmethod
    def retire(self, candidate_id: str) -> None:
        """Remove a candidate from the active population.

        Physically deletes it if ``cleanup_unavailable`` was set at
        construction; otherwise only flips state to ``"unavailable"`` and keeps
        the data for later inspection.

        Args:
            candidate_id: The candidate id to retire.
        """

    @abstractmethod
    def exists(self, candidate_id: str) -> bool:
        """Whether the candidate is known to this store (cache-membership check).

        Args:
            candidate_id: The candidate id to check.

        Returns:
            True if the candidate is known.
        """

    # -- meta + state ---------------------------------------------------------

    @abstractmethod
    def get_meta(self, candidate_id: str) -> CandidateMeta | None:
        """Return the candidate's meta, or None if unknown.

        Args:
            candidate_id: The candidate id to look up.

        Returns:
            The ``CandidateMeta``, or None.
        """

    @abstractmethod
    def save_meta(self, candidate_id: str, meta: CandidateMeta) -> None:
        """Persist (overwrite) the candidate's meta.

        Args:
            candidate_id: The candidate id whose meta to write.
            meta: The new ``CandidateMeta`` to persist.
        """

    @abstractmethod
    def set_state(self, candidate_id: str, state: CandidateState) -> None:
        """Canonical state mutator. Silently no-ops if the candidate was deleted.

        Args:
            candidate_id: The candidate id to mutate.
            state: The target ``CandidateState``.
        """

    @abstractmethod
    def set_available(self, candidate_id: str, is_available: bool) -> None:
        """Deprecated shim: maps True → ``"pending"``, False → ``"unavailable"``.

        Prefer ``set_state`` directly.

        Args:
            candidate_id: The candidate id to mutate.
            is_available: True → ``"pending"``, False → ``"unavailable"``.
        """

    @abstractmethod
    def set_progress(self, candidate_id: str, epoch: int, dataset_index: int) -> None:
        """Atomically write both progress fields and persist to meta.

        Args:
            candidate_id: The candidate id whose progress to update.
            epoch: The epoch counter to stamp.
            dataset_index: The dataset cursor index to stamp.
        """

    # -- summary + scores -----------------------------------------------------

    @abstractmethod
    def get_summary(self, candidate_id: str) -> CandidateSummary | None:
        """Return the candidate's summary (scores), or an empty one if unknown.

        Args:
            candidate_id: The candidate id to look up.

        Returns:
            The ``CandidateSummary``, or None.
        """

    @abstractmethod
    def save_summary(self, candidate_id: str, summary: CandidateSummary) -> None:
        """Persist (overwrite) the candidate's summary.

        Args:
            candidate_id: The candidate id whose summary to write.
            summary: The new ``CandidateSummary`` to persist.
        """

    @abstractmethod
    def update_summary_scores(self, candidate_id: str, eval_results: list[EvaluationResult]) -> None:
        """Rewrite ``summary.score_list`` from ``eval_results`` and recompute ``avg_score``.

        Args:
            candidate_id: The candidate id whose summary scores to update.
            eval_results: Evaluation results to record as the new score list.
        """

    @abstractmethod
    def get_best_candidate(self) -> tuple[CandidateMeta, CandidateSummary] | None:
        """Return (meta, summary) of the best *alive* candidate by ``avg_score``.

        Only ``pending``/``evolving`` candidates (the live, validated
        population) are considered — never retired/unavailable ones. Among
        evaluated alive candidates the one with the highest ``avg_score`` wins,
        tie-broken by (generation, created_at) descending. Returns None when no
        alive candidate has been evaluated yet.
        """

    @abstractmethod
    def get_available_meta_list(self) -> list[CandidateMeta]:
        """Return all candidates eligible for EA selection (state == ``"pending"``).

        Returns:
            Metas of all pending candidates.
        """

    @abstractmethod
    def get_pool_by_state(self, *states: CandidateState) -> list[CandidateMeta]:
        """Filter the in-memory pool by lifecycle state(s).

        Args:
            *states: One or more ``CandidateState`` values to match.

        Returns:
            Metas of candidates whose state is in ``states``.
        """

    @abstractmethod
    def get_all_candidate_id_list(self) -> list[str]:
        """Return all known candidate ids.

        Returns:
            All candidate ids known to this store.
        """

    # -- analysis results -----------------------------------------------------

    @abstractmethod
    def read_analysis_content(self, candidate_id: str, data_id: str) -> str | None:
        """Read the raw JSON content of a single analysis result file, or None.

        Args:
            candidate_id: The candidate id to read from.
            data_id: The data instance id whose analysis to read.

        Returns:
            The raw JSON string, or None if the file doesn't exist.
        """

    @abstractmethod
    def read_all_analysis_json_content(
        self, candidate_id: str, max_chars: int = 100000, last_n: int | None = None
    ) -> str:
        """Read analysis results as a formatted JSON string, budget-limited.

        Prioritizes entries that have ``actions`` and returns the newest ones
        first.

        Args:
            candidate_id: The candidate id to read from.
            max_chars: Cap on total output length (default 100_000).
            last_n: If set, limit to the most recent N entries.

        Returns:
            A formatted JSON string of the (filtered) analysis results.
        """

    @abstractmethod
    def update_analysis(self, candidate_id: str, entry: RunAnalysis) -> None:
        """Write a single analysis result file, preserving ``created_at`` from any existing entry.

        Args:
            candidate_id: The candidate id whose analysis to write.
            entry: The ``RunAnalysis`` to persist (filename derives from its ``data_id``).
        """

    # -- trajectories ---------------------------------------------------------

    @abstractmethod
    def save_analysis_trajectory(
        self, parent_candidate_id: str, new_candidate_id: str, trajectory: Trajectory
    ) -> None:
        """Persist a child's analysis-phase trajectory (one JSON per child).

        Args:
            parent_candidate_id: Candidate whose analysis-trajectory dir to write under.
            new_candidate_id: The child candidate this trajectory belongs to (filename).
            trajectory: The ``Trajectory`` to serialize.
        """

    @abstractmethod
    def save_propose_trajectory(
        self, parent_candidate_id: str, new_candidate_id: str, trajectory: Trajectory
    ) -> None:
        """Persist a child's mutation-phase trajectory (one JSON per child).

        Args:
            parent_candidate_id: Candidate whose mutation-trajectory dir to write under.
            new_candidate_id: The child candidate this trajectory belongs to (filename).
            trajectory: The ``Trajectory`` to serialize.
        """

    # -- run records ----------------------------------------------------------

    @abstractmethod
    def get_all_run_data_ids(self, candidate_id: str, split: RunSplit = "train") -> list[str]:
        """Return all data_ids that have run records, sorted by data_id.

        Args:
            candidate_id: The candidate id to inspect.
            split: Train or val run dir (default ``"train"``).

        Returns:
            Sorted list of data_ids with run records.
        """

    @abstractmethod
    def find_unanalyzed_runs(self, candidate_id: str) -> dict[str, list[str]]:
        """Return ``{data_id: [run_name, …]}`` for runs newer than the latest analysis result.

        Freshness is computed via mtime-equivalent ordering (contract #2):
        runs whose last-modified timestamp exceeds the newest analysis-result
        timestamp are "unanalyzed" and returned. Train split only.

        Args:
            candidate_id: The candidate id to inspect.

        Returns:
            Mapping of data_id → list of unanalyzed run filenames.
        """

    @abstractmethod
    def list_run_files(self, candidate_id: str, data_id: str, split: RunSplit = "train") -> list[str]:
        """Return full paths/keys of all run files for a (candidate, data_id), sorted (newest last).

        Args:
            candidate_id: The candidate id to inspect.
            data_id: The data instance id whose run files to list.
            split: Train or val run dir (default ``"train"``).
        """

    @abstractmethod
    def latest_run_file(self, candidate_id: str, data_id: str, split: RunSplit = "train") -> str | None:
        """Return the full path/key of the most recent run file for a (candidate, data_id).

        Args:
            candidate_id: The candidate id to inspect.
            data_id: The data instance id whose latest run to find.
            split: Train or val run dir (default ``"train"``).

        Returns:
            The latest run file's path/key, or None if there are no runs.
        """

    @abstractmethod
    def run_file_path(
        self, candidate_id: str, data_id: str, run_name: str, split: RunSplit = "train"
    ) -> str:
        """Return the full path/key for a run file given its name.

        Args:
            candidate_id: The candidate id.
            data_id: The data instance id.
            run_name: The run file's filename (e.g. ``run_20260101_120000.json``).
            split: Train or val run dir (default ``"train"``).
        """

    @abstractmethod
    def get_run_score(
        self, candidate_id: str, data_id: str, run_name: str, split: RunSplit = "train"
    ) -> float | None:
        """Read the evaluation score from a run record file.

        Args:
            candidate_id: The candidate id.
            data_id: The data instance id.
            run_name: The run file's filename.
            split: Train or val run dir (default ``"train"``).

        Returns:
            The ``evaluation_result.score``, or None if unreadable.
        """

    @abstractmethod
    def save_run_record(self, candidate_id: str, record: RunRecord, split: RunSplit = "train") -> None:
        """Persist a run record (filename timestamped ``run_YYYYMMDD_HHMMSS.json``).

        Args:
            candidate_id: The candidate id to write under.
            record: The ``RunRecord`` to persist.
            split: Train or val run dir (default ``"train"``).
        """

    # -- changelog ------------------------------------------------------------

    @abstractmethod
    def changelog_path(self, candidate_id: str) -> str:
        """Return the path/key of the candidate's ``changelog.jsonl``.

        Note: the live append path is driven by an external ``append-changelog``
        CLI (contract #3), not only by ``append_changelog`` below.

        Args:
            candidate_id: The candidate id whose changelog to locate.
        """

    @abstractmethod
    def append_changelog(self, candidate_id: str, entry: ChangeLogEntry) -> None:
        """Append a single changelog entry to the JSONL stream (Python-side convenience).

        The real propose flow appends via the external ``append-changelog`` CLI,
        so implementors must support both this call and concurrent appends from
        that subprocess (contract #3).

        Args:
            candidate_id: The candidate id whose changelog to append to.
            entry: The ``ChangeLogEntry`` to append.
        """

    @abstractmethod
    def read_changelog(self, candidate_id: str) -> list[ChangeLogEntry] | None:
        """Read changelog entries line by line.

        Returns None (signaling "needs repair") if any entry is malformed.

        Args:
            candidate_id: The candidate id whose changelog to read.

        Returns:
            Parsed entries, or None if any line is malformed.
        """

    # -- statistics + iteration logs ------------------------------------------

    @abstractmethod
    def save_statistics(self, statistics: OptimizationStatistics) -> None:
        """Persist (overwrite) the global optimization statistics.

        Args:
            statistics: The ``OptimizationStatistics`` to persist.
        """

    @abstractmethod
    def get_statistics(self) -> OptimizationStatistics:
        """Return the global optimization statistics (empty/default if none yet).

        Returns:
            The current ``OptimizationStatistics``.
        """

    @abstractmethod
    def append_iteration_record(self, record: IterationRecord) -> None:
        """Append a single iteration record to ``iteration_records.jsonl``.

        Args:
            record: The ``IterationRecord`` to append.
        """

    @abstractmethod
    def read_iteration_records(self) -> list[IterationRecord]:
        """Read all iteration records, skipping malformed lines.

        Returns:
            All parsed ``IterationRecord`` entries.
        """

    @abstractmethod
    def append_parameters(self, params: dict) -> None:
        """Append a launch-parameters record to ``parameters.jsonl`` (once per optimizer launch).

        Args:
            params: The launch parameters dict to persist as one JSON line.
        """

    # -- startup recovery -----------------------------------------------------

    @abstractmethod
    def reset_evolving_to_pending(self) -> list[str]:
        """Startup recovery: flip every ``"evolving"`` candidate back to ``"pending"``.

        Returns:
            The ids of candidates that were reset.
        """

    @abstractmethod
    def delete_unavailable_candidates(self) -> list[str]:
        """Delete every candidate whose state is ``"unavailable"``.

        Returns:
            The ids of candidates that were deleted.
        """
