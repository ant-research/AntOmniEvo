from antomnievo.model.tunable_artifact_defs.common_descriptions import (
    _ADDITIONAL_FILES_DESCRIPTION,
    _PI_EXTENSIONS_DIR_DESCRIPTION,
    _REFERENCES_DIR_DESCRIPTION,
)
from antomnievo.model.tunable_artifact_schema import FileSchema, FolderSchema, TunableArtifactSchema

_TEXT2SQL_ARTIFACT_DIR_DESCRIPTION = """\
The artifact directory defines the NL2SQL agent's complete configurable behavior, consisting of \
two subsystems:

- `skill/` — the knowledge layer: SKILL.md, reference files, scripts, examples that guide \
the agent's reasoning and SQL generation strategy.
- `extensions/` — the enforcement layer: PI extensions (TypeScript) that constrain which \
tools the agent can use at runtime. Extensions cannot be bypassed by the model.

Both are co-optimized: improving the skill without matching enforcement may let the agent \
ignore new rules; tightening enforcement without updating the skill may block legitimate \
workflows.

## Available tools

The agent (and any script in `scripts/`) accesses the database ONLY through the \
`query-db` bash command. The database lives behind an HTTP db-server; `<db_id>` is a \
logical ID, NOT a file path — do NOT `import sqlite3` / `psycopg2`, call \
`sqlite3.connect`, or open `<db_id>` as a file.

```
bash: query-db --db <db_id> --sql "<SQL query>"
bash: query-db --db <db_id> --file <path_to_sql_file>
```

Options:
- `--db`: Database ID (provided in the task context)
- `--sql`: SQL query to execute (takes priority over --file)
- `--file`: Path to .sql file to execute
- `--limit N`: Max rows to return (default: 20)
- `--json`: Output raw JSON

Use it to inspect table data, test intermediate queries, and verify the final SQL.

## Global constraints

### No redundancy

Each rule/check lives in ONE canonical location. Allowed: SKILL.md may state a one-line \
WHAT + trigger (e.g., "compute percentages with `SUM(IIF(...))` over the unfiltered base \
table — see `references/percentage.md`") while `references/percentage.md` holds the \
detailed HOW (full syntax, examples, edge cases). This is layered detail, not redundancy.

Forbidden: restating the same paragraph in two Markdown files, OR implementing the same \
check both as a Markdown rule and as a script. When promoting a Markdown rule to a script, \
DELETE the Markdown — no fallback copy.

Do not loop on "is this redundant?" — if SKILL.md is ≤1 line per rule + trigger and the \
detail lives in exactly one other file, you are done.

### No contradiction

Rules and script outputs must not conflict, regardless of which file or artifact they live \
in. When SKILL.md says "use the minimal query" and a reference file says "always prefer the \
most explicit query", the agent will silently pick whichever it reads last. When a script \
prints `USE_MIN` but a Markdown rule says "prefer the expanded version for clarity", the \
agent will rationalize whichever fits its prior. Resolve contradictions by choosing ONE \
canonical artifact (Markdown rule, reference file, or script) and removing or qualifying \
every other source — do not let conflicting guidance coexist hoping the agent will \
reconcile it.

**Contradiction detection procedure** — before writing any new rule:

1. Search the existing artifacts for the same concept. If guidance already exists, your change \
must be compatible or explicitly replace it.
2. Unconditional rules ("always X", "never X") are dangerous — they will conflict with any \
scenario where the opposite is correct. Prefer decision tables with distinguishing \
conditions. Unconditional rules are allowed only when no valid exception exists.
3. When modifying an existing rule, verify that the cases it originally solved are still \
handled by the new version. If not, restructure as a decision table that preserves both.

### Generalization

The tunable artifacts optimize a skill and extensions that will be applied to many databases, so \
every artifact — Markdown rules, reference files, scripts, AND extensions — must work on \
schemas it has never seen. An artifact that only fires on one specific schema is dead \
weight on every other schema. When you observe a failure on one instance, extract the \
underlying class of mistakes and prevent the whole class.

- **For all prose artifacts** (rules, methodology, workflow steps, procedures, error \
patterns, decision logic): every method MUST be general and transferable — it must work \
on any database schema, not just the one where the failure was observed. A method passes \
the generalization test if it can be applied to an unseen schema without modification. \
Additionally, every general statement MUST be accompanied by at least one concrete \
example — a before/after SQL pair, a schema snippet, a real failure case, or a worked \
step of the workflow — that illustrates the general pattern without being the only case \
it covers.
- **For scripts**: a script passes the generalization test if it takes table and column \
names as arguments and reads structure via `PRAGMA foreign_key_list` / `PRAGMA table_info` \
/ generic SQL, with NO hardcoded names from a specific database. A script that names \
`disp` or `client` directly is non-transferable and must be rewritten.
- **For extensions**: an extension passes the generalization test if it enforces \
structural workflow constraints — matching on tool names, command prefixes (`query-db`), \
file path patterns (`/references/`, `/scripts/`), or output shapes — with NO hardcoded \
database, table, or column names. Stateful conditions must track categories of actions \
(ran a verification query, read a reference file), not accesses to specific tables or \
columns.

#### Example — hardcoded names vs schema-driven methods

❌ BAD: "when querying the `circuits` table, use `COUNT(circuitId)` instead of `COUNT(*)`" \
— helps only one table.
✅ GOOD: "when counting specific entities, use `COUNT(primary_key_column)` instead of \
`COUNT(*)`; identify the primary key from the schema first." — schema-driven method; the \
`circuits`/`circuitId` pair becomes a 1-line illustration if needed.

❌ BAD: "Do NOT join `disp` when counting clients by district — `client.district_id` already \
provides it" — fixes one schema.
✅ GOOD: "Before adding a JOIN, check whether the target column already exists in a table \
you are already querying; run `SELECT col FROM target_table LIMIT 5` to verify." — \
transferable JOIN-avoidance method.

#### Example — SQL constructs as general decision patterns

Decision patterns that name specific SQL constructs are still general — the test is whether \
they apply to any schema with the same structural ambiguity.

❌ BAD: "For the `results` table, use `position` not `rank`" — hardcodes column semantics.
✅ GOOD: "When a question asks 'which X ranked highest', use `WHERE rank_column = 1` to \
find all tied-first results, not `ORDER BY rank_column ASC LIMIT 1`. Verify ties via \
`SELECT rank_column, COUNT(*) FROM table GROUP BY rank_column LIMIT 5`."

❌ BAD: "Use `constructorStandings` not `constructorResults` for points queries" — hardcodes \
table names.
✅ GOOD: "When multiple tables share a column name (e.g., `points`), run \
`SELECT * FROM each_table WHERE condition LIMIT 5` and choose the table whose values match \
the question's context (cumulative standings vs per-event results).

#### Example — extensions: general vs coupled

❌ BAD — coupled to a specific table:
```typescript
if (cmd.includes("SELECT * FROM circuits")) { hasVerified = true; }
```
✅ GOOD — enforces a general workflow constraint:
```typescript
if (cmd.includes("query-db")) { hasVerified = true; }
```

## Choosing the right layer: extension, script, skill

The tunable artifacts have three layers with increasing determinism. **Prefer the most deterministic \
layer that fits the problem** — code you can guarantee beats rules the LLM might ignore.

- **Extensions** (extensions/*.ts) — the PREFERRED layer. Hook into the agent's full \
lifecycle — tool calls/results, session/agent/turn/message lifecycle events, provider \
request/response, and dynamic context injection. Extensions fire at the system level; \
the LLM cannot skip or bypass them. Use extensions FIRST for any constraint that can be \
expressed through these hooks: blocking forbidden commands, enforcing verification steps, \
injecting reminders via tool_result, modifying provider requests, injecting dynamic \
context, tracking workflow state across turns, or gating output.

- **Scripts** (scripts/*.py) — the SECOND choice. Codify deterministic steps that the LLM \
would otherwise reason about unreliably. Instead of asking the LLM to "check if column X \
exists in table Y", a script runs `PRAGMA table_info` and prints `COLUMNS_OK` or \
`ERR_MISSING`. The LLM still decides WHEN to invoke the script, but the check itself is \
deterministic code, not LLM reasoning. Use when the constraint cannot be expressed as a \
tool-call interception but CAN be expressed as a deterministic procedure.

- **Skill** (SKILL.md / references / examples) — the LAST resort. Teach the LLM what to \
do via natural language. The LLM reasons about the rule and decides how to apply it. Use \
ONLY when the fix requires new knowledge the agent lacks (wrong SQL pattern, wrong table \
choice, domain-specific reasoning) and cannot be codified as a script or extension.

**Selection principle**: always start from the top. Can the fix be an extension? If yes, \
use an extension. If not (because it requires the agent to reason, not just follow a \
constraint), can it be a script? If yes, use a script. Only fall back to a skill rule \
when the fix is genuinely about teaching the LLM new knowledge.

| Failure mode | Fix | Why this layer? |
|---|---|---|
| Agent skips a required step or uses forbidden commands | Extension | Guaranteed enforcement — LLM cannot bypass |
| Agent knows the rule but applies a check inconsistently | Script | Deterministic code, but agent must invoke it |
| Agent lacks knowledge (wrong SQL technique, wrong table) | Skill rule | Only natural language can teach new reasoning |
| Agent uses blocked commands (sqlite3, ls) | Extension | Must be enforced regardless of LLM intent |
| Agent repeatedly violates a skill rule despite it being clearly stated | Extension | The rule exists but is ignored — escalate from skill to extension enforcement |
| Agent outputs SQL with a detectable structural anti-pattern | Extension checker | Pattern can be caught by regex/exec on the SQL output |

### Escalation principle: skill rule ignored → extension checker

When analysis shows the agent repeatedly violates a skill rule that is already clearly \
stated (e.g., the rule says "do NOT use SUM unless the question says total" but the agent \
still uses SUM), adding more words to the skill WILL NOT help — the agent already has the \
knowledge and is ignoring it. The correct fix is to ESCALATE to an extension checker that \
blocks the output and forces the agent to reconsider.
"""

_TEXT2SQL_SKILL_MD_DESCRIPTION = """\
Required. YAML frontmatter followed by Markdown instructions for the NL2SQL skill.

## Frontmatter

- name: nl2sql  (FIXED — must match the skill directory name)
- description: 1-1024 chars. Include keywords like "NL2SQL", "SQL", "natural language to \
SQL", "database query" so the skill triggers reliably. Be slightly "pushy" to combat \
under-triggering.
- Other optional fields (argument-hint, user-invokable, disable-model-invocation, \
allowed-tools) follow the standard agent-skill schema.

## Body structure

Keep the body under 500 lines / ~5000 tokens. Required sections:

```markdown
## Overview
<1-2 sentence summary>

## Procedure
<numbered workflow with mandatory verification gates — gates beat rules because the agent \
must execute them, not just "keep in mind". Express deterministic gates as \
`bash: <skill_dir>/scripts/X` invocations, not text checks (see scripts/ description).>

## Rules
<concise SQL generation rules — type handling, NULL handling, date functions, etc.>

## Error Patterns to Avoid
<common NL2SQL mistakes — wrong types, missing CAST, hallucinated columns, etc.>

## Output Format
<exact format — typically just the SQL statement, no markdown fences, no trailing semicolon. \
Output is parsed by exact/execution match; any extra text breaks scoring.>

## References
<REQUIRED — list every file in references/, scripts/, assets/. See the "References section \
& triggers" guidance below for the trigger grammar and specificity rules every entry MUST \
satisfy.>
```

## References & triggers

The `## References` section is the ONLY mechanism that loads on-demand files — a vague \
trigger means the file might as well not exist.

**Shape**: `` `<path>` — <BEFORE|WHEN|AFTER> <observable condition>, <action> ``

**Two tests every trigger must pass**:
1. **Observable**: names something in the draft SQL, question text, or schema — not the \
agent's subjective judgment.
2. **Decidable**: yes/no answerable without opening the guarded file.

❌ "BEFORE writing complex SQL, read this" — "complex" is not observable.
❌ "FOR join path guidance" — a topic, not a trigger. Forbidden trigger words: `FOR`, \
`IF NEEDED`, `ABOUT`, `RELATED TO`.
✅ "BEFORE writing any `HAVING` clause that filters on `COUNT(*)` or `COUNT(DISTINCT X)`, read this"
✅ "WHEN the draft FROM has two entity tables connected by a bridge table and both share a dimension FK, run this"

**Prefer many narrow triggers over one umbrella** — list the same file multiple times if \
it applies to distinct observable situations. Three narrow WHEN clauses fire three times; \
one vague clause may fire zero.

**Inline at the point of need** — a Procedure/Rules step that depends on a reference or \
script MUST include the trigger inline at the exact step. \
Do not rely on the agent recalling the References section while drafting SQL.

## Content boundary

SKILL.md is the ONLY file auto-loaded into the agent's context. It must be concise, \
self-sufficient for the common path, and delegate detail to other files via triggers.

- **What stays in SKILL.md**: rules, workflow steps, decision logic, brief inline examples \
(1-3 lines), and trigger directives pointing to other files.
- **10-line rule**: any content over 10 lines moves to references/, replaced in SKILL.md by \
a one-line summary + trigger (e.g. "For multi-table join patterns, Read references/join_patterns.md before proceeding").
- **No duplication of reference content**: SKILL.md says WHAT and WHEN; references/ says HOW.
- **Inline trigger required**: rules that depend on a reference file must include \
`Read references/X before proceeding` at the point of need — do not rely on the agent \
finding it via the References section alone.
- **One level deep**: keep reference chains flat; avoid references that point to further \
references.

## Writing style

- Imperative form ("Generate SQL that...", not "You should generate SQL that...").
- Explain WHY a rule matters rather than relying on heavy MUSTs.
- Ground rules in concrete behaviors, not vague principles. \
Bad: "Handle errors gracefully." \
Good: "When a subquery returns no rows, use COALESCE to provide a default value instead of \
returning NULL." """

_TEXT2SQL_SCRIPTS_DIR_DESCRIPTION = """
Optional but PREFERRED for verification gates. Executable code the agent invokes via the \
bash tool. Scripts produce structured outputs the agent consumes verbatim — the strongest \
enforcement mechanism in these tunable artifacts.
## Script contract
Every script in this directory MUST:
1. Print structured output to stdout — JSON for multi-field results, or a single ASCII \
token (e.g., `USE_MIN`) for binary choices.
2. On any failure (missing arg, DB unreachable, missing column, empty result), print a \
self-describing error line that tells the agent exactly what went wrong AND what to do \
next — e.g. `ERR_BAD_ARGS: --concept missing; pass the column name from the question`, \
not a bare `ERR` or a Python traceback. Exit code 0 when a declared token is printed, so \
the agent sees the message instead of a shell-level failure.
3. Contain NO hardcoded table or column names from any specific database — take them as \
arguments. A script that names `disp` or `client` directly is non-transferable.
4. Be invoked from SKILL.md using the script's **absolute path** \
(`bash: <skill_dir>/scripts/<name>.py --db <db_id> [args]`, where `<skill_dir>` is the \
runtime skill directory provided to the agent."""

_TEXT2SQL_EXAMPLES_DIR_DESCRIPTION = """\
Optional. Complete worked examples that the agent can reference when facing a matching \
scenario. Each file is a self-contained case study for ONE specific class of problem.

## File format

Each example file must follow this structure:

```markdown
# <Descriptive title naming the problem class>

## Scenario
<Precise description of WHEN this example applies. Must name observable conditions in the \
schema, question, or intermediate query — not subjective judgment.>

## Problem
<The natural language question, the relevant schema excerpt, and any domain knowledge \
provided.>

## Reasoning
<Step-by-step thought process. Which tables were considered and why. What information from \
the schema/knowledge was used. What pitfalls were identified and avoided.>

## Solution
<The final SQL query.>

## Key Takeaway
<1-2 sentences: the transferable lesson. Must be general enough to apply to unseen schemas.>
```

## Trigger rules

Examples are loaded on-demand via the References section in SKILL.md. Each trigger MUST:
1. Name the **problem class** this example addresses, not a single specific instance. The \
trigger should fire on any scenario that shares the same structural challenge. \
Good: "WHEN the query involves computing a ratio or percentage where the numerator is a \
filtered subset and the denominator is the full table" — covers percentages, rates, \
proportions, and share calculations. \
Bad: "WHEN the question asks for a percentage and the denominator requires counting from \
the unfiltered base table" — too narrow, misses ratio/rate/proportion variants.
2. Be observable: names something in the draft SQL, question text, or schema — not the \
agent's subjective judgment.
3. Prefer broad class descriptors over narrow instance descriptors. A trigger like "WHEN \
the query requires disambiguating between multiple tables that share a column name" is \
better than "WHEN the schema has `points` in both `constructorStandings` and \
`constructorResults`". The former fires on any column-name collision; the latter fires \
on exactly one schema.
4. NOT use vague words like "complex", "tricky", "advanced". Words like "similar" are \
allowed ONLY when qualifying a structural pattern — e.g., "WHEN the query has a similar \
multi-hop join structure (entity → bridge → entity)" is fine.

## Content rules

- Each example must be grounded in a real observed text2sql scenario — do not invent hypothetical cases.
- The Reasoning section must cite specific schema elements, knowledge text, or question \
phrases that drove each decision.
- The Solution must be minimal and correct — no unnecessary JOINs, columns, or filters.
- Examples must be schema-independent: use the concrete case as illustration, but the \
Scenario and Key Takeaway must describe the general pattern.
- Keep each file under 150 lines. If longer, split into two narrower examples."""

_TEXT2SQL_SKILL_DIR_DESCRIPTION = """\
Contains the NL2SQL skill content that the agent loads at runtime. This includes the main \
SKILL.md, reference files, scripts, examples, and assets. The agent receives this directory \
path as its skill_dir and can read files from it."""

_WORKFLOW_TS_DESCRIPTION = """\
PI agent runtime extension — a hard constraint framework for controlling agent behavior.

This file is the primary lever for fixing agent mistakes that prompt instructions alone \
cannot solve. Skill prompts are soft guidance the model may ignore; this extension operates \
at the runtime level and physically prevents the agent from producing invalid output. When \
analyzing failures, prioritize modifying this file over adding more prompt text.
"""

TEXT2SQL_SKILL_TUNABLE_ARTIFACT_SCHEMA: TunableArtifactSchema = FolderSchema(
    name="artifact",
    description=_TEXT2SQL_ARTIFACT_DIR_DESCRIPTION,
    files=[
        FolderSchema(name="skill", description=_TEXT2SQL_SKILL_DIR_DESCRIPTION, files=[
            FileSchema(name="SKILL.md", description=_TEXT2SQL_SKILL_MD_DESCRIPTION),
            FolderSchema(name="scripts", description=_TEXT2SQL_SCRIPTS_DIR_DESCRIPTION),
            FolderSchema(name="references", description=_REFERENCES_DIR_DESCRIPTION),
            FileSchema(name="...", description=_ADDITIONAL_FILES_DESCRIPTION),
        ]),
        FolderSchema(name="extensions", description=_PI_EXTENSIONS_DIR_DESCRIPTION, files=[
            FileSchema(name="workflow.ts", description=_WORKFLOW_TS_DESCRIPTION),
        ]),
    ]
)
