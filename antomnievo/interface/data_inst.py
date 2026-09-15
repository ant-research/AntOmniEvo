from pydantic import BaseModel, Field


class DataInst(BaseModel):
    """Base data instance for optimization.

    Users can subclass this to add domain-specific fields
    (e.g. context, metadata, tools) while keeping the required
    id / query / golden_answer contract.
    """

    id: str = Field(description="Data instance identifier")
    query: str = Field(description="The input question")
    golden_answer: str = Field(description="Ground truth answer")

    @property
    def name(self) -> str:
        return self.__class__.__name__
