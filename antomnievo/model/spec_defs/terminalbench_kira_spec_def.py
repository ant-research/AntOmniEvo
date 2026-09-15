"""Spec schema definition for the Terminus-KIRA agent on Terminal-Bench 2.

The KIRA spec is "agent code + skill" — the agent's Python code
lives IN the spec dir so the proposer can mutate it as part of evolution.
"""

from antomnievo.model.spec_defs.common_descriptions import (
    _ADDITIONAL_FILES_DESCRIPTION,
    _REFERENCES_DIR_DESCRIPTION,
    _SCRIPTS_DIR_DESCRIPTION,
)
from antomnievo.model.spec_schema import FileSchema, FolderSchema, SpecSchema

# ── Top-level spec dir ──────────────────────────────────────────────────────

_KIRA_SPEC_DIR_DESCRIPTION = """\
The spec directory defines the Terminus-KIRA agent's full configurable behavior:
both the agent's Python code (tool definitions, middleware overrides, context
engineering) and its skill (prompt-level guidance). The proposer mutates files
here to evolve the agent.

## Global Constraints

### No redundancy
Each rule or pattern lives in ONE canonical location. The agent code
(kira_agent.py) is the single source of truth for tool definitions and
middleware behavior; SKILL.md is the single source of truth for prompt-level
guidance. Do not restate tool usage rules in SKILL.md that are already in the
TOOLS constant's descriptions.

### No contradiction
Rules across SKILL.md and agent code must not conflict. When the skill says one
thing but the code enforces another, the code wins (it is a hard constraint).
Resolve contradictions by choosing ONE canonical location.

### Generalization
Every artifact — SKILL.md rules, reference files, agent code — must work on
tasks it has never seen. An artifact that only fires on one specific task is
dead weight on every other task. When you observe a failure on one instance,
extract the underlying class of mistakes and prevent the whole class.

## Choosing the right layer: agent code, skill, references, scripts

The KIRA spec has four layers with increasing determinism. **Prefer the most
deterministic layer that fits the problem.**

- **Agent code** (agent/kira_agent.py) — the MOST deterministic layer. Tool
  definitions (TOOLS constant), middleware (override methods like
  _handle_llm_interaction, _run_agent_loop, _execute_commands), and context
  engineering (summarization, caching) are all Python code that the LLM cannot
  skip or bypass. Use this layer for: new tools, tool behavior changes,
  hard enforcement (block commands, force verification), trajectory extensions.

- **Scripts** (skill/scripts/) — deterministic procedures the agent invokes
  on demand. Codify steps the LLM would otherwise reason about unreliably.
  The LLM decides WHEN to invoke; the procedure itself is deterministic code.

- **Skill** (skill/SKILL.md) — prompt-level guidance. The LLM reasons about
  the rule and decides how to apply it. Use ONLY when the fix requires new
  knowledge the agent lacks (wrong command pattern, domain-specific reasoning)
  and cannot be codified as code or a script.

- **References** (skill/references/) — detailed documentation loaded on demand.
  Use for methodology docs, pattern catalogs, worked examples that exceed what
  belongs in SKILL.md's concise body.

**Selection principle**: Can the fix be agent code? If yes, use code. If not
(because it requires the agent to reason, not just follow a constraint), can it
be a script? If yes, use a script. Only fall back to a skill rule when the fix
is genuinely about teaching the LLM new knowledge.

## Trajectory extensibility

The agent's full run must be reconstructable from trajectory.json. When adding a
new runtime module, make its activity observable as a Span.
"""

# ── agent/ ──────────────────────────────────────────────────────────────────

_AGENT_DIR_DESCRIPTION = """\
Contains the KIRA agent's Python code. This IS the agent — mutating these files
mutates the agent's behavior.
"""

_AGENT_MAIN_DESCRIPTION = """\
Required. The main agent file — AgentHarness(Terminus2) with native tool calling.

This file defines:
- TOOLS constant: the tool schemas (execute_commands, task_complete, image_read).
  Tool descriptions ARE the prompt engineering — edit them to change how the
  model uses each tool.
- AgentHarness class: overrides Terminus2's LLM interaction layer to use
  litellm.acompletion(tools=...) instead of JSON/XML parsing.
- Middleware (Python overrides): _handle_llm_interaction, _run_agent_loop,
  _execute_commands (marker polling), _execute_image_read (multimodal).
- Context engineering: _build_skills_section (skill preload), _summarize_or_fallback
  (context overflow recovery), anthropic caching.

To add a new tool: add it to TOOLS + handle in _parse_tool_calls + execute in
_run_agent_loop + record a Step (trajectory auto-captures it via the converter).
To add middleware: override the relevant Terminus2 method in this class.
"""

_PROMPT_TEMPLATES_DIR_DESCRIPTION = """\
Prompt template files used by the agent. The template is loaded by
_get_prompt_template_path() and formatted with {instruction} and {terminal_state}
to build each turn's prompt.
"""

_PROMPT_TEMPLATE_DESCRIPTION = """\
Required. The prompt template for the KIRA agent.
"""

# ── skill/ ──────────────────────────────────────────────────────────────────

_KIRA_SKILL_DIR_DESCRIPTION = """\
Contains the agent's skill content. SKILL.md is preloaded into the system prompt
at runtime. references/ and scripts/ are listed in
the prompt but loaded on demand by the agent.
"""

_KIRA_SKILL_MD_DESCRIPTION = """\
Required. YAML frontmatter followed by Markdown instructions for the agent skill. \

## Frontmatter

- name: tb2-task-skill (FIXED)
- description: 1-1024 chars. Include keywords like "terminal", "shell", \
"docker", "build", "debug", "verification" so the skill is discoverable.

## Body structure

KIRA uses native tool-calling — tool usage rules live in the TOOLS constant's \
descriptions in kira_agent.py, NOT in SKILL.md. SKILL.md should focus on \
high-level workflow and domain knowledge that the tool descriptions cannot \
express. Keep the body under 500 lines / ~5000 tokens.

```markdown
## Overview
<1-2 sentence summary of what this skill does>

## Procedure
<numbered workflow with mandatory verification gates. Express gates as \
shell commands the agent must execute, not text instructions.>

## Rules
<concise shell / tool usage rules — file inspection, structured output \
parsing, sudo policy, etc.>

## Error Patterns to Avoid
<common terminal-task mistakes — answering from prior knowledge, silent \
failure via /dev/null, marking done without re-running the verifier, etc.>

## References
<REQUIRED — list every file in skill/references/, skill/scripts/. Each entry: \
BEFORE/WHEN/AFTER trigger + the exact executable directive.
```

## Writing Style

- Imperative form ("Run the command", not "You should run the command").
- Explain WHY a rule matters rather than relying on heavy-handed MUSTs.
- Ground rules in concrete terminal behaviors (exit codes, stderr shape, \
file paths), not vague principles.
- Every rule must generalize across tasks — no hardcoded task names, image \
tags, or paths from a specific task.

## Content Boundary

Keep SKILL.md concise and self-sufficient for the common path. Delegate \
detail to `references/` and `scripts/`.

- **10-line rule**: move any HOW content over 10 lines to `references/`. Keep \
at most 2 sentences in the rule: WHAT + WHEN.
- **No duplication**: never restate a reference file's content in SKILL.md, \
and never restate tool usage rules that are already in the TOOLS descriptions \
in kira_agent.py. If you write a code snippet in a rule, delete either the \
snippet or the reference file — never keep both.
- **No code-layer rules**: middleware behavior (double-confirm, marker polling, \
verify budget) is enforced by Python code in kira_agent.py. Do not add SKILL.md \
rules that duplicate these — the code is authoritative. Only add skill rules \
when the fix requires knowledge the agent lacks.
"""

# ── Schema ──────────────────────────────────────────────────────────────────

TERMINALBENCH_KIRA_SPEC_SCHEMA: SpecSchema = FolderSchema(
    name="spec",
    description=_KIRA_SPEC_DIR_DESCRIPTION,
    files=[
        FolderSchema(
            name="agent",
            description=_AGENT_DIR_DESCRIPTION,
            files=[
                FileSchema(
                    name="kira_agent.py",
                    description=_AGENT_MAIN_DESCRIPTION,
                ),
                FolderSchema(
                    name="prompt-templates",
                    description=_PROMPT_TEMPLATES_DIR_DESCRIPTION,
                    files=[
                        FileSchema(
                            name="terminus-kira.txt",
                            description=_PROMPT_TEMPLATE_DESCRIPTION,
                        ),
                    ],
                ),
                FileSchema(name="...", description=_ADDITIONAL_FILES_DESCRIPTION),
            ],
        ),
        FolderSchema(
            name="skill",
            description=_KIRA_SKILL_DIR_DESCRIPTION,
            files=[
                FileSchema(
                    name="SKILL.md",
                    description=_KIRA_SKILL_MD_DESCRIPTION,
                ),
                FolderSchema(name="scripts", description=_SCRIPTS_DIR_DESCRIPTION),
                FolderSchema(name="references", description=_REFERENCES_DIR_DESCRIPTION),
                FileSchema(name="...", description=_ADDITIONAL_FILES_DESCRIPTION),
            ],
        ),
    ],
)
