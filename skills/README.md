# AntOmniEvo Skills

Per-scenario [Agent Skill](https://docs.claude.com/en/docs/claude-code/skills)s for driving
[AntOmniEvo](../antomnievo) optimization experiments. Each skill distills the best practices of one
scenario into something an agent can run, so the next user skips the pitfalls that took the first
person days to discover.

**Language convention: this folder targets Ant Group internal users — skill content is written in
Chinese (the internal preference); this README stays in English.**

## Why this exists: agent-driven, not human-driven

The old way of standing up an AntOmniEvo run: a human reads the framework docs, figures out which of
the pluggable components they need, hand-wires an entry script, guesses at concurrency / budget /
env vars, runs once, and debugs the failure modes everyone hits the first time. The human carries
the whole learning curve and every foot-gun.

Every skill in this folder is expected to invert that: a **skill is an agent that proactively
drives** the setup and management of the experiment. It does not wait to be told
what to do step by step — it interviews the user for the few facts only the user knows (where is
the repo, where is the dataset, what is the metric), then takes ownership of the rest: picking
components, writing the entry script, setting sane defaults, launching the run, and triaging
failures by mapping symptoms to the known causes recorded in its references.

In short: the user answers a handful of questions; the agent does the wiring, running, and
pitfall-avoidance that a human used to do by hand.

## Skills

### eddy-antomnievo-experiment

**Purpose-built for the eddy high-code agent runtime.** This skill exists to make standing up an
AntOmniEvo optimization experiment on an eddy business agent a fixed, repeatable path — its steps,
recipes, and pitfall logs are all written against eddy-specific mechanics (entry discovery,
trajectory schema, sandbox-transport, MCP identity). **Other runtimes may use it as a reference
template for distilling their own skill, but cannot use it directly.**

For onboarding an **Ant internal high-code agent runtime (eddy) business agent** onto AntOmniEvo —
you have an eddy agent and want AntOmniEvo to evolve user-chosen tunable artifacts of it (prompts,
skills, configs). Covers the full path from workspace/data setup through `generate.py` /
`evaluate.py` smoke tests to the wired System / Evaluator / Optimizer loop. Distilled from the
real rollout in the module-peizhiagent project; per-step details and pitfall logs live in its
`references/`.

## Suggestion

If you run optimization experiments on your own agent scenario: follow the `eddy-antomnievo-experiment`
example and distill your hard-won best practices into a skill of your own. Once captured, the skill
drives the experiment setup for you — no repeated manual wiring, and no re-stepping on the pits you
already climbed out of.
