import asyncio
import logging
import time
from contextlib import AbstractContextManager, nullcontext
from datetime import datetime

from antomnievo.common.utils.param_utils import extract_params
from antomnievo.interface.candidate_store import CandidateStore
from antomnievo.interface.data_inst import DataInst
from antomnievo.interface.evaluator import Evaluator
from antomnievo.interface.evolution_algorithm import EvolutionAlgorithm
from antomnievo.interface.proposer import Proposer
from antomnievo.interface.system import System
from antomnievo.model.antomnievo_data import (
    SCORE_EPS,
    AcceptedCandidate,
    ChainNode,
    IterationRecord,
    MaraChain,
    ProposalOutcome,
    ProposalTask,
    RolloutEvalResult,
    build_iteration_record,
)
from antomnievo.model.budget import Budget, BudgetUsage
from antomnievo.model.candidate_data import CandidateMeta, RunRecord
from antomnievo.model.evaluation_result import EvaluationResult
from antomnievo.model.system_result import SystemResult
from antomnievo.model.usage_stats import UsageStats

logger = logging.getLogger(__name__)

class Optimizer:
    """Evolutionary optimization loop for agent spec improvement.

    Uses a candidate-pool / parallel-slot scheduler. Up to ``num_proposals``
    candidates evolve concurrently, each consuming its own (epoch, dataset_index)
    progress slice of ``train_dataset``. Slots are scheduled by a single asyncio
    loop guarded by an ``asyncio.Semaphore(num_proposals)``.

    Lifecycle states (on ``CandidateMeta.state``):
      - 'pending'     — evaluated, in the pool, selectable by the EA.
      - 'evolving'    — currently occupying a slot.
      - 'unavailable' — either a pre-validation child or a retired candidate.

    Supports checkpoint resume: if candidates already exist on disk, baseline
    creation is skipped and any candidate found in 'evolving' state is reset to
    'pending' (its prior slot was lost when the process died).
    """

    def __init__(
        self,
        system: System,
        proposer: Proposer,
        evaluator: Evaluator,
        evolution_algorithm: EvolutionAlgorithm,
        candidate_store: CandidateStore,
        train_dataset: list[DataInst],
        val_dataset: list[DataInst],
        batch_size: int = 3,
        budget: Budget | None = None,
        num_proposals: int = 1,
        max_reflection_iterations: int = 0,
        min_improvement_per_batch: float = 0.0,
        initial_spec_dir: str | None = None,
    ):
        """
        Args:
            system: The system to optimize. Runs on each data instance and produces outputs.
            proposer: Generates mutated candidate specs from existing ones. Uses candidate_store
                internally to resolve candidate IDs to metadata. The proposer's own
                ``concurrency`` should be >= ``num_proposals`` for the parallelism to
                actually take effect — otherwise slots queue on the proposer's semaphore.
            evaluator: Scores system outputs against ground truth labels.
            evolution_algorithm: Selects candidates for mutation and eliminates weak ones
                (e.g. ParetoFrontierEvolutionAlgorithm). Operates only on 'pending'
                candidates — 'evolving' parents are never re-selected or eliminated.
            candidate_store: Filesystem-backed storage for candidate specs, run records,
                analysis, changelogs, and summaries. Configure cleanup behavior via
                ``CandidateStore(cleanup_unavailable=...)`` at construction time.
            train_dataset: Data instances used for rollout evaluation during each iteration.
                Each candidate carries its own (epoch, dataset_index) cursor; when selected
                for a slot, it consumes ``batch_size`` items starting at its
                ``dataset_index`` (or the tail-aligned ``train[n - batch_size : n]`` slice
                when the cursor is near the end, after which epoch+1 / index=0).
            val_dataset: Data instances used for validation after a candidate is accepted.
                Scores on this set determine the official avg_score.
            batch_size: Number of training instances per slot occupation.
            budget: Hard caps for the run (:class:`~antomnievo.model.budget.Budget`):
                ``max_iterations`` (slot occupations), ``max_rollouts`` (cumulative
                TRAINING data instances run; val/baseline excluded),
                ``max_system_runs`` (cumulative data instances run across ALL
                splits), ``max_tokens`` (cumulative input+output tokens across all
                phases), ``max_elapsed_seconds`` (wall-clock). Any field left
                ``None`` means unlimited on that axis. The loop opens no new slots
                once ANY set limit is reached; in-flight slots drain. ``None``
                (default) means no global cap — the loop then stops only when the
                evolution algorithm has no selectable candidate.
            num_proposals: Maximum number of candidates evolving concurrently. Each
                in-flight slot occupies one semaphore permit.
            max_reflection_iterations: When > 0, enables reflection iterations. If a proposed
                child does not clear the per-batch improvement threshold (see
                ``min_improvement_per_batch``), the optimizer creates up to this many
                additional reflection-mode children chained off the previous failure.
                The best-scoring reflection child that beats the original parent on the
                batch is then forwarded to validation. 0 disables the feature.
            min_improvement_per_batch: Required absolute batch score improvement
                (``new_sum - old_sum``) to accept a child without entering the mara
                chain. 0.0 keeps the legacy "any positive delta" behavior.
        """
        self.system = system
        self.proposer = proposer
        self.evaluator = evaluator
        self.ea = evolution_algorithm
        self.candidate_store = candidate_store
        self.train_dataset = train_dataset
        self.val_dataset = val_dataset
        self.batch_size = batch_size
        self.budget = budget
        self.num_proposals = num_proposals
        self.statistics = candidate_store.get_statistics()
        self.max_reflection_iterations = max_reflection_iterations
        self.min_improvement_per_batch = min_improvement_per_batch
        self.initial_spec_dir = initial_spec_dir

        candidate_store.append_parameters({
            "start_time": datetime.now().isoformat(),
            "system": system.name,
            "system_params": extract_params(system),
            "proposer": proposer.name,
            "proposer_params": extract_params(proposer),
            "evaluator": evaluator.name,
            "evaluator_params": extract_params(evaluator),
            "evolution_algorithm": evolution_algorithm.name,
            "evolution_algorithm_params": extract_params(evolution_algorithm),
            "data_inst": train_dataset[0].name,
            "batch_size": batch_size,
            "budget": budget.model_dump() if budget is not None else None,
            "num_proposals": num_proposals,
            "max_reflection_iterations": max_reflection_iterations,
            "min_improvement_per_batch": min_improvement_per_batch,
            "train_dataset_size": len(train_dataset),
            "val_dataset_size": len(val_dataset),
            "train_inst_ids": [inst.id for inst in train_dataset],
            "val_inst_ids": [inst.id for inst in val_dataset],
            "workspace_dir": candidate_store.workspace_dir,
            "initial_spec_dir": initial_spec_dir,
        })

        if candidate_store.cleanup_unavailable:
            candidate_store.delete_unavailable_candidates()
        reset_ids = candidate_store.reset_evolving_to_pending()
        if reset_ids:
            logger.info(f"Reset {len(reset_ids)} evolving candidate(s) to pending on startup: {reset_ids}")
    # ── helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _is_improvement_accepted(
        improvement: float,
        new_scores: list[float],
        threshold: float,
    ) -> bool:
        """Whether a child's improvement over its parent is sufficient to accept.

        Accepts if either condition holds:
          - improvement >= threshold AND improvement > 0 (clears the bar)
          - all scores are perfect (nothing left to improve, accept immediately)
        """
        if improvement >= threshold and improvement > SCORE_EPS:
            return True
        return all(s >= 1.0 - SCORE_EPS for s in new_scores)

    def _budget_exhausted(self) -> str | None:
        """Return a description of the first exhausted budget limit, or None.

        No budget (``self.budget is None``) → loop stops only on empty select.
        """
        if self.budget is None:
            return None
        stats = self.statistics
        used_tokens = sum(
            u.input_tokens + u.output_tokens
            for u in (stats.proposer_usage, stats.system_usage, stats.eval_usage)
        )
        elapsed_seconds = (datetime.now() - stats.start_time).total_seconds()
        return self.budget.is_exhausted(
            BudgetUsage(
                current_iteration=stats.current_iteration,
                current_rollouts=stats.current_rollouts,
                current_system_runs=stats.current_system_runs,
                used_tokens=used_tokens,
                elapsed_seconds=elapsed_seconds,
            )
        )

    async def _run_and_evaluate_wrapper(
        self, candidate_id: str, data_list: list[DataInst], split: str = "train",
    ) -> RolloutEvalResult:
        """Counting wrapper around :meth:`_run_and_evaluate`.

        Bumps two counters here, BEFORE delegating to :meth:`_run_and_evaluate`:
          - ``statistics.current_system_runs`` += len(data_list)   (every call, all splits)
          - ``statistics.current_rollouts``   += len(data_list)   (only when split == "train")

        ``split`` distinguishes training rollouts (parent/child batches, reflection
        children) from validation rollouts (``_evaluate_first`` baseline, ``_step_validate``
        acceptance check). ``current_rollouts`` is the cumulative count of TRAINING
        data instances run; ``current_system_runs`` is the all-splits total. Callers
        that run the val set MUST pass ``split="val"`` so those instances are excluded
        from ``current_rollouts`` (and thus from ``Budget.max_rollouts``) while still
        counting toward ``Budget.max_system_runs``.

        The main loop and all internal callers go through this wrapper, so both
        counters are applied uniformly regardless of which ``System``/``Evaluator``
        plumbing a subclass uses. Subclasses that forget to route through here would
        silently break ``Budget.max_rollouts`` / ``Budget.max_system_runs``;
        centralizing it here makes that impossible.

        Per-scenario subclasses MUST override :meth:`_run_and_evaluate`, NOT
        this wrapper — ``split`` stays on the wrapper and is NOT forwarded, so
        subclass signatures are unaffected.
        """
        self.statistics.current_system_runs += len(data_list)
        if split == "train":
            self.statistics.current_rollouts += len(data_list)
        return await self._run_and_evaluate(candidate_id, data_list)

    async def _run_and_evaluate(
        self, candidate_id: str, data_list: list[DataInst],
    ) -> RolloutEvalResult:
        """Run one candidate on a list of data items, then evaluate the outputs.

        Override this in per-scenario subclasses to thread scenario-specific kwargs
        (e.g. ``job_name``/``output_dir`` for batch-subprocess systems, temp dirs
        for containerized systems) through ``System.run_batch`` /
        ``Evaluator.evaluate_batch``. The default implementation is the plain
        in-process path. Callers should go through :meth:`_run_and_evaluate_wrapper`
        so every executed data instance is counted against ``Budget.max_system_runs``.
        """
        meta = self.candidate_store.get_meta(candidate_id)
        results = await self.system.run_batch(meta, data_list)
        evals = await self.evaluator.evaluate_batch(data_list, results)
        return RolloutEvalResult(results=results, evals=evals)

    async def _evaluate_first(
        self, candidate_id: str
    ) -> list[EvaluationResult]:
        rollout = await self._run_and_evaluate_wrapper(candidate_id, self.val_dataset, split="val")
        self._save_run_record_list(candidate_id, self.val_dataset, rollout.results, rollout.evals, split="val")
        self.candidate_store.update_summary_scores(candidate_id, rollout.evals)
        return rollout.evals

    def _save_run_record_list(
        self, candidate_id: str,
        data_inst_list: list[DataInst],
        system_result_list: list[SystemResult],
        eval_result_list: list[EvaluationResult],
        split: str = "train",
    ) -> None:
        for data_inst, system_result, eval_result in zip(data_inst_list, system_result_list, eval_result_list, strict=False):
            record = RunRecord(
                candidate_id=candidate_id,
                timestamp=datetime.now(),
                data_inst=data_inst,
                system_result=system_result,
                evaluation_result=eval_result,
            )
            self.candidate_store.save_run_record(candidate_id, record, split=split)

    def _record_iteration(self, record: IterationRecord) -> None:
        stats = self.statistics

        if record.accepted:
            stats.total_candidates_created += 1
        else:
            stats.rejected_count += 1

        pending = self.candidate_store.get_pool_by_state("pending")
        evolving = self.candidate_store.get_pool_by_state("evolving")
        stats.current_population_size = len(pending) + len(evolving)

        # get_best_candidate() returns None when no alive candidate has been
        # evaluated yet — keep the prior best in that case (see its docstring).
        best = self.candidate_store.get_best_candidate()
        if best is not None:
            _, best_summary = best
            stats.best_candidate_id = best_summary.candidate_id
            stats.best_avg_score = best_summary.avg_score

        # Stamp the current highest score onto the record before persisting it.
        record.current_best_avg_score = stats.best_avg_score

        # Append the detailed iteration record to JSONL (lightweight, no full rewrite).
        self.candidate_store.append_iteration_record(record)

        stats.avg_score_history.append(stats.best_avg_score)

        stats.last_updated_at = datetime.now()
        stats.total_duration_seconds = (datetime.now() - self.statistics.start_time).total_seconds()
        self.candidate_store.save_statistics(stats)

    # ── iteration steps ──────────────────────────────────────────────

    def _step_build_proposal_task(
        self, parent_id: str,
        old_rollout: RolloutEvalResult,
        next_epoch: int,
        next_dataset_index: int,
    ) -> ProposalTask | None:
        """Build a proposal task for this parent, or None if it's already perfect.

        ``next_epoch`` / ``next_dataset_index`` are stamped on the child so it
        resumes at the ADVANCED position if accepted (no extra ``set_progress``
        call needed downstream).
        """
        if all(score >= 1.0 - SCORE_EPS for score in old_rollout.scores):
            logger.info(f"Selected candidate {parent_id} already perfect on batch, skipping")
            return None
        new_meta = self.candidate_store.create_child(
            parent_id, epoch=next_epoch, dataset_index=next_dataset_index,
        )
        return ProposalTask(parent_id=parent_id, new_id=new_meta.candidate_id)

    async def _step_propose(
        self, proposal_task: ProposalTask,
    ) -> ProposalOutcome | None:
        """Run proposer on a single proposal task. Returns None on failure (and retires the new candidate)."""
        proposer_start = datetime.now()
        try:
            result = await self.proposer.propose(proposal_task.parent_id, proposal_task.new_id)
        except Exception as e:
            logger.error(f"Proposer failed for {proposal_task.new_id}: {e}")
            self.candidate_store.retire(proposal_task.new_id)
            return None
        duration = (datetime.now() - proposer_start).total_seconds()

        if not result.success:
            logger.warning(f"Proposer failed: {result.error_message}")
            self.candidate_store.retire(proposal_task.new_id)
            return None

        if result.stats:
            self.statistics.proposer_usage.add(result.stats)

        logger.info(f"Proposal completed for {proposal_task.new_id} in {duration:.1f}s")
        return ProposalOutcome(
            parent_id=proposal_task.parent_id,
            new_id=proposal_task.new_id,
            proposer_duration=duration,
        )

    async def _step_challenge_parent(
        self,
        proposal: ProposalOutcome,
        old_rollout: RolloutEvalResult,
        new_rollout: RolloutEvalResult,
        batch: list[DataInst],
    ) -> AcceptedCandidate | None:
        """The child challenges its parent on the batch.

        If the child beats the per-batch improvement threshold, the challenge
        succeeds and the accepted candidate is returned. Otherwise, when
        ``max_reflection_iterations > 0``, the child reflects on the failure and
        may spawn a deeper challenger; the loop returns the first descendant to
        clear the threshold, or None if every challenger fails.
        """
        threshold = self.min_improvement_per_batch
        new_id = proposal.new_id
        new_scores = new_rollout.scores
        old_scores = old_rollout.scores
        new_sum = sum(new_scores) if new_scores else 0
        old_sum = sum(old_scores) if old_scores else 0

        # per-question score breakdown for agent-driven analysis of underperforming children
        old_detail = ", ".join(f"{e.data_id}={e.score:.4f}" for e in old_rollout.evals)
        new_detail = ", ".join(f"{e.data_id}={e.score:.4f}" for e in new_rollout.evals)
        logger.info(f"Parent {proposal.parent_id} scores: [{old_detail}], Child  {new_id} scores: [{new_detail}]")

        improvement = new_sum - old_sum
        if self._is_improvement_accepted(improvement, new_scores, threshold):
            is_perfect = all(s >= 1.0 - SCORE_EPS for s in new_scores)
            logger.info(
                f"New candidate {new_id} {'has perfect score' if is_perfect else 'cleared batch threshold'} "
                f"(new={new_sum:.4f} - old={old_sum:.4f} = {improvement:+.4f})"
            )
            return AcceptedCandidate(
                parent_id=proposal.parent_id,
                new_id=new_id,
                old_batch_score_sum=old_sum,
                new_batch_score_sum=new_sum,
            )

        # Below threshold (or regression). Decide between reflection vs reject.
        if self.max_reflection_iterations <= 0:
            logger.info(
                f"New candidate {new_id} not improved enough on batch "
                f"(new={new_sum:.4f}, old={old_sum:.4f}, threshold={threshold:.4f}), rejecting"
            )
            self.candidate_store.retire(new_id)
            return None

        logger.info(
            f"New candidate {new_id} below threshold on batch "
            f"(old_sum={old_sum:.4f}, new_sum={new_sum:.4f}, delta={improvement:+.4f} < threshold={threshold:.4f}), entering reflection loop "
            f"(max_iter={self.max_reflection_iterations})"
        )
        return await self._step_reflect(
            original_parent_id=proposal.parent_id,
            original_parent_rollout=old_rollout,
            failed_child_id=new_id,
            failed_child_rollout=new_rollout,
            batch=batch,
            threshold=threshold,
        )

    async def _step_reflect(
        self,
        original_parent_id: str,
        original_parent_rollout: RolloutEvalResult,
        failed_child_id: str,
        failed_child_rollout: RolloutEvalResult,
        batch: list[DataInst],
        threshold: float,
    ) -> AcceptedCandidate | None:
        """Run up to ``max_reflection_iterations`` reflection children, return the best one that beats the parent.

        Args:
            original_parent_id: Chain root — the candidate that was originally selected
                for mutation this iteration. Every accepted child must improve over this
                one (``new_sum > parent_sum``); the returned ``AcceptedCandidate.parent_id``
                points here regardless of which intermediate chain node actually produced
                the winner.
            original_parent_rollout: The original parent's evaluation on this batch.
                Used as the comparison baseline for ``chain_accepted`` and as the first
                column of the per-data score history table fed to ``proposer.reflect``.
            failed_child_id: The first failed child (v0) — the candidate produced by the
                normal propose path that did NOT clear the batch threshold and triggered
                reflection. Serves three roles inside the loop:
                  (1) the initial ``prev_id`` so v1's spec is built on top of it,
                  (2) the initial ``best_id`` / ``best_rollout`` (any reflection child
                      must beat THIS, not the original parent, to become best),
                  (3) the v0 entry in ``chain_evals`` / ``chain_ids`` so the
                      reflection prompt can show its per-data scores.
                Its lifecycle is owned by this method: retired on exit unless it ends
                up being the accepted best (v0 below early-stop threshold but still
                stronger than the original parent and stronger than every v_k).
            failed_child_rollout: v0's evaluation on this batch. Same triple role as
                ``failed_child_id``: best-baseline + first column after root in the
                score history table.
            batch: The training batch all candidates are evaluated against. Each
                reflection child is run on this same batch so its score is directly
                comparable to ``original_parent_rollout`` and ``failed_child_rollout``.
            threshold: ``min_improvement_per_batch`` — the absolute batch-sum delta
                a reflection child needs to clear to trigger early-stop. Acceptance at
                the end of the loop only requires beating ``parent_sum`` by SCORE_EPS,
                NOT clearing this threshold (the threshold is just the "stop trying
                more reflection iterations" signal).

        Each reflection child is created as an independent candidate whose ``parent_id`` is
        the immediately-previous (failed) child in the chain. During the loop, intermediate
        children are created with ``state="unavailable"`` so they never enter selection.

        On exit, every chain candidate (v0 plus every reflection-produced v_k) EXCEPT
        the accepted ``best`` is retired via ``store.retire`` (honors the store's
        ``cleanup_unavailable`` flag). When ``cleanup_unavailable=True`` this leaves
        the accepted best's ``parent_id`` pointing at a deleted intermediate — that is
        treated as normal lineage decay (same as any other eliminated candidate's
        references), not an error to fix.

        Returns the best AcceptedCandidate or None if no chain candidate beats the parent.
        """
        original_parent_sum = sum(original_parent_rollout.scores)
        best_id = failed_child_id
        best_rollout = failed_child_rollout
        best_depth = 0
        prev_id = failed_child_id
        cumulative_proposer_usage = UsageStats()
        # Every candidate in the chain whose lifecycle this method owns: v0 plus
        # every reflection-produced v_k. At exit, all of them except the accepted
        # best are retired.
        child_id_list: list[str] = [failed_child_id]
        # Full mara chain passed to proposer.reflect — every node is already
        # evaluated. chain.root=root, chain.last=v_{k-1}. The candidate being
        # produced (v_k) is passed separately as new_candidate_id.
        chain = MaraChain([
            ChainNode.from_eval_list(original_parent_id, original_parent_rollout.evals),
            ChainNode.from_eval_list(failed_child_id, failed_child_rollout.evals),
        ])

        for depth in range(1, self.max_reflection_iterations + 1):
            new_meta = self.candidate_store.create_child(prev_id, reflection_depth=depth, state="unavailable")
            if new_meta is None:
                logger.warning(
                    f"Reflection iter {depth}: create_child failed for prev={prev_id}, stopping reflection"
                )
                break
            new_id = new_meta.candidate_id
            child_id_list.append(new_id)
            logger.info(
                f"Reflection iter {depth}: created candidate {new_id} (parent={prev_id}, root={original_parent_id})"
            )

            try:
                reflection_result = await self.proposer.reflect(chain, new_id)
            except Exception as e:
                logger.error(f"Reflection iter {depth}: proposer.reflect raised: {e}")
                break

            cumulative_proposer_usage.add(reflection_result.stats)

            if not reflection_result.success:
                logger.warning(
                    f"Reflection iter {depth}: proposer.reflect failed ({reflection_result.error_message}), stopping"
                )
                break

            rollout = await self._run_and_evaluate_wrapper(new_id, batch)
            self._save_run_record_list(new_id, batch, rollout.results, rollout.evals)
            new_sum = sum(rollout.scores)
            reflection_detail = ", ".join(f"{e.data_id}={e.score:.4f}" for e in rollout.evals)
            chain.add(ChainNode.from_eval_list(new_id, rollout.evals))
            logger.info(
                f"Reflection iter {depth}: candidate {new_id} batch sum={new_sum:.4f} "
                f"(parent_sum={original_parent_sum:.4f}, threshold={threshold:.4f}), "
                f"scores=[{reflection_detail}], chain=[{chain.format_id_path()}]"
            )

            if new_sum > sum(best_rollout.scores):
                best_id, best_rollout, best_depth = new_id, rollout, depth

            # Met threshold or perfect score — stop early.
            improvement = new_sum - original_parent_sum
            if self._is_improvement_accepted(improvement, rollout.scores, threshold):
                is_perfect = all(e.score >= 1.0 - SCORE_EPS for e in rollout.evals)
                logger.info(
                    f"Reflection iter {depth}: {'perfect score' if is_perfect else 'cleared threshold'}, "
                    f"stopping reflection loop"
                )
                break

            # v_k joins the chain as a fully-evaluated node for the next iteration.
            prev_id = new_id

        best_sum = sum(best_rollout.scores)
        # try max attempts to find a reflection child that beats the original parent.
        chain_accepted = best_sum > original_parent_sum + SCORE_EPS

        # Retire every chain candidate (including v0) except the accepted best.
        # When the chain is rejected, the best stays in but is still retired —
        # nothing in the chain survives.
        for cid in child_id_list:
            if chain_accepted and cid == best_id:
                continue
            self.candidate_store.retire(cid)
        self.statistics.proposer_usage.add(cumulative_proposer_usage)
        if not chain_accepted:
            logger.info(
                f"Reflection: no descendant beats original parent {original_parent_id} "
                f"(best_sum={best_sum:.4f} <= parent_sum={original_parent_sum:.4f}, threshold={threshold:.4f}), rejecting chain"
            )
            return None

        logger.info(
            f"Reflection: accepting candidate {best_id} (depth={best_depth}) "
            f"new_sum={best_sum:.4f} vs parent_sum={original_parent_sum:.4f}"
        )
        return AcceptedCandidate(
            parent_id=original_parent_id,
            new_id=best_id,
            old_batch_score_sum=original_parent_sum,
            new_batch_score_sum=best_sum,
            reflection_depth=best_depth,
        )

    async def _step_validate(
        self,
        accepted: AcceptedCandidate,
    ) -> tuple[float, RolloutEvalResult]:
        """Validate one accepted candidate on the val set.

        Returns (val_avg_score, rollout_result).
        """
        new_id = accepted.new_id
        val_rollout = await self._run_and_evaluate_wrapper(new_id, self.val_dataset, split="val")
        self._save_run_record_list(new_id, self.val_dataset, val_rollout.results, val_rollout.evals, split="val")
        self.candidate_store.update_summary_scores(new_id, val_rollout.evals)
        new_avg = sum(val_rollout.scores) / len(val_rollout.scores) if val_rollout.scores else 0
        logger.info(f"New candidate {new_id} avg_score: {new_avg:.4f}")
        return new_avg, val_rollout

    # ── per-evolution hooks (subclass overrides) ──────────────────────

    def _enter_evolution_scope(self, parent_id: str) -> AbstractContextManager:
        """Context manager active for the lifetime of a single evolution slot.

        Subclasses can use this to set up per-evolution scratch state (e.g. a
        ``ContextVar`` collecting tmp file paths) that is naturally torn down
        when the slot exits, without race-prone shared dicts.
        """
        return nullcontext()

    def _on_evolution_finished(self, parent_id: str) -> None:
        """Hook called inside ``_enter_evolution_scope`` after the slot's work is done.

        Subclasses can override to drain artifacts collected via the scope
        (e.g. cleanup tmp directories). Always called — success or failure —
        before the scope's tear-down.
        """
        return

    # ── batch derivation ──────────────────────────────────────────────

    def _derive_batch(self, meta: CandidateMeta) -> tuple[list[DataInst], int, int, int]:
        """Return (batch, next_epoch, next_index, batch_start_index) for this candidate's slot.

        Snapshot semantics: ``batch`` is what should be evaluated NOW;
        ``next_epoch``/``next_index`` is what the candidate's progress should
        advance to AFTER this slot completes (even on failure — see _evolve_one).

        When ``dataset_index + batch_size > len(train_dataset)``, the slice is
        tail-aligned (``train[n - batch_size : n]``) and progress wraps to the
        next epoch with index reset to 0.
        """
        dataset_size = len(self.train_dataset)
        epoch, index = meta.epoch, meta.dataset_index
        if index + self.batch_size > dataset_size:
            batch = self.train_dataset[dataset_size - self.batch_size : dataset_size]
            return batch, epoch + 1, 0, dataset_size - self.batch_size
        batch = self.train_dataset[index : index + self.batch_size]
        return batch, epoch, index + self.batch_size, index

    # ── main loop ────────────────────────────────────────────────────

    async def optimize(self) -> None:
        """Run the full optimization loop using the candidate-pool scheduler."""
        logger.info("Starting Optimizer")

        if self.statistics and self.statistics.root_candidate_id:
            logger.info("Resuming from checkpoint")
            # Refresh budget caps on resume too — a workspace started under one
            # budget can be resumed with another, and max_rollouts/max_system_runs
            # may have been added to an old statistics.json that didn't carry them.
            self.statistics.max_iterations = (self.budget.max_iterations or 0) if self.budget else 0
            self.statistics.max_rollouts = (self.budget.max_rollouts or 0) if self.budget else 0
            self.statistics.max_system_runs = (self.budget.max_system_runs or 0) if self.budget else 0
        else:
            logger.info("Starting from scratch, creating root candidate")
            root_spec = self.candidate_store.create_root(initial_spec_dir=self.initial_spec_dir)
            root_id = root_spec.candidate_id
            logger.info(f"Evaluating root candidate baseline: {root_id}")
            baseline_eval_list = await self._evaluate_first(root_id)
            baseline_score_list = [eval_result.score for eval_result in baseline_eval_list]
            baseline_avg = sum(baseline_score_list) / len(baseline_score_list) if baseline_score_list else 0.0
            self.candidate_store.update_summary_scores(root_id, baseline_eval_list)
            self.candidate_store.set_state(root_id, "pending")
            self.statistics.root_candidate_id = root_id
            self.statistics.baseline_avg_score = baseline_avg
            self.statistics.best_candidate_id = root_id
            self.statistics.best_avg_score = baseline_avg
            # max_iterations / max_rollouts / max_system_runs mirror budget.* for stats-file back-compat.
            self.statistics.max_iterations = (self.budget.max_iterations or 0) if self.budget else 0
            self.statistics.max_rollouts = (self.budget.max_rollouts or 0) if self.budget else 0
            self.statistics.max_system_runs = (self.budget.max_system_runs or 0) if self.budget else 0
            self.statistics.current_population_size = 1
            self.statistics.total_candidates_created = 1
            self.statistics.avg_score_history = [baseline_avg]
            self.statistics.last_updated_at = datetime.now()
            self.candidate_store.save_statistics(self.statistics)

        slot_sem = asyncio.Semaphore(self.num_proposals)
        active_tasks: set[asyncio.Task] = set()

        while True:
            exhausted = self._budget_exhausted()
            if exhausted:
                logger.info(f"Budget exhausted ({exhausted}); draining {len(active_tasks)} in-flight slot(s)")
                break

            await slot_sem.acquire()

            try:
                picked = self.ea.select(num=1)
            except Exception:
                slot_sem.release()
                logger.exception("EvolutionAlgorithm.select raised; stopping scheduler")
                break

            if not picked:
                # No selectable candidate right now. Either everything is in flight
                # (wait for any slot to finish, then retry) or we're truly out of
                # candidates and no slots are running (done).
                slot_sem.release()
                if not active_tasks:
                    logger.info("No selectable candidate and no slots in flight; stopping")
                    break
                await asyncio.wait(active_tasks, return_when=asyncio.FIRST_COMPLETED)
                continue

            cid = picked[0]
            # Flip BEFORE spawning so a concurrent select can't pick the same id.
            # (Single-threaded asyncio, but the spawn-then-await pattern leaves a
            # gap if we ever introduce more parallelism around this point.)
            self.candidate_store.set_state(cid, "evolving")
            self.statistics.current_iteration += 1
            slot_iteration = self.statistics.current_iteration

            cid_meta = self.candidate_store.get_meta(cid)
            elapsed = datetime.now() - self.statistics.start_time
            iter_cap = (self.budget.max_iterations if self.budget and self.budget.max_iterations else None) or "?"
            logger.info(
                f"Iteration {slot_iteration}/{iter_cap}: opening for candidate {cid} "
                f"(epoch={cid_meta.epoch}, idx={cid_meta.dataset_index}, elapsed={elapsed})"
            )

            async def _run_slot(parent_id: str, iteration: int) -> None:
                try:
                    await self._evolve_one(parent_id, iteration)
                finally:
                    slot_sem.release()

            task = asyncio.create_task(_run_slot(cid, slot_iteration))
            active_tasks.add(task)
            task.add_done_callback(active_tasks.discard)

        # Drain phase — wait for all in-flight slots to finish.
        if active_tasks:
            logger.info(f"Draining {len(active_tasks)} in-flight slot(s) before exit")
            await asyncio.gather(*active_tasks, return_exceptions=True)

        self.statistics.total_duration_seconds = (datetime.now() - self.statistics.start_time).total_seconds()
        self.statistics.last_updated_at = datetime.now()
        self.candidate_store.save_statistics(self.statistics)

    async def _evolve_one(
        self,
        parent_id: str,
        slot_iteration: int,
    ) -> None:
        """Full evolution path for one candidate. Releases the slot in finally."""
        iter_start = datetime.now()
        parent_meta = self.candidate_store.get_meta(parent_id)
        snapshot_epoch = parent_meta.epoch
        batch, advanced_epoch, advanced_index, batch_start_index = self._derive_batch(parent_meta)
        record = IterationRecord(
            iteration=slot_iteration,
            epoch=snapshot_epoch,
            selected_id=parent_id,
            new_id="",
            old_batch_score_sum=0.0,
            new_batch_score_sum=0.0,
            accepted=False,
            candidate_created=False,
            proposer_duration_seconds=0.0
        )
        try:
            with self._enter_evolution_scope(parent_id):
                try:
                    # Rollout parent candidate. This is the baseline the child must beat to advance.
                    old_rollout = await self._run_and_evaluate_wrapper(parent_id, batch)
                    self._save_run_record_list(parent_id, batch, old_rollout.results, old_rollout.evals)

                    proposal_task = self._step_build_proposal_task(
                        parent_id,
                        old_rollout,
                        next_epoch=advanced_epoch,
                        next_dataset_index=advanced_index,
                    )

                    proposal: ProposalOutcome | None = None
                    new_rollout: RolloutEvalResult | None = None
                    accepted: AcceptedCandidate | None = None
                    val_avg: float | None = None
                    val_rollout: RolloutEvalResult | None = None
                    challenge_duration_seconds = 0.0

                    if proposal_task is not None:
                        proposal = await self._step_propose(proposal_task)

                    if proposal is not None:
                        # Proposal succeeded, rollout the child and compare vs parent.
                        new_rollout = await self._run_and_evaluate_wrapper(proposal.new_id, batch)
                        self._save_run_record_list(proposal.new_id, batch, new_rollout.results, new_rollout.evals)
                        challenge_start = time.time()
                        accepted = await self._step_challenge_parent(proposal, old_rollout, new_rollout, batch)
                        challenge_duration_seconds = time.time() - challenge_start

                    if accepted is not None:
                        val_avg, val_rollout = await self._step_validate(accepted)
                        self.candidate_store.set_state(accepted.new_id, "pending")

                    # Parent always advances (it consumed this batch). Accepted children
                    # already carry the ADVANCED position (stamped at create_child time
                    # inside _step_build_proposal_task), so no extra set_progress needed.
                    self.candidate_store.set_progress(parent_id, advanced_epoch, advanced_index)
                    # Flip parent back to pending so it's eligible for selection again if it remains competitive.
                    self.candidate_store.set_state(parent_id, "pending")

                    # Run eliminate every slot (not only when a child was accepted): the
                    # parent just flipped from evolving → pending and is back in the pool
                    # competing for a frontier slot. Eliminate is synchronous and contains
                    # no `await`, so under asyncio's cooperative single-threaded scheduling
                    # it's already atomic across concurrent slots — no lock needed. (If
                    # `eliminate` ever grows an `await`, reintroduce serialization here.)
                    self.ea.eliminate()

                    # Accumulate system/eval usage (proposer usage already accumulated upstream).
                    all_rollouts: list[RolloutEvalResult] = [old_rollout]
                    if new_rollout is not None:
                        all_rollouts.append(new_rollout)
                    if val_rollout is not None:
                        all_rollouts.append(val_rollout)
                    for rollout in all_rollouts:
                        for sr in rollout.results:
                            self.statistics.system_usage.add(sr.usage)
                        for er in rollout.evals:
                            self.statistics.eval_usage.add(er.usage)

                    record = build_iteration_record(
                        parent_id=parent_id,
                        old_rollout=old_rollout,
                        proposal_task=proposal_task,
                        proposal=proposal,
                        new_rollout=new_rollout,
                        accepted=accepted,
                        val_avg_score=val_avg,
                        iter_start=iter_start,
                        iteration=slot_iteration,
                        epoch=snapshot_epoch,
                        challenge_duration_seconds=challenge_duration_seconds,
                        dataset_index=batch_start_index,
                        current_rollouts=self.statistics.current_rollouts,
                        current_system_runs=self.statistics.current_system_runs,
                    )
                finally:
                    try:
                        self._on_evolution_finished(parent_id)
                    except Exception:
                        logger.exception(f"_on_evolution_finished failed for {parent_id}")
        except Exception:
            logger.exception(f"Slot {slot_iteration} (candidate {parent_id}) failed")
            self.candidate_store.set_state(parent_id, "pending")
        finally:
            # _record_iteration is synchronous and contains no `await`, so under
            # asyncio's cooperative single-threaded scheduling it's already atomic
            # across concurrent slots — no lock needed. (If it ever grows an
            # `await`, e.g. switching save_statistics to async IO, reintroduce
            # serialization here.)
            self._record_iteration(record)
