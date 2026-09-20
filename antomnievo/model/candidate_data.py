from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from antomnievo.common.utils.pydantic_desc import model_fields_description
from antomnievo.interface.data_inst import DataInst
from antomnievo.model.evaluation_result import EvaluationResult
from antomnievo.model.system_result import SystemResult

CandidateState = Literal["pending", "evolving", "unavailable"]

# Train vs validation split for run records / trajectories.
RunSplit = Literal["train", "val"]


class ArtifactAction(BaseModel):
    """One tunable-artifact change: a file location with its diagnosis and prescription."""

    file: str = Field(
        description=(
            "The file to modify, as a concrete path relative to the tunable-artifact directory root. "
            "Do NOT use vague targets like 'the tunable artifacts' or a category name — always a concrete file path."
        ),
    )
    operation: str = Field(
        description=(
            "The type of modification: 'add', 'delete', or 'modify'. "
            "- add: create a new file or append content to an existing file/section. "
            "- delete: remove a file, section, or specific content. "
            "- modify: replace existing content with new content."
        ),
    )
    artifact_issue: str = Field(
        description=(
            "The defect in this file — what is wrong, misleading, harmful, "
            "missing, or incomplete. Be specific about the current text (or its absence)."
        ),
    )
    change: str = Field(
        description=(
            "The exact change to apply. "
            "For 'modify': use BEFORE/AFTER format to show what to replace:\n"
            "```\n"
            "BEFORE:\n"
            "<the existing text to find — copy verbatim from the current file>\n"
            "AFTER:\n"
            "<the new text that replaces it>\n"
            "```\n"
            "The BEFORE block must match the current file content exactly (copy-paste from "
            "your earlier read of the file). Include enough surrounding context (3+ lines) "
            "for unambiguous matching. "
            "For 'add': the exact content to insert (no BEFORE/AFTER needed — just the raw content). "
            "For 'delete': a brief description of what to remove (e.g. 'the paragraph about X'). "
            "If the change requires touching another file too, include a separate ArtifactAction for that file."
        ),
    )
    resolves: list[int] = Field(
        description=(
            "0-based indices into `RunAnalysis.trajectory_analysis` — the trajectory problem(s) "
            "this action resolves. e.g. [1] means this action fixes trajectory_analysis[1] "
            "(the 2nd item). Most actions resolve a single problem; multiple indices are allowed "
            "ONLY when one file change genuinely fixes several distinct trajectory "
            "problems. Every index must be valid for the analysis's trajectory_analysis length. "
            "MUST be non-empty — an action with no trajectory link does not belong in the analysis."
        ),
    )


class RunAnalysis(BaseModel):
    """Analysis of a single run: trajectory observations + tunable-artifact actions linked by index.

    Action quality rules:
    - Mutation-actionable: every action's `change` must contain enough concrete content
      (specific commands, patterns, decision procedures, examples) that the mutation agent
      can implement it directly without reading run data.
    - Root-cause depth: target WHY the mistake happened, not just WHAT went wrong.
      "System used wrong field" is a symptom; "system sampled one row and assumed all
      rows share the same schema" is the root cause. A root-cause action produces a mechanism
      that prevents the whole class of mistakes, not just one instance.
    - No silent drops: every `trajectory_analysis` item SHOULD be referenced by at least
      one action's `resolves`. If a trajectory item has no feasible tunable-artifact fix, explain why
      in `data_quality_issues` rather than silently dropping it.
    """

    data_id: str = Field(description="Which data instance this analysis covers")
    trajectory_analysis: list[str] = Field(
        default_factory=list,
        description=(
            "Run-trajectory observations — one observation per list item. "
            "Each item describes ONE specific point in the trajectory: a problem (where the "
            "system went wrong and why) OR a notable success worth codifying (a behavior that "
            "produced the correct result and should be solidified into the tunable artifacts so it reproduces). "
            "Be specific per item: which trajectory step, what the system did vs what would have "
            "been better, what was expected vs what happened. "
            "Do NOT combine multiple observations into one item — each item is referenced by "
            "0-based index from `actions[*].resolves`, so granularity matters. "
            "Prefer fewer high-quality observations over many vague ones. "
            "MUTUALLY EXCLUSIVE with data_quality_issues — leave empty if data is flawed."
        ),
    )
    actions: list[ArtifactAction] = Field(
        default_factory=list,
        description=(
            "Concrete tunable-artifact actions to fix the trajectory problems (or codify the successes) "
            "listed in `trajectory_analysis`. Each action targets a file, pairs a "
            "`artifact_issue` diagnosis with a `change` prescription, and references via `resolves` "
            "which trajectory_analysis items it addresses. "
            "An action's file MUST be the same location identified in its `artifact_issue`. "
            "Every action MUST cite at least one trajectory_analysis index in `resolves`. "
            "MUTUALLY EXCLUSIVE with data_quality_issues — leave empty if data is flawed."
        ),
    )
    data_quality_issues: list[str] = Field(
        default_factory=list,
        description=(
            "Issues with the data instance itself (NOT the system's behavior). "
            "Flag problems such as: incorrect or ambiguous golden answer, contradictions "
            "between the question and provided context, missing information needed "
            "to solve the question, or the question being unsolvable given the input. "
            "Each item describes ONE specific data quality problem with evidence. "
            "Leave empty when the data instance is well-formed. "
            "MUTUALLY EXCLUSIVE with trajectory_analysis/actions — if set, those must be empty."
        ),
    )
    created_at: datetime = Field(
        default_factory=datetime.now,
        description="When this analysis was first created",
    )
    updated_at: datetime = Field(
        default_factory=datetime.now,
        description="When this analysis was last updated (timestamp of the run that was analyzed). If a newer run exists, re-analysis is needed.",
    )

    @model_validator(mode="after")
    def _validate_mutual_exclusion_and_indices(self) -> "RunAnalysis":
        if self.data_quality_issues:
            if self.trajectory_analysis or self.actions:
                raise ValueError(
                    "data_quality_issues and trajectory_analysis/actions are mutually exclusive. "
                    "If the data instance itself is flawed, do not analyze trajectory or propose actions."
                )
            return self
        n = len(self.trajectory_analysis)
        for j, action in enumerate(self.actions):
            if not action.resolves:
                raise ValueError(f"actions[{j}].resolves is empty; every action must cite at least one trajectory_analysis index")
            for idx in action.resolves:
                if not (0 <= idx < n):
                    raise ValueError(
                        f"actions[{j}].resolves contains {idx}, which is out of range "
                        f"[0, {n - 1}] for trajectory_analysis of length {n}"
                    )
        return self

    @staticmethod
    def to_description() -> str:
        return (
            "Analysis of a single run record. Captures what happened in the trajectory and the "
            "tunable-artifact changes that should follow from it.\n\n"
            "Fields:\n" + model_fields_description(RunAnalysis) + "\n"
        )


class CandidateMeta(BaseModel):
    """Schema for meta.json — candidate metadata and filesystem paths."""

    candidate_id: str = Field(description="Unique identifier")
    artifact_dir: str = Field(default="", description="Absolute path to the candidate's tunable-artifact directory")
    data_dir: str = Field(default="", description="Absolute path to the candidate's data directory")
    parent_id: str | None = Field(default=None, description="Parent candidate ID, null for root")
    children_ids: list[str] = Field(default_factory=list, description="IDs of child candidates")
    created_at: datetime = Field(default_factory=datetime.now, description="Creation timestamp")
    state: CandidateState = Field(
        default="unavailable",
        description=(
            "Lifecycle state. 'pending' = evaluated and selectable for evolution. "
            "'evolving' = currently occupying an evolution slot (mutating + evaluating). "
            "'unavailable' = either an un-validated child (just created, not yet scored) "
            "or a retired candidate that was eliminated. Only 'pending' candidates are "
            "visible to EvolutionAlgorithm.select / .eliminate."
        ),
    )
    epoch: int = Field(
        default=0,
        description=(
            "Number of completed full passes over the train_dataset for THIS candidate. "
            "Independent across candidates — each candidate carries its own progress."
        ),
    )
    dataset_index: int = Field(
        default=0,
        description=(
            "Next train_dataset index this candidate will consume on its next slot occupation. "
            "After a slot completes, advanced to (epoch, idx+batch_size) — or (epoch+1, 0) when "
            "the slice wraps past len(train_dataset)."
        ),
    )
    generation: int = Field(default=0, description="Evolution generation number (root = 0)")
    reflection_depth: int = Field(
        default=0,
        description=(
            "Reflection iteration depth within a single batch attempt. "
            "0 = normal child of its parent. k>0 = the k-th reflection child in a chain "
            "rooted at a normal child that failed to clear the batch improvement threshold."
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_is_available(cls, data: Any) -> Any:
        """Translate legacy meta.json that stored `is_available: bool` into the new `state` field."""
        if not isinstance(data, dict):
            return data
        if "is_available" in data:
            data = dict(data)
            legacy = data.pop("is_available")
            if "state" not in data:
                data["state"] = "pending" if legacy else "unavailable"
        return data

    @property
    def is_available(self) -> bool:
        """Backward-compat alias. True when state is NOT 'unavailable' (i.e. pending or evolving)."""
        return self.state != "unavailable"

    @is_available.setter
    def is_available(self, value: bool) -> None:
        """Backward-compat setter. True → 'pending', False → 'unavailable'. Prefer set_state for new code."""
        self.state = "pending" if value else "unavailable"

    @staticmethod
    def to_description() -> str:
        return (
            "Candidate metadata.\n\n"
            "What you can learn: generation indicates refinement depth, "
            "parent_id traces ancestry for comparison, state indicates lifecycle "
            "('pending' selectable, 'evolving' in-flight, 'unavailable' retired or pre-validation), "
            "(epoch, dataset_index) is the per-candidate training progress.\n\n"
            "Fields:\n" + model_fields_description(CandidateMeta) + "\n"
        )


class ChangeLogEntry(BaseModel):
    """Schema for a single line in changelog.jsonl.

    Example:
        type: "feat"
        subject: "add multi-hop decomposition strategy"
        body: "Run analysis showed failures on chained questions...\\n\\nAdded step-by-step decomposition..."
        diff: "--- a/SKILL.md\\n+++ b/SKILL.md\\n@@ -10,6 +10,12 @@\\n+### Step-by-step Decomposition\\n+Break complex questions into..."
        files_modified: ["SKILL.md"]
        author: "claude_code"
    """

    timestamp: datetime = Field(default_factory=datetime.now, description="When the change was made")
    type: str = Field(description="One of: feat, fix, refactor, perf, docs, style, chore")
    subject: str = Field(description="Short imperative summary, max 72 chars")
    body: str = Field(
        default="",
        description=(
            "Detailed explanation of the mutation. Must include: "
            "(1) What failure pattern or opportunity was observed, citing specific data_ids and scores from analysis; "
            "(2) What tunable-artifact change was made and why this change addresses the observed pattern; "
            "(3) Expected impact or hypothesis. "
        ),
    )
    diff: str = Field(default="", description="Unified diff of the actual changes, in git diff format")
    files_modified: list[str] = Field(default_factory=list, description="List of modified file paths")
    author: str = Field(default="", description="Proposer identity, e.g. claude_code, human")

    def truncate_diff(self, max_chars: int = 3000) -> "ChangeLogEntry":
        """Truncate the diff field to avoid wasting LLM context.

        Returns self for chaining. Modifies in place.
        """
        if len(self.diff) <= max_chars:
            return self
        truncated = self.diff[:max_chars]
        last_nl = truncated.rfind("\n")
        if last_nl > 0:
            truncated = truncated[:last_nl]
        self.diff = truncated + f"\n... ({len(self.diff) - len(truncated) - 1} more chars truncated)"
        return self

    @staticmethod
    def to_description() -> str:
        return (
            "Mutation history, one JSON line per entry.\n\n"
            "What you can learn: what changes were tried and why (body) — avoid repeating failed ideas; "
            "which files were modified and how (diff, files_modified) — understand evolution direction; "
            "type and scope reveal patterns of past mutations (e.g. all fixes on SKILL.md suggests systemic issues).\n\n"
            "Fields:\n" + model_fields_description(ChangeLogEntry) + "\n"
        )


class ScoreEntry(BaseModel):
    """A single data instance score entry."""

    data_id: str = Field(description="Data instance identifier")
    score: float = Field(description="Evaluation score for this instance")


class CandidateSummary(BaseModel):
    """Schema for summary.json — evaluation results summary."""

    candidate_id: str = Field(description="Unique identifier")
    score_list: list[ScoreEntry] = Field(default_factory=list, description="Score per validation data instance")
    avg_score: float = Field(default=0.0, description="Average of score_list")
    last_evaluated_at: datetime | None = Field(default=None, description="Last evaluation timestamp")

    @staticmethod
    def to_description() -> str:
        return (
            "Evaluation results summary.\n\n"
            "What you can learn: avg_score shows overall quality, score_list spots weak inputs.\n\n"
            "NOTE: For validation dataset, you can ONLY see the scores (score_list, avg_score). "
            "You CANNOT see the actual data instances, system outputs, trajectories, or evaluation details. "
            "Do NOT attempt to infer optimization strategies from validation run records — they do not exist.\n\n"
            "Fields:\n" + model_fields_description(CandidateSummary) + "\n"
        )


class RunRecord(BaseModel):
    """Schema for system_run/{data_id}/run_{time}.json."""

    candidate_id: str = Field(description="Which candidate was run")
    timestamp: datetime = Field(default_factory=datetime.now, description="When the run happened")
    data_inst: DataInst
    system_result: SystemResult
    evaluation_result: EvaluationResult

    @staticmethod
    def to_description() -> str:
        return (
            "Single run record for a candidate on a data instance.\n\n"
            "What you can learn: compare data_inst with "
            "system_result (actual answer) and evaluation_result (score + reason) "
            "to identify failure modes; the trajectory in system_result shows step-by-step "
            "reasoning and tool calls — look for where it goes wrong (e.g. wrong tool call, "
            "missed retrieval, hallucinated answer); high-score runs reveal correct patterns "
            "to preserve; low-score runs reveal specific weaknesses to target with tunable-artifact changes.\n\n"
            "Fields:\n" + model_fields_description(RunRecord) + "\n"
        )
