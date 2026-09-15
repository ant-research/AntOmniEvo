import asyncio
import logging
import time
import traceback
from datetime import datetime
from typing import Annotated, Any, TypedDict
from uuid import uuid4

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from pydantic import BaseModel
from tenacity import RetryCallState, retry, retry_if_exception, stop_after_attempt, wait_exponential

from antomnievo.model.trajectory import Span, Trajectory

logger = logging.getLogger(__name__)

_RETRYABLE_API_MESSAGES = (
    "request queue is full",
    "rate limit",
    "too many requests",
    "non-exist tool",
    "service unavailable",
)


def _is_retryable_error(exception: BaseException) -> bool:
    try:
        import openai
        if isinstance(exception, (openai.RateLimitError, openai.APIConnectionError, openai.APITimeoutError)):
            return True
        if isinstance(exception, openai.APIError):
            msg = str(exception).lower()
            if any(kw in msg for kw in _RETRYABLE_API_MESSAGES):
                return True
    except ImportError:
        pass

    try:
        import httpx
        if isinstance(exception, (httpx.RemoteProtocolError, httpx.ConnectError, httpx.ReadTimeout)):
            return True
    except ImportError:
        pass

    try:
        import httpcore
        if isinstance(exception, (httpcore.RemoteProtocolError, httpcore.ConnectError, httpcore.ReadTimeout)):
            return True
    except ImportError:
        pass

    return False


def _log_retry(description: str):
    def _before_sleep(retry_state: RetryCallState) -> None:
        exception = retry_state.outcome.exception()
        wait_seconds = retry_state.next_action.sleep if retry_state.next_action else 0
        logger.warning(
            f"[Retry] {description} attempt {retry_state.attempt_number} failed, "
            f"retrying in {wait_seconds:.1f}s. "
            f"Exception: {type(exception).__name__}, Error: {exception}"
        )
    return _before_sleep


_LLM_RETRY_CONFIG = dict(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=2, max=60),
    retry=retry_if_exception(_is_retryable_error),
    before_sleep=_log_retry("LLM call"),
    reraise=True,
)

_TOOL_RETRY_CONFIG = dict(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=1, max=30),
    retry=retry_if_exception(_is_retryable_error),
    before_sleep=_log_retry("Tool call"),
    reraise=True,
)


DEFAULT_SYSTEM_PROMPT = """You are an intelligent assistant that can use tools to help users solve problems.

Follow these steps:
1. Understand the user's question
2. Decide which tools to use
3. Call tools to gather information
4. Provide a final answer based on the information gathered

When the task is complete, give a clear answer."""


class AgentState(TypedDict):
    id: str
    name: str
    initialized: bool
    messages: Annotated[list[BaseMessage], add_messages]
    current_turn: int
    terminated: bool
    max_assistant_turns: int
    user_input: str
    answer: str | None


class TrajectoryCollector:
    def __init__(self, session_id: str | None = None, trace_id: str | None = None):
        self.session_id = session_id or str(uuid4())
        self.trace_id = trace_id or str(uuid4())
        self.root_span_list: list[Span] = []
        self._current_span_stack: list[Span] = []
        self._tool_call_results: dict[str, str] = {}

    def start_span(
        self,
        name: str,
        span_type: str,
        input_data: Any | None = None,
        metadata: dict[str, Any] | None = None
    ) -> Span:
        span = Span(
            name=name,
            span_type=span_type,
            input=input_data,
            start_time=datetime.now(),
            metadata=metadata or {}
        )

        if self._current_span_stack:
            parent_span = self._current_span_stack[-1]
            span.parent_span_id = parent_span.id
            parent_span.add_child(span)
        else:
            self.root_span_list.append(span)

        self._current_span_stack.append(span)
        return span

    def end_span(
        self,
        span: Span,
        output_data: Any | None = None,
        metadata: dict[str, Any] | None = None
    ) -> None:
        span.end_time = datetime.now()
        if output_data is not None:
            span.output = output_data
        if metadata:
            span.metadata.update(metadata)

        if self._current_span_stack and self._current_span_stack[-1].id == span.id:
            self._current_span_stack.pop()

    def record_tool_result(self, tool_call_id: str, result: str) -> None:
        self._tool_call_results[tool_call_id] = result

    def get_tool_result(self, tool_call_id: str) -> str | None:
        return self._tool_call_results.get(tool_call_id)

    def get_trajectory(self) -> Trajectory:
        return Trajectory(
            root_span_list=self.root_span_list,
            session_id=self.session_id,
            trace_id=self.trace_id
        )

    def reset(self) -> None:
        self.root_span_list = []
        self._current_span_stack = []
        self._tool_call_results = {}


class ReactAgentConfig(BaseModel):
    model_name: str = "Kimi-K2-Instruct-0905"
    temperature: float = 1.2
    max_assistant_turns: int = 15
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    agent_name: str = "agent"


class ReactAgentResult(BaseModel):
    answer: str = ""
    trajectory: Trajectory | None = None
    success: bool = True
    error: str | None = None
    latency: float = 0.0
    llm_call_count: int = 0
    tool_call_count: int = 0
    session_id: str | None = None
    trace_id: str | None = None


class ReactAgent:
    def __init__(
        self,
        llm: Any,
        tools: list[BaseTool],
        config: ReactAgentConfig | None = None,
    ):
        self.llm = llm
        self.tools = tools
        self.config = config or ReactAgentConfig()
        self.tools_by_name = {tool.name: tool for tool in tools}
        self.llm_with_tools = llm.bind_tools(tools, tool_choice="auto")
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        def receive_user_input(state: AgentState, config: RunnableConfig) -> dict:
            if state.get("initialized", False):
                raise RuntimeError("Agent does not support multi-turn conversation!")

            return {
                "initialized": True,
                "name": self.config.agent_name,
                "messages": [
                    SystemMessage(content=self.config.system_prompt),
                    HumanMessage(content=state["user_input"])
                ],
                "current_turn": 0,
                "terminated": False,
            }

        async def chatbot(state: AgentState, config: RunnableConfig) -> dict:
            current_turn = state.get("current_turn", 0)

            @retry(**_LLM_RETRY_CONFIG)
            async def _invoke_llm():
                return await self.llm_with_tools.ainvoke(
                    state["messages"],
                    config=config
                )

            ai_message: AIMessage = await _invoke_llm()

            return {
                "messages": [ai_message],
                "current_turn": current_turn + 1
            }

        async def execute_tool_calls(state: AgentState, config: RunnableConfig) -> dict:
            def _resolve_tool_name(name: str) -> str | None:
                if name in self.tools_by_name:
                    return name
                # LLM may generate prefixed names like "skills.read_spec_file"
                short_name = name.rsplit(".", 1)[-1]
                if short_name in self.tools_by_name:
                    logger.warning(f"Tool name '{name}' resolved to '{short_name}'")
                    return short_name
                return None

            async def process_single_tool_call(tool_call: dict) -> ToolMessage:
                tool_name = tool_call["name"]
                resolved_name = _resolve_tool_name(tool_name)
                if resolved_name is None:
                    observation = f"Tool {tool_name} not found. Available tools: {list(self.tools_by_name.keys())}"
                else:
                    try:
                        tool = self.tools_by_name[resolved_name]

                        @retry(**_TOOL_RETRY_CONFIG)
                        async def _invoke_tool():
                            return await tool.ainvoke(tool_call["args"])

                        observation = await _invoke_tool()
                    except Exception as e:
                        observation = f"Tool {tool_name} execution error: {e!s}"

                return ToolMessage(content=str(observation), tool_call_id=tool_call["id"])

            msg: AIMessage = state["messages"][-1]
            tool_call_tasks = [
                process_single_tool_call(tool_call)
                for tool_call in msg.tool_calls
            ]

            result = await asyncio.gather(*tool_call_tasks)
            return {"messages": result}

        def max_turn_exceeded_alert(state: AgentState, config: RunnableConfig) -> dict:
            return {
                "messages": [HumanMessage(content="Max turns reached, please provide your final answer.")]
            }

        def extract_answer(state: AgentState, config: RunnableConfig) -> dict:
            msg: AIMessage = state["messages"][-1]
            content = msg.content or ""
            return {
                "answer": content,
                "terminated": True
            }

        def tools_condition(state: AgentState, config: RunnableConfig) -> str:
            max_turns = state.get("max_assistant_turns", self.config.max_assistant_turns)
            msg: AIMessage = state["messages"][-1]

            if not msg.tool_calls:
                return "extract_answer"

            if state["current_turn"] > max_turns:
                return "max_turn_exceeded_alert"

            return "execute_tool_calls"

        graph_builder = StateGraph(AgentState)

        graph_builder.add_node("receive_user_input", receive_user_input)
        graph_builder.add_node("chatbot", chatbot)
        graph_builder.add_node("execute_tool_calls", execute_tool_calls)
        graph_builder.add_node("max_turn_exceeded_alert", max_turn_exceeded_alert)
        graph_builder.add_node("extract_answer", extract_answer)

        graph_builder.set_entry_point("receive_user_input")

        graph_builder.add_edge("receive_user_input", "chatbot")
        graph_builder.add_conditional_edges(
            "chatbot",
            tools_condition,
            ["execute_tool_calls", "max_turn_exceeded_alert", "extract_answer"]
        )
        graph_builder.add_edge("execute_tool_calls", "chatbot")
        graph_builder.add_edge("max_turn_exceeded_alert", "chatbot")
        graph_builder.add_edge("extract_answer", END)

        return graph_builder.compile()

    def _collect_trajectory_from_messages(
        self,
        messages: list[BaseMessage],
        collector: TrajectoryCollector
    ) -> None:
        root_span = collector.start_span(
            name="agent",
            span_type="agent",
            input_data=messages[1].content if len(messages) > 1 else "",
        )

        i = 2
        while i < len(messages):
            msg = messages[i]

            if isinstance(msg, AIMessage):
                thinking_span = collector.start_span(
                    name="model",
                    span_type="model",
                )

                if msg.tool_calls:
                    collector.end_span(
                        thinking_span,
                        output_data={
                            "content": msg.content if msg.content else None,
                            "tool_calls": msg.tool_calls if msg.tool_calls else None,
                        },
                    )

                    for tool_call in msg.tool_calls:
                        tool_span = collector.start_span(
                            name=tool_call["name"],
                            span_type="tool_call",
                            input_data={
                                "arguments": tool_call.get("args", {})
                            },
                            metadata={
                                "tool_call_id": tool_call.get("id")
                            }
                        )

                        tool_call_id = tool_call.get("id")
                        tool_result = None

                        for j in range(i + 1, len(messages)):
                            next_msg = messages[j]
                            if isinstance(next_msg, ToolMessage) and next_msg.tool_call_id == tool_call_id:
                                tool_result = next_msg.content
                                break

                        collector.end_span(
                            tool_span,
                            output_data={
                                "result": tool_result
                            }
                        )
                else:
                    collector.end_span(
                        thinking_span,
                        output_data={
                            "thought": msg.content
                        }
                    )

            i += 1

        collector.end_span(
            root_span,
            output_data=messages[-1].content if messages else None
        )

    async def arun(
        self,
        user_input: str,
        session_id: str | None = None,
        trace_id: str | None = None,
        **kwargs
    ) -> ReactAgentResult:
        collector = TrajectoryCollector(
            session_id=session_id,
            trace_id=trace_id
        )

        start_time = time.time()
        llm_call_count = 0
        tool_call_count = 0
        success = True
        error = None
        answer = ""

        try:
            thread_id = str(uuid4())
            config = {
                "configurable": {"thread_id": thread_id},
                "recursion_limit": 1000
            }

            input_state: AgentState = {
                "id": thread_id,
                "user_input": user_input,
                "max_assistant_turns": kwargs.get("max_assistant_turns", self.config.max_assistant_turns)
            }

            agent_state = await self.graph.ainvoke(input_state, config=config)

            messages = agent_state.get("messages", [])
            self._collect_trajectory_from_messages(messages, collector)

            for msg in messages:
                if isinstance(msg, AIMessage):
                    llm_call_count += 1
                    if msg.tool_calls:
                        tool_call_count += len(msg.tool_calls)

            answer = agent_state.get("answer", "")

        except Exception as e:
            success = False
            error = str(e)
            traceback.print_exc()

        latency = time.time() - start_time

        return ReactAgentResult(
            answer=answer,
            trajectory=collector.get_trajectory(),
            success=success,
            error=error,
            latency=latency,
            llm_call_count=llm_call_count,
            tool_call_count=tool_call_count
        )


def create_react_agent(
    llm: Any,
    tools: list[BaseTool],
    system_prompt: str | None = None,
    max_assistant_turns: int = 15,
    agent_name: str = "react_agent",
) -> ReactAgent:
    config = ReactAgentConfig(
        system_prompt=system_prompt or DEFAULT_SYSTEM_PROMPT,
        max_assistant_turns=max_assistant_turns,
        agent_name=agent_name
    )

    return ReactAgent(
        llm=llm,
        tools=tools,
        config=config,
    )
