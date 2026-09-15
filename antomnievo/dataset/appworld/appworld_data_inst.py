from __future__ import annotations

from pydantic import Field

from antomnievo.interface.data_inst import DataInst


class AppWorldDataInst(DataInst):
    """Data instance for AppWorld task optimization.

    Each instance represents a single AppWorld task identified by its task_id.
    The ``query`` field holds the task instruction, and ``golden_answer``
    holds the expected answer (from ground truth).
    """

    task_id: str = Field(description="AppWorld task identifier, e.g. '9bf2c8a_1'")
    scenario_id: str = Field(
        description="Scenario identifier (prefix before _N), e.g. '9bf2c8a'"
    )
