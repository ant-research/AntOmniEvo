from pydantic import BaseModel, Field


class RolloutResult(BaseModel):
    content: str = Field(default="", description="The final answer produced by the system")
