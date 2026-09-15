"""Parse agent CLI output (stream-json / Pi JSON mode / eddy) into Trajectory + UsageStats.

Provides:
- parse_stream_json: Claude Code stream-json → Trajectory parsing
- parse_pi_json_output: Pi Coding Agent JSON mode → Trajectory parsing
- parse_eddy_trajectory: eddy agent trajectory dict → Trajectory parsing
"""

import json
import logging
from datetime import datetime
from typing import Any

from antomnievo.model.trajectory import Span, Trajectory
from antomnievo.model.usage_stats import UsageStats

logger = logging.getLogger(__name__)


def parse_stream_json(raw_output: str) -> tuple[Trajectory, UsageStats]:
    """Parse Claude Code stream-json output into a Trajectory and UsageStats.

    Each line of raw_output is a JSON event. Supported event types:
    - "assistant": model turn with text and/or tool_use content blocks
    - "user": tool_result content blocks (matched by tool_use_id)
    - "result": final result text (attached to last model span) with usage stats

    Returns:
        A tuple of (Trajectory, UsageStats).
    """
    root_spans: list[Span] = []
    current_model_span: Span | None = None
    tool_result_map: dict[str, str] = {}
    stats = UsageStats()

    for line in raw_output.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        event_type = event.get("type")

        if event_type == "assistant":
            message = event.get("message", {})
            content: list[dict[str, Any]] = message.get("content", [])

            model_span = Span(
                name="model",
                span_type="model",
                input=None,
                start_time=datetime.now(),
            )
            tool_spans: list[Span] = []

            for block in content:
                if block.get("type") == "tool_use":
                    tool_span = Span(
                        name=block.get("name", "unknown"),
                        span_type="tool_call",
                        input=block.get("input"),
                        start_time=datetime.now(),
                        metadata={"tool_call_id": block.get("id")},
                    )
                    tool_spans.append(tool_span)
                elif block.get("type") == "text":
                    model_span.input = block.get("text", "")

            for ts in tool_spans:
                tc_id = ts.metadata.get("tool_call_id")
                if tc_id and tc_id in tool_result_map:
                    ts.output = {"result": tool_result_map.pop(tc_id)}
                model_span.add_child(ts)

            model_span.end_time = datetime.now()
            root_spans.append(model_span)
            current_model_span = model_span

        elif event_type == "user":
            message = event.get("message", {})
            for block in message.get("content", []):
                if block.get("type") == "tool_result":
                    tc_id = block.get("tool_use_id")
                    content_str = block.get("content", "")
                    if tc_id:
                        tool_result_map[tc_id] = str(content_str)

        elif event_type == "result":
            result_text = event.get("result", "")
            if current_model_span:
                current_model_span.output = result_text

            usage = event.get("usage", {})
            if usage:
                stats.input_tokens = usage.get("input_tokens", 0)
                stats.output_tokens = usage.get("output_tokens", 0)
                stats.cache_creation_input_tokens = usage.get("cache_creation_input_tokens", 0)
                stats.cache_read_input_tokens = usage.get("cache_read_input_tokens", 0)

    # Attach any remaining tool results to matching tool spans
    for tc_id, result in tool_result_map.items():
        for span in root_spans:
            for child in span.children:
                if child.metadata.get("tool_call_id") == tc_id:
                    child.output = {"result": result}
                    break

    return Trajectory(root_span_list=root_spans), stats


def parse_pi_json_output(raw_output: str) -> tuple[Trajectory, UsageStats]:
    """Parse Pi Coding Agent JSON mode output into a Trajectory and UsageStats.

    Pi emits NDJSON events. Key event types:
    - "message_start" / "message_update" / "message_end": message streaming
    - "tool_execution_start" / "tool_execution_end": tool calls
    - "agent_start" / "agent_end" / "turn_start" / "turn_end": lifecycle

    Assistant message content blocks include "thinking", "text", and "toolCall".
    Each assistant message becomes one "model" span whose children are, in stream
    order, "thinking" spans and "tool_call" spans. Plain text segments are
    concatenated into the model span's output. Tool results from "toolResult"
    user messages or "tool_execution_end" events are attached as the tool span's
    output. Usage stats accumulate from each assistant message_end's usage field.

    Returns:
        A tuple of (Trajectory, UsageStats).
    """
    root_spans: list[Span] = []
    current_model_span: Span | None = None
    current_thinking_span: Span | None = None
    pending_children: list[Span] = []
    tool_result_map: dict[str, str] = {}
    stats = UsageStats()

    ignored_event_types = {
        "session", "agent_start",
        "compaction_start", "compaction_end",
        "auto_retry_start", "auto_retry_end",
        "thinking_level_changed", "session_info_changed",
        "queue_update", "tool_execution_update",
        "turn_start", "turn_end",
    }

    def flush_current_model_span() -> None:
        nonlocal current_model_span, current_thinking_span, pending_children
        if current_model_span is None:
            pending_children = []
            current_thinking_span = None
            return
        for ch in pending_children:
            if ch.span_type == "tool_call":
                tc_id = ch.metadata.get("tool_call_id")
                if tc_id and tc_id in tool_result_map:
                    ch.output = {"result": tool_result_map.pop(tc_id)}
            current_model_span.add_child(ch)
        current_model_span.end_time = datetime.now()
        root_spans.append(current_model_span)
        current_model_span = None
        current_thinking_span = None
        pending_children = []

    def find_pending_tool_span(tc_id: str) -> Span | None:
        for ch in pending_children:
            if ch.span_type == "tool_call" and ch.metadata.get("tool_call_id") == tc_id:
                return ch
        return None

    def _iter_events(raw: str):
        """Yield event dicts from NDJSON, flattening any nested arrays."""
        for line_num, line in enumerate(raw.strip().splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                logger.warning(f"Skipping malformed JSON at line {line_num}: {line[:100]}")
                continue
            if isinstance(parsed, dict):
                yield parsed
            elif isinstance(parsed, list):
                for item in parsed:
                    if isinstance(item, dict):
                        yield item
                    else:
                        logger.warning(f"Skipping non-dict element in nested array at line {line_num}: {type(item).__name__}")
            else:
                logger.warning(f"Skipping unexpected JSON type at line {line_num}: {type(parsed).__name__}")

    for event in _iter_events(raw_output):
        event_type = event.get("type")
        if event_type in ignored_event_types:
            continue

        if event_type == "message_start":
            message = event.get("message", {})
            if message.get("role") == "assistant":
                flush_current_model_span()
                current_model_span = Span(
                    name="model",
                    span_type="model",
                    input=None,
                    start_time=datetime.now(),
                )

        elif event_type == "message_update":
            if current_model_span is None:
                continue
            assistant_event = event.get("assistantMessageEvent", {})
            delta_type = assistant_event.get("type", "")

            if delta_type == "thinking_start":
                current_thinking_span = Span(
                    name="thinking",
                    span_type="thinking",
                    input=None,
                    output="",
                    start_time=datetime.now(),
                )
                pending_children.append(current_thinking_span)

            elif delta_type == "thinking_delta":
                if current_thinking_span is None:
                    current_thinking_span = Span(
                        name="thinking",
                        span_type="thinking",
                        input=None,
                        output="",
                        start_time=datetime.now(),
                    )
                    pending_children.append(current_thinking_span)
                delta = assistant_event.get("thinking") or assistant_event.get("text") or ""
                current_thinking_span.output = (current_thinking_span.output or "") + delta

            elif delta_type == "thinking_end":
                if current_thinking_span is not None:
                    canonical = assistant_event.get("content") or assistant_event.get("thinking")
                    if canonical:
                        current_thinking_span.output = canonical
                    current_thinking_span.end_time = datetime.now()
                    current_thinking_span = None

            elif delta_type == "text_delta":
                text = assistant_event.get("text", "")
                if text:
                    current_model_span.output = (current_model_span.output or "") + text

            elif delta_type == "toolcall_start":
                tool_call = assistant_event.get("toolCall", {})
                if tool_call.get("name"):
                    pending_children.append(Span(
                        name=tool_call["name"],
                        span_type="tool_call",
                        input=tool_call.get("arguments"),
                        start_time=datetime.now(),
                        metadata={"tool_call_id": tool_call.get("id", "")},
                    ))

            elif delta_type == "toolcall_end":
                tool_call = assistant_event.get("toolCall", {})
                tc_id = tool_call.get("id", "")
                existing = find_pending_tool_span(tc_id) if tc_id else None
                if existing:
                    args = tool_call.get("arguments")
                    if args is not None:
                        existing.input = args

        elif event_type == "message_end":
            message = event.get("message", {})
            role = message.get("role", "")

            if role == "assistant" and current_model_span is not None:
                content = message.get("content", [])
                text_parts: list[str] = []
                thinking_parts: list[str] = []
                if isinstance(content, list):
                    for block in content:
                        if not isinstance(block, dict):
                            continue
                        btype = block.get("type", "")
                        if btype == "text":
                            text_parts.append(block.get("text", ""))
                        elif btype == "thinking":
                            thinking_parts.append(block.get("thinking", ""))
                        elif btype == "toolCall":
                            tc_id = block.get("id", "")
                            existing = find_pending_tool_span(tc_id) if tc_id else None
                            if existing:
                                args = block.get("arguments")
                                if args is not None:
                                    existing.input = args
                            else:
                                pending_children.append(Span(
                                    name=block.get("name", "unknown"),
                                    span_type="tool_call",
                                    input=block.get("arguments"),
                                    start_time=datetime.now(),
                                    metadata={"tool_call_id": tc_id},
                                ))

                if text_parts:
                    joined = "\n\n".join(t for t in text_parts if t)
                    if joined:
                        current_model_span.output = joined

                thinking_children = [ch for ch in pending_children if ch.span_type == "thinking"]
                for span_ch, full_text in zip(thinking_children, thinking_parts, strict=False):
                    if full_text:
                        span_ch.output = full_text
                for extra in thinking_parts[len(thinking_children):]:
                    if extra:
                        pending_children.append(Span(
                            name="thinking",
                            span_type="thinking",
                            input=None,
                            output=extra,
                            start_time=datetime.now(),
                            end_time=datetime.now(),
                        ))

                usage = message.get("usage", {})
                if usage:
                    stats.input_tokens += usage.get("input", 0)
                    stats.output_tokens += usage.get("output", 0)
                    stats.cache_read_input_tokens += usage.get("cacheRead", 0)
                    stats.cache_creation_input_tokens += usage.get("cacheWrite", 0)

                # Capture assistant-message failures (e.g. antchat 401 "服务未授权",
                # 5xx, rate limit) so they surface instead of being silently
                # dropped — see _check_agent_errors below.
                stop_reason = message.get("stopReason")
                error_message = message.get("errorMessage")
                if current_model_span is not None:
                    if stop_reason:
                        current_model_span.metadata["stop_reason"] = stop_reason
                    if error_message:
                        current_model_span.metadata["error_message"] = error_message

                flush_current_model_span()

            elif role == "user":
                content = message.get("content", [])
                text_parts = []
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            text_parts.append(block.get("text", ""))
                if text_parts:
                    root_spans.append(Span(
                        name="input",
                        span_type="span",
                        input="\n".join(text_parts),
                        start_time=datetime.now(),
                        end_time=datetime.now(),
                    ))

            elif role == "toolResult":
                tc_id = message.get("toolCallId", "")
                if tc_id:
                    content = message.get("content", [])
                    text_parts = []
                    if isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                text_parts.append(block.get("text", ""))
                    tool_result_map[tc_id] = "\n".join(text_parts) if text_parts else str(content)

        elif event_type == "tool_execution_start":
            tc_id = event.get("toolCallId", "")
            existing = find_pending_tool_span(tc_id) if tc_id else None
            if existing is not None:
                existing.start_time = datetime.now()

        elif event_type == "tool_execution_end":
            tool_call_id = event.get("toolCallId", "")
            result = event.get("result", {})
            if tool_call_id and result:
                if isinstance(result, dict):
                    content = result.get("content", [])
                    text_parts = []
                    if isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                text_parts.append(block.get("text", ""))
                    tool_result_map[tool_call_id] = "\n".join(text_parts) if text_parts else str(result)
                else:
                    tool_result_map[tool_call_id] = str(result)
            if tool_call_id:
                end_ts = datetime.now()
                stamped = False
                pending = find_pending_tool_span(tool_call_id)
                if pending is not None:
                    pending.end_time = end_ts
                    stamped = True
                if not stamped:
                    for span in root_spans:
                        for child in span.children:
                            if (child.span_type == "tool_call"
                                    and child.metadata.get("tool_call_id") == tool_call_id):
                                child.end_time = end_ts
                                stamped = True
                                break
                        if stamped:
                            break

        elif event_type == "agent_end":
            flush_current_model_span()

    flush_current_model_span()

    for tc_id, result in tool_result_map.items():
        for span in root_spans:
            for child in span.children:
                if child.span_type == "tool_call" and child.metadata.get("tool_call_id") == tc_id:
                    child.output = {"result": result}
                    break

    trajectory = Trajectory(root_span_list=root_spans)
    _collect_agent_errors(trajectory, stats)
    return trajectory, stats


# ─────────────────────────────────────────────────────────────────────────────
# eddy agent trajectory parser
# ─────────────────────────────────────────────────────────────────────────────

def parse_eddy_trajectory(
    raw_trajectory: dict,
    *,
    tool_output_max_chars: int = 4000,
    root_output_max_chars: int = 4000,
    pre_reasoning_max_chars: int = 300,
) -> tuple[Trajectory, UsageStats]:
    """Parse an eddy agent trajectory dict into a :class:`Trajectory` + :class:`UsageStats`.

    This is the eddy equivalent of parse_stream_json / parse_pi_json_output.
    It is **reusable across eddy System modules** — do NOT write a bespoke
    trajectory builder in each System; call this instead.

    ## What you give it

    ``raw_trajectory`` is one row from `generate.py`'s ``trajectories.jsonl`` output.
    The eddy trajectory schema (produced by the project's ``build_trajectory()``)
    is a JSON dict with these top-level keys (all optional; the parser falls back
    to scanning ``messages`` for anything missing):

    - ``case_id`` (str)
    - ``case`` — nested block; ``case.instruction`` or ``case.query`` = the user's prompt
    - ``output.final_text`` (str) — the agent's final answer text
    - ``messages`` (list[dict]) — the eddy agent's message stream. Each message is
      ``{source: "react"|None, status: str|None, content: list[content_item]}``.
      Each content item is ``{type: "reasoning"|"text"|"tool_call"|"tool_result", ...}``.
      - `reasoning`: the agent's thinking block (with `reasoning` field holding the text).
      - `text`: a text output block (`text` field).
      - `tool_call`: ``{tool_call_id, tool_name, args}``.
      - `tool_result`: ``{tool_call_id, tool_name, output}``.
      - The final message has ``status`` in {`completed`, `awaiting`, `pause`, `error`}.
    - ``tool_calls`` (optional list[dict]) — pre-extracted tool_call dict list.
    - ``tool_results`` (optional list[dict]) — pre-extracted tool_result dict list.
    - ``message_summary`` (optional dict) — has ``content_type_counts`` or similar.
    - ``human_input_required`` (optional list|None) — HITL gate block.
    - ``run`` (optional dict) — may carry ``status`` for run_status.

    ## What you get

    A :class:`Trajectory` with:

    - **Root span** (``span_type=eddy_agent_run``)
        - `name` = case_id
        - `input` = `case.instruction` (the user's prompt)
        - `output` = `output.final_text` (truncated to ``root_output_max_chars``)
        - `metadata` = {case_id, run_status, n_messages, content_type_counts, human_input_required}

    - **Child spans** (one per tool_call, ``span_type=tool_call``)
        - `name` = tool_name (e.g., `adconfig_getHistoryConfigContent`)
        - `input` = tool args (the dict passed to the tool)
        - `output` = tool result's `output` field (truncated past ``tool_output_max_chars``,
            with metadata flag ``output_truncated=True`` + ``output_original_len``)
        - `metadata` = {tool_call_id, , output_truncated?, output_original_len?, pre_reasoning?}
            - ``pre_reasoning`` — reasoning text from the eddy agent's `reasoning` blocks
              that immediately preceded this tool_call (truncated to
              ``pre_reasoning_max_chars``). This WHY context helps the proposer analyze
              agent behavior beyond raw tool inputs.
            - **No** ``raw_tool_call`` or ``raw_tool_result`` (we don't duplicate
              ``span.input``/``span.output`` — those ARE the data, and the prior
              practice of storing copies in metadata was a 47% bloat bug)

    - ``errors`` — non-empty if ``run_status ∈ {error, timeout}`` (terminal message status)
      or if the trajectory has no messages AND no tool_calls (silent empty).

    A :class:`UsageStats` with zeros (eddy doesn't surface token usage in the
    trajectory dict; populate separately if your generate.py emits usage data).

    ## Size considerations

    The trajectory is persisted to the candidate store for the proposer (a coding agent)
    to read. A 35-tool-call trajectory with full outputs can hit 750 KB; truncating
    tool outputs to 4 KB each + removing metadata redundancy cuts it to ~80 KB.
    The thresholds are kwargs so each System module can tune:

    >>> from antomnievo.common.utils.trajectory_parser import parse_eddy_trajectory
    >>> tr, stats = parse_eddy_trajectory(
    ...     traj_dict,
    ...     tool_output_max_chars=8000,   # more context for proposer
    ...     root_output_max_chars=4000,
    ...     pre_reasoning_max_chars=500,
    ... )

    Reuse this for ANY eddy agent by loading the row from trajectories.jsonl.
    """
    stats = UsageStats()

    messages = raw_trajectory.get("messages")
    if not isinstance(messages, list):
        messages = []

    # 1. extract tool events — prefer the project's pre-extracted top-level fields;
    #    fall back to scanning messages[].content[] by type.
    tool_calls, tool_results = _eddy_extract_tool_events(raw_trajectory, messages)

    # 2. case info + final text
    case_block = raw_trajectory.get("case") or {}
    case_id = str(
        raw_trajectory.get("case_id")
        or case_block.get("case_id")
        or ""
    )
    instruction = str(
        case_block.get("instruction")
        or case_block.get("query")
        or ""
    )
    out_block = raw_trajectory.get("output") or {}
    final_text = str(out_block.get("final_text") or "") if isinstance(out_block, dict) else ""
    if len(final_text) > root_output_max_chars:
        final_text = final_text[:root_output_max_chars] + "…(truncated)"

    # 3. run_status — walk messages reversed; first message with status = latest
    run_status = ""
    for msg in reversed(messages):
        s = msg.get("status") if isinstance(msg, dict) else None
        if s:
            run_status = str(s)
            break
    if not run_status:
        run_block = raw_trajectory.get("run") or {}
        run_status = str(run_block.get("status") or "") if isinstance(run_block, dict) else ""

    # 4. content-type counts (prefer message_summary from generate.py; fall back to scan)
    content_type_counts: dict[str, Any] = {}
    msg_summary = raw_trajectory.get("message_summary")
    if isinstance(msg_summary, dict):
        ctc = msg_summary.get("content_type_counts")
        if isinstance(ctc, dict):
            content_type_counts = ctc
    if not content_type_counts:
        for msg in messages:
            for item in (msg.get("content") or []):
                if isinstance(item, dict):
                    t = str(item.get("type", ""))
                    if t:
                        content_type_counts[t] = content_type_counts.get(t, 0) + 1

    # 5. human_input_required
    hitl = raw_trajectory.get("human_input_required")
    if hitl is not None and not isinstance(hitl, (list, dict)):
        hitl = None  # normalize: only store structured data or None

    # 6. pre_reasoning — walk messages in order; collect reasoning text;
    #    when a tool_call is hit, flush the accumulated buffer as that tool_call's
    #    pre_reasoning (truncated), then reset the buffer.
    pre_reasoning_map: dict[str, str] = {}
    _reasoning_buffer: list[str] = []

    for msg in messages:
        content = msg.get("content") if isinstance(msg, dict) else None
        if not isinstance(content, list):
            continue
        for item in content:
            if not isinstance(item, dict):
                continue
            item_type = item.get("type", "")
            if item_type == "reasoning":
                r = item.get("reasoning") or item.get("text") or ""
                if r:
                    _reasoning_buffer.append(str(r))
            elif item_type == "tool_call":
                tcid = str(item.get("tool_call_id") or "")
                pre_reasoning_text = " ".join(_reasoning_buffer)
                if len(pre_reasoning_text) > pre_reasoning_max_chars:
                    pre_reasoning_text = pre_reasoning_text[:pre_reasoning_max_chars] + "…"
                if tcid:
                    pre_reasoning_map[tcid] = pre_reasoning_text
                _reasoning_buffer = []  # reset

    # 7. pair tool_results by tool_call_id
    result_by_id: dict[str, dict] = {}
    for tr in tool_results:
        tcid = tr.get("tool_call_id")
        if tcid is not None:
            result_by_id[str(tcid)] = tr

    # 8. build root span
    root = Span(
        name=case_id,
        span_type="eddy_agent_run",
        input=instruction,
        output=final_text,
    )
    root.metadata = {
        "case_id": case_id,
        "run_status": run_status,
        "n_messages": len(messages),
        "content_type_counts": content_type_counts,
        "human_input_required": hitl,
    }

    # 9. build tool_call child spans
    for tc in tool_calls:
        tcid = str(tc.get("tool_call_id") or "")
        tr = result_by_id.get(tcid, {})
        raw_output = tr.get("output") if isinstance(tr, dict) else None
        child_output, child_meta_extra = _eddy_truncate_output(raw_output, tool_output_max_chars)

        child = Span(
            name=str(tc.get("tool_name") or tc.get("name") or "tool"),
            span_type="tool_call",
            input=tc.get("args") or tc.get("arguments") or tc.get("input"),
            output=child_output,
        )
        child_meta: dict[str, Any] = {"tool_call_id": tcid}
        child_meta.update(child_meta_extra)
        if pre_reasoning_map.get(tcid):
            child_meta["pre_reasoning"] = pre_reasoning_map[tcid]
        child.metadata = child_meta
        root.add_child(child)

    # 10. errors
    errors: list[str] = []
    if run_status in {"error", "timeout"}:
        errors.append(f"eddy agent ended with status={run_status}")
    if not messages and not tool_calls:
        errors.append("empty trajectory: no messages / tool_calls found")
    elif not tool_calls:
        errors.append("no tool_calls found in trajectory (agent may not have used tools)")

    return Trajectory(root_span_list=[root], errors=errors), stats


def _eddy_extract_tool_events(
    raw_trajectory: dict, messages: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Extract tool_calls and tool_results from an eddy trajectory.

    Prefers the project's pre-extracted top-level ``tool_calls`` / ``tool_results``
    lists (if generate.py's ``build_trajectory()`` writes them). Falls back to
    scanning ``messages[].content[]`` for items with ``type == 'tool_call'`` or
    ``type == 'tool_result'``.
    """
    calls = list(raw_trajectory.get("tool_calls") or [])
    results = list(raw_trajectory.get("tool_results") or [])
    if calls or results:
        return calls, results
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for item in content:
            if not isinstance(item, dict):
                continue
            ty = item.get("type")
            if ty == "tool_call":
                calls.append(item)
            elif ty == "tool_result":
                results.append(item)
    return calls, results


def _eddy_truncate_output(
    raw_output: Any, max_chars: int,
) -> tuple[Any, dict[str, Any]]:
    """Truncate a tool output if it exceeds ``max_chars`` (when stringified).

    Returns (truncated_output, extra_metadata_dict). The metadata dict contains
    ``output_truncated=True`` + ``output_original_len=N`` when truncation
    occurs, or an empty dict when no truncation is needed.
    """
    if raw_output is None:
        return None, {}
    if isinstance(raw_output, str):
        if len(raw_output) > max_chars:
            return raw_output[:max_chars] + "…(truncated)", {
                "output_truncated": True,
                "output_original_len": len(raw_output),
            }
        return raw_output, {}
    if isinstance(raw_output, (dict, list)):
        s = json.dumps(raw_output, ensure_ascii=False, default=str)
        if len(s) > max_chars:
            return s[:max_chars] + "…(truncated)", {
                "output_truncated": True,
                "output_original_len": len(s),
            }
    return raw_output, {}


def _collect_agent_errors(trajectory: Trajectory, stats: UsageStats) -> None:
    """Record fatal assistant-message failures onto ``trajectory.errors``.

    Pi (and Claude Code) attach ``stopReason: "error"`` + ``errorMessage`` to an
    assistant message when the LLM call itself fails — e.g. antchat returning
    ``401 service not authorized``, a 5xx, or a rate limit. We surface these by recording
    them on the trajectory rather than raising, so the caller can **first
    persist the trajectory** (which still contains the error spans) and then
    decide whether to abort. A run with usable model output (output_tokens > 0)
    is treated as successful regardless of stray error turns; only an all-error
    / zero-output run is flagged fatal.
    """
    if stats.output_tokens > 0:
        return
    for span in trajectory.root_span_list:
        if span.span_type == "model" and span.metadata.get("stop_reason") == "error":
            err = span.metadata.get("error_message") or "unknown LLM error"
            trajectory.errors.append(err)
