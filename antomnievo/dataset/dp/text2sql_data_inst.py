from __future__ import annotations

import json
from functools import cached_property
from pathlib import Path

from pydantic import Field

from antomnievo.interface.data_inst import DataInst


class Text2SQLDataInst(DataInst):
    """Text2SQL data instance backed by a pre-prepared Harbor task directory.

    Each instance corresponds to a task directory under
    ``harbor_tasks_train/`` or ``harbor_tasks_val/``.

    Heavy data (schema, knowledge) is **not** loaded at construction time —
    it is lazily read from disk on first access via ``cached_property``.

    Directory layout of a Harbor task::

        task_<id>/
        ├── task.toml              # Task config (timeouts, env vars)
        ├── instruction.md         # NL question for the agent
        ├── environment/
        │   ├── Dockerfile         # Docker build (FROM harbor-dp-base:latest + COPY)
        │   ├── business_table_list.md   # DDL schema
        │   └── knowledge.md       # Domain knowledge (may be empty)
        ├── solution/
        │   └── .gitkeep
        └── tests/
            ├── test_data.json     # {question, standard_answer, eval_api_url, eval_api_token, ...}
            ├── test.py            # Verifier: extracts SQL from trajectory, calls eval API
            └── test.sh            # Test runner
    """

    task_dir: str = Field(
        description="Absolute path to the pre-prepared Harbor task directory",
        exclude=True,
    )

    # -- lazy-loaded properties --------------------------------------------------

    @cached_property
    def schemas(self) -> str:
        """DDL schema, read from ``environment/business_table_list.md``."""
        p = Path(self.task_dir) / "environment" / "business_table_list.md"
        return p.read_text(encoding="utf-8") if p.is_file() else ""

    @cached_property
    def knowledges(self) -> str:
        """Domain knowledge, read from ``environment/knowledge.md``."""
        p = Path(self.task_dir) / "environment" / "knowledge.md"
        if not p.is_file():
            return ""
        return p.read_text(encoding="utf-8").strip()

    def get_dataset_dir(self) -> str:
        """Return the directory containing all task directories."""
        return str(Path(self.task_dir).parent)

    # -- construction ------------------------------------------------------------

    @classmethod
    def from_task_dir(
        cls,
        task_dir: str,
    ) -> Text2SQLDataInst:
        """Build a Text2SQLDataInst from a Harbor task directory.

        Only reads ``tests/test_data.json`` (lightweight); schema and
        knowledge files are loaded lazily on first access.
        """
        p = Path(task_dir).resolve()

        # Read test_data.json — the only file read at construction time
        test_data_path = p / "tests" / "test_data.json"
        test_data: dict = {}
        if test_data_path.is_file():
            with open(test_data_path, encoding="utf-8") as f:
                test_data = json.load(f)

        question = test_data.get("question", "")
        standard_answer = test_data.get("standard_answer", "")

        return cls(
            id=p.name,
            query=question,
            golden_answer=standard_answer,
            task_dir=str(p),
        )
