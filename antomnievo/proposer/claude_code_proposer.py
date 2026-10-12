import logging

from antomnievo.common.utils.trajectory_parser import parse_stream_json
from antomnievo.interface.candidate_store import CandidateStore
from antomnievo.interface.evaluator import Evaluator
from antomnievo.interface.system import System
from antomnievo.model.candidate_data_schema import CANDIDATE_DATA_SCHEMA
from antomnievo.model.trajectory import Trajectory
from antomnievo.model.tunable_artifact_schema import TunableArtifactSchema
from antomnievo.model.usage_stats import UsageStats
from antomnievo.proposer.base_proposer import BaseProposer
from antomnievo.proposer.utils.claude_code_utils import (
    ClaudeCodeConfig,
    invoke_claude_code,
)
from antomnievo.proposer.utils.trajectory_utils import find_degenerate_ending

logger = logging.getLogger(__name__)


class ClaudeCodeProposer(BaseProposer):
    """Proposer that uses Claude Code CLI in two phases:

    Phase 1 (Analysis): Identifies unanalyzed runs, groups by data_id, and
    invokes Claude Code for each group. Claude Code reads existing analysis,
    reads run files, writes analysis result, and validates it — all within
    the agent session.

    Phase 2 (Propose): Invokes Claude Code with a propose-specific prompt to
    read analysis results and propose targeted tunable-artifact modifications.

    Why a separate analysis phase?
        As runs accumulate, reading all run records in the propose phase becomes
        impractical: the total data volume grows unboundedly, causing the agent
        to skip long files, lose coherence across chunks, or trigger context
        compression that introduces non-deterministic truncation. The analysis
        phase avoids this by incrementally processing only new runs and
        re-summarizing into compact per-data_id result files — the propose
        phase then reads these summaries instead of the raw run data, keeping
        its context small and stable regardless of how many runs exist.

    .. warning::
        This backend is UNFINISHED. Development moved to PiCodingAgentProposer
        midway; this class works end-to-end in principle (analysis, mutation,
        and reflection / mara chain are inherited from BaseProposer, which
        only requires ``invoke_agent``) but never received the pi backend's
        hardening (see the TODO at ``invoke_agent``): no retry on transient
        gateway errors (429/5xx), no agent-error classification, degenerate
        sessions fail the phase instead of retrying in-slot. Note the
        reflection path in particular has never been exercised with this
        backend — treat it as unverified here.
    """

    def __init__(
        self,
        tunable_artifact_schema: TunableArtifactSchema,
        candidate_store: CandidateStore,
        evaluator: Evaluator,
        system: System | None = None,
        data_schema: TunableArtifactSchema = CANDIDATE_DATA_SCHEMA,
        claude_code_path: str = "claude",
        model: str = "kimi-k2.5",
        max_turns: int = 150,
        timeout: int = 3600,
        api_key: str | None = None,
        base_url: str = 'https://antchat.alipay.com/api/anthropic',
        concurrency: int = 2,
        max_context_tokens: int | None = None,
        autocompact_pct: int | None = None,
        config_dir: str | None = None,
        skip_perfect_score_runs: bool = False,
        last_n_analysis: int | None = None,
    ):
        """
        Args:
            tunable_artifact_schema: Schema describing the tunable-artifact directory structure to optimize.
            candidate_store: Store for reading/writing candidate data and metadata.
            evaluator: Evaluator whose scoring criteria will be injected into the analysis prompt.
            system: System whose description will be injected into the analysis prompt.
            data_schema: Schema describing the data directory structure (run records, analysis).
            claude_code_path: Path to the Claude Code CLI binary.
            model: Model identifier passed to Claude Code via --model.
            max_turns: Maximum agent turns per Claude Code invocation.
            timeout: Maximum seconds to wait for a single Claude Code invocation.
            api_key: Anthropic API key (ANTHROPIC_API_KEY).
                See https://code.claude.com/docs/en/env-vars
            base_url: Base URL for the Anthropic API (ANTHROPIC_BASE_URL).
                See https://code.claude.com/docs/en/env-vars
            concurrency: Maximum number of concurrent Claude Code invocations
                across all phases (analyze and mutate).
            max_context_tokens: Context capacity in tokens for auto-compaction
                (CLAUDE_CODE_AUTO_COMPACT_WINDOW). When set, autocompact_pct is
                applied as a percentage of this value, creating a soft cap that
                triggers compaction before the inference server's token limit.
                See https://code.claude.com/docs/en/env-vars
            autocompact_pct: Percentage of context window at which auto-compaction
                triggers (CLAUDE_AUTOCOMPACT_PCT_OVERRIDE). Applied as a percentage
                of max_context_tokens. Default ~93.5%; set lower (e.g. 80) to
                compact earlier. See https://code.claude.com/docs/en/env-vars
            config_dir: Directory for Claude Code configuration (CLAUDE_CONFIG_DIR).
                See https://code.claude.com/docs/en/env-vars
            skip_perfect_score_runs: If True, always skip runs with score >= 1.0
                from analysis, regardless of total run count. Prevents the analysis
                agent from proposing unnecessary changes to already-perfect cases.
        """
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
        self._config = ClaudeCodeConfig(
            claude_code_path=claude_code_path,
            model=model,
            max_turns=max_turns,
            timeout=timeout,
            api_key=api_key,
            base_url=base_url,
            max_context_tokens=max_context_tokens,
            autocompact_pct=autocompact_pct,
            config_dir=config_dir,
        )
        logger.warning(
            "ClaudeCodeProposer is unfinished: development moved to "
            "PiCodingAgentProposer midway, and this backend never received "
            "pi's retry/error-classification hardening (see class docstring). "
            "Prefer PiCodingAgentProposer."
        )

    async def invoke_agent(self, prompt: str, cwd: str) -> tuple[Trajectory, UsageStats]:
        """Invoke Claude Code CLI and return parsed trajectory and stats."""
        # TODO(claude-backend): unfinished backend — development moved to
        # PiCodingAgentProposer midway. Port pi's hardening here (or better,
        # into BaseProposer so both backends share it):
        #   1. tenacity retry on transient gateway errors (429/5xx), holding
        #      the semaphore across backoff like _invoke_pi_once does;
        #   2. classify_agent_error over trajectory.errors so transients join
        #      the retry path and fatals surface immediately;
        #   3. raise AgentEmptyResponseError on a degenerate ending instead of
        #      appending to trajectory.errors, so it retries in-slot.
        # Remove the __init__ warning once this lands.
        async with self._sem:
            raw_output = await invoke_claude_code(prompt, cwd, self._config)
        async with self._sem:
            raw_output = await invoke_claude_code(prompt, cwd, self._config)
        trajectory, stats = parse_stream_json(raw_output)
        # Under gateway overload the model can return empty assistant messages;
        # the CLI retries internally and exits 0, so the result event still
        # reads "success" and nothing lands in trajectory.errors. Detect that by
        # span shape — same rule the pi backend applies — so a half-finished
        # session is not rolled out as a candidate.
        if not trajectory.errors:
            degenerate = find_degenerate_ending(trajectory)
            if degenerate:
                trajectory.errors.append(f"Claude Code trajectory degenerate: {degenerate}")
        return trajectory, stats
