from antomnievo.model.spec_schema import FileSchema, FolderSchema, SpecSchema

_ADCONFIG_AGENT_SPEC_DESCRIPTION = """\
The ad-config agent's editable behavior package (`agents/`). The agent turns a
natural-language config-change request (offline-replay baseline: a config base
version + a source-code revision) into a structured config edit
(`textproto_edit_result`), stopping at a human-in-the-loop gate before any
release/push.

Subpackages:
- `starter_agent.py` — agent entry/builder + system prompt.
- `tools/` — the `@function_tool` wrappers + the adconfig MCP client (programmatic
  read/edit of the real baseline + release ticket). The agent's real read/edit
  flow goes through these, NOT raw LLM-exposed MCP tools.
- `modules/` — workspace (LocalWorkspace / sandbox-transport VFS), safe MCP,
  config-data review, progress.
- `skills/` — domain skills (e.g. ad-search-pos).
- `knowledge/`, `utils/`, `workspace/` — knowledge loading, mcp host / mist /
  env, run-context / identity / settings.

## Constraints (keep when mutating)
- **No redundancy / no contradiction** across files: a rule/convention lives in ONE
  canonical place; resolve contradictions by choosing one. Each general statement
  paired with a concrete example.
- **Generalize across ad-config types**: the agent edits many config types
  (algoCommonTableConfigText / dedupConfigMappingsText / creativeStyleConfigText /
  rawSortConfigText / …). A fix must transfer to unseen config types, not hardcode
  one. State the method; illustrate with ONE concrete config.
- **Code stays importable**: after any change,
  `python -c "from module_peizhiagent.agents.starter_agent import agent"` must
  still succeed (eddy builds the model/MCP at import). Don't break imports /
  signatures / builder wiring.
- **Preserve the tool flow + HITL gate**: keep `record_requirement_understanding`
  → investigate (knowledge/source/MCP baseline read) → `record_evidence_proof` /
  `record_config_hypotheses` → `finalize_textproto_change_draft` → STOP at the
  release HITL gate (`create_release_ticket` is NOT auto-executed offline).
- **Don't weaken run prerequisites**: keep sandbox-transport + MCP identity/permission
  assumptions intact. A run that produces no artifact (`prediction_present=False`)
  is a 0 / 漏改, NOT a crash — don't mask it.
- **Don't couple to a single test case / value**: rules about base_version /
  target values must be data-driven from the case gold, never hardcoded.

## Non-editable (do NOT mutate — runtime/base, not behavior)
`config/`, `main.py`/`app.py`/`solution.py` (platform wiring), `knowledge_data/*.jsonl`
(heavy non-behavior data), `runtime_env`, the eddy/arec/antmcp SDK. Only the
`agents/` editable package above is the spec.
"""

_ADCONFIG_STARTER_AGENT_DESCRIPTION = """\
The agent entry/builder + system prompt. Constructs the eddy agent (model, MCP,
tools, workspace, system prompt). Import-time builds model/MCP — keep it
importable (eddy builds at import). The system prompt encodes the config-change
workflow + decision rules; edits here change the agent's behavior directly."""

_ADCONFIG_TOOLS_DESCRIPTION = """\
@function_tool wrappers + the adconfig MCP client. The agent's real read/edit
flow goes through these (programmatic MCP calls), not raw LLM-exposed MCP tools.
Keep tool signatures + the MCP call/transport intact when mutating."""

_ADCONFIG_MODULES_DESCRIPTION = """\
Workspace / safe MCP / config-data review / progress modules. Includes the
eval-mode sandbox-transport + skill_only_workspace (the VFS the write-type agent
needs to produce artifacts). Don't break the eval-mode VFS path."""

_ADCONFIG_SKILLS_DESCRIPTION = """\
Domain skills (e.g. ad-search-pos). Skill files are editable behavior; keep them
general + importable."""

_ADCONFIG_KNOWLEDGE_DESCRIPTION = """\
Knowledge loading helpers (jsonl/pcsv readers for config field registry, adrtbcore
/adexchange code & docs, understand-anything graph). The agent's retrieval
calls these to load `knowledge_data/*.jsonl` at runtime; if the agent consistently
retrieves the WRONG config (e.g. returns a sibling config ranking higher than the
requested one), the fix lives HERE — loader query logic, ranking, filtering,
or search over which knowledge file to open. Keep importable + general."""

_ADCONFIG_UTILS_DESCRIPTION = """\
Supporting utilities (mcp_host, mist, env, config_data_chain, debug_logger,
output_summary, etc.). Infrastructure code the agent's tools depend on. Keep
importable + general; don't hardcode one config type or test case."""

_ADCONFIG_WORKSPACE_DESCRIPTION = """\
Workspace settings (context, identity, repo_registry, skill_sync, workspace).
Runtime identity/session/workspace management; usually stable, editable to fix
identity/session/registry issues. Keep importable."""

ADCONFIG_AGENT_SPEC_SCHEMA: SpecSchema = FolderSchema(
    name="agents",
    description=_ADCONFIG_AGENT_SPEC_DESCRIPTION,
    files=[
        FileSchema(name="starter_agent.py", description=_ADCONFIG_STARTER_AGENT_DESCRIPTION),
        FolderSchema(name="tools", description=_ADCONFIG_TOOLS_DESCRIPTION),
        FolderSchema(name="modules", description=_ADCONFIG_MODULES_DESCRIPTION),
        FolderSchema(name="knowledge", description=_ADCONFIG_KNOWLEDGE_DESCRIPTION),
        FolderSchema(name="skills", description=_ADCONFIG_SKILLS_DESCRIPTION),
        FolderSchema(name="utils", description=_ADCONFIG_UTILS_DESCRIPTION),
        FolderSchema(name="workspace", description=_ADCONFIG_WORKSPACE_DESCRIPTION),
    ],
)
