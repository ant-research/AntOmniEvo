from datetime import datetime

from pydantic import BaseModel, Field

from antomnievo.model.evaluation_result import EvaluationResult
from antomnievo.model.system_result import SystemResult
from antomnievo.model.usage_stats import UsageStats

SCORE_EPS = 1e-8

class RolloutEvalResult(BaseModel):
    results: list[SystemResult] = Field(default_factory=list, description="System results from rollout")
    evals: list[EvaluationResult] = Field(default_factory=list, description="Evaluation results")

    @property
    def scores(self) -> list[float]:
        return [e.score for e in self.evals]


class ProposalTask(BaseModel):
    """A pending proposal: parent to mutate + new child candidate."""

    parent_id: str = Field(description="Parent candidate ID to mutate from")
    new_id: str = Field(description="New child candidate ID")


class ProposalResult(BaseModel):
    """Result of a proposer generating a new candidate."""

    success: bool = True
    error_message: str | None = None
    stats: UsageStats | None = None


class ChainNode(BaseModel):
    """A single node in a mara chain passed to ``Proposer.reflect``.

    A mara chain has the shape::

        chain[0]  = root (the original parent that was selected for mutation)
        chain[1]  = v0  (the first failed child)
        chain[2]  = v1  (the first reflection attempt that also failed)
        ...
        chain[-1] = v_{k-1}  (the most recent failed attempt; its spec is the
                              starting point for the candidate being produced)

    Every node carries the evals it scored on the current batch — there is no
    placeholder for the not-yet-evaluated candidate (that one is passed
    alongside the chain as a separate ``new_candidate_id`` argument).

    The reflection depth is implied: ``len(chain) - 1`` (the number of failed
    attempts so far; equivalently, k for the v_k about to be produced).
    """

    candidate_id: str = Field(description="Candidate id of this chain node.")
    evals: dict[str, EvaluationResult] = Field(
        description="Per-data eval results for this node on the current batch. Key=data_id."
    )

    @classmethod
    def from_eval_list(cls, candidate_id: str, eval_list: list[EvaluationResult]) -> "ChainNode":
        """Convenience constructor accepting a ``list[EvaluationResult]`` (auto-converts to dict)."""
        return cls(candidate_id=candidate_id, evals={e.data_id: e for e in eval_list})


class MaraChain:
    """Ordered list of evaluated ``ChainNode``s used by reflection-mode proposing.

    Layout::

        chain[0]    = root (original parent)
        chain[1..]  = v0, v1, …, v_{k-1}  (failed attempts, newest last)

    ``new_candidate_id`` (v_k, the candidate about to be produced) is NOT in
    the chain — it is passed separately.

    Provides convenience accessors so callers don't need to manually compute
    ``chain[0]``, ``chain[-1]``, or ``len(chain) - 1`` everywhere.
    """

    def __init__(self, nodes: list[ChainNode]) -> None:
        if len(nodes) < 2:
            raise ValueError(
                f"MaraChain requires at least 2 nodes (root + first failed), got {len(nodes)}"
            )
        self._nodes: list[ChainNode] = list(nodes)

    def add(self, node: ChainNode) -> None:
        """Append a new failed-attempt node to the chain."""
        self._nodes.append(node)

    # ── Convenience accessors ──────────────────────────────────────────

    @property
    def root(self) -> ChainNode:
        """The original parent node (chain[0])."""
        return self._nodes[0]

    @property
    def last(self) -> ChainNode:
        """The most recent failed-attempt node (chain[-1])."""
        return self._nodes[-1]

    @property
    def depth(self) -> int:
        """Number of failed attempts so far (``len(chain) - 1``).

        Equivalently, k for the v_k about to be produced.
        """
        return len(self._nodes) - 1

    @property
    def nodes(self) -> list[ChainNode]:
        """The underlying node list, ordered oldest → newest."""
        return self._nodes

    # ── Prompt artifact builders ───────────────────────────────────────

    def format_id_path(self) -> str:
        """Render the chain as ``cid0 → cid1 → cid2`` — full candidate ids, oldest→newest.

        Useful as the canonical reference for every other reflection prompt
        artifact (score table columns, changelog, preloaded analysis blocks).
        """
        return " → ".join(node.candidate_id for node in self._nodes)

    def format_score_history_table(self, data_id: str | None = None) -> str:
        """Render per-data scores across the chain as a markdown table.

        Columns (left to right): data_id, then one column per chain node keyed
        by its candidate id, then ``Δ_{root_id}→{cid}`` for every non-root
        attempt, then ``Δ_{prev_id}→{cid}`` for v1, v2, ... (the first
        attempt's "prev" is root, already covered by the Δ-vs-root column).

        When *data_id* is given, only that row is rendered (useful for
        per-data_id parallel analysis prompts).
        """
        if not self._nodes:
            return "| (no score data available) |"

        col_ids = [node.candidate_id for node in self._nodes]
        score_columns: list[dict[str, float]] = [
            {did: er.score for did, er in node.evals.items()} for node in self._nodes
        ]

        if data_id is None:
            all_ids = sorted({did for col in score_columns for did in col})
        else:
            all_ids = [data_id]
        if not all_ids:
            return "| (no score data available) |"

        root_id = col_ids[0]
        header_cells = ["data_id", *col_ids]
        for cid in col_ids[1:]:
            header_cells.append(f"Δ_{root_id}→{cid}")
        for i in range(2, len(col_ids)):
            header_cells.append(f"Δ_{col_ids[i-1]}→{col_ids[i]}")

        sep_cells = ["---"] * len(header_cells)

        def _fmt(v: float | None) -> str:
            return f"{v:.4f}" if v is not None else "n/a"

        def _delta(a: float | None, b: float | None) -> str:
            if a is None or b is None:
                return "n/a"
            return f"{b - a:+.4f}"

        rows: list[str] = [
            "| " + " | ".join(header_cells) + " |",
            "| " + " | ".join(sep_cells) + " |",
        ]
        for did in all_ids:
            scores = [col.get(did) for col in score_columns]
            cells = [did, *[_fmt(s) for s in scores]]
            for i in range(1, len(scores)):
                cells.append(_delta(scores[0], scores[i]))
            for i in range(2, len(scores)):
                cells.append(_delta(scores[i - 1], scores[i]))
            rows.append("| " + " | ".join(cells) + " |")
        return "\n".join(rows)


class ProposalOutcome(BaseModel):
    """A completed proposal with timing info."""

    parent_id: str = Field(description="Parent candidate ID")
    new_id: str = Field(description="New child candidate ID")
    proposer_duration: float = Field(description="Time spent on propose call in seconds")


class AcceptedCandidate(BaseModel):
    """An accepted candidate pending validation on the val set."""

    parent_id: str = Field(description="Parent candidate ID")
    new_id: str = Field(description="New child candidate ID")
    old_batch_score_sum: float = Field(description="Parent's total score on training batch")
    new_batch_score_sum: float = Field(description="Child's total score on training batch")
    reflection_depth: int = Field(
        default=0,
        description=(
            "Reflection depth of the accepted child: 0 = first attempt, k>0 = accepted from the k-th reflection iteration."
        ),
    )


class IterationRecord(BaseModel):
    """Record for a single optimization iteration.

    candidate_created / accepted combinations:
        - candidate_created=False, accepted=False: selected candidate already perfect on batch, skipped propose
        - candidate_created=True,  accepted=False: child created but rejected (propose failed OR score not improved)
        - candidate_created=True,  accepted=True:  child accepted (score improved on batch), validated on val set
    """

    iteration: int = Field(description="Iteration number within the optimization loop")
    epoch: int = Field(description="Current epoch number")
    selected_id: str = Field(description="Parent candidate ID selected for mutation")
    new_id: str = Field(description="Child candidate ID (empty if propose was skipped)")
    old_batch_score_sum: float = Field(description="Parent's total score on training batch")
    new_batch_score_sum: float = Field(description="Child's total score on training batch (0 if no child)")
    accepted: bool = Field(description="True if new candidate improved on batch and passed val validation")
    candidate_created: bool = Field(default=True, description="False if propose was skipped (parent already perfect)")
    new_val_avg_score: float | None = Field(default=None, description="Child's avg score on val set (only when accepted)")
    proposer_duration_seconds: float = Field(default=0.0, description="Time spent on propose call in seconds")
    duration_seconds: float = Field(default=0.0, description="Total wall time for this iteration step")
    timestamp: datetime = Field(default_factory=datetime.now, description="When this iteration occurred")
    challenge_duration_seconds: float = Field(default=0.0, description="Time spent on challenge parent in seconds")
    reflection_depth: int = Field(
        default=0,
        description=(
            "Reflection depth of the involved child (matches CandidateMeta.reflection_depth). "
            "0 = normal proposal. k>0 = the k-th reflection iteration accepted/rejected within this iteration."
        ),
    )
    data_indices: list[str] = Field(default_factory=list, description="Data IDs used in this iteration's training batch")
    dataset_index: int = Field(default=0, description="Starting index of the batch within the full training dataset")
    current_rollouts: int = Field(default=0, description="Cumulative rollout count (statistics.current_rollouts) at the end of this iteration")
    current_system_runs: int = Field(default=0, description="Cumulative system-run count (statistics.current_system_runs) at the end of this iteration")
    current_best_avg_score: float | None = Field(default=None, description="Current highest avg score across alive candidates (statistics.best_avg_score) at the end of this iteration")

    @staticmethod
    def from_accepted(acc: AcceptedCandidate, iteration: int, epoch: int, val_avg_score: float | None = None, proposer_duration_seconds: float = 0.0, duration_seconds: float = 0.0, challenge_duration_seconds: float = 0.0, reflection_depth: int = 0, data_indices: list[str] | None = None, dataset_index: int = 0, current_rollouts: int = 0, current_system_runs: int = 0) -> "IterationRecord":
        return IterationRecord(
            iteration=iteration,
            epoch=epoch,
            selected_id=acc.parent_id,
            new_id=acc.new_id,
            old_batch_score_sum=acc.old_batch_score_sum,
            new_batch_score_sum=acc.new_batch_score_sum,
            accepted=True,
            candidate_created=True,
            new_val_avg_score=val_avg_score,
            proposer_duration_seconds=proposer_duration_seconds,
            duration_seconds=duration_seconds,
            challenge_duration_seconds=challenge_duration_seconds,
            reflection_depth=reflection_depth,
            data_indices=data_indices or [],
            dataset_index=dataset_index,
            current_rollouts=current_rollouts,
            current_system_runs=current_system_runs,
        )


def build_iteration_record(
    parent_id: str,
    old_rollout: RolloutEvalResult,
    proposal_task: ProposalTask | None,
    proposal: ProposalOutcome | None,
    new_rollout: RolloutEvalResult | None,
    accepted: AcceptedCandidate | None,
    val_avg_score: float | None,
    iter_start: datetime,
    iteration: int,
    epoch: int,
    challenge_duration_seconds: float = 0.0,
    dataset_index: int = 0,
    current_rollouts: int = 0,
    current_system_runs: int = 0,
) -> IterationRecord:
    """Build a single IterationRecord summarizing one evolution slot.

    Branches (mutually exclusive):
      - proposal_task is None  → parent was already perfect on batch, propose skipped
      - proposal is None       → proposer call failed
      - accepted is None       → child evaluated but rejected (score not improved)
      - accepted is not None   → child accepted and validated
    """
    duration = (datetime.now() - iter_start).total_seconds()
    old_sum = sum(old_rollout.scores)
    proposer_duration = proposal.proposer_duration if proposal is not None else 0.0
    data_indices = [e.data_id for e in old_rollout.evals]

    if proposal_task is None:
        # Skipped: parent already perfect on batch.
        return IterationRecord(
            iteration=iteration, epoch=epoch,
            selected_id=parent_id, new_id="",
            old_batch_score_sum=old_sum,
            new_batch_score_sum=0.0,
            accepted=False, candidate_created=False,
            proposer_duration_seconds=0.0,
            duration_seconds=duration,
            data_indices=data_indices,
            dataset_index=dataset_index,
            current_rollouts=current_rollouts,
            current_system_runs=current_system_runs,
        )

    if proposal is None:
        # Proposer failed.
        return IterationRecord(
            iteration=iteration, epoch=epoch,
            selected_id=parent_id, new_id=proposal_task.new_id,
            old_batch_score_sum=old_sum,
            new_batch_score_sum=0.0,
            accepted=False, candidate_created=True,
            proposer_duration_seconds=proposer_duration,
            duration_seconds=duration,
            data_indices=data_indices,
            dataset_index=dataset_index,
            current_rollouts=current_rollouts,
            current_system_runs=current_system_runs,
        )

    if accepted is None:
        # Child evaluated but rejected.
        new_sum = sum(new_rollout.scores) if new_rollout is not None else 0.0
        return IterationRecord(
            iteration=iteration, epoch=epoch,
            selected_id=parent_id, new_id=proposal.new_id,
            old_batch_score_sum=old_sum,
            new_batch_score_sum=new_sum,
            accepted=False, candidate_created=True,
            proposer_duration_seconds=proposer_duration,
            duration_seconds=duration,
            challenge_duration_seconds=challenge_duration_seconds,
            data_indices=data_indices,
            dataset_index=dataset_index,
            current_rollouts=current_rollouts,
            current_system_runs=current_system_runs,
        )

    # Accepted + validated.
    return IterationRecord.from_accepted(
        accepted, iteration=iteration, epoch=epoch,
        val_avg_score=val_avg_score,
        proposer_duration_seconds=proposer_duration,
        duration_seconds=duration,
        challenge_duration_seconds=challenge_duration_seconds,
        reflection_depth=accepted.reflection_depth,
        data_indices=data_indices,
        dataset_index=dataset_index,
        current_rollouts=current_rollouts,
        current_system_runs=current_system_runs,
    )
