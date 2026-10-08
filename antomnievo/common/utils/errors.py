"""Error types and error/retry classification shared by the coding-agent backends.

Single home for the exceptions the agent layer raises and for deciding whether
a gateway error is retryable, fatal, or unknown — so this logic is not
duplicated inside the individual backend modules.

Pi and its gateway (antchat/litellm) fail transiently: 429 rate-limit, 5xx,
"overloaded", "too many requests". These clear on their own after a short wait,
so re-invoking is worth it. Auth/permission failures (401/403) are NOT transient
— retrying wastes time and never succeeds — so they surface immediately.
Unknown errors are also not retried, to avoid masking real bugs (agent/import
failures) with retries. Pi itself does no internal 429 retry (verified in
@mariozechner/pi-coding-agent), so without this layer a single rate-limit hit
aborts the whole propose phase.
"""

import asyncio
import logging

from tenacity import retry_if_exception

logger = logging.getLogger(__name__)

MAX_RETRY_ATTEMPTS: int = 5

# Substrings (matched case-insensitively) that mark a transient, retryable
# gateway error. Matched against the Pi subprocess stderr (which surfaces in
# the RuntimeError message from invoke_pi_coding_agent) and against
# Trajectory.errors entries parsed from a clean Pi exit.
_RETRYABLE_MARKERS: tuple[str, ...] = (
    "429", "rate limit", "rate_limit", "ratelimit", "too many requests",
    "retry-after", "retry_after", "overloaded", "service unavailable",
    "temporarily unavailable", "try again", "502", "503", "504",
    "bad gateway", "gateway timeout",
)
# Substrings that mark a non-transient auth/permission failure. Checked first:
# if any is present the error is 'fatal' regardless of concurrent retryable
# markers (e.g. a "401" output bundled with "rate limit" text still stays
# fatal — retrying won't fix the auth problem).
_FATAL_MARKERS: tuple[str, ...] = (
    "401", "403", "unauthorized", "forbidden", "invalid api key",
    "invalid_api_key", "not authorized", "authentication",
)


class AgentTimeoutError(asyncio.TimeoutError):
    """An agent subprocess exceeded its timeout and was killed."""


class AgentEmptyResponseError(RuntimeError):
    """Pi's model returned repeated empty responses (transient gateway overload).

    Distinct from message-based classification: an empty assistant message
    carries no error text, so nothing matches ``_RETRYABLE_MARKERS`` and the
    failure would slip past ``classify_agent_error`` as 'unknown' — never retried,
    never surfaced in ``trajectory.errors`` (Pi exits 0). Detected by shape via
    ``find_degenerate_ending`` and raised as this type so it joins the same
    retry path as 429s.
    """


def classify_agent_error(text: str) -> str:
    """Classify an agent/gateway error string as ``'retryable'``, ``'fatal'``, or ``'unknown'``.

    ``'retryable'`` — transient (429 / rate-limit / 5xx / overloaded): wait + retry.
    ``'fatal'``     — auth/permission (401/403): surface immediately, do not retry.
    ``'unknown'``   — neither: surface immediately (don't mask real bugs with retries).
    """
    if not text:
        return "unknown"
    low = text.lower()
    if any(m in low for m in _FATAL_MARKERS):
        return "fatal"
    if any(m in low for m in _RETRYABLE_MARKERS):
        return "retryable"
    return "unknown"


def is_retryable_agent_error(exc: BaseException) -> bool:
    """True for transient RuntimeErrors (429 / rate-limit / 5xx) and for
    ``AgentEmptyResponseError`` (repeated empty model responses — transient
    gateway overload by shape, no error text to classify). Auth (401/403)
    and unknown errors return False — not retried (retrying auth is pointless,
    retrying unknowns masks bugs)."""
    if isinstance(exc, AgentEmptyResponseError):
        return True
    return isinstance(exc, RuntimeError) and classify_agent_error(str(exc)) == "retryable"


# Retry only on transient exceptions. Callers that surface a transient result
# (e.g. a clean Pi exit whose parsed trajectory carries a rate-limit error) should
# raise a RuntimeError so it joins this single retry path — see
# ``PiCodingAgentProposer._invoke_pi_once``. Matches the repo's kira_agent
# retry-on-exception idiom.
RETRYABLE = retry_if_exception(is_retryable_agent_error)


def log_retry_sleep(retry_state) -> None:
    """tenacity ``before_sleep`` hook: log one line before each backoff sleep."""
    wait = retry_state.next_action.sleep if retry_state.next_action else 0.0
    outcome = retry_state.outcome
    exc = outcome.exception() if outcome is not None else None
    cause = str(exc)[:200] if exc is not None else "transient error"
    logger.warning(
        f"Pi transient error (attempt {retry_state.attempt_number}/"
        f"{MAX_RETRY_ATTEMPTS}), retrying in {wait:.1f}s: {cause}"
    )
