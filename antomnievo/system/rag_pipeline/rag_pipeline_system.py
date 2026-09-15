from __future__ import annotations

import asyncio
import json
import logging
import os
import time

from antomnievo.interface.data_inst import DataInst
from antomnievo.interface.system import System
from antomnievo.model.candidate_data import CandidateMeta
from antomnievo.model.rollout_result import RolloutResult
from antomnievo.model.system_result import SystemResult
from antomnievo.model.trajectory import Span, Trajectory

logger = logging.getLogger(__name__)


_RAG_PIPELINE_SYSTEM_DESCRIPTION = """\
Retrieval Pipeline System:

A deterministic retrieval DAG whose nodes may call models (embedding dense
recall, cross-encoder rerank, LLM query rewrite). The optimized system is the
spec directory: ``pipeline.json`` (ordered nodes + params), ``nodes/*.py`` (one
``run(query, hits, params, ctx) -> list[Hit]`` per node TYPE), and ``prompt/*.md``
(prompt templates nodes read at run time).

## System input

A batch of queries (MuSiQue questions). Each query flows through the enabled
DAG nodes in list order, threading hits node->node. Recall nodes contribute
candidate lists that accumulate (multi-route); fuse/rerank/truncate consume.

## System output

A ranked hit list ``[{doc_id, score}, ...]`` per query, written to
``predictions.jsonl`` plus a per-query pipeline-run trajectory under
``trajectories/<query_id>.json`` (node spans carry full hits, golden_present /
golden_dropped, and model-call notes). The evaluator scores Recall@k / nDCG@k
of these hits against the query's golden_doc_ids.

## What the Proposer mutates

pipeline.json (enable/disable nodes, tune k / rrf_k / top_m, reorder), nodes/*.py
(backends, guards, tokenization), and prompt/*.md (rewrite templates). Model
calls degrade on deterministic failure (no key / empty corpus) and re-raise on
replayable transients (the harness replays the whole per-query DAG).
"""


def _safe_filename(query_id: str) -> str:
    """Match generate._safe_filename so per-query trajectory files line up."""
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in str(query_id))
    return f"{safe or 'query'}.json"


def _span_from_dict(d: dict) -> Span:
    """Convert a retrieval_test span dict (envelope ``{trajectory,...}``) to an
    antomnievo Span. Field map: type->span_type, parent_id->parent_span_id; the
    two trajectory formats are otherwise identical."""
    return Span(
        id=d.get("id") or "",
        parent_span_id=d.get("parent_id"),
        name=d.get("name", ""),
        span_type=d.get("type", "span"),
        input=d.get("input"),
        output=d.get("output"),
        start_time=d.get("start_time"),
        end_time=d.get("end_time"),
        children=[_span_from_dict(c) for c in d.get("children", []) or []],
    )


def _load_trajectory(path: str, query_id: str) -> Trajectory:
    """Read a per-query trajectory JSON written by generate.py into a Trajectory."""
    if not os.path.isfile(path):
        return Trajectory(root_span_list=[], trace_id=query_id)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.warning("failed to read trajectory %s: %s", path, e)
        return Trajectory(root_span_list=[], trace_id=query_id)

    spans = [_span_from_dict(s) for s in data.get("trajectory", [])]
    return Trajectory(
        root_span_list=spans,
        session_id=data.get("session_id"),
        trace_id=data.get("trace_id") or query_id,
        errors=list(data.get("errors", []) or []),
    )


class RagPipelineSystem(System):
    """System that runs a retrieval-pipeline spec via retrieval-test's generate.py.

    Mirrors AppWorldSystem: ``_run`` is unused (raises); all execution goes
    through ``run_batch``, which shells out to ``generate.py`` in the
    retrieval-test venv. The subprocess loads ``candidate_meta.spec_dir`` (the
    pipeline DAG the Proposer mutates), runs it over the batch's queries, and
    writes ``predictions.jsonl`` + per-query trajectories to ``run_output_dir``.
    """

    def __init__(
        self,
        retrieval_test_python: str,
        retrieval_test_dir: str,
        concurrency: int = 8,
        subprocess_timeout: float = 1800.0,
        max_hits_per_span: int | None = None,
    ):
        super().__init__(concurrency=concurrency)
        self.retrieval_test_python = retrieval_test_python
        self.retrieval_test_dir = retrieval_test_dir
        self.subprocess_timeout = subprocess_timeout
        self.max_hits_per_span = max_hits_per_span
        self._generate_script = os.path.join(
            retrieval_test_dir, "src", "retrieval_test", "generate.py"
        )

    def system_description(self) -> str:
        return _RAG_PIPELINE_SYSTEM_DESCRIPTION

    async def _run(self, candidate_meta: CandidateMeta, data_inst: DataInst) -> SystemResult:
        raise NotImplementedError(
            "RagPipelineSystem._run is not used; call run_batch, which shells out to generate.py"
        )

    @staticmethod
    def _write_queries(data_list: list[DataInst], queries_path: str) -> None:
        # One {query_id, query, golden_doc_ids, golden_docs} per line.
        # golden_doc_ids: what generate.py / evaluate.py score against (derived
        #   from the data inst's golden_docs, each of which carries doc_id).
        # golden_docs:   the full supporting passages [{doc_id, title, text}],
        #   so the artifact is self-contained and the proposer can read the
        #   evidence without joining the corpus.
        with open(queries_path, "w", encoding="utf-8") as f:
            for d in data_list:
                golden_docs = list(getattr(d, "golden_docs", []) or [])
                f.write(json.dumps({
                    "query_id": d.id,
                    "query": d.query,
                    "golden_doc_ids": [gd.get("doc_id") for gd in golden_docs],
                    "golden_docs": golden_docs,
                }) + "\n")

    @staticmethod
    def _read_predictions(predictions_path: str) -> dict[str, list[dict]]:
        preds: dict[str, list[dict]] = {}
        if not os.path.isfile(predictions_path):
            logger.warning("predictions.jsonl not found at %s", predictions_path)
            return preds
        with open(predictions_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                preds[str(rec["query_id"])] = rec.get("hits", [])
        return preds

    def _build_cmd(
        self, spec_dir: str, queries_path: str, output_dir: str, corpus_path: str
    ) -> list[str]:
        cmd = [
            self.retrieval_test_python, self._generate_script,
            "--spec-dir", spec_dir,
            "--queries", queries_path,
            "--output-dir", output_dir,
        ]
        # corpus is split-specific (train vs val) and comes from the data inst
        # at runtime; omitted if absent (generate.py falls back to an empty corpus).
        if corpus_path:
            cmd.extend(["--corpus", corpus_path])
        # fan out concurrent queries inside generate.py (first warms, rest gather).
        cmd.extend(["--concurrency", str(self.concurrency)])
        if self.max_hits_per_span is not None:
            cmd.extend(["--max-hits-per-span", str(self.max_hits_per_span)])
        return cmd

    def _subprocess_env(self) -> dict:
        env = os.environ.copy()
        src_dir = os.path.join(self.retrieval_test_dir, "src")
        # Make `from retrieval_test.X import Y` resolve even if the package is
        # not pip-installed in the venv (run the script with src on PYTHONPATH).
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = src_dir + (os.pathsep + existing if existing else "")
        return env

    async def run_batch(
        self,
        candidate_meta: CandidateMeta,
        data_list: list[DataInst],
        *,
        run_output_dir: str,
        **kwargs,
    ) -> list[SystemResult]:
        """Run generate.py over the batch; return one SystemResult per query.

        Keyword args:
            run_output_dir: working dir for this rollout — generate.py writes
                predictions.jsonl + trajectories/ here. Supplied by the optimizer.

        The corpus is split-specific and is NOT fixed at construction — it is
        read at runtime from each data inst's ``corpus_path`` (train queries ->
        train corpus, val -> val corpus).
        """
        if not data_list:
            return []
        os.makedirs(run_output_dir, exist_ok=True)
        queries_path = os.path.join(run_output_dir, "queries.jsonl")
        self._write_queries(data_list, queries_path)

        effective_corpus = getattr(data_list[0], "corpus_path", "")
        cmd = self._build_cmd(candidate_meta.spec_dir, queries_path, run_output_dir, effective_corpus)
        logger.info(
            "Running generate.py: %d queries, spec_dir=%s, corpus=%s",
            len(data_list), candidate_meta.spec_dir, effective_corpus or "(none)",
        )

        t0 = time.monotonic()
        process = await asyncio.create_subprocess_exec(
            *cmd,
            env=self._subprocess_env(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=self.subprocess_timeout
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            logger.error("generate.py timed out after %.0fs", self.subprocess_timeout)
            return [
                SystemResult(
                    trajectory=Trajectory(root_span_list=[], trace_id=d.id),
                    output=RolloutResult(content="error: generate.py timed out"),
                )
                for d in data_list
            ]
        elapsed = time.monotonic() - t0

        if process.returncode != 0:
            logger.error(
                "generate.py failed (exit %d) in %.1fs:\nstdout: %s\nstderr: %s",
                process.returncode, elapsed,
                stdout.decode("utf-8", errors="replace")[:2000],
                stderr.decode("utf-8", errors="replace")[:2000],
            )
        else:
            logger.info("generate.py completed in %.1fs", elapsed)

        predictions = self._read_predictions(os.path.join(run_output_dir, "predictions.jsonl"))
        traj_dir = os.path.join(run_output_dir, "trajectories")

        results: list[SystemResult] = []
        for d in data_list:
            hits = predictions.get(d.id, [])
            traj = _load_trajectory(os.path.join(traj_dir, _safe_filename(d.id)), d.id)
            content = "\n".join(
                f"[{i + 1}] {h.get('doc_id')} ({h.get('score')})"
                for i, h in enumerate(hits)
            )
            results.append(SystemResult(
                trajectory=traj,
                output=RolloutResult(content=content),
            ))
        logger.info(
            "system run_batch: %d/%d queries produced predictions",
            sum(1 for d in data_list if d.id in predictions), len(data_list),
        )
        return results
