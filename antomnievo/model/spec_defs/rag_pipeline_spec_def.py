"""Spec definition for a retrieval (RAG) pipeline.

A hybrid retrieval pipeline: a deterministic DAG whose nodes may call models
(embedding, cross-encoder rerank, LLM rewrite). An editable spec directory
configures it; a Proposer mutates the directory, the runner materializes and
executes it.

Node function signature:
    async def run(query, hits, params, ctx) -> list[dict]
    def init(params, ctx) -> None            # sync; one-time setup at load, no model I/O
Each hit is a dict with at least {doc_id, score, ...}. `run` is AWAITED by the
runner; model nodes `await` the async client functions (embed_async /
rerank_async / chat_async) so HTTP I/O yields and queries run concurrently.
Nodes communicate only via the return value (hits, threaded node->node) and
ctx.resources (shared state).
"""

from antomnievo.model.spec_defs.common_descriptions import _ADDITIONAL_FILES_DESCRIPTION
from antomnievo.model.spec_schema import FileSchema, FolderSchema, SpecSchema

# ---------------------------------------------------------------------------
# Trajectory monitoring convention (referenced by file descriptions)
# ---------------------------------------------------------------------------

_TRAJECTORY = """\
## Trajectory recording

Behavior lands on the trajectory in two layers.

### Layer 1 — boundary (automatic; the node does nothing)

The runner records each node call as a `node:<id>` span:
- `input.hits`  : full hits received, each `{doc_id, score, rank}`.
- `output.hits` : full hits produced.
- `output.golden_present` : golden docs in this node's OUTPUT, with rank/score.
- `output.golden_dropped`  : golden docs in input but absent from output — \
  this node discarded them. Localizes "recall found it at rank 11 but truncate \
  cut it" to the truncating node.
- timing; `output.error` on failure.

Computed over the full hit sets. A `max_hits_per_span` cap bounds only the \
stored `hits` arrays, never `golden_*`, so a cap cannot hide a diagnosis.

### Layer 2 — internal (the node opts in via ctx.notes, typed)

A node appends to `ctx.notes`; the runner clears it before each call and puts it \
on `output.notes`. Every value carries an explicit type via \
`node_io.io(value, type_)` -> `{"value":..., "type":...}`, where `type_` is \
human-asserted ("str"/"int"/"float"/"bool"/"list[str]"). Example:

```python
from retrieval_test.node_io import io
ctx.notes.append({
    "input":    {"query": io(q, "str"), "k": io(k, "int")},
    "output":   {"hits_out_count": io(len(out), "int")},
    "internal": {"backend": io("rank_bm25", "str")},
})
```

### Model calls must be recorded in `internal`

A node that calls a model client (embedding/rerank/LLM) records, typed:
- `model: io(<id>, "str")`
- `n_calls: io(<int>, "int")`, `n_tokens: io(<int>, "int")` (when reported)
- `latency_ms: io(<float>, "float")`
- `status: io("ok"|"fallback"|"error", "str")`
- `fallback_reason: io(<str>, "str")` — only when status != "ok"

This separates a real call from a graceful degradation. The node does not record
transport details (URLs, paths) — it calls a client FUNCTION and records the
call's facts, not the wire.

### When Layer 2 is mandatory

- TRANSFORM nodes (query_rewrite): `run()` returns hits unchanged, so Layer 1 \
  shows hits_in==hits_out. The node MUST surface the rewritten string, mode, \
  whether it changed, and (LLM mode) the model-call facts above.
- A recall/rerank node using `params.use_rewritten` records `query_searched` = \
  the actual query searched, which may differ from the incoming `query`.

### Stay narrow

Record only the facts needed to answer "why did this node do that, and what did \
the model cost?" — backend, query used, model-call facts, fallback reason, one \
or two shaping counts. Do not dump intermediate score frames; Layer 1's \
`output.hits` already has per-doc scores with ranks.
"""


# ---------------------------------------------------------------------------
# spec/ directory
# ---------------------------------------------------------------------------

_SPEC_DIR = """\
The spec directory defines a retrieval pipeline. It is materialized by \
`load_pipeline` into a runnable DAG:

    spec/
    ├── pipeline.json     # the DAG: ordered nodes + params
    ├── nodes/            # node implementations, one .py per node TYPE
    └── prompt/           # prompt / resource files nodes read at run time

Hard constraints (e.g. "truncate k must be >= 1", "rerank needs a reasonable recall depth") live INSIDE \
each node's `run` as plain Python guards + `ctx.notes` warnings — the node \
author enforces them where the relevant state actually is.

## System form

The runtime loop is deterministic (DAG order and hit threading come from \
pipeline.json + node code), but some nodes call models — dense recall \
(embedding), cross-encoder rerank, and LLM query rewrite (its prompt is a file \
in prompt/). A node reaches a model through the matching client function (see \
nodes/), supplies params, and records the call on the trajectory; transport, \
retries, and credentials are the client's concern, not exposed to the node.

Model calls have cost/latency and a transient-failure mode. The split a node \
MUST honor: a replayable transient (HTTP 429/5xx/network, raised as \
`RateLimitError` by the client after its own retries) is **re-raised, not \
degraded** — it propagates out of `run()` and the harness replays the whole DAG \
for that query. Only DETERMINISTIC failures (no key, empty corpus, no doc text) \
fall back to a `status:"fallback"` note ([] for retrievers, pass-through for \
rerank/transform). This keeps a rate-limited run from silently becoming \
BM25-only. These facts are invisible to the DAG boundary, so model-calling \
nodes MUST record them on the trajectory (see nodes/).

## Node roles (implied by behavior; not declared)

  - recall_*  : RETRIEVER. top-k {doc_id, score} for a query. Lexical (no model), \
    dense (embedding), or structural (graph).
  - fuse_*    : combine recall lists (e.g. RRF) into one.
  - rerank*   : RE-RANKER, model-backed. Re-score top-m; costly, bounded by top_m. \
    If reranking a near-empty recall set is a concern, the guard lives in the \
    rerank node's `run`, not a separate invariant.
  - query_*   : TRANSFORM, possibly model-backed. Stashes a rewrite onto \
    ctx.resources['rewritten_query']; downstream recalls opt in via \
    params.use_rewritten. Returns hits unchanged.
  - truncate  : take top-k. Terminal; fixes the final result size.

## Global constraints

### No redundancy
Each rule/check lives in ONE canonical location. Allowed: pipeline.json states a \
param default + type while a node header explains the semantics. Forbidden: \
stating a hard guard in a node `run` AND restating it as prose in the header, \
or duplicating a prompt as both a prompt/ file and a hardcoded node string. \
When promoting prose to code, delete the prose.

### No contradiction
Rules across pipeline.json params, node headers, and node `run` code must not \
conflict. If a node header claims "rerank helps at any recall depth" but its \
`run` degrades when recall is tiny, the contradiction misleads the Proposer. \
Resolve by choosing ONE source and removing/qualifying the other. Avoid \
unconditional rules ("always X"); prefer decision rules with distinguishing \
conditions.

### Generalization
Every artifact must be corpus- and query-agnostic. A node that hardcodes a \
doc_id, query term, or golden set is dead weight on every other query. Abstract \
observed failures to the class (e.g. "term-overlap misses morphology" -> tokenize \
with word boundaries, NOT "add 'deafness'"). Guards key on ROLE/type-prefix \
(rerank + rerank_*) so they survive new backends.

  BAD:  `if doc_id == "MED-10": score *= 2`
  GOOD: normalize by BM25 document-length factor (corpus-wide).
"""


# ---------------------------------------------------------------------------
# pipeline.json
# ---------------------------------------------------------------------------

_PIPELINE_JSON = """\
Required. The DAG: an ordered list of nodes the runner threads `hits` through. \
Per-node field contract:

```json
{
  "dag": [
    {"id": "<node_id>", "type": "<node_type>", "enabled": true, "params": {"<param>": <value>}}
  ]
}
```

The block above fixes ONLY the per-node shape (id / type / enabled / params), \
not any particular pipeline. Every `type` resolves to a `nodes/<type>.py` \
implementation, and available types are whatever lives in `nodes/`. The \
proposer decides which node types the DAG contains, their order, which are \
enabled, and their params — so do not read the example as a recommended or \
required baseline.

Runner-enforced semantics:
- `dag` executes in LIST ORDER, threading `hits` node->node. The first enabled \
  node gets hits=[].
- `type` resolves to nodes/<type>.py which MUST define \
  `async def run(query, hits, params, ctx)` (the runner awaits it). Unknown type -> SpecError at load.
- `id` is the trajectory span name (`node:<id>`). Keep it STABLE across \
  mutations so the same node can be diffed before/after.
- `enabled: false` SKIPS the node but still records a `skipped` span. Use it to \
  A/B-test without deleting code.
- `params` is opaque to the runner — passed verbatim to run/init. The node \
  header docstring is the ONLY spec of `params` meaning, INCLUDING model-call \
  params (model, top_m, api_key, base_url, instruct, batch_size, prompt_file).

Hard param bound (proposer MUST honor):
- `recall_*` nodes: `params.k` <= 30. Multi-route recall is capped at 30 per \
  route so the fused candidate set stays bounded

Derived quantities (keep coherent across nodes):
- `recall_k`: max params.k across ENABLED recall_* nodes — what a rerank node
  reads (from ctx.resources, injected by the runner) to gate its recall-depth guard.
- final `k` : params.k of the enabled truncate node (the scored result size).
"""


# ---------------------------------------------------------------------------
# nodes/
# ---------------------------------------------------------------------------

_NODES = """\
Required. One `async def run(query, hits, params, ctx) -> list[Hit]` per node TYPE, \
filename = type. The runner imports nodes/<type>.py and binds pipeline.json \
params. A node MAY define `init(params, ctx)` for one-time setup (build an \
index, pre-compute embeddings). init() runs ONCE during load_pipeline, in DAG \
order, BEFORE the runner injects the corpus — so init usually cannot see \
ctx.resources['corpus']; nodes needing it build lazily on first run() and \
memoize on ctx.resources.

## Node contract (HARD)

1. Return `list[dict]`, each hit with at least {"doc_id": str, "score": number}. \
   A non-list return or a missing doc_id -> SpecError, recorded as output.error.
2. Pure w.r.t. declared I/O: read query/hits/params/ctx.resources, return hits. \
   Side effects (caching, rewrite stash) go ONLY on ctx.resources, never global \
   state.
3. `params` is the contract with pipeline.json. Document every key + default + \
   type in the header docstring.

## Model-calling nodes

- Split failures by replayability. A client `RateLimitError` (HTTP 429/5xx/network \
  after the client's own retries) MUST propagate out of `run()` — do not catch it \
  into a fallback; the harness replays the whole DAG for that query. Only \
  DETERMINISTIC failures (api_key missing, corpus/empty doc text) degrade: return \
  [] (retriever) or pass hits through (rerank/transform) with a `status:"fallback"` \
  note, so the pipeline completes and quality simply drops.
- Record the call on the trajectory (see the convention below).

### Model calls

A node calls a model through the corresponding client function. The client owns
transport, retries, and credentials; the node only supplies the params below and
records the call on the trajectory. Do not reimplement a model call inline.

| Call | Client function | Cost shape the node controls via params |
|---|---|---|
| embedding | `embedding_client.embed_async` (await) | batched (`batch_size`, default ~32) |
| rerank | `rerank_client.rerank_async` (await) | re-scores the top-m; cost ∝ `top_m` |
| **LLM chat** | `llm_client.chat_async` (await) | one call; `max_tokens` caps the OUTPUT (completion) only — input (prompt+messages) is billed separately and NOT limited by it.|

### How a node calls an LLM (e.g. query_rewrite mode="llm")

1. Read the prompt TEMPLATE from `ctx.resources["prompts"][params.prompt_file]`
   (loaded by the runner from `prompt/<stem>.md`). Substitute `placeholders` like
   `{query}` with node inputs. NEVER hardcode the prompt in the node — it lives
   in `prompt/` so a Proposer edits it without touching code (see prompt/).
2. Build OpenAI-shaped `messages` (system/user) and `await`
   `llm_client.chat_async(messages, model=params.model, max_tokens=params.max_tokens)`.
3. Extract the answer with `llm_client.extract_content(resp)` — do NOT read
   `choices[0].message.content` directly. `extract_content` guards the
   empty-answer footgun: if `content` is empty with `finish_reason == 'length'`
   (output hit the max_tokens cap), it RAISES a clear "raise max_tokens" error
   instead of silently injecting an empty string.
4. Record the call's facts on `ctx.notes` (typed, per the convention below).
5. On failure: a `RateLimitError` from `chat_async` propagates out of `run()`
   (the harness replays the DAG); do not catch it. A deterministic failure is the
   only degrade case — for query_rewrite, keep the ORIGINAL query (don't
   rewrite), append a `status:"fallback"` note, return hits unchanged.

### LLM params a node documents (in its header docstring)

- `model`: chat model id (default "GLM-5.2"; "GLM-5" and "GLM-5.1" also available)  [str]
- `prompt_file`: prompt stem in ctx.resources['prompts'] (default "rewrite")  [str]
- `max_tokens`: budget for the rewrite answer (default 2048, hard upper bound \
  2048). Reasoning is always OFF (not a tunable param), so this covers just the \
  rewritten query text.
- `temperature`: retrieval rewrite wants 0.0; raise for diverse expansions  [float]

Hard param bound (proposer MUST honor):
- `query_rewrite` nodes: `params.max_tokens` <= 2048. Reasoning is off by default, \
  so 2048 is ample for the rewritten query; exceeding it only inflates latency.
- `graph_rescore` nodes: `params.alpha` in [0,1] (0=ignore graph, 1=only graph). \
  Degrades to pass-through if graph unavailable.

## Per-query timeout (runtime, runner-enforced)

The whole pipeline has a HARD per-query budget: 10 seconds wall-clock from the
first node to the last. Each node is awaited under `asyncio.wait_for` with the
REMAINING budget — so if a node blows it, the trajectory names EXACTLY that node:
its span gets an `output.timeout` field with `timeout_reason`, `budget_used_ms`,
and `budget_limit_ms`. Remaining nodes are skipped; the query returns its current
(partial) hits instead of failing, so a slow node degrades the result rather than
aborting the batch. A Proposer CANNOT raise this limit via the spec (it is a
runner code constant). To stay under 10s: keep `top_m` bounded, recall `k` modest
(<=30 per route), `hop` <= 2, and `max_tokens` <= 2048.

""" + _TRAJECTORY


# ---------------------------------------------------------------------------
# prompt/
# ---------------------------------------------------------------------------

_PROMPT_DIR = """\
Required when any node reads a prompt template at run time. `load_pipeline` \
reads every file here into `ctx.resources["prompts"]` keyed by filename STEM \
(e.g. `prompt/rewrite.md` -> `ctx.resources["prompts"]["rewrite"]`). Nodes read \
their prompt from there by stem; a node may choose which stem via its \
`params.prompt_file`.

A prompt file is a template. The conventional placeholder is `{query}`, which a \
node substitutes with the incoming query. A node MUST support the placeholders \
documented in its header; unsupported placeholders are a node bug, not a spec bug.

Why a file and not a hardcoded string: editing a prompt file changes behavior \
with no node code change, and a node records the `prompt_file` it used on the \
trajectory, so which prompt shaped a run is observable. Editing behavior by \
mutating prose rather than code is the point of an editable spec.

Contract:
- One prompt per file; filename stem is the stable id nodes and trajectory refer to.
- Keep templates self-contained — they are loaded verbatim, not preprocessed \
  beyond nodestub substitution.
- If a node's prompt has variants, use multiple files (e.g. rewrite_long.md, \
  rewrite_short.md) and select via `params.prompt_file`, not branches inside one file.
"""


RAG_PIPELINE_SPEC_SCHEMA: SpecSchema = FolderSchema(
    name="spec",
    description=_SPEC_DIR,
    files=[
        FileSchema(name="pipeline.json", description=_PIPELINE_JSON),
        FolderSchema(name="nodes", description=_NODES, files=[]),
        FolderSchema(name="prompt", description=_PROMPT_DIR, files=[]),
        FileSchema(name="...", description=_ADDITIONAL_FILES_DESCRIPTION),
    ],
)


if __name__ == "__main__":
    from antomnievo.model.spec_schema import render_spec_schema

    print(render_spec_schema(RAG_PIPELINE_SPEC_SCHEMA))
