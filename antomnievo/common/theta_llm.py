"""LLM client with retry logic, based on ThetaLLM."""

import logging
from typing import Any

import httpx
from langchain_core.language_models.base import LanguageModelInput
from langchain_core.messages import BaseMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from tenacity import RetryCallState, retry, retry_if_exception, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

_RETRYABLE_EXCEPTIONS: tuple[type[Exception], ...] = (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.ReadError, httpx.RemoteProtocolError, ConnectionError)

try:
    import openai

    _RETRYABLE_EXCEPTIONS = (
        openai.APIConnectionError,
        openai.APITimeoutError,
        openai.RateLimitError,
        openai.InternalServerError,
        *_RETRYABLE_EXCEPTIONS,
    )
except ImportError:
    pass


def _before_sleep_log(retry_state: RetryCallState):
    exc = retry_state.outcome.exception() if retry_state.outcome else None  # type: ignore[union-attr]
    exc_info = f"{type(exc).__name__}: {exc}" if exc else "unknown"
    logger.warning(
        f"LLM call failed, retry #{retry_state.attempt_number}, "
        f"wait {retry_state.idle_for:.1f}s, error: {exc_info}"
    )


class ThetaLLM(ChatOpenAI):
    """OpenAI-compatible LLM client with automatic retry.

    Defaults to the BAILING_API_KEY env var and antchat endpoint if not
    explicitly provided.
    """

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.streaming = True

    @retry(
        stop=stop_after_attempt(10),
        wait=wait_exponential(multiplier=2, min=2, max=120),
        retry=retry_if_exception(lambda exc: isinstance(exc, _RETRYABLE_EXCEPTIONS)),
        before_sleep=_before_sleep_log,
        reraise=True,
    )
    def invoke(
        self,
        input: LanguageModelInput,
        config: RunnableConfig | None = None,
        *,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> BaseMessage:
        try:
            result = super().invoke(input, config, stop=stop, **kwargs)
            logger.debug("LLM invoke succeeded")
            return result
        except _RETRYABLE_EXCEPTIONS:
            raise
        except Exception as e:
            logger.error(f"LLM invoke error: {type(e).__name__}: {e}")
            raise

    @retry(
        stop=stop_after_attempt(10),
        wait=wait_exponential(multiplier=2, min=2, max=120),
        retry=retry_if_exception(lambda exc: isinstance(exc, _RETRYABLE_EXCEPTIONS)),
        before_sleep=_before_sleep_log,
        reraise=True,
    )
    async def ainvoke(
        self,
        input: LanguageModelInput,
        config: RunnableConfig | None = None,
        *,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> BaseMessage:
        try:
            result = await super().ainvoke(input, config, stop=stop, **kwargs)
            logger.debug("LLM ainvoke succeeded")
            return result
        except _RETRYABLE_EXCEPTIONS:
            raise
        except Exception as e:
            logger.error(f"LLM ainvoke error: {type(e).__name__}: {e}")
            raise


async def areq_llm(llm: ChatOpenAI, prompt: str, params: dict[str, Any] | None = None) -> str:
    """Fill prompt template and invoke LLM asynchronously, returning text."""
    params = params or {}
    for k, v in params.items():
        prompt = prompt.replace("{" + str(k) + "}", str(v))
    result = await llm.ainvoke(prompt)
    return result.text()


def req_llm(llm: ChatOpenAI, prompt: str, params: dict[str, Any] | None = None) -> str:
    """Fill prompt template and invoke LLM synchronously, returning text."""
    params = params or {}
    for k, v in params.items():
        prompt = prompt.replace("{" + str(k) + "}", str(v))
    result = llm.invoke(prompt)
    return result.text()
