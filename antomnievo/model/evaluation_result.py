from pydantic import BaseModel, Field

from antomnievo.model.usage_stats import UsageStats


class EvaluationResult(BaseModel):
    """Result of evaluating a single system output."""

    data_id: str = Field(description="Data instance identifier")
    metric_name: str = Field(description="Name of the evaluation metric")
    score: float = Field(description="Evaluation score (0.0 to 1.0)")
    reason: str = Field(description="Explanation of the score")
    usage: UsageStats | None = Field(default=None, description="Token usage statistics", exclude=True)
