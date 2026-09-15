from antomnievo.model.spec_defs.common_descriptions import (
    _ADDITIONAL_FILES_DESCRIPTION,
    _PI_EXTENSIONS_DIR_DESCRIPTION,
    _REFERENCES_DIR_DESCRIPTION,
    _SCRIPTS_DIR_DESCRIPTION,
)
from antomnievo.model.spec_schema import FileSchema, FolderSchema, SpecSchema

_TERMINALBENCH_SPEC_DIR_DESCRIPTION = """\
The spec directory defines the agent's configurable behavior.

## Global Constraints

### No redundancy
Each rule or pattern lives in ONE canonical location. Allowed: SKILL.md may \
state a one-line WHAT + trigger while `skill/references/<file>.md` holds the \
detailed HOW. Forbidden: restating the same paragraph in two files.

### No contradiction
Rules across files must not conflict. When two files disagree the agent will \
pick whichever it reads last. Resolve by choosing ONE canonical location and \
removing or qualifying every other source.

### Generalization

The spec optimizes a skill and extensions that will be applied to many tasks, so \
every artifact — Markdown rules, reference files, scripts, AND extensions — must work on \
tasks it has never seen. An artifact that only fires on one specific task is dead \
weight on every other task. When you observe a failure on one instance, extract the \
underlying class of mistakes and prevent the whole class.

- **For all prose artifacts** (rules, methodology, workflow steps, procedures, error \
patterns, decision logic): every method MUST be general and transferable — it must work \
on any task, not just the one where the failure was observed. A method passes \
the generalization test if it can be applied to an unseen task without modification. \
Additionally, every general statement MUST be accompanied by at least one concrete \
example that illustrates the general pattern without being the only case \
it covers.
- **For scripts**: a script passes the generalization test if it takes task-specific \
values as arguments or discovers them at runtime (reading config files, parsing command \
output, inspecting environment variables), with NO hardcoded paths, package names, or \
config values from a specific task. A script that hardcodes `pip install pandas` or \
`/home/user/project` directly is non-transferable and must be rewritten.
- **For extensions**: an extension passes the generalization test if it enforces \
structural workflow constraints — matching on tool names, command prefixes (`bash`, `edit`), \
file path patterns (`/references/`, `/scripts/`), or output shapes — with NO hardcoded \
task-specific identifiers (project names, dependency versions, specific file contents). \
Stateful conditions must track categories of actions \
(ran a verification command, read a reference file, edited a source file), not accesses \
to specific files or commands from a particular task.

#### Example — hardcoded values vs parameterized methods

❌ BAD: "when editing `main.py`, always add the import at line 3" — helps only one file \
structure.
✅ GOOD: "when adding a new import, place it in the existing import block, grouped by \
standard library / third-party / local, and matching the file's existing style." — \
transferable import-placement method; `main.py` becomes a 1-line illustration if needed.

❌ BAD: "run `pip install flask==2.3.0` before starting the server" — fixes one task's \
dependency.
✅ GOOD: "before running the project, install dependencies from the task's declared \
package file (`requirements.txt`, `package.json`, `Cargo.toml`, etc.); detect the file \
type and use the matching install command." — transferable dependency-install method.

#### Example — task-specific fixes vs general decision patterns

Decision patterns that name specific tools or constructs are still general — the test is \
whether they apply to any task with the same structural challenge.

❌ BAD: "use `pytest tests/test_converter.py::test_round_trip` to verify the converter" \
— hardcodes one test path.
✅ GOOD: "after modifying source code, run the project's test suite using the task's \
declared test command (e.g., `pytest`, `make test`, `cargo test`); if no test command is \
declared, run the most specific test file related to the change."

❌ BAD: "set `FLASK_ENV=production` in the `.env` file" — hardcodes one project's config.
✅ GOOD: "check for the project's config mechanism (`.env`, `config.yaml`, environment \
variables) and set the deployment-specific values declared in the task description, not \
defaults from a tutorial."

## Choosing the right layer: extension, script, skill

The spec has three layers with increasing determinism. **Prefer the most deterministic \
layer that fits the problem** — code you can guarantee beats rules the LLM might ignore.

- **Extensions** (extensions/*.ts) — the PREFERRED layer. Hook into the agent's full \
lifecycle — tool calls/results, session/agent/turn/message lifecycle events, provider \
request/response, and dynamic context injection. Extensions fire at the system level; \
the LLM cannot skip or bypass them. Use extensions FIRST for any constraint that can be \
expressed through these hooks: blocking forbidden commands, enforcing verification steps, \
injecting reminders via tool_result, modifying provider requests, injecting dynamic \
context, tracking workflow state across turns, or gating output.

- **Scripts** (scripts/*.py) — the SECOND choice. Codify deterministic steps that the LLM \
would otherwise reason about unreliably. Instead of asking the LLM to "check if the \
server is running", a script runs `curl -s http://localhost:<port>/health` and prints \
`HEALTHY` or `ERR_UNREACHABLE`. The LLM still decides WHEN to invoke the script, but \
the check itself is deterministic code, not LLM reasoning. Use when the constraint \
cannot be expressed as a tool-call interception but CAN be expressed as a deterministic \
procedure.

- **Skill** (SKILL.md / references / examples) — the LAST resort. Teach the LLM what to \
do via natural language. The LLM reasons about the rule and decides how to apply it. Use \
ONLY when the fix requires new knowledge the agent lacks (wrong command pattern, wrong \
tool choice, domain-specific reasoning) and cannot be codified as a script or extension.

**Selection principle**: always start from the top. Can the fix be an extension? If yes, \
use an extension. If not (because it requires the agent to reason, not just follow a \
constraint), can it be a script? If yes, use a script. Only fall back to a skill rule \
when the fix is genuinely about teaching the LLM new knowledge.

| Failure mode | Fix | Why this layer? |
|---|---|---|
| Agent skips a required step or uses forbidden commands | Extension | Guaranteed enforcement — LLM cannot bypass |
| Agent knows the rule but applies a check inconsistently | Script | Deterministic code, but agent must invoke it |
| Agent lacks knowledge (wrong command, wrong tool choice) | Skill rule | Only natural language can teach new reasoning |
| Agent uses blocked commands (curl to external APIs, rm -rf) | Extension | Must be enforced regardless of LLM intent |
| Agent repeatedly violates a skill rule despite it being clearly stated | Extension | The rule exists but is ignored — escalate from skill to extension enforcement |
| Agent produces output with a detectable structural anti-pattern | Extension checker | Pattern can be caught by regex/exec on the output |

### Escalation principle: skill rule ignored → extension checker

When analysis shows the agent repeatedly violates a skill rule that is already clearly \
stated (e.g., the rule says "run the test suite before marking done" but the agent \
skips it), adding more words to the skill WILL NOT help — the agent already has the \
knowledge and is ignoring it. The correct fix is to ESCALATE to an extension checker that \
blocks the output and forces the agent to reconsider.
"""

_TERMINALBENCH_SKILL_DIR_DESCRIPTION = """\
Contains the agent's skill content. The agent receives the SKILL.md content as part of its system prompt at runtime."""

_TERMINALBENCH_SKILL_MD_DESCRIPTION = """\
Required. YAML frontmatter followed by Markdown instructions for the \
agent skill.

## Frontmatter

- name: tb2-task-skill (FIXED)
- description: 1-1024 chars.
## Body structure

Keep the body under 500 lines / ~5000 tokens. Required sections:

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
- Every rule must generalize across tasks — no hardcoded \
task names, image tags, or paths from a specific task.

## Content Boundary

Keep SKILL.md concise and self-sufficient for the common path. Delegate detail \
to `references/` and `scripts/`.

- **10-line rule**: move any HOW content over 10 lines to `references/`. Keep \
at most 2 sentences in the rule: WHAT + WHEN.
- **No duplication**: never restate a reference file's content in SKILL.md. \
If you write a code snippet in a rule, delete either the snippet or the \
reference file — never keep both.
"""

_WORKFLOW_TS_DESCRIPTION = """\
PI agent runtime extension — a hard constraint framework for controlling \
agent behavior on Terminal-Bench tasks.

This file is the primary lever for fixing agent mistakes that prompt \
instructions alone cannot solve. Skill prompts are soft guidance the model \
may ignore; this extension operates at the runtime level and physically \
prevents the agent from producing invalid output. When analyzing failures, \
prioritize modifying this file over adding more prompt text.
"""

TERMINALBENCH_SKILL_SPEC_SCHEMA: SpecSchema = FolderSchema(
    name="spec",
    description=_TERMINALBENCH_SPEC_DIR_DESCRIPTION,
    files=[
        FolderSchema(
            name="skill",
            description=_TERMINALBENCH_SKILL_DIR_DESCRIPTION,
            files=[
                FileSchema(name="SKILL.md", description=_TERMINALBENCH_SKILL_MD_DESCRIPTION),
                FolderSchema(name="scripts", description=_SCRIPTS_DIR_DESCRIPTION),
                FolderSchema(name="references", description=_REFERENCES_DIR_DESCRIPTION),
                FileSchema(name="...", description=_ADDITIONAL_FILES_DESCRIPTION),
            ],
        ),
        FolderSchema(
            name="extension",
            description=_PI_EXTENSIONS_DIR_DESCRIPTION,
            files=[
                FileSchema(name="workflow.ts", description=_WORKFLOW_TS_DESCRIPTION),
            ],
        ),
    ],
)
