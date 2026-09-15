from antomnievo.model.spec_defs.common_descriptions import (
    _ADDITIONAL_FILES_DESCRIPTION,
    _SCRIPTS_DIR_DESCRIPTION,
)
from antomnievo.model.spec_schema import FileSchema, FolderSchema, SpecSchema

_APPWORLD_SPEC_DIR_DESCRIPTION = """\
The spec directory defines the AppWorld coding agent's configurable behavior, \
consisting of two subsystems:

- `skill/` — the knowledge layer: SKILL.md (instructions, API usage patterns, \
error handling), reference files, and helper scripts that guide the agent's \
code-generation strategy.

## Available Tools

The agent writes Python code that is executed in a sandboxed REPL. Available APIs:

- `apis.<app_name>.<api_name>(**kwargs)`: Call an app API (e.g., \
`apis.spotify.login(username=..., password=...)`).
- `apis.supervisor.complete_task(answer=..., status=...)`: Mark the task as done.
- `apis.api_docs.show_app_descriptions()`: List available apps.
- `apis.api_docs.show_api_descriptions(app_name=...)`: List APIs for an app.
- `apis.api_docs.show_api_doc(app_name=..., api_name=...)`: Get API spec.
- Python standard library: `datetime`, `json`, `math`, `re`, `collections`, etc.
- NO OS access: `os`, `shutil`, `subprocess`, etc. are disabled.

## Global Constraints

### No redundancy

Each rule or pattern lives in ONE canonical location. Allowed: SKILL.md may \
state a one-line WHAT + trigger while `references/pagination.md` holds \
the detailed HOW. Forbidden: restating the same paragraph in two files.

### No contradiction

Rules across files must not conflict. When SKILL.md says "always paginate" and \
a reference says "skip pagination for small datasets", the agent will pick \
whichever it reads last. Resolve contradictions by choosing ONE canonical \
location and removing or qualifying every other source.

### Generalization

The spec optimizes a skill applied to many AppWorld tasks across many apps. \
Every artifact — rules, references, scripts, extensions — must work on tasks \
and apps it has never seen. When observing a failure on one task, extract the \
underlying class of mistakes and prevent the whole class.

- **For prose artifacts**: every method MUST be general and transferable — \
it must work on any app/task, not just the one where the failure was observed.
- **For scripts**: must take app names and API names as arguments, with NO \
hardcoded names from specific tasks or apps.
"""

_APPWORLD_SKILL_DIR_DESCRIPTION = """\
Contains the AppWorld coding agent's skill content. The agent receives the \
SKILL.md content as part of its system prompt at runtime. Reference files \
and scripts are loaded on-demand when the agent reads them."""

_APPWORLD_REFERENCES_DIR_DESCRIPTION = """\
Optional. Documentation the agent reads via `open()` inside its Python REPL.

Consume every reference file inside a numbered Procedure step in SKILL.md using \
this exact form:

    print((SKILL_DIR / 'references/X.md').read_text())

Do not use natural-language phrases like "Read references/X.md for Y" — the \
agent will not open the file.

Do not put content here that the SKILL.md rule already inlines. If content \
fits in a 2-sentence rule, inline it and delete the reference file.

Per file: max 500 lines / 5000 tokens. Add a TOC if over 100 lines. One topic \
per file."""

_APPWORLD_SKILL_MD_DESCRIPTION = """\
Required. YAML frontmatter followed by Markdown instructions for the AppWorld \
coding agent skill.

## Frontmatter

- name: appworld-coding (FIXED — must match the skill directory name)
- description: 1-1024 chars. Include keywords like "AppWorld", "coding agent", \
"API interaction", "task completion" so the skill triggers reliably.

## Body structure

Keep the body under 500 lines / ~5000 tokens. Required sections:

```markdown
## Overview
<1-2 sentence summary of what this skill does>

## Procedure
<numbered workflow with mandatory verification gates. Express gates as \
code checks the agent must execute, not text instructions.>

## Rules
<concise API usage rules — pagination, credential lookup, date handling, etc.>

## Error Patterns to Avoid
<common AppWorld mistakes — missing complete_task call, wrong answer format, \
unhandled pagination, etc.>

## Output Format
<The agent must call apis.supervisor.complete_task(answer=...) as the final step. \
Answers must be minimal: entity names, numbers, not full sentences.>

## References
<REQUIRED — list every file in references/, scripts/. Each entry: \
BEFORE/WHEN/AFTER trigger + the exact executable directive.
- `scripts/pagination.py` — BEFORE any list API call: \
`exec((SKILL_DIR / 'scripts/pagination.py').read_text())`
- `references/pagination.md` — BEFORE first list API call: \
`print((SKILL_DIR / 'references/pagination.md').read_text())`>
```

## Writing Style

- Imperative form ("Call the API", not "You should call the API").
- Explain WHY a rule matters rather than relying on heavy-handed MUSTs.
- Ground rules in concrete AppWorld behaviors, not vague principles.
- Every rule must generalize across apps and tasks — no hardcoded app or API names.

## Content Boundary

Keep SKILL.md concise and self-sufficient for the common path. Delegate detail \
to references/ and scripts/.

- **10-line rule**: move any HOW content over 10 lines to references/. Keep \
at most 2 sentences in the rule: WHAT + WHEN.
- **No duplication**: never restate a reference file's content in SKILL.md. \
If you write a code snippet in a rule, delete either the snippet or the \
reference file — never keep both.
- **Reference consumption**: consume every reference file inside a numbered \
Procedure step using the exact form \
`print((SKILL_DIR / 'references/X.md').read_text())`. Do not use \
"Read references/X" phrasing — it does not trigger a read.
- **Script consumption**: same pattern with \
`exec((SKILL_DIR / 'scripts/X.py').read_text())`.
"""

APPWORLD_SKILL_SPEC_SCHEMA: SpecSchema = FolderSchema(
    name="spec",
    description=_APPWORLD_SPEC_DIR_DESCRIPTION,
    files=[
        FolderSchema(
            name="skill",
            description=_APPWORLD_SKILL_DIR_DESCRIPTION,
            files=[
                FileSchema(name="SKILL.md", description=_APPWORLD_SKILL_MD_DESCRIPTION),
                FolderSchema(name="scripts", description=_SCRIPTS_DIR_DESCRIPTION),
                FolderSchema(name="references", description=_APPWORLD_REFERENCES_DIR_DESCRIPTION),
                FileSchema(name="...", description=_ADDITIONAL_FILES_DESCRIPTION),
            ],
        )
    ],
)

# ---------------------------------------------------------------------------
# Skill-only variant — a minimal spec with only SKILL.md (no references/,
# scripts/, or other sub-directories). Used as a control variant in A/B
# experiments to isolate the effect of the multi-file skill structure.
# ---------------------------------------------------------------------------

_APPWORLD_SKILL_ONLY_SPEC_DIR_DESCRIPTION = """\
The spec directory defines the AppWorld coding agent's configurable behavior.

## Available Tools

The agent writes Python code that is executed in a sandboxed REPL. Available APIs:

- `apis.<app_name>.<api_name>(**kwargs)`: Call an app API (e.g., \
`apis.spotify.login(username=..., password=...)`).
- `apis.supervisor.complete_task(answer=..., status=...)`: Mark the task as done.
- `apis.api_docs.show_app_descriptions()`: List available apps.
- `apis.api_docs.show_api_descriptions(app_name=...)`: List APIs for an app.
- `apis.api_docs.show_api_doc(app_name=..., api_name=...)`: Get API spec.
- Python standard library: `datetime`, `json`, `math`, `re`, `collections`, etc.
- NO OS access: `os`, `shutil`, `subprocess`, etc. are disabled.

## Global Constraints

### Generalization

The spec optimizes a skill applied to many AppWorld tasks across many apps.
Every rule must work on tasks and apps it has never seen. When observing a
failure on one task, extract the underlying class of mistakes and prevent
the whole class.

- Every method MUST be general and transferable — it must work on any
app/task, not just the one where the failure was observed.
- No hardcoded app or API names in rules.
"""

_APPWORLD_SKILL_ONLY_MD_DESCRIPTION = """\
Required. YAML frontmatter followed by Markdown instructions for the AppWorld \
coding agent skill.

This is the ONLY file in the spec — all guidance must be self-contained here.

## Frontmatter

- name: appworld-coding (FIXED — must match the skill directory name)
- description: 1-1024 chars. Include keywords like "AppWorld", "coding agent", \
"API interaction", "task completion" so the skill triggers reliably.

## Body structure

Keep the body under 500 lines / ~5000 tokens. Since there are no references/ or \
scripts/ to delegate to, fit the most critical content within this limit. \
Required sections:

```markdown
## Overview
<1-2 sentence summary of what this skill does>

## Procedure
<numbered workflow with mandatory verification gates. Express gates as \
code checks the agent must execute, not text instructions.>

## Rules
<concise API usage rules — pagination, credential lookup, date handling, etc.>

## Error Patterns to Avoid
<common AppWorld mistakes — missing complete_task call, wrong answer format, \
unhandled pagination, etc.>

## Output Format
<The agent must call apis.supervisor.complete_task(answer=...) as the final step. \
Answers must be minimal: entity names, numbers, not full sentences.>
```

## Writing Style

- Imperative form ("Call the API", not "You should call the API").
- Explain WHY a rule matters rather than relying on heavy-handed MUSTs.
- Ground rules in concrete AppWorld behaviors, not vague principles.
- Every rule must generalize across apps and tasks — no hardcoded app or API names.

"""

APPWORLD_SKILL_ONLY_SPEC_SCHEMA: SpecSchema = FolderSchema(
    name="spec",
    description=_APPWORLD_SKILL_ONLY_SPEC_DIR_DESCRIPTION,
    files=[
        FolderSchema(
            name="skill",
            description="Contains the AppWorld coding agent's skill content. The agent receives the SKILL.md content as part of its system prompt at runtime.",
            files=[
                FileSchema(name="SKILL.md", description=_APPWORLD_SKILL_ONLY_MD_DESCRIPTION),
            ],
        )
    ],
)
