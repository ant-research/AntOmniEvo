from pydantic import BaseModel, Field

from antomnievo.model.rollout_result import RolloutResult
from antomnievo.model.trajectory import Trajectory
from antomnievo.model.usage_stats import UsageStats


class SystemResult(BaseModel):
    """Result from running the system on a single data instance."""

    trajectory: Trajectory = Field(description="Step-by-step reasoning and tool calls")
    output: RolloutResult = Field(description="System output")
    usage: UsageStats | None = Field(default=None, description="Token usage statistics", exclude=True)
