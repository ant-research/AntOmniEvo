import logging
import os
from datetime import datetime
from typing import Any
from uuid import uuid4

from langchain_core.tools import BaseTool, tool

from antomnievo.interface.data_inst import DataInst
from antomnievo.interface.system import System
from antomnievo.model.candidate_data import CandidateMeta
from antomnievo.model.rollout_result import RolloutResult
from antomnievo.model.system_result import SystemResult
from antomnievo.model.trajectory import Span, Trajectory
from antomnievo.system.langgraph.react_agent import create_react_agent

logger = logging.getLogger(__name__)

def _skill_md_path(candidate_meta: CandidateMeta) -> str:
    return os.path.join(candidate_meta.artifact_dir, "SKILL.md")


def _read_skill_md(candidate_meta: CandidateMeta) -> str | None:
    path = _skill_md_path(candidate_meta)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return f.read()
    return None

def _build_artifact_file_tools(candidate_meta: CandidateMeta) -> list[BaseTool]:
    """Build file tools scoped to a candidate's tunable-artifact directory."""
    artifact_dir = candidate_meta.artifact_dir

    @tool
    def read_artifact_file(path: str) -> str:
        """Read a file from the specific skill directory. You MUST call this tool whenever SKILL.md
        instructs you to read a reference file (e.g. lines containing "Read `references/...`"
        or "see references/... for"). File paths are listed in SKILL.md's ## References
        section — use the exact paths shown there. These reference files contain detailed
        strategies, examples, and rules that are essential for correct task completion —
        SKILL.md only contains summaries, the full guidance is in the reference files.

        Args:
            path: Relative path within the tunable-artifact directory (e.g. "references/patterns.md", "scripts/search.py").
        """
        full_path = os.path.normpath(os.path.join(artifact_dir, path))
        if not full_path.startswith(os.path.normpath(artifact_dir)):
            return "Error: path traversal not allowed"
        if not os.path.isfile(full_path):
            return f"File not found: {path}"
        try:
            with open(full_path, encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            return f"Error reading file: {e}"

    return [read_artifact_file]


class ReactAgentSystem(System):
    """System implementation that runs a LangGraph ReAct Agent. It is used for experiment.
    It loads the candidate tunable-artifact data to complete tasks.

    Loads SKILL.md as the system prompt. Provides file tools so the agent
    """

    def __init__(
        self,
        llm: Any,
        tools: list[BaseTool],
        system_prompt: str = "",
        max_assistant_turns: int = 20,
        agent_name: str = "react_agent",
        concurrency: int = 8,
    ):
        super().__init__(concurrency=concurrency)
        self.llm = llm
        self.tools = tools
        self.system_prompt = system_prompt
        self.max_assistant_turns = max_assistant_turns
        self.agent_name = agent_name

    async def _run(self, candidate_meta: CandidateMeta, data_inst: DataInst) -> SystemResult:
        skill_prompt = _read_skill_md(candidate_meta) or ""

        # Build tool usage instructions
        tool_instructions = "\n\n## Available Tools\nYou MUST use the following tools to complete tasks. Do NOT answer without calling tools first.\n"
        for t in self.tools:
            tool_instructions += f"- `{t.name}`: {t.description}\n"
        tool_instructions += "- `read_artifact_file`: Read reference files from the tunable-artifact directory as instructed by SKILL.md.\n"
        tool_instructions += "\nIMPORTANT: Always call the appropriate tool(s) before answering. Never say you cannot access information — use the tools to retrieve it."

        system_prompt = f"{self.system_prompt}\n\n{skill_prompt}{tool_instructions}".strip()
        artifact_tools = _build_artifact_file_tools(candidate_meta)

        agent = create_react_agent(
            llm=self.llm,
            tools=self.tools + artifact_tools,
            system_prompt=system_prompt,
            max_assistant_turns=self.max_assistant_turns,
            agent_name=self.agent_name,
        )

        session_id = f"session_{candidate_meta.candidate_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        trace_id = str(uuid4())

        result = await agent.arun(
            user_input=data_inst.query,
            session_id=session_id,
            trace_id=trace_id,
        )

        trajectory = result.trajectory or Trajectory(root_span_list=[])
        output = RolloutResult(content=result.answer or "")

        if not result.success:
            logger.error(f"ReactAgentSystem run failed for data_id={data_inst.id}: {result.error}")

        return SystemResult(trajectory=trajectory, output=output)


async def main():
    import tempfile

    import httpx
    import yaml

    from antomnievo.common.theta_llm import ThetaLLM
    from antomnievo.common.tool.rag.rag_search import build_rag_tool

    # antchat creds from <repo>/config/config.yaml.
    _cfg_file = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "config", "config.yaml")
    )
    with open(_cfg_file, encoding="utf-8") as _f:
        _antchat_cfg = yaml.safe_load(_f)
    _api_keys = _antchat_cfg["api_keys"]
    _base_url = _antchat_cfg["base_url"]

    # ---- HTTP client ----
    timeout = httpx.Timeout(1200.0, connect=1200.0, read=1200.0, write=1200.0, pool=100.0)
    http_client = httpx.Client(
        timeout=timeout,
        limits=httpx.Limits(max_keepalive_connections=20, max_connections=100),
        follow_redirects=True,
    )
    async_http_client = httpx.AsyncClient(
        timeout=timeout,
        limits=httpx.Limits(max_keepalive_connections=20, max_connections=100),
        follow_redirects=True,
    )

    # ---- LLM ----
    llm = ThetaLLM(
        model="Kimi-K2.5",
        api_key=_api_keys[0],
        base_url=_base_url,
        temperature=1,
        max_retries=10,
        http_client=http_client,
        http_async_client=async_http_client,
        request_timeout=1200,
    )

    # ---- RAG Tool ----
    rag_tool = build_rag_tool(
        tenant="duanyuedekongjian_3d6c",
        library_id_list=[68600736],
    )

    # ---- Build a candidate tunable-artifact directory ----
    artifact_dir = tempfile.mkdtemp(prefix="artifact_")
    os.makedirs(os.path.join(artifact_dir, "references"), exist_ok=True)

    with open(os.path.join(artifact_dir, "SKILL.md"), "w") as f:
        f.write(
            "---\n"
            "name: knowledge-qa\n"
            "description: Knowledge base Q&A assistant that answers questions using retrieved information.\n"
            "---\n\n"
            "## Core Workflow\n"
            "1. BEFORE answering any question, read `references/city_info.md` for essential domain facts.\n"
            "2. Use the rag_retrieval tool to search the knowledge base.\n"
            "3. Synthesize the answer from retrieved information and reference files.\n\n"
            "## Rules\n"
            "- All answers must be based on retrieved information or reference files, never your own knowledge.\n"
            "- Read `references/city_info.md` before attempting any question — it contains critical facts.\n\n"
            "## References\n"
            "- `references/city_info.md` — BEFORE answering any question, read this for essential domain facts.\n"
        )

    with open(os.path.join(artifact_dir, "references", "city_info.md"), "w") as f:
        f.write(
            "# City Information\n\n"
            "Faceby is a small town in North Yorkshire, England. "
            "It is located near the A172 road between Stokesley and Swainby. "
            "The town has a population of approximately 200 people.\n"
        )

    meta = CandidateMeta(candidate_id="demo", artifact_dir=artifact_dir, data_dir="")

    # ---- Run ----
    system = ReactAgentSystem(
        llm=llm,
        tools=[rag_tool],
        max_assistant_turns=20,
    )

    query = "What is Faceby?"
    data_inst = DataInst(id="0", query=query, golden_answer="")

    logger.info(f"Query: {query}")
    logger.info(f"Artifact dir: {artifact_dir}")

    result = await system.run(meta, data_inst)

    logger.info(f"Output: {result.output.content}")
    logger.info(f"Trajectory spans: {len(result.trajectory.root_span_list)}")

    # ---- Check tool calls ----
    read_artifact_file_called = False
    rag_retrieval_called = False

    def _check_spans(spans: list[Span]):
        nonlocal read_artifact_file_called, rag_retrieval_called
        for span in spans:
            if span.span_type == "tool_call":
                if span.name == "read_artifact_file":
                    read_artifact_file_called = True
                    logger.info(f"read_artifact_file called with input: {span.input}")
                elif span.name == "rag_retrieval":
                    rag_retrieval_called = True
                    logger.info(f"rag_retrieval called with input: {span.input}")
            _check_spans(span.children)

    _check_spans(result.trajectory.root_span_list)
    if read_artifact_file_called:
        logger.info("SUCCESS: read_artifact_file was called by the agent")
    else:
        logger.warning("FAILURE: read_artifact_file was NOT called by the agent")
    if rag_retrieval_called:
        logger.info("SUCCESS: rag_retrieval was called by the agent")
    else:
        logger.warning("FAILURE: rag_retrieval was NOT called by the agent")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
