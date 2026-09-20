from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    wait_random,
)

from antomnievo.common.utils.trajectory_parser import parse_pi_json_output
from antomnievo.interface.candidate_store import CandidateStore
from antomnievo.interface.evaluator import Evaluator
from antomnievo.interface.system import System
from antomnievo.model.candidate_data_schema import CANDIDATE_DATA_SCHEMA
from antomnievo.model.trajectory import Trajectory
from antomnievo.model.tunable_artifact_schema import TunableArtifactSchema
from antomnievo.model.usage_stats import UsageStats
from antomnievo.proposer.base_proposer import BaseProposer
from antomnievo.proposer.utils.pi_coding_agent_utils import (
    MAX_RETRY_ATTEMPTS,
    PROVIDER_ANTHROPIC,
    RETRYABLE,
    PiCodingAgentConfig,
    PiThinkingLevel,
    Provider,
    classify_pi_error,
    invoke_pi_coding_agent,
    log_retry_sleep,
)


class PiCodingAgentProposer(BaseProposer):
    """Proposer that uses the Pi Coding Agent CLI in two phases:

    Phase 1 (Analysis): Identifies unanalyzed runs, groups by data_id, and
    invokes Pi for each group. Pi reads existing analysis, reads run files,
    writes analysis result, and validates it.

    Phase 2 (Propose): Invokes Pi with a propose-specific prompt to read
    analysis results and propose targeted tunable-artifact modifications.

    The two-phase architecture is the same as ClaudeCodeProposer — see its
    docstring for the rationale.
    """

    def __init__(
        self,
        tunable_artifact_schema: TunableArtifactSchema,
        candidate_store: CandidateStore,
        evaluator: Evaluator,
        *,
        thinking: PiThinkingLevel | None = None,
        system: System | None = None,
        data_schema: TunableArtifactSchema = CANDIDATE_DATA_SCHEMA,
        pi_path: str = "pi",
        model: str = "kimi-k2.5",
        provider: Provider = PROVIDER_ANTHROPIC,
        max_turns: int = 150,
        timeout: int = 3600,
        api_key: str | None = None,
        base_url: str | None = None,
        concurrency: int = 2,
        skip_perfect_score_runs: bool = False,
        last_n_analysis: int | None = None,
    ):
        super().__init__(
            tunable_artifact_schema=tunable_artifact_schema,
            candidate_store=candidate_store,
            evaluator=evaluator,
            system=system,
            data_schema=data_schema,
            concurrency=concurrency,
            skip_perfect_score_runs=skip_perfect_score_runs,
            last_n_analysis=last_n_analysis,
        )
        self._config = PiCodingAgentConfig(
            pi_path=pi_path,
            model=model,
            provider=provider,
            max_turns=max_turns,
            timeout=timeout,
            api_key=api_key,
            base_url=base_url,
            thinking=thinking,
        )

    async def invoke_agent(self, prompt: str, cwd: str) -> tuple[Trajectory, UsageStats]:
        """Invoke Pi Coding Agent CLI and return parsed trajectory and stats.

        Retries transient gateway errors (429 / rate-limit / 5xx / overloaded)
        via tenacity (see ``_invoke_pi_once``), bounded to ``MAX_RETRY_ATTEMPTS``.
        Auth (401/403) and unknown errors surface immediately.

        The semaphore is held across backoff sleeps — intentional backpressure:
        while one invocation recovers from a rate limit we don't launch more
        concurrent calls that would pile on 429s. Pi itself does no internal 429
        retry, so without this a single rate-limit hit aborts the whole phase.
        """
        async with self._sem:
            return await self._invoke_pi_once(prompt, cwd)

    @retry(
        stop=stop_after_attempt(MAX_RETRY_ATTEMPTS),
        wait=wait_exponential(multiplier=2, exp_base=2, min=2, max=60)
        + wait_random(0, 1),
        retry=RETRYABLE,
        reraise=True,
        before_sleep=log_retry_sleep,
    )
    async def _invoke_pi_once(
        self, prompt: str, cwd: str
    ) -> tuple[Trajectory, UsageStats]:
        """One Pi invocation + parse; retried by tenacity on transient errors.

        Two transient modes share one exception-based retry path: (1) a non-zero
        Pi exit raises a retryable ``RuntimeError`` (429 in stderr) from
        ``invoke_pi_coding_agent``, and (2) a clean exit whose parsed trajectory
        carries a rate-limit error span is surfaced as a ``RuntimeError`` here
        so tenacity retries it the same way. Fatal (401/403) and unknown
        trajectory errors are NOT raised — the trajectory is returned as-is for
        the proposer's ``trajectory.errors`` short-circuit. On exhaustion
        (``reraise=True``) the original ``RuntimeError`` is re-raised.
        """
        raw_output = await invoke_pi_coding_agent(prompt, cwd, self._config)
        trajectory, stats = parse_pi_json_output(raw_output)
        verdicts = [classify_pi_error(e) for e in trajectory.errors]
        if "retryable" in verdicts and "fatal" not in verdicts:
            err = next(
                e for e, v in zip(trajectory.errors, verdicts, strict=False) if v == "retryable"
            )
            raise RuntimeError(f"Pi trajectory transient error: {err}")
        return trajectory, stats
