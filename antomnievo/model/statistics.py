from datetime import datetime

from pydantic import BaseModel, Field

from antomnievo.common.utils.pydantic_desc import model_fields_description
from antomnievo.model.usage_stats import UsageStats


class OptimizationStatistics(BaseModel):
    """Tracks overall optimization progress. Saved as statistics/statistics.json.

    Per-iteration details are stored separately in iteration_records.jsonl
    (one JSON object per line, appended after each iteration) to keep this
    file lightweight.
    """

    root_candidate_id: str = Field(default="", description="Root candidate ID")
    baseline_avg_score: float = Field(default=0.0, description="Root candidate's baseline avg score")
    best_candidate_id: str = Field(default="", description="Current best candidate ID")
    best_avg_score: float = Field(default=0.0, description="Current best avg score")
    current_iteration: int = Field(default=0, description="Current iteration (slot occupation) number")
    max_iterations: int = Field(default=0, description="Maximum iterations (slot occupations) allowed")
    current_rollouts: int = Field(default=0, description="Total rollouts executed so far: cumulative TRAINING data instances run by System. Incremented by len(data_list) on every _run_and_evaluate call whose split is 'train' (parent batch, child batch, each mara-chain child run). Validation runs and the root baseline (which run on the val split) are NOT counted — use current_system_runs for the all-splits total.")
    max_rollouts: int = Field(default=0, description="Maximum rollouts allowed (0 = not set / unlimited)")
    current_system_runs: int = Field(default=0, description="Total system runs so far: cumulative data instances executed by System across ALL splits. Incremented by len(data_list) on every _run_and_evaluate call (parent batch, child batch, each validation run, each mara-chain child run). Inclusive of val/baseline that current_rollouts excludes.")
    max_system_runs: int = Field(default=0, description="Maximum system runs allowed (0 = not set / unlimited)")
    current_population_size: int = Field(default=0, description="Number of available candidates (pending + evolving)")
    total_candidates_created: int = Field(default=0, description="Total candidates ever created")
    rejected_count: int = Field(default=0, description="Candidates rejected (not improved)")
    avg_score_history: list[float] = Field(default_factory=list, description="Best avg score after each iteration")
    start_time: datetime = Field(default_factory=datetime.now, description="When optimization started")
    last_updated_at: datetime = Field(default_factory=datetime.now, description="Last update timestamp")
    total_duration_seconds: float = Field(default=0.0, description="Total elapsed time in seconds")
    proposer_usage: UsageStats = Field(default_factory=UsageStats, description="Cumulative token usage from all proposer invocations")
    system_usage: UsageStats = Field(default_factory=UsageStats, description="Cumulative token usage from system (rollout) invocations")
    eval_usage: UsageStats = Field(default_factory=UsageStats, description="Cumulative token usage from evaluator invocations")

    @staticmethod
    def to_description() -> str:
        return (
            "Optimization progress statistics.\n\n"
            "What you can learn: best_avg_score shows overall progress, "
            "avg_score_history reveals convergence trends, "
            "Per-iteration details are in iteration_records.jsonl (one JSON object per line).\n\n"
            "Fields:\n" + model_fields_description(OptimizationStatistics) + "\n"
        )
