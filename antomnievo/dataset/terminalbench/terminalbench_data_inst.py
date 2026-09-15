from __future__ import annotations

from functools import cached_property
from pathlib import Path

from pydantic import Field

from antomnievo.interface.data_inst import DataInst


def _read_text(path: Path, limit: int | None = None) -> str:
    if not path.is_file():
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    if limit is not None and len(text) > limit:
        text = text[:limit] + f"\n\n... (truncated at {limit} chars)"
    return text


class TerminalBenchDataInst(DataInst):
    """Terminal-Bench 2 data instance backed by a task directory on disk.

    Each instance corresponds to one task under
    ``terminalbench2/dataset/<task_name>/``.

    Directory layout of a task::

        <task_name>/
        ├── task.toml         # Harbor task spec (timeouts, docker image, ...)
        ├── instruction.md    # User-facing task prompt (agent input)
        ├── README.md
        ├── environment/
        │   └── Dockerfile
        ├── solution/
        │   └── solve.sh      # Reference solution (not shown to agent)
        └── tests/
            ├── test.sh       # Verifier runner
            └── test_outputs.py

    The ``golden_answer`` field stores a **verifier summary** — concatenated
    ``tests/test.sh`` and ``tests/test_outputs.py`` content — so a proposer
    doing failure analysis can see what the verifier actually checks.
    """

    task_dir: str = Field(
        description="Absolute path to the task directory under terminalbench2/dataset/",
        exclude=True,
    )

    @cached_property
    def instruction(self) -> str:
        """Full task prompt from ``instruction.md``."""
        return _read_text(Path(self.task_dir) / "instruction.md")

    @cached_property
    def task_toml(self) -> str:
        """Raw ``task.toml`` content (for debug / analysis prompts)."""
        return _read_text(Path(self.task_dir) / "task.toml")

    def get_dataset_dir(self) -> str:
        return str(Path(self.task_dir).parent)

    @classmethod
    def from_task_dir(cls, task_dir: str) -> TerminalBenchDataInst:
        """Build a TerminalBenchDataInst from a task directory.

        Reads ``instruction.md`` for ``query`` and concatenates
        ``tests/test.sh`` + ``tests/test_outputs.py`` for ``golden_answer``
        (as a verifier summary the analyzer can inspect).
        """
        p = Path(task_dir).resolve()

        query = _read_text(p / "instruction.md")

        # Verifier summary: test.sh + test_outputs.py, truncated so the
        # analyzer prompt stays bounded.
        test_sh = _read_text(p / "tests" / "test.sh", limit=4000)
        test_outputs = _read_text(p / "tests" / "test_outputs.py", limit=8000)
        verifier_parts: list[str] = []
        if test_sh:
            verifier_parts.append("=== tests/test.sh ===\n" + test_sh)
        if test_outputs:
            verifier_parts.append("=== tests/test_outputs.py ===\n" + test_outputs)
        golden_answer = "\n\n".join(verifier_parts)

        return cls(
            id=p.name,
            query=query,
            golden_answer=golden_answer,
            task_dir=str(p),
        )
