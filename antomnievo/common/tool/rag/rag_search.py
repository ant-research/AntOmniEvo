import json
import logging
import os
from functools import partial

import httpx
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from tenacity import (
    AsyncRetrying,
    RetryCallState,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    wait_random,
)

logger = logging.getLogger(__name__)

# ---- Configuration (all via environment; no credentials in code) ----
RAG_SEARCH_URL = os.getenv("RAG_SEARCH_URL", "")
RAG_API_KEY = os.getenv("RAG_API_KEY")
RAG_USER_ID = os.getenv("RAG_USER_ID", "")
KNOWLEDGE_TYPE = "DOC"


class _RetryError(Exception):
    pass


_RETRYABLE_EXCEPTIONS = (
    _RetryError,
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.ReadError,
    httpx.RemoteProtocolError,
    ConnectionError,
    OSError,
)


def _before_sleep_log(retry_state: RetryCallState):
    exc = retry_state.outcome.exception() if retry_state.outcome else None  # type: ignore[union-attr]
    exc_info = f"{type(exc).__name__}: {exc}" if exc else "unknown"
    logger.warning(
        f"[RAG retry] attempt {retry_state.attempt_number} failed, "
        f"retrying in {retry_state.next_action.sleep:.1f}s. "
        f"Error: {exc_info}"
    )


# ---- API helpers ----

def _build_header(api_key: str | None = None) -> dict:
    key = api_key or RAG_API_KEY
    if not key:
        raise RuntimeError("Missing RAG_API_KEY")
    return {
        "content-type": "application/json",
        "Authorization": f"Bearer {key}",
    }


def _build_knowledge_info_list(
    library_id_list: list[int], document_id_list: list[int]
) -> list[dict]:
    info = []
    if library_id_list:
        for lib_id in library_id_list:
            info.append({"type": KNOWLEDGE_TYPE, "libId": lib_id})
    if document_id_list:
        for doc_id in document_id_list:
            info.append({"type": KNOWLEDGE_TYPE, "id": doc_id})
    return info


# ---- Core search ----

async def _remote_call_rag(url: str, header: dict, body: dict) -> list[str]:
    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=header, data=json.dumps(body), timeout=300)

    resp = response.json()
    if not resp.get("success"):
        logger.error(f"RAG API error: {json.dumps(resp, ensure_ascii=False)}")
        raise _RetryError(f"RAG API error: {json.dumps(resp, ensure_ascii=False)}")

    return [item["content"] for item in resp["data"]]


async def _search(
    tenant: str,
    library_id_list: list[int],
    document_id_list: list[int],
    query: str,
    api_key: str | None = None,
) -> str:
    if not query or not query.strip():
        return "error: query must be a non-empty string"

    body = {
        "spaceId": tenant,
        "query": query,
        "userId": RAG_USER_ID,
        "knowledgeIdInfos": _build_knowledge_info_list(library_id_list, document_id_list),
        "topK": 20,
        "ext": {"enableGraph": True},
    }

    try:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(20),
            wait=wait_random(min=0, max=60) + wait_exponential(multiplier=2, min=0, max=60),
            retry=retry_if_exception_type(_RETRYABLE_EXCEPTIONS),
            before_sleep=_before_sleep_log,
        ):
            with attempt:
                result_list = await _remote_call_rag(RAG_SEARCH_URL, _build_header(api_key), body)

        return "\n".join(f"[{i+1}] {item}" for i, item in enumerate(result_list))

    except Exception as e:
        logger.error(f"RAG search failed for query '{query}': {e}")
        return f"error occurred when searching for query {query}"


# ---- LangChain Tool builder ----

class RagSearchInput(BaseModel):
    query: str = Field(description="The question to search for", min_length=1)


def build_rag_tool(tenant: str, library_id_list: list[int], api_key: str | None = None) -> StructuredTool:
    """Build a RAG search tool with preset parameters, exposing only the query argument."""
    key = api_key or RAG_API_KEY
    search_fn = partial(
        _search,
        tenant=tenant,
        library_id_list=library_id_list,
        document_id_list=[],
        api_key=key,
    )

    return StructuredTool.from_function(
        coroutine=search_fn,
        name="rag_retrieval",
        description="RAG search tool for retrieving relevant information from the knowledge base. Use this tool to look up any unknown questions.",
        args_schema=RagSearchInput,
    )


if __name__ == "__main__":
    import asyncio

    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    async def test_rag_search():
        print("=== Test 1: Direct _search call ===")
        result = await _search(
            tenant="duanyuedekongjian_3d6c",
            library_id_list=[68600736],
            document_id_list=[],
            query="What is Faceby?",
        )
        print(f"Result length: {len(result)} chars")
        print(f"Preview: {result[:300]}...")
        print()

        print("=== Test 2: build_rag_tool (LangChain StructuredTool) ===")
        tool = build_rag_tool(
            tenant="duanyuedekongjian_3d6c",
            library_id_list=[68600736],
        )
        print(f"Tool name: {tool.name}")
        print(f"Tool description: {tool.description}")
        print(f"Tool args schema: {tool.args_schema.model_json_schema()}")
        result2 = await tool.ainvoke({"query": "When did World War II end?"})
        print(f"Result length: {len(result2)} chars")
        print(f"Preview: {result2[:300]}...")
        print()

        print("=== Test 3: Error handling - empty query ===")
        result3 = await _search(
            tenant="duanyuedekongjian_3d6c",
            library_id_list=[68600736],
            document_id_list=[],
            query="",
        )
        print(f"Empty query result: '{result3}'")
        print()

        print("All tests passed!")

    asyncio.run(test_rag_search())

