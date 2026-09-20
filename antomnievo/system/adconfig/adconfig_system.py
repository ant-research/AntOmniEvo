from __future__ import annotations

import asyncio
import json
import logging
import subprocess
from pathlib import Path
from typing import Any

from antomnievo.common.utils.trajectory_parser import parse_eddy_trajectory
from antomnievo.interface.data_inst import DataInst
from antomnievo.interface.system import System
from antomnievo.model.candidate_data import CandidateMeta
from antomnievo.model.rollout_result import RolloutResult
from antomnievo.model.system_result import SystemResult
from antomnievo.model.trajectory import Trajectory

logger = logging.getLogger(__name__)


_ADCONFIG_SYSTEM_DESCRIPTION = """\
Ad-Config Change Agent System (eddy): an eddy agent that turns a natural-language
config-change request (with an offline-replay baseline — a config baseline version
+ a source-code revision) into a structured config edit, then stops at a
human-in-the-loop gate before any release/push. The run is driven by generate.py,
which seeds the eddy RunContext from the case gold (app/env/base_config_version +
code_version) and runs the agent offline against the real prod baseline.

## Input (one case)
- `input.user_request`: the NL config-change request.
- `input.extra_context`: replay constraints — a code baseline version (git sha)
  and a config baseline version; generate.py injects them as [关键约束].
- `expected.artifact.changes[0]`: gold (config_name / base_config_version /
  target_type / target_config) — also seeds run-context app/env; NOT shown to the
  agent as the answer.

## What the agent does (tool flow)
1. `record_requirement_understanding` — parse request + replay baselines.
2. Investigate via knowledge search (`search_config_field_registry` /
   `search_adrtbcore_code` / `search_adexchange_code` / `search_source_understanding`)
   + source read (`grep_source_code` / `read_source_file` / `list_source_dir`) +
   adconfig MCP baseline read (`adconfig_getConfigList`, `adconfig_getHistoryConfigContent`
   for the real baseline at base_version). The run uses a local sandbox-transport VFS
   mapped to the project source repo at the case's code revision → the agent reads
   the real baseline and writes edits.
3. `record_evidence_proof` + `record_config_hypotheses`, then
   `finalize_textproto_change_draft` → a `textproto_edit_result` (the edited config)
   + `config_patch_draft` + `current_config_fact` + `release_ticket_payload`.
4. Stops at the HITL/release gate — `create_release_ticket` is a release action and
   is NOT auto-executed offline → run typically ends `awaiting`.

## Output (predictions.jsonl row)
- `artifact` = `{all_change_summary, changes[0]{config_name, app, env,
  base_config_version, target_type, target_config, summary}}` — selected by the
  project converter (it picks the `textproto_edit_result` from the workspace
  artifact chain); `prediction_present` = whether an artifact was produced;
  `inference.run_status` ∈ {completed, awaiting} (a HITL stop is NOT a failure).
- Absent artifact (`prediction_present=False`) when the agent blocked at
  hypotheses / couldn't read the baseline / MCP unavailable — the run still
  completes; that's a 0 / "漏改" on the evaluator, not a crash.
"""


class AdConfigSystem(System):
    """System that runs one ad-config candidate by shelling out to the business
    project's ``scripts/generate.py`` (eddy ``agent.invoke`` per case).

    Overrides ``run_batch`` to run ONE ``generate.py`` subprocess for the whole
    batch, then reads ``predictions.jsonl`` + ``trajectories.jsonl`` back and
    builds a :class:`SystemResult` per data instance.

    The candidate's tunable artifacts are loaded onto the runtime via
    ``--artifact-dir <candidate_meta.artifact_dir> --tunable <entry>...`` ("load artifact"),
    so each candidate runs as mutated tunable artifacts on the non-tunable runtime base.
    Ad-config is a write-type agent, so ``--local-sandbox-transport`` is on by
    default (maps a snapshot of the project source repo at the case's code
    revision into a writable sandbox VFS).
    """

    def __init__(
        self,
        *,
        generate_script: str,
        python_path: str,
        agent_src: str,
        tunable: list[str],
        local_source_repo: str,
        env_file: str | None = None,
        timeout: int = 1200,
        concurrency: int = 1,
        local_sandbox_transport: bool = True,
        no_install_deps: bool = True,
        extra_args: list[str] | None = None,
    ):
        """
        Args:
            generate_script: abs path to the business project's ``scripts/generate.py``.
            python_path: abs path to the business project's venv python
                (``.venv/bin/python``) — generate.py + its deps run there.
            agent_src: the runtime agent package dir passed to generate.py
                ``--agent-src`` (e.g. ``src/module_peizhiagent``).
            tunable: the agreed tunable-artifact entries (antomnievo-guidelines step 3),
                passed to generate.py as repeated ``--tunable <pkg-rel>``.
            local_source_repo: project source repo checkout for
                ``--local-source-repo`` (the case's code revision is resolved in
                it; a snapshot is exported into the local sandbox VFS).
            env_file: optional ``.env.local`` path passed via ``--env-file``
                (holds the model key + MCP identity token). ``None`` → rely on
                generate.py's default (``.env.local`` then ``.env`` relative to
                the generate.py repo root).
            timeout: per-case agent timeout (generate.py ``--timeout-seconds``).
            concurrency: case-level concurrency passed to generate.py
                (``--concurrency``); candidate-level concurrency is handled by
                the optimizer's slot semaphore, not here.
            local_sandbox_transport: pass ``--local-sandbox-transport``
                (write-type agent; default True). Set False only for a read-only
                ad-config agent that needs no writable VFS.
            no_install_deps: pass ``--no-install-deps`` — deps must be
                pre-flighted into the business venv once; this avoids per-candidate
                ``uv pip install`` write contention on the shared venv.
            extra_args: extra CLI args appended to the generate.py command.
        """
        super().__init__()
        self.generate_script = generate_script
        self.python_path = python_path
        self.agent_src = agent_src
        self.tunable = list(tunable)
        self.local_source_repo = local_source_repo
        self.env_file = env_file
        self.timeout = timeout
        self.generate_concurrency = concurrency
        self.local_sandbox_transport = local_sandbox_transport
        self.no_install_deps = no_install_deps
        self.extra_args = list(extra_args or [])

    def system_description(self) -> str:
        return _ADCONFIG_SYSTEM_DESCRIPTION

    async def _run(self, candidate_meta: CandidateMeta, data_inst: DataInst) -> SystemResult:
        # Batch-subprocess path: the optimizer calls run_batch with output_dir +
        # cases_path. Per-instance _run is intentionally unsupported.
        raise NotImplementedError(
            "AdConfigSystem runs via run_batch (one generate.py subprocess per batch). "
            "Per-instance _run is not supported — use an Optimizer subclass that threads "
            "output_dir + cases_path through run_batch."
        )

    async def run_batch(
        self,
        candidate_meta: CandidateMeta,
        data_list: list[DataInst],
        *,
        output_dir: str,
        cases_path: str,
        **kwargs,
    ) -> list[SystemResult]:
        """Run generate.py for the batch under one subprocess, then read back
        predictions + trajectories.

        The caller (an ``Optimizer`` subclass) must prepare ``cases_path``
        — a jsonl containing the FULL case rows for ``data_list`` (generate.py
        reads app/env/base_config_version from ``expected.artifact.changes``) —
        and a per-candidate ``output_dir`` (isolated per candidate per batch).
        """
        if not data_list:
            return []

        cmd = [
            self.python_path, self.generate_script,
            "--agent-src", self.agent_src,
            "--artifact-dir", candidate_meta.artifact_dir,
            "--cases", cases_path,
            "--output-dir", output_dir,
            "--concurrency", str(self.generate_concurrency),
            "--timeout-seconds", str(self.timeout),
        ]
        for ent in self.tunable:
            cmd.extend(["--tunable", ent])
        if self.local_sandbox_transport:
            cmd.extend(["--local-sandbox-transport", "--local-source-repo", self.local_source_repo])
        if self.env_file:
            cmd.extend(["--env-file", self.env_file])
        if self.no_install_deps:
            cmd.append("--no-install-deps")
        cmd.extend(self.extra_args)

        logger.info("Running ad-config generate: %s", " ".join(cmd))

        loop = asyncio.get_running_loop()
        total_timeout = self.timeout * len(data_list) + 300
        proc: subprocess.CompletedProcess | None = None
        try:
            proc = await loop.run_in_executor(
                None,
                lambda: subprocess.run(cmd, capture_output=True, timeout=total_timeout),
            )
        except subprocess.TimeoutExpired:
            logger.error("ad-config generate timed out after %ss", total_timeout)

        if proc is not None and proc.returncode != 0:
            stderr = proc.stderr.decode(errors="replace")[:3000] if proc.stderr else ""
            logger.error("ad-config generate failed rc=%s: %s", proc.returncode, stderr)

        predictions = self._read_predictions(output_dir)
        trajectories = self._read_trajectories(output_dir)

        results: list[SystemResult] = []
        for data_inst in data_list:
            case_id = str(data_inst.id)
            row = predictions.get(case_id, {})
            traj = trajectories.get(case_id, {})
            results.append(self._build_system_result(case_id, row, traj))
        return results

    # ── output readers ────────────────────────────────────────────────

    @staticmethod
    def _read_jsonl(path: Path) -> list[dict]:
        if not path.is_file():
            return []
        out: list[dict] = []
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(rec, dict):
                    out.append(rec)
        return out

    def _read_predictions(self, output_dir: str) -> dict[str, dict]:
        rows = self._read_jsonl(Path(output_dir) / "predictions.jsonl")
        return {str(r.get("case_id")): r for r in rows if r.get("case_id") is not None}

    def _read_trajectories(self, output_dir: str) -> dict[str, dict]:
        rows = self._read_jsonl(Path(output_dir) / "trajectories.jsonl")
        out: dict[str, dict] = {}
        for r in rows:
            cid = r.get("case_id")
            if cid is None:
                cid = (r.get("case") or {}).get("case_id")
            if cid is not None:
                out[str(cid)] = r
        return out

    # ── SystemResult builder ───────────────────────────────────────────

    def _build_system_result(self, case_id: str, row: dict, traj: dict) -> SystemResult:
        inf = row.get("inference") or {}
        run_status = str(inf.get("run_status") or "")
        artifact = row.get("artifact")
        artifact_source = row.get("artifact_source") or {}

        final_text = self._extract_final_text(row, traj, inf)
        content = {
            "case_id": case_id,
            "prediction_present": bool(row.get("prediction_present")),
            "run_status": run_status,
            "final_text": final_text[:4000],
            "artifact_source": artifact_source,
            "artifact_summary": self._artifact_summary(artifact),
            "error": inf.get("run_error") or inf.get("error"),
        }
        return SystemResult(
            trajectory=self._build_trajectory(case_id, traj, run_status),
            output=RolloutResult(content=json.dumps(content, ensure_ascii=False, default=str)),
            usage=None,
        )

    @staticmethod
    def _extract_final_text(row: dict, traj: dict, inf: dict) -> str:
        for src in (traj, row, inf):
            block = src.get("output")
            if isinstance(block, dict) and block.get("final_text"):
                return str(block["final_text"])
        return str(inf.get("final_text") or "")

    @staticmethod
    def _artifact_summary(artifact: Any) -> dict | None:
        if not isinstance(artifact, dict):
            return None
        # generate.py's prediction-row artifact = {all_change_summary, changes: [...]},
        # where changes[0] carries the per-change gold-shape fields
        # (config_name / app / env / base_config_version / target_type / target_config / summary).
        changes = artifact.get("changes")
        change: dict[str, Any] = {}
        if isinstance(changes, list) and changes and isinstance(changes[0], dict):
            change = changes[0]
        elif isinstance(artifact.get("payload"), dict):
            # fallback for an older payload-wrapped shape
            change = artifact["payload"]
        target_value = change.get("target_config") or change.get("target_value") or ""
        if isinstance(target_value, str) and len(target_value) > 2000:
            target_value = target_value[:2000] + "…(truncated)"
        edit_desc = change.get("edit_descriptions")
        if not edit_desc and change.get("summary"):
            edit_desc = [change["summary"]]
        return {
            "artifact_type": artifact.get("artifact_type") or change.get("artifact_type"),
            "config_name": change.get("config_name") or change.get("field_name"),
            "app": change.get("app") or change.get("app_name"),
            "env": change.get("env"),
            "base_version": change.get("base_config_version") or change.get("base_version"),
            "target_type": change.get("target_type"),
            "edit_descriptions": edit_desc,
            "all_change_summary": artifact.get("all_change_summary"),
            "n_changes": len(changes) if isinstance(changes, list) else None,
            "target_value_head": target_value,
        }

    # ── sizes ── tune these to control run_record/file size (the trajectory
    # is serialized into the candidate store for the proposer to read)
    TOOL_OUTPUT_MAX_CHARS: int = 4000
    ROOT_OUTPUT_MAX_CHARS: int = 4000
    PRE_REASONING_MAX_CHARS: int = 300

    def _build_trajectory(self, case_id: str, traj: dict, run_status: str) -> Trajectory:
        """Build an antomnievo Trajectory from an eddy agent's trajectory row, via
        :func:`parse_eddy_trajectory`. The size thresholds are class constants on
        ``AdConfigSystem`` (``TOOL_OUTPUT_MAX_CHARS`` / ``ROOT_OUTPUT_MAX_CHARS`` /
        ``PRE_REASONING_MAX_CHARS``).
        """
        tr, _stats = parse_eddy_trajectory(
            traj,
            tool_output_max_chars=self.TOOL_OUTPUT_MAX_CHARS,
            root_output_max_chars=self.ROOT_OUTPUT_MAX_CHARS,
            pre_reasoning_max_chars=self.PRE_REASONING_MAX_CHARS,
        )
        return tr
