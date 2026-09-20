# Examples

Each example demonstrates an end-to-end antomnievoimization scenario using `antomnievo`. To run any example:

```bash
python -m antomnievo.example.<module_path>
# e.g. python -m antomnievo.example.rag.agentic_rag
```

## Agentic RAG (`rag/agentic_rag.py`)

Optimizes a ReAct agent that answers multi-hop questions by iteratively searching a knowledge base.

| Component | Implementation | Description |
|-----------|---------------|-------------|
| System | `ReactAgentSystem` | LLM agent with tool-calling (search, lookup) |
| Evaluator | `AtomicFactEvaluator` | Decomposes answers into atomic facts and checks each |
| Dataset | MuSiQue | Multi-hop QA requiring 2-4 reasoning steps |
| Proposer | `ClaudeCodeProposer` | Evolves system prompt and skill tunable artifacts |
| EA | `ParetoFrontierEvolutionAlgorithm` | Pareto dominance + top-N truncation |

**Goal**: Maximize factual correctness on complex, multi-hop questions.

## Text2SQL — BirdTest (`text2sql/birdtest_text2sql.py`)

Optimizes a PI coding agent that converts natural language questions into SQL, evaluated against the BIRD benchmark.

| Component | Implementation | Description |
|-----------|---------------|-------------|
| System | `BirdTestSystem` | Runs `birdtest.generate` per question via PI agent |
| Evaluator | `BirdTestEvaluator` | Execution accuracy (EX) + VES scoring |
| Dataset | BIRD (sampled train/val split) | Real-world databases with knowledge hints |
| Proposer | `PiCodingAgentProposer` | Evolves skill (SKILL.md, references, scripts) + extensions |
| EA | `ParetoFrontierEvolutionAlgorithm` | Pareto dominance + top-N truncation |

**Goal**: Evolve the NL2SQL skill and runtime extensions to maximize execution accuracy across diverse database schemas.

**Artifact structure**: `skill/` (SKILL.md, references, examples, scripts) + `extensions/` (TypeScript PI agent hooks that enforce hard constraints at runtime).

## Text2SQL — Dataphin (`text2sql/dp_text2sql.py`)

Optimizes a Text2SQL agent for Dataphin's Harbor-based NL2SQL runtime.

| Component | Implementation | Description |
|-----------|---------------|-------------|
| System | `DPText2SQLSystem` | Wraps Harbor-based NL2SQL runtime |
| Evaluator | `DPText2SQLEvaluator` | Harbor evaluation module (generated SQL vs ground-truth) |
| Dataset | Harbor tasks (train/val split) | Dataphin production scenarios |
| Proposer | `PiCodingAgentProposer` | Evolves agent tunable artifacts |
| EA | `ParetoFrontierEvolutionAlgorithm` | Pareto dominance + top-N truncation |

**Goal**: Evolve the NL2SQL agent tunable artifacts to maximize query correctness on Dataphin production workloads.
