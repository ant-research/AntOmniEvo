from antomnievo.model.tunable_artifact_defs.common_descriptions import (
    _ADDITIONAL_FILES_DESCRIPTION,
    _ASSETS_DIR_DESCRIPTION,
    _REFERENCES_DIR_DESCRIPTION,
    _SCRIPTS_DIR_DESCRIPTION,
)
from antomnievo.model.tunable_artifact_schema import (
    FileSchema,
    FolderSchema,
    TunableArtifactSchema,
    render_tunable_artifact_schema,
)

"""
Follows the Agent Skills artifacts (agentskills.io):
    {candidate_id}/artifact/
    ├── SKILL.md       # Required: frontmatter + instructions
    ├── scripts/       # Optional: executable code
    ├── references/    # Optional: documentation
    └── assets/        # Optional: templates, resources

Progressive disclosure:
    L1 Metadata (~100 tokens): name + description from frontmatter (loaded at startup for routing)
    L2 Instructions (< 500 lines, < 5000 tokens recommended): SKILL.md body (loaded when skill is activated)
    L3 Resources (as needed): files in scripts/, references/, assets/, etc. (loaded on demand)

Keep SKILL.md under 500 lines. Move detailed content to references/.
"""

_ARTIFACT_DIR_DESCRIPTION = """\
The artifact directory defines the system's configurable behavior. Files are loaded progressively: \
SKILL.md frontmatter at startup for routing; SKILL.md body when the skill is activated; \
other files on-demand — the agent must actively discover and read them.

Global constraints across all artifact files:
- No redundancy: each piece of information must live in exactly one place. If two files state \
the same rule, one must be removed or replaced with a cross-reference. Cross-references are \
allowed (e.g., "See references/X for details"), but never duplicate the content itself.
- No contradiction: rules across files must not conflict. If two files give conflicting \
instructions, the agent will behave unpredictably. Resolve contradictions by choosing one \
canonical location and removing or qualifying the other."""

_SKILL_MD_DESCRIPTION = """\
Required. YAML frontmatter followed by Markdown instructions.

## Frontmatter

Frontmatter fields:
- name (required): 1-64 chars, lowercase letters (a-z), numbers, and hyphens only. \
Must not start or end with a hyphen. Must not contain consecutive hyphens (--). \
Must match the parent directory name.
- description (required): 1-1024 chars. This is the PRIMARY triggering mechanism — \
include both WHAT the skill does AND WHEN to use it, with specific keywords and contexts. \
Be slightly "pushy" to combat under-triggering: e.g., "Use for topics related to X, Y, Z" \
rather than just "Handles X". All "when to use" info goes here, not in the body.
- argument-hint (optional): Hint for arguments when the user invokes the skill, e.g. "File path or module name".
- user-invokable (optional, default true): Whether users can manually invoke the skill.
- disable-model-invocation (optional, default false): Set true to disable automatic model invocation.
- license (optional): SPDX license identifier or reference to a bundled license file.
- compatibility (optional): List of compatible agents and environment requirements.
- metadata (optional): Arbitrary key-value mapping (author, version, tags, etc.). \
Keys should be reasonably unique to avoid accidental conflicts.
- allowed-tools (optional): Space-separated string of pre-approved tools. (Experimental)

## Body Structure

Body structure (keep under 500 lines, ideally < 5000 tokens):
```markdown
## Overview
<1-2 sentence summary of what this skill does and why it matters>

## Procedure
<numbered step-by-step workflow in imperative form — what to do, not how to do each step in detail>

## Rules
<concise rules with brief examples — one paragraph per rule, not full tutorials>

## Error Patterns to Avoid
<common mistakes and how to prevent them>

## Output Format
<exact format the agent must produce as its final answer — structure, delimiters, \
what to include and what to omit. The agent's output is parsed/evaluated automatically; \
any deviation from this format will cause failures.>

## References
<REQUIRED section — list every file in references/, scripts/, assets/, etc.
Each entry MUST use a BEFORE/WHEN/AFTER trigger — do NOT use FOR or other keywords.
Triggers tell the agent WHEN to read the file, not just what it's about.>
- `references/patterns.md` — BEFORE attempting multi-hop decomposition, read this for patterns
- `references/strategies.md` — WHEN retrieval fails, read this for recovery strategies
- `scripts/validate.py` — BEFORE submitting final answer, run this to validate format
```

## Writing Style

- Use imperative form ("Extract facts exactly as they appear", not "You should extract facts")
- Explain WHY things matter rather than relying on heavy-handed MUSTs
- Make rules general, not narrow to specific examples
- Ground each rule in a concrete behavior: write what the agent should DO in a specific \
situation, not vague principles. Bad: "Handle errors gracefully." \
Good: "When a tool call returns an error, retry once with the same arguments. \
If it still fails, skip the current item and move to the next."

## Content Boundary

SKILL.md is the ONLY file automatically loaded into the agent's context — other files
are loaded on-demand only when SKILL.md explicitly tells the agent to read them.
SKILL.md must be concise, self-sufficient for the common path, and point to other files for details.

What belongs in SKILL.md: rules, workflow steps, decision logic, brief inline examples
(1-3 lines each), and trigger directives that tell the agent WHEN to read other files.
Anything else belongs in references/, scripts/, or assets/.

1. 10-line rule: if content exceeds 10 lines, extract to references/ and replace in SKILL.md
with a one-line summary plus a trigger directive.
Bad: a 30-line worked example in SKILL.md.
Good: "BEFORE planning complex multi-hop queries, read `references/decomposition-patterns.md` for patterns."
2. No duplication: SKILL.md tells the agent WHAT to do and WHEN to read a file; references/
tells the agent HOW. Never restate reference content in SKILL.md.
3. SKILL.md MUST include a ## References section listing every other skill file, each with a
BEFORE/WHEN/AFTER trigger condition — never use FOR or other non-trigger keywords (see Body Structure template for examples).
4. Rules that depend on reference content MUST include an inline directive like
'Read `references/X` before proceeding' — do NOT rely on the agent discovering the References section.
5. Keep file references one level deep from SKILL.md. Avoid deeply nested reference chains.

Multi-variant skills: organize by variant so the agent reads only what it needs:
```
references/
├── aws.md
├── gcp.md
└── azure.md
```"""

AGENT_SKILL_TUNABLE_ARTIFACT_SCHEMA: TunableArtifactSchema = FolderSchema(
    name="artifact",
    description=_ARTIFACT_DIR_DESCRIPTION,
    files=[
        FileSchema(name="SKILL.md", description=_SKILL_MD_DESCRIPTION),
        FolderSchema(name="scripts", description=_SCRIPTS_DIR_DESCRIPTION),
        FolderSchema(name="references", description=_REFERENCES_DIR_DESCRIPTION),
        FolderSchema(name="assets", description=_ASSETS_DIR_DESCRIPTION),
        FileSchema(name="...", description=_ADDITIONAL_FILES_DESCRIPTION),
    ]
)


if __name__ == "__main__":
    print(render_tunable_artifact_schema(AGENT_SKILL_TUNABLE_ARTIFACT_SCHEMA))

    print("\n" + "=" * 60 + "\n")

    # nested test
    nested = FolderSchema(
        name="my-skill",
        description="A skill with nested folders.",
        files=[
            FileSchema(name="SKILL.md", description="Main instructions."),
            FolderSchema(
                name="scripts",
                description="Executable scripts.",
                files=[
                    FileSchema(name="run.py", description="Main entry script."),
                    FolderSchema(
                        name="utils",
                        description="Utility scripts.",
                        files=[
                            FileSchema(name="helper.py", description="Helper functions."),
                            FileSchema(name="parser.py", description="Parsing utilities."),
                        ],
                    ),
                ],
            ),
            FolderSchema(
                name="references",
                description="Documentation.",
                files=[
                    FileSchema(name="api.md", description="API reference."),
                ],
            ),
        ],
    )
    print(render_tunable_artifact_schema(nested))
