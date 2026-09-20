#!/usr/bin/env python3
"""Ad-config optimizer entry: wires System + Evaluator + Proposer + EA +
CandidateStore + AdConfigOptimizer, then `await optimizer.optimize()`.

**Config = a workspace YAML file** (path via `--config` / env `ADCONFIG_CONFIG` /
default `./config.yaml`). All run config + secrets live there — **NO secrets are
hardcoded here**. Required secrets (`proposer.api_key`, `system.theta_api_key`,
`system.iam_token`) must be in the YAML; the entry materializes a `run.env` from
the system secrets that generate.py loads via `--env-file`. `--check-config`
validates the YAML's required fields without running (don't commit the secrets).

Run prerequisites (expensive — kick off deliberately): the `pi` coding-agent CLI
installed (PiCodingAgentProposer shells out to it); adrtbcore source repo at the
cases' code_version (sandbox-transport VFS); a pre-built schema_manifest covering
the cases; all secrets filled in the YAML.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os

import yaml

from antomnievo.common.config.config import setup_logging
from antomnievo.dataset.adconfig import load_adconfig_dataset
from antomnievo.evaluator.adconfig import AdConfigEvaluator
from antomnievo.evolution_algorithm.pareto_frontier import ParetoFrontierEvolutionAlgorithm
from antomnievo.model.budget import Budget
from antomnievo.model.tunable_artifact_defs.adconfig_tunable_artifact_def import ADCONFIG_AGENT_TUNABLE_ARTIFACT_SCHEMA
from antomnievo.optimizer.adconfig import AdConfigOptimizer
from antomnievo.proposer.pi_coding_agent_proposer import PiCodingAgentProposer
from antomnievo.store.candidate_store import LocalCandidateStore
from antomnievo.system.adconfig import AdConfigSystem

logger = logging.getLogger(__name__)

# secrets that must be present in the YAML (no defaults — never hardcode here)
REQUIRED_SECRETS = ["proposer.api_key", "proposer.base_url", "proposer.model", "system.theta_api_key", "system.iam_token"]


def _load_config(path: str) -> dict:
    if not os.path.isfile(path):
        raise SystemExit(f"config file not found: {path}")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _get_dotted(cfg: dict, dotted: str):
    cur: object = cfg
    for k in dotted.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return cur


def _missing_required(cfg: dict) -> list[str]:
    return [k for k in REQUIRED_SECRETS if not _get_dotted(cfg, k)]


def _raise_required(field: str) -> str:
    raise SystemExit(f"config missing required field: {field} — fill it in your YAML config (run --check-config to recheck)")


def _materialize_run_env(workspace_dir: str, system_cfg: dict) -> str:
    """Write theta_api_key + iam_token (from the YAML) to <workspace>/run.env so
    generate.py can load them via --env-file (the System reads run.env, not
    .env.local). One source of truth = the YAML."""
    path = os.path.join(workspace_dir, "run.env")
    lines: list[str] = []
    for yaml_key, env_key in (("theta_api_key", "THETA_API_KEY"), ("iam_token", "IAM_TOKEN")):
        v = (system_cfg or {}).get(yaml_key)
        if v:
            lines.append(f"{env_key}={v}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path


async def _run(cfg: dict) -> None:
    setup_logging()
    repo = cfg.get("repo", "/Users/jacklv/work/module-peizhiagent")
    adrtb = cfg.get("local_source_repo", "/Users/jacklv/work/adrtbcore")
    workspace_dir = cfg.get("workspace_dir", "/tmp/adconfig_opt_workspace")
    os.makedirs(workspace_dir, exist_ok=True)

    system_cfg = cfg.get("system") or {}
    python = system_cfg.get("python", f"{repo}/.venv/bin/python")
    generate_script = system_cfg.get("generate_script", f"{repo}/scripts/generate.py")
    evaluate_script = system_cfg.get("evaluate_script", f"{repo}/scripts/evaluate.py")
    run_env_file = _materialize_run_env(workspace_dir, system_cfg)
    agent_src = cfg.get("agent_src", f"{repo}/src/module_peizhiagent")
    schema_manifest = cfg.get(
        "schema_manifest",
        f"{repo}/outputs/评估结果/full_eval_20260617/deterministic/schema_preflight/schema_manifest.jsonl",
    )
    cases = cfg.get(
        "cases",
        f"{repo}/评测数据/final_cold_cases_20260612_1542/cases_final_cold_cases_20260612_1542.jsonl",
    )
    hp = cfg.get("hyperparams") or {}
    # ── smoke switch: true = small data + 1 iteration for fast test; false = real
    # run with the user-aligned hyperparams from YAML. flip in the YAML to switch.
    smoke = bool(cfg.get("smoke", False))
    if smoke:
        train_max = 2
        val_max = 0
        batch_size = 1
        max_iter = 1
        num_proposals = 1
        max_refl = 0
        min_imp = 0.5
        logger.warning(
            "SMOKE MODE: overriding hyperparams → train=%d val=%d batch=%d max_iter=%d "
            "num_proposals=%d max_refl=%d (set `smoke: false` in YAML for real run with user-aligned sizes)",
            train_max, val_max, batch_size, max_iter, num_proposals, max_refl,
        )
    else:
        train_max = int(hp.get("train_max", 98))
        val_max = int(hp.get("val_max", 0))
        batch_size = int(hp.get("batch_size", 2))
        max_iter = int(hp.get("max_iterations", 5))
        num_proposals = int(hp.get("num_proposals", 2))
        max_refl = int(hp.get("max_reflection_iterations", 2))
        min_imp = float(hp.get("min_improvement_per_batch", 2.0))
        logger.info(
            "REAL RUN: train=%d val=%d batch=%d max_iter=%d num_proposals=%d (from YAML hyperparams)",
            train_max, val_max, batch_size, max_iter, num_proposals,
        )

    system = AdConfigSystem(
        generate_script=generate_script, python_path=python,
        agent_src=agent_src, tunable=list(cfg.get("tunable", ["agents"])),
        local_source_repo=adrtb, env_file=run_env_file,
        timeout=int(system_cfg.get("timeout", 1200)),
        concurrency=int(system_cfg.get("concurrency", 1)),
    )
    evaluator = AdConfigEvaluator(
        evaluate_script=evaluate_script, python_path=python,
        schema_manifest=schema_manifest, adrtbcore_repo=adrtb,
        eval_stage=system_cfg.get("eval_stage", "deterministic"),
    )

    all_insts = await load_adconfig_dataset(cases, max_samples=train_max + val_max)
    train, val = all_insts[:train_max], all_insts[train_max:]  # sequential subset (no real split)
    logger.info("dataset: train=%d val=%d (sequential subset; no real split yet)", len(train), len(val))

    candidate_store = LocalCandidateStore(workspace_dir, cleanup_unavailable=False)
    prop = cfg.get("proposer") or {}
    proposer = PiCodingAgentProposer(
        tunable_artifact_schema=ADCONFIG_AGENT_TUNABLE_ARTIFACT_SCHEMA, candidate_store=candidate_store,
        evaluator=evaluator, system=system,
        api_key=prop.get("api_key") or None,
        base_url=prop.get("base_url"),
        model=prop.get("model") or _raise_required("proposer.model"),
        pi_path=prop.get("pi_path", "pi"),
        max_turns=int(prop.get("max_turns", 150)),
        timeout=int(prop.get("timeout", 3600)),
        concurrency=int(prop.get("concurrency", num_proposals)),
    )
    evolution_algorithm = ParetoFrontierEvolutionAlgorithm(
        candidate_store=candidate_store,
        max_candidate_num=int((cfg.get("evolution") or {}).get("max_candidate_num", 3)),
    )
    optimizer = AdConfigOptimizer(
        system=system, proposer=proposer, evaluator=evaluator,
        evolution_algorithm=evolution_algorithm, candidate_store=candidate_store,
        train_dataset=train, val_dataset=val,
        batch_size=batch_size,
        budget=Budget(max_iterations=max_iter),
        num_proposals=num_proposals,
        max_reflection_iterations=max_refl,
        min_improvement_per_batch=min_imp,
        initial_artifacts_dir=cfg.get("initial_artifacts_dir") or _raise_required("initial_artifacts_dir"),
    )
    logger.info("calling optimizer.optimize() (workspace=%s, run.env=%s)...", workspace_dir, run_env_file)
    await optimizer.optimize()
    logger.info("finished.")


def main() -> int:
    ap = argparse.ArgumentParser(description="ad-config optimizer entry")
    ap.add_argument("--config", default=os.environ.get("ADCONFIG_CONFIG", "config.yaml"),
                    help="workspace YAML config path (all run config + secrets; env ADCONFIG_CONFIG)")
    ap.add_argument("--check-config", action="store_true", help="validate the config's required fields; don't run")
    args = ap.parse_args()

    cfg = _load_config(args.config)
    missing = _missing_required(cfg)
    if args.check_config:
        print(f"config: {args.config}")
        print("missing required secrets:", missing or "(none)")
        # surfacing which optional fields would fall back to ad-config defaults
        empty = [k for k in ("workspace_dir", "repo", "cases", "schema_manifest", "local_source_repo") if not cfg.get(k)]
        print("optional fields not set (will use ad-config defaults):", empty or "(none)")
        print("OK to run:", "yes" if not missing else "NO — fill the missing secrets in the config, recheck")
        return 0
    if missing:
        raise SystemExit(
            f"config {args.config} missing required secrets: {missing}. "
            f"Fill them (run with --check-config to recheck). Do NOT hardcode them here."
        )
    asyncio.run(_run(cfg))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        logger.info("user interrupted")
    except Exception as exc:
        logger.error("optimizer failed: %s", exc)
        import traceback
        traceback.print_exc()
