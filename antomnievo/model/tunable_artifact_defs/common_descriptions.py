"""Shared DESCRIPTION constants used by multiple tunable_artifact_def modules.

These describe generic, agent-agnostic parts of a skill artifact directory
(scripts/, references/, assets/, and free-form additional files). Individual
tunable_artifact_def modules (appworld, text2sql, agent_skill, ...) import from here so
the wording stays in sync; when an agent needs a specialized variant, define
it locally in that agent's tunable_artifact_def module instead of editing these.
"""

_SCRIPTS_DIR_DESCRIPTION = """
Optional. Executable code the agent can run. Scripts should be
self-contained or clearly document dependencies, include helpful error messages,
and handle edge cases gracefully. Common languages: Python, Bash, JavaScript.
Scripts can execute without being loaded into context, making them efficient for
deterministic or repetitive tasks."""

_REFERENCES_DIR_DESCRIPTION = """
Optional. Detailed documentation loaded on demand by the agent.

Content that belongs here:
- Worked examples and step-by-step walkthroughs
- Pattern catalogs and strategy guides
- Domain-specific reference material
- Any content exceeding 10 lines that is not a core rule

File size limits (every loaded file costs context):
- Each file: hard limit 500 lines / 5000 tokens. Split into separate files before exceeding.
- For files over 100 lines, include a table of contents at the top.

Keep individual files focused on one topic so the agent loads only what it needs.
Examples: patterns.md for decomposition patterns, strategies.md for retrieval strategies,
constraints.md for constraint verification details."""

_ASSETS_DIR_DESCRIPTION = """
Optional. Non-executable static resources: templates, images,
lookup tables, schemas, configuration files."""

_ADDITIONAL_FILES_DESCRIPTION = """
You may add any additional files or directories to the artifacts.
Use them when the existing structure is insufficient to express a needed behavior change."""

_PI_EXTENSIONS_DIR_DESCRIPTION = """\
PI agent extensions (TypeScript `.ts` files) loaded at runtime.

## How the System Works

The host agent runs as a PI coding agent — an LLM-driven loop that reads context, \
generates responses, and executes tool calls (read/write/edit/bash/grep/find). Extensions \
are middleware hooks that intercept every stage of this loop. They can **block tool calls**, \
**mutate tool arguments**, **rewrite tool results**, **inject messages into the \
conversation**, and **modify the system prompt or context**. Unlike skill prompt \
instructions which the model may ignore under pressure, extension rules are enforced at the \
runtime level — the agent physically cannot bypass a blocking extension.

The lifecycle is:
1. PI initializes, loads all `.ts` files from this directory, builds system prompt.
2. Agent loop starts with the user prompt.
3. Each turn: model generates → tool calls fire → results returned → next turn.
4. Agent ends (output produced or max turns hit).

Extensions hook into any stage. All files compose — handlers run in load order; any one \
can block independently.

## Extension File Schema

Each file is a TypeScript module with a default export function receiving the `pi` API:

```typescript
interface ToolCallEvent {
  toolName: string;       // "write", "edit", "read", "bash", "grep", "find", "ls"
  toolCallId: string;
  input: Record<string, unknown>;  // mutable for tool_call event
}
interface ToolCallEventResult { block?: boolean; reason?: string; }
interface ToolResultEvent {
  toolName: string;
  toolCallId: string;
  input: Record<string, unknown>;
  content: Array<{ type: string; text?: string }>;
  details?: any;
  isError: boolean;
}
interface ToolResultEventResult { content?: Array<{ type: string; text?: string }>; details?: any; isError?: boolean; }
interface TurnEndEvent {
  turnIndex: number;
  message: any;
  toolResults: any[];
}
interface Model { generateContent(prompt: string): Promise<string>; }
interface ExtensionContext { model: Model; signal?: AbortSignal; }

interface ExtensionAPI {
  on(event: "tool_call", handler: (event: ToolCallEvent, ctx: ExtensionContext) => ToolCallEventResult | void | Promise<ToolCallEventResult | void>): void;
  on(event: "tool_result", handler: (event: ToolResultEvent, ctx: ExtensionContext) => ToolResultEventResult | void | Promise<ToolResultEventResult | void>): void;
  on(event: "before_agent_start", handler: (event: { prompt: string; images?: any[]; systemPrompt: string; systemPromptOptions?: any }, ctx: ExtensionContext) => { message?: any; systemPrompt?: string } | void | Promise<{ message?: any; systemPrompt?: string } | void>): void;
  on(event: "agent_start", handler: (event: any, ctx: ExtensionContext) => void): void;
  on(event: "agent_end", handler: (event: { messages: any[] }, ctx: ExtensionContext) => void): void;
  on(event: "turn_start", handler: (event: { turnIndex: number; timestamp: number }, ctx: ExtensionContext) => void): void;
  on(event: "turn_end", handler: (event: TurnEndEvent, ctx: ExtensionContext) => void | Promise<void>): void;
  on(event: "message_end", handler: (event: any, ctx: ExtensionContext) => { message?: any } | void): void;
  on(event: "context", handler: (event: { messages: any[] }, ctx: ExtensionContext) => { messages: any[] } | void | Promise<{ messages: any[] } | void>): void;
  on(event: "input", handler: (event: { text: string }, ctx: ExtensionContext) => { action: "transform"; text: string } | { action: "handled" } | { action: "continue" } | void): void;
  on(event: "session_start" | "session_shutdown", handler: (event: { reason: string }, ctx: ExtensionContext) => void): void;
  on(event: "before_provider_request", handler: (event: any, ctx: ExtensionContext) => any | void): void;
  on(event: "after_provider_response", handler: (event: { status: number; headers: any }, ctx: ExtensionContext) => void): void;
  exec(command: string, args: string[], options?: {
    signal?: AbortSignal; timeout?: number;
  }): Promise<{ stdout: string; stderr: string; code: number; killed: boolean }>;
}

export default function (pi: ExtensionAPI) {
  // register handlers here
}
```

**Key APIs:**
- `pi.on(event, handler)` — register handler. Return value semantics depend on event type.
- `pi.exec(cmd, args, opts)` — run external process for validation (e.g. execute SQL).
- `ctx.model.generateContent(prompt)` — lightweight LLM call for checks (adds latency).

## Available Events

### Lifecycle
| Event | Fires when | Can return |
|-------|-----------|------------|
| `session_start` | Session initialized | void |
| `before_agent_start` | After prompt received, before loop | `{message?, systemPrompt?}` |
| `agent_start` / `agent_end` | Loop begins/ends | void |
| `turn_start` / `turn_end` | Each model turn | void |
| `message_end` | Message finalized | `{message}` to replace |
| `session_shutdown` | Before teardown | void |

### Tool (intercept every tool call)
| Event | Fires when | Can return |
|-------|-----------|------------|
| `tool_call` | BEFORE tool executes | `{block:true, reason}` to deny; mutate `event.input` in place |
| `tool_result` | AFTER tool executes | `{content, isError}` to override result (chains like middleware) |

`event` for tool_call: `{toolName, toolCallId, input}`. Tool names include: "write", \
"edit", "read", "bash", "grep", "find", "ls".

### Input
- `input` — before skill expansion. Return `{action:"transform", text}`, \
`{action:"handled"}`, or `{action:"continue"}`.

### Context
- `context` — receives `{messages:[...]}`, return `{messages:[...]}` to modify what the \
model sees. Append message objects to inject information.

### Provider
- `before_provider_request` — modify LLM API payload before send.
- `after_provider_response` — observe raw response (`event.status`, `event.headers`).

## What Extensions Can Achieve (Impact)

Extensions are the mechanism for enforcing hard behavioral constraints:

1. **Output validation gates** — block writes to the output file unless content passes \
checks (execution, pattern matching, LLM-based consistency). The agent sees the block \
reason as an error and must fix before retrying.

2. **Runtime state tracking** — use module-level variables to build state machines across \
events (e.g. track write→verify→fix cycles, detect flag conditions from the prompt).

3. **Result augmentation** — append reminders/warnings to `tool_result` content so the \
agent is continuously guided toward correct workflow regardless of what it "remembers".

4. **Access control** — block reads/writes to certain paths to prevent data contamination.

5. **Context manipulation** — via the `context` event, rewrite or filter the message \
history before it reaches the model (e.g. compress, deduplicate, inject fresh context).
"""
