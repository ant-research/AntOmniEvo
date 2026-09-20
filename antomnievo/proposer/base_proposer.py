"""Base proposer with generic two-phase orchestration logic.

Subclasses implement the agent-specific invoke_agent() method.
"""

import asyncio
import logging
from abc import abstractmethod
from collections.abc import Callable
from datetime import datetime

from antomnievo.common.utils.fs_utils import get_latest_mtime
from antomnievo.interface.candidate_store import CandidateStore
from antomnievo.interface.evaluator import Evaluator
from antomnievo.interface.proposer import Proposer
from antomnievo.interface.system import System
from antomnievo.model.antomnievo_data import MaraChain, ProposalResult
from antomnievo.model.candidate_data import CandidateMeta, RunAnalysis, RunRecord
from antomnievo.model.candidate_data_schema import CANDIDATE_DATA_SCHEMA
from antomnievo.model.trajectory import Trajectory, merge_trajectories
from antomnievo.model.tunable_artifact_schema import TunableArtifactSchema, render_tunable_artifact_schema
from antomnievo.model.usage_stats import UsageStats
from antomnievo.proposer.template import (
    ANALYSIS_PROMPT_TEMPLATE,
    PROPOSER_PROMPT_TEMPLATE,
    REFLECTION_ANALYSIS_PROMPT_TEMPLATE,
)
from antomnievo.proposer.utils.reflection_utils import (
    build_attributed_changelog,
    preload_chain_analyses_for_data_id,
)
from antomnievo.proposer.utils.trajectory_utils import check_trajectory_issues

_MTIME_EPS = 1e-6
_SCRIPT_VALIDATE_ANALYSIS = "validate-analysis"
_SCRIPT_APPEND_CHANGELOG = "append-changelog"
_MAX_DIFF_CHARS_IN_PROMPT = 3000
_MAX_UNANALYZED_RUNS = 10
_PERFECT_SCORE = 1.0

logger = logging.getLogger(__name__)


class BaseProposer(Proposer):
    """Generic two-phase proposer: analyze runs, then mutate the tunable artifacts.

    Subclasses must implement invoke_agent() to provide the coding agent
    invocation (e.g. Claude Code, Pi Coding Agent, etc.).
    """

    def __init__(
        self,
        tunable_artifact_schema: TunableArtifactSchema,
        candidate_store: CandidateStore,
        evaluator: Evaluator,
        system: System | None = None,
        data_schema: TunableArtifactSchema = CANDIDATE_DATA_SCHEMA,
        concurrency: int = 2,
        skip_perfect_score_runs: bool = False,
        last_n_analysis: int | None = None,
    ):
        """Initialize the proposer.

        Args:
            tunable_artifact_schema: Schema defining the tunable-artifact directory structure and constraints.
            candidate_store: Store for reading/writing candidate data.
            evaluator: Evaluator for scoring criteria.
            system: Optional system instance for system description.
            data_schema: Schema for candidate data directory.
            concurrency: Maximum number of concurrent analysis agents.
            skip_perfect_score_runs: If True, skip analysis of runs with score 1.0.
                For probabilistic systems (e.g. LLM-based), a perfect-score run
                may still contain fragile reasoning that could break on re-runs;
                analyzing it could reinforce the correct pattern and increase the
                probability of consistent success. For deterministic systems, a
                perfect-score run reliably reproduces and can be safely skipped.
            last_n_analysis: If set, only pass the most recent N analysis entries
                to the mutator. Limits context size and avoids older
                analyses that may be incorrect or misleading from trapping the
                candidate in a cycle where it never improves.
                Should be >= batch_size so that the mutator always sees at least
                one full batch of fresh analyses from the latest evaluation round.
        """
        self.concurrency = concurrency
        self._sem = asyncio.Semaphore(concurrency)
        self.candidate_store = candidate_store
        self.tunable_artifact_schema = tunable_artifact_schema
        self.evaluator = evaluator
        self.system = system
        self.data_schema = data_schema
        self.skip_perfect_score_runs = skip_perfect_score_runs
        self.last_n_analysis = last_n_analysis

    @abstractmethod
    async def invoke_agent(self, prompt: str, cwd: str) -> tuple[Trajectory, UsageStats]:
        """Invoke the coding agent and return (trajectory, usage_stats).

        Subclasses implement this to call their specific agent CLI/SDK,
        parse the output, and return a Trajectory + UsageStats.
        """
        ...

    # ── Public interface ─────────────────────────────────────────────

    async def propose(
        self,
        parent_candidate_id: str,
        new_candidate_id: str,
    ) -> ProposalResult:
        """Phase 1 + 2: Analyze unanalyzed runs and propose tunable-artifact modifications."""
        start_time = datetime.now()
        parent_meta = self.candidate_store.get_meta(parent_candidate_id)
        new_meta = self.candidate_store.get_meta(new_candidate_id)
        if parent_meta is None or new_meta is None:
            missing = "parent" if parent_meta is None else "new"
            return ProposalResult(success=False, error_message=f"{missing} candidate not found in store")

        analyze_result = await self.analyze(parent_candidate_id, new_candidate_id)
        if not analyze_result.success:
            logger.error(f"Phase 1 (Analysis) failed: {analyze_result.error_message}")
            return analyze_result

        mutate_result = await self._mutate(parent_candidate_id, new_candidate_id)

        # Merge stats from both phases
        merged = UsageStats()
        merged.add(analyze_result.stats)
        merged.add(mutate_result.stats)

        logger.info(
            f"Phase 1 + 2 (Analysis + Propose): completed for candidate {new_candidate_id}, "
            f"duration {(datetime.now() - start_time).total_seconds():.1f}s"
            + (f", tokens={merged.input_tokens + merged.output_tokens}" if merged else "")
        )
        return ProposalResult(success=mutate_result.success, stats=merged, error_message=mutate_result.error_message)

    # ── Phase 1: Analysis ────────────────────────────────────────────

    async def analyze(
        self,
        parent_candidate_id: str,
        new_candidate_id: str,
    ) -> ProposalResult:
        """Phase 1: Analyze unanalyzed runs and write analysis results.

        Public default implementation of ``Proposer.analyze`` — business entry
        points can call this directly to run only the analysis phase.
        """
        return await self._run_analysis_pipeline(
            parent_candidate_id=parent_candidate_id,
            new_candidate_id=new_candidate_id,
            prompt_builder=lambda data_id, run_file_paths, candidate_id: self._build_analysis_prompt(
                data_id=data_id,
                run_file_paths=run_file_paths,
                candidate_id=candidate_id,
            ),
            phase_label="Analysis",
        )

    async def _run_analysis_pipeline(
        self,
        parent_candidate_id: str,
        new_candidate_id: str,
        prompt_builder: Callable[[str, list[str], str], str],
        phase_label: str,
    ) -> ProposalResult:
        """Shared core of Phase 1: discover unanalyzed runs, build prompts via prompt_builder, invoke agent.

        ``prompt_builder`` takes (data_id, run_file_paths, parent_candidate_id) and returns the prompt string.
        ``phase_label`` is used for logging (e.g. "Analysis" or "Reflection-Analysis").
        """
        start_time = datetime.now()

        run_groups = self.candidate_store.find_unanalyzed_runs(parent_candidate_id)

        run_groups = self._apply_run_filters(parent_candidate_id, run_groups, phase_label)

        if not run_groups:
            logger.info(f"Phase 1 ({phase_label}): no unanalyzed runs, skipping for candidate {new_candidate_id}")
            return ProposalResult(success=True)

        parent_meta = self.candidate_store.get_meta(parent_candidate_id)

        total_runs = sum(len(v) for v in run_groups.values())
        logger.info(
            f"Phase 1 ({phase_label}): {total_runs} unanalyzed runs in "
            f"{len(run_groups)} data_id groups for candidate {parent_candidate_id}"
        )

        all_trajectories: list[Trajectory] = []
        all_stats: list[UsageStats] = []
        data_ids_ok = 0
        data_ids_fail = 0
        first_fatal_error: str | None = None

        async def _process(data_id: str, run_names: list[str]) -> tuple[Trajectory, UsageStats] | None:
            logger.info(f"Phase 1 ({phase_label}): processing data_id={data_id} ({len(run_names)} run(s))")
            try:
                return await self._analyze_single_data_id(
                    parent_meta=parent_meta,
                    data_id=data_id,
                    run_names=run_names,
                    prompt_builder=prompt_builder,
                    phase_label=phase_label,
                )
            except Exception as e:
                logger.error(
                    f"Phase 1 ({phase_label}): failed for data_id={data_id}: {e}",
                    exc_info=True,
                )
                return None

        results = await asyncio.gather(
            *[_process(data_id, run_names) for data_id, run_names in run_groups.items()]
        )
        for (data_id, _run_names), result in zip(run_groups.items(), results, strict=False):
            if result is None:
                data_ids_fail += 1
                continue
            trajectory, stats = result
            all_trajectories.append(trajectory)
            all_stats.append(stats)
            if trajectory.errors:
                # LLM call failed (e.g. antchat 401). The trajectory is still
                # saved below so the failure is reconstructable; count it as
                # failed and surface the first error.
                data_ids_fail += 1
                if first_fatal_error is None:
                    first_fatal_error = trajectory.errors[0]
                logger.error(
                    f"Phase 1 ({phase_label}): data_id={data_id} LLM call failed: "
                    f"{trajectory.errors[0][:160]}"
                )
            else:
                data_ids_ok += 1

        if all_trajectories:
            combined = merge_trajectories(all_trajectories)
            self.candidate_store.save_analysis_trajectory(
                parent_candidate_id, new_candidate_id, combined
            )

        aggregated = UsageStats()
        for s in all_stats:
            aggregated.add(s)

        logger.info(
            f"Phase 1 ({phase_label}): {data_ids_ok} succeeded, {data_ids_fail} failed, "
            f"duration {(datetime.now() - start_time).total_seconds():.1f}s, "
            f"tokens={aggregated.input_tokens + aggregated.output_tokens}"
        )
        if data_ids_fail > 0:
            if first_fatal_error:
                # LLM call failure (e.g. antchat 401) — surface the real cause
                # instead of a generic "N data_id(s) failed" that hides it.
                return ProposalResult(
                    success=False,
                    error_message=f"{data_ids_fail} data_id(s) failed analysis; LLM call failed: {first_fatal_error[:200]}",
                    stats=aggregated,
                )
            return ProposalResult(success=False, error_message=f"{data_ids_fail} data_id(s) failed analysis", stats=aggregated)
        return ProposalResult(success=True, stats=aggregated)

    async def _analyze_single_data_id(
        self,
        parent_meta: CandidateMeta,
        data_id: str,
        run_names: list[str],
        prompt_builder: Callable[[str, list[str], str], str],
        phase_label: str,
    ) -> tuple[Trajectory, UsageStats]:
        """Analyze runs for a single data_id: build prompt via prompt_builder, invoke agent."""
        run_file_paths = [
            self.candidate_store.run_file_path(parent_meta.candidate_id, data_id, name)
            for name in run_names
        ]
        prompt = prompt_builder(data_id, run_file_paths, parent_meta.candidate_id)

        trajectory, stats = await self.invoke_agent(prompt, parent_meta.data_dir)
        check_trajectory_issues(trajectory, phase=f"{phase_label}/{data_id}")

        return trajectory, stats

    def _filter_perfect_score_runs(
        self,
        candidate_id: str,
        run_groups: dict[str, list[str]],
        max_runs: int,
    ) -> dict[str, list[str]]:
        """Filter out perfect-score runs when total exceeds max_runs.

        Removes runs with score == 1.0 until the total count drops to
        max_runs or no more perfect-score runs remain.
        """
        total = sum(len(v) for v in run_groups.values())
        if total <= max_runs:
            return run_groups

        def _key(data_id: str, run_name: str) -> str:
            """Unique key for a run, used for tracking which runs to remove."""
            return f'{data_id}/{run_name}'

        to_remove: set[str] = set()
        for data_id, run_names in run_groups.items():
            if total - len(to_remove) <= max_runs:
                break
            for run_name in run_names:
                if total - len(to_remove) <= max_runs:
                    break
                score = self.candidate_store.get_run_score(candidate_id, data_id, run_name)
                # missing score or perfect score counts as 1.0 for removal purposes, since we want to prioritize analyzing any runs that have a chance of containing issues
                if score is None or score >= _PERFECT_SCORE - _MTIME_EPS:
                    to_remove.add(_key(data_id, run_name))

        if not to_remove:
            return run_groups

        filtered: dict[str, list[str]] = {}
        for data_id, run_names in run_groups.items():
            kept = [name for name in run_names if _key(data_id, name) not in to_remove]
            if kept:
                filtered[data_id] = kept
        return filtered

    def _apply_run_filters(
        self,
        candidate_id: str,
        run_groups: dict[str, list[str]],
        phase_label: str,
    ) -> dict[str, list[str]]:
        """Apply perfect-score and max-run filters with logging.

        Two-stage filter:
          1. If ``skip_perfect_score_runs`` is set, remove all perfect-score runs.
          2. If the remaining count exceeds ``_MAX_UNANALYZED_RUNS``, remove
             perfect-score runs until at most ``_MAX_UNANALYZED_RUNS`` remain.
        """
        if self.skip_perfect_score_runs:
            total_before = sum(len(v) for v in run_groups.values())
            run_groups = self._filter_perfect_score_runs(candidate_id, run_groups, 0)
            filtered_total = sum(len(v) for v in run_groups.values())
            if filtered_total < total_before:
                logger.info(
                    f"Phase 1 ({phase_label}): skipped perfect-score runs: {total_before} -> {filtered_total}"
                )

        total_runs = sum(len(v) for v in run_groups.values())
        if total_runs > _MAX_UNANALYZED_RUNS:
            run_groups = self._filter_perfect_score_runs(
                candidate_id, run_groups, _MAX_UNANALYZED_RUNS
            )
            filtered_total = sum(len(v) for v in run_groups.values())
            logger.info(
                f"Phase 1 ({phase_label}): {total_runs} unanalyzed runs exceeds {_MAX_UNANALYZED_RUNS}, "
                f"filtered out perfect-score runs: {total_runs} -> {filtered_total}"
            )

        return run_groups

    # ── Phase 2: Mutation ────────────────────────────────────────────

    async def _mutate(
        self,
        parent_candidate_id: str,
        new_candidate_id: str,
    ) -> ProposalResult:
        """Phase 2: Read analysis and propose tunable-artifact modifications."""
        parent_meta = self.candidate_store.get_meta(parent_candidate_id)
        new_meta = self.candidate_store.get_meta(new_candidate_id)
        propose_prompt = self._build_propose_prompt(parent_meta, new_meta)
        return await self._run_mutation_pipeline(
            parent_candidate_id=parent_candidate_id,
            new_candidate_id=new_candidate_id,
            prompt=propose_prompt,
            phase_label="Propose",
        )

    async def _run_mutation_pipeline(
        self,
        parent_candidate_id: str,
        new_candidate_id: str,
        prompt: str,
        phase_label: str,
    ) -> ProposalResult:
        """Shared core of Phase 2: invoke agent in the new tunable-artifact dir, persist trajectory, check mtime."""
        start_time = datetime.now()
        new_meta = self.candidate_store.get_meta(new_candidate_id)

        try:
            mtime_before = get_latest_mtime(new_meta.artifact_dir)
            logger.info(f"Phase 2 ({phase_label}): invoking propose agent in {new_meta.artifact_dir}")
            trajectory, stats = await self.invoke_agent(prompt, new_meta.artifact_dir)
            mtime_after = get_latest_mtime(new_meta.artifact_dir)

            check_trajectory_issues(trajectory, phase=phase_label)
            # Persist the trajectory FIRST, even on fatal LLM errors, so the
            # failure (with its error spans) is reconstructable on disk. This
            # must happen before raising below — otherwise a 401/5xx aborts the
            # run and we lose the only record of what went wrong.
            self.candidate_store.save_propose_trajectory(
                parent_candidate_id, new_candidate_id, trajectory
            )

            if trajectory.errors:
                # The LLM call itself failed (e.g. antchat 401 服务未授权, 5xx,
                # rate limit). Surface the real cause instead of the misleading
                # "No tunable-artifact files were modified" — the agent never got to run.
                err = trajectory.errors[0]
                logger.error(f"Phase 2 ({phase_label}): LLM call failed: {err[:200]}")
                return ProposalResult(
                    success=False,
                    error_message=f"LLM call failed (stopReason=error): {err[:300]}",
                    stats=stats,
                )

            if mtime_after <= mtime_before + _MTIME_EPS:
                return ProposalResult(success=False, error_message="No tunable-artifact files were modified", stats=stats)

            return ProposalResult(success=True, stats=stats)
        except Exception as e:
            logger.error(f"Phase 2 ({phase_label}) failed: {e}", exc_info=True)
            return ProposalResult(success=False, error_message=str(e))
        finally:
            logger.info(f"Phase 2 ({phase_label}): completed for candidate {new_candidate_id}, duration {(datetime.now() - start_time).total_seconds():.1f}s")

    # ── Prompt builders ──────────────────────────────────────────────

    def _build_analysis_prompt(
        self,
        data_id: str,
        run_file_paths: list[str],
        candidate_id: str,
    ) -> str:
        """Build the analysis prompt for a single data_id."""
        paths_text = "\n".join(f"- {p}" for p in run_file_paths)

        return ANALYSIS_PROMPT_TEMPLATE.format(
            data_id=data_id,
            run_file_paths=paths_text,
            artifact_dir=self.candidate_store.artifact_dir(candidate_id),
            analysis_result_path=self.candidate_store.analysis_result_path(candidate_id, data_id),
            validate_script=_SCRIPT_VALIDATE_ANALYSIS,
            current_timestamp=datetime.now().isoformat(timespec="seconds"),
            scoring_criteria=self.evaluator.scoring_criteria(),
            system_description=self.system.system_description() if self.system else "",
            tunable_artifact_schema=render_tunable_artifact_schema(self.tunable_artifact_schema),
            run_analysis_schema=RunAnalysis.to_description(),
            run_record_schema=RunRecord.to_description(),
            changelog_path=self.candidate_store.changelog_path(candidate_id),
        )

    def _build_propose_prompt(
        self,
        parent_meta: CandidateMeta,
        new_meta: CandidateMeta,
    ) -> str:
        """Build the propose prompt."""
        analysis_content = self.candidate_store.read_all_analysis_json_content(
            parent_meta.candidate_id, last_n=self.last_n_analysis
        )

        return PROPOSER_PROMPT_TEMPLATE.format(
            tunable_artifact_schema=render_tunable_artifact_schema(self.tunable_artifact_schema),
            data_schema=render_tunable_artifact_schema(self.data_schema),
            analysis_content=analysis_content,
            parent_data_dir=parent_meta.data_dir,
            new_artifact_dir=new_meta.artifact_dir,
            new_data_dir=new_meta.data_dir,
            parent_artifact_dir=parent_meta.artifact_dir,
            append_changelog_script=_SCRIPT_APPEND_CHANGELOG,
        )

    # ── Reflection ───────────────────────────────────────────────────

    async def reflect(
        self,
        chain: MaraChain,
        new_candidate_id: str,
    ) -> ProposalResult:
        """Reflection-mode propose. See ``Proposer.reflect`` for the contract.

        Reuses the same analysis and mutation pipelines as normal propose,
        with reflection-specific prompts that inject chain context (score
        history, changelog, prior analyses) into the agent.
        """
        start_time = datetime.now()
        parent_meta = self.candidate_store.get_meta(chain.last.candidate_id)
        new_meta = self.candidate_store.get_meta(new_candidate_id)
        if parent_meta is None or new_meta is None:
            missing = "parent" if parent_meta is None else "new"
            return ProposalResult(success=False, error_message=f"{missing} candidate not found in store")

        # Phase 1: Reflection analysis — reuses _run_analysis_pipeline with
        # a reflection-specific prompt builder that preloads chain context.
        def _reflection_analysis_prompt_builder(
            data_id: str, run_file_paths: list[str], _: str
        ) -> str:
            chain_analyses = preload_chain_analyses_for_data_id(
                chain.nodes, data_id, self.candidate_store
            )
            score_row = chain.format_score_history_table(data_id)
            return self._build_reflection_analysis_prompt(
                chain=chain,
                data_id=data_id,
                run_file_paths=run_file_paths,
                chain_analyses_for_data_id=chain_analyses,
                score_history_row=score_row,
            )

        analyze_result = await self._run_analysis_pipeline(
            parent_candidate_id=chain.last.candidate_id,
            new_candidate_id=new_candidate_id,
            prompt_builder=_reflection_analysis_prompt_builder,
            phase_label=f"Reflection-Analysis iter={chain.depth}",
        )
        if not analyze_result.success:
            logger.error(f"Reflection Phase 1 failed: {analyze_result.error_message}")
            return analyze_result

        # Phase 2: Mutation — reuses the same _mutate pipeline as normal propose.
        # The reflection analysis already incorporates chain context (score
        # history, changelog, prior analyses), so the propose prompt doesn't
        # need extra chain information.
        mutate_result = await self._mutate(
            parent_candidate_id=chain.last.candidate_id,
            new_candidate_id=new_candidate_id,
        )

        merged = UsageStats()
        merged.add(analyze_result.stats)
        merged.add(mutate_result.stats)

        logger.info(
            f"Reflection (iter {chain.depth}): completed for candidate {new_candidate_id}, "
            f"duration {(datetime.now() - start_time).total_seconds():.1f}s"
            + (f", tokens={merged.input_tokens + merged.output_tokens}" if merged else "")
        )
        return ProposalResult(success=mutate_result.success, stats=merged, error_message=mutate_result.error_message)

    def _build_reflection_analysis_prompt(
        self,
        chain: MaraChain,
        data_id: str,
        run_file_paths: list[str],
        chain_analyses_for_data_id: str,
        score_history_row: str,
    ) -> str:
        paths_text = "\n".join(f"- {p}" for p in run_file_paths)
        # Analysis written by this iteration lands under the LAST chain candidate
        # (same convention as normal propose: "analysis lives under the candidate
        # being analyzed").
        last_candidate_id = chain.last.candidate_id
        chain_id_path = chain.format_id_path()
        attributed_changelog = build_attributed_changelog(
            chain.nodes, self.candidate_store, _MAX_DIFF_CHARS_IN_PROMPT
        )

        # Collect the latest run file path from each earlier chain candidate
        # (exclude the last one, whose runs are already listed under "Run Files").
        # Only one file per candidate to keep prompt size bounded — the latest
        # run is the most representative. These are used for cross-candidate
        # comparison in Method 2 (Success Extraction) and Method 4
        # (Inconsistency Pattern Discovery).
        chain_candidate_paths_lines: list[str] = []
        for node in chain.nodes[:-1]:
            cid = node.candidate_id
            latest = self.candidate_store.latest_run_file(cid, data_id)
            if latest is not None:
                chain_candidate_paths_lines.append(f"- {latest}  ({cid})")
        chain_candidate_paths_text = (
            "\n".join(chain_candidate_paths_lines)
            if chain_candidate_paths_lines
            else "(no run files available from earlier chain candidates)"
        )

        return REFLECTION_ANALYSIS_PROMPT_TEMPLATE.format(
            data_id=data_id,
            run_file_paths=paths_text,
            chain_candidate_run_file_paths=chain_candidate_paths_text,
            artifact_dir=self.candidate_store.artifact_dir(last_candidate_id),
            analysis_result_path=self.candidate_store.analysis_result_path(
                last_candidate_id, data_id
            ),
            validate_script=_SCRIPT_VALIDATE_ANALYSIS,
            current_timestamp=datetime.now().isoformat(timespec="seconds"),
            scoring_criteria=self.evaluator.scoring_criteria(),
            system_description=self.system.system_description() if self.system else "",
            tunable_artifact_schema=render_tunable_artifact_schema(self.tunable_artifact_schema),
            run_analysis_schema=RunAnalysis.to_description(),
            run_record_schema=RunRecord.to_description(),
            changelog_path=self.candidate_store.changelog_path(last_candidate_id),
            original_parent_id=chain.root.candidate_id,
            last_candidate_id=last_candidate_id,
            reflection_depth=chain.depth,
            chain_id_path=chain_id_path,
            attributed_changelog=attributed_changelog,
            chain_analyses_for_data_id=chain_analyses_for_data_id,
            score_history_row=score_history_row,
        )
