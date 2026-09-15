from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import subprocess
from pathlib import Path

from antomnievo.common.utils.concurrency_pool import ConcurrencyPool
from antomnievo.common.utils.trajectory_parser import parse_pi_json_output, parse_stream_json
from antomnievo.interface.data_inst import DataInst
from antomnievo.interface.system import System
from antomnievo.model.candidate_data import CandidateMeta
from antomnievo.model.rollout_result import RolloutResult
from antomnievo.model.system_result import SystemResult
from antomnievo.model.trajectory import Trajectory
from antomnievo.model.usage_stats import UsageStats

logger = logging.getLogger(__name__)

BIRD_SEPARATOR = "\t----- bird -----\t"

_TEXT2SQL_SYSTEM_DESCRIPTION = """\
NL2SQL Agent System:

A pi agent that converts natural language questions to SQL queries,
with the ability to interactively query the database to verify results.

## Agent Input Format (User Prompt)

The user prompt is a JSON object:

```json
{
  "output_file": "/path/to/predictions/{qid}.sql",
  "database": "<db_id>",
  "schema": "CREATE TABLE `table1` ( ... );\\nCREATE TABLE `table2` ( ... );",
  "question": "<natural language question>",
  "knowledge": "<domain mappings>"  // optional
}
```

## Agent Tools

The agent has access to:
- `query-db --db <db_id> --sql "<SQL>"`: Execute SQL query directly
- `query-db --db <db_id> --file <path>`: Execute SQL from a .sql file
- `query-db --limit N`: Max rows to return (default: 20)
- `query-db --json`: Output raw JSON instead of formatted table
- File read (skill directory only) and file write (output SQL file only)

## Output

The agent writes a single SQL query to the output file. The SQL must be directly executable against the database.
"""

def _load_trace_raw(trace_path: Path) -> str:
    """Load trace file and return NDJSON string.

    Handles both JSON array format and newline-delimited JSON.
    """
    with trace_path.open("r", encoding="utf-8") as f:
        raw = f.read().strip()

    if raw.startswith("["):
        with contextlib.suppress(json.JSONDecodeError):
            events = json.loads(raw)
            return "\n".join(json.dumps(ev, ensure_ascii=False) for ev in events)
    return raw


_TRACE_PARSERS = {
    "claude": parse_stream_json,
    "pi": parse_pi_json_output,
}


def _parse_trace_file(
    trace_path: Path, agent_type: str = "claude",
) -> tuple[Trajectory, UsageStats | None]:
    """Parse a trace file into a Trajectory and UsageStats."""
    raw = _load_trace_raw(trace_path)
    parser = _TRACE_PARSERS.get(agent_type, parse_stream_json)
    trajectory, stats = parser(raw)
    return trajectory, stats


class Text2SQLSystem(System):
    """System that generates SQL predictions via a generate subprocess.

    Works with both BirdTest and Spider2Snow backends — the caller provides
    the appropriate generate_script, python_path, and any extra CLI args.
    """

    MAX_TOTAL_CONCURRENCY: int = 60
    _pool: ConcurrencyPool | None = None
    _pool_lock = asyncio.Lock()

    @classmethod
    def set_max_total_concurrency(cls, total: int) -> None:
        if cls._pool is not None:
            raise RuntimeError(
                "Cannot change MAX_TOTAL_CONCURRENCY after the pool has been created"
            )
        cls.MAX_TOTAL_CONCURRENCY = total

    @classmethod
    async def _get_pool(cls) -> ConcurrencyPool:
        async with cls._pool_lock:
            if cls._pool is None:
                cls._pool = ConcurrencyPool(cls.MAX_TOTAL_CONCURRENCY)
        return cls._pool

    def __init__(
        self,
        generate_script: str,
        python_path: str,
        model: str = "kimi-k2.5",
        timeout: int = 3000,
        concurrency: int = 1,
        api_key: str | None = None,
        base_url: str | None = None,
        agent_type: str = "pi",
        extra_args: list[str] | None = None,
    ):
        """
        Args:
            generate_script: Path to generate.py script.
            python_path: Path to venv python executable.
            model: Model name.
            timeout: Timeout per question in seconds.
            concurrency: Max number of parallel generation tasks.
            api_key: API key.
            base_url: API base URL.
            agent_type: Agent backend type, "claude" or "pi".
            extra_args: Additional CLI args appended to the subprocess command.
        """
        super().__init__()
        self.generate_script = generate_script
        self.python_path = python_path
        self.model = model
        self.timeout = timeout
        self.generate_concurrency = concurrency
        self.api_key = api_key
        self.base_url = base_url
        self.agent_type = agent_type
        self.extra_args = extra_args or []

    def system_description(self) -> str:
        return _TEXT2SQL_SYSTEM_DESCRIPTION

    async def _run(self, candidate_meta: CandidateMeta, data_inst: DataInst) -> SystemResult:
        pass

    async def run_batch(
        self,
        candidate_meta: CandidateMeta,
        data_list: list[DataInst],
        *,
        output_dir: str,
        contexts_path: str,
        **kwargs,
    ) -> list[SystemResult]:
        """Run generate_predictions via subprocess for a batch of data items."""
        skill_dir = os.path.join(candidate_meta.spec_dir, "skill")
        extensions_dir = os.path.join(candidate_meta.spec_dir, "extensions")

        cmd = [
            self.python_path, self.generate_script,
            "--contexts", contexts_path,
            "--output_dir", output_dir,
            "--skill_dir", skill_dir,
            "--model", self.model,
            "--timeout", str(self.timeout),
            "--concurrency", str(self.generate_concurrency),
            "--no-resume",
            "--agent", self.agent_type,
        ]
        if self.api_key:
            cmd.extend(["--api-key", self.api_key])
        if self.base_url:
            cmd.extend(["--base-url", self.base_url])

        if os.path.isdir(extensions_dir):
            for fname in sorted(os.listdir(extensions_dir)):
                if fname.endswith(".ts"):
                    cmd.extend(["--extension", os.path.join(extensions_dir, fname)])

        cmd.extend(self.extra_args)

        logger.info(f"Running text2sql generate: {' '.join(cmd)}")

        slots = min(self.generate_concurrency, len(data_list), self.MAX_TOTAL_CONCURRENCY)
        pool = await self._get_pool()
        loop = asyncio.get_running_loop()
        async with pool.slot(slots):
            result = await loop.run_in_executor(
                None,
                lambda: subprocess.run(cmd, capture_output=True, timeout=self.timeout * len(data_list) + 300),
            )

        if result.returncode != 0:
            stderr_msg = result.stderr.decode(errors="replace")[:3000] if result.stderr else ""
            logger.error(f"text2sql generate failed (rc={result.returncode}): {stderr_msg}")

        predictions = self._read_predictions(output_dir)
        trace_dir = Path(output_dir) / "traces"

        results: list[SystemResult] = []
        for data_inst in data_list:
            qid = str(data_inst.id)

            sql_content = ""
            if qid in predictions:
                raw = predictions[qid]
                if BIRD_SEPARATOR in raw:
                    sql_content = raw.split(BIRD_SEPARATOR, 1)[0].strip()
                else:
                    sql_content = raw.strip()

            trajectory = Trajectory(root_span_list=[])
            usage = None
            trace_file = trace_dir / f"{qid}.json"
            if trace_file.is_file():
                try:
                    trajectory, usage = _parse_trace_file(trace_file, self.agent_type)
                except Exception as e:
                    logger.warning(f"Failed to parse trace for qid={qid}: {e}", exc_info=True)

            results.append(SystemResult(
                trajectory=trajectory,
                output=RolloutResult(content=sql_content),
                usage=usage,
            ))

        return results

    @staticmethod
    def _read_predictions(output_dir: str) -> dict[str, str]:
        pred_path = Path(output_dir) / "predictions.json"
        if not pred_path.is_file():
            return {}
        try:
            with pred_path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to read predictions.json: {e}")
            return {}
