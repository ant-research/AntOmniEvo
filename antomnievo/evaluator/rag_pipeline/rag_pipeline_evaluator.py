from __future__ import annotations

import asyncio
import json
import logging
import os
import time

from antomnievo.interface.data_inst import DataInst
from antomnievo.interface.evaluator import Evaluator
from antomnievo.model.evaluation_result import EvaluationResult
from antomnievo.model.system_result import SystemResult

logger = logging.getLogger(__name__)


_RAG_PIPELINE_SCORING_CRITERIA = """\
Retrieval quality for MuSiQue (top-k). Per-query score:

    score = {ndcg_w} * nDCG@k + {recall_w} * Recall@k    (both in [0, 1])

- nDCG@k: binary relevance, IDCG = min(k, |gold|). Rewards ranking found gold higher.
- Recall@k: fraction of golden_doc_ids in the top-k. Rewards finding more gold.
- Both 0 if no gold in top-k.
- Candidate score = mean of per-query scores over the eval set.

Proposer knobs: enable/combine recall routes (lexical vs dense), recall depth k,
fuse weights (rrf_k), rerank (top_m), query rewriting.
"""


class RagPipelineEvaluator(Evaluator):
    """Evaluator that scores the retrieval-pipeline tunable artifacts via retrieval-test's evaluate.py.

    Mirrors AppWorldEvaluator: ``_evaluate`` is unused (raises); all scoring goes
    through ``evaluate_batch``, which shells out to ``evaluate.py`` in the
    retrieval-test venv. It REUSES the predictions the system already produced
    (``--predictions <path>``) so the pipeline is not re-run, then reads
    ``details.jsonl`` for per-query nDCG@k / Recall@k + a deterministic reason.
    """

    def __init__(
        self,
        retrieval_test_python: str,
        retrieval_test_dir: str,
        k: int = 10,
        ndcg_weight: float = 0.2,
        recall_weight: float = 0.8,
        concurrency: int = 8,
        subprocess_timeout: float = 1800.0,
    ):
        super().__init__(concurrency=concurrency)
        self.retrieval_test_python = retrieval_test_python
        self.retrieval_test_dir = retrieval_test_dir
        self.k = k
        self.ndcg_weight = ndcg_weight
        self.recall_weight = recall_weight
        self.subprocess_timeout = subprocess_timeout
        self._evaluate_script = os.path.join(
            retrieval_test_dir, "src", "retrieval_test", "evaluate.py"
        )

    def scoring_criteria(self) -> str:
        return _RAG_PIPELINE_SCORING_CRITERIA.format(
            ndcg_w=self.ndcg_weight, recall_w=self.recall_weight
        )

    async def _evaluate(
        self,
        data_inst: DataInst,
        system_result: SystemResult,
    ) -> EvaluationResult:
        raise NotImplementedError(
            "RagPipelineEvaluator._evaluate is not used; call evaluate_batch, "
            "which shells out to evaluate.py"
        )

    @staticmethod
    def _write_queries(data_list: list[DataInst], queries_path: str) -> None:
        # One {query_id, query, golden_doc_ids, golden_docs} per line.
        # golden_doc_ids: what evaluate.py scores against (REQUIRED by evaluate.py;
        #   derived from the data inst's golden_docs, each of which carries doc_id).
        # golden_docs:   the full supporting passages [{doc_id, title, text}].
        with open(queries_path, "w", encoding="utf-8") as f:
            for d in data_list:
                golden_docs = list(getattr(d, "golden_docs", []) or [])
                f.write(json.dumps({
                    "query_id": d.id,
                    "query": d.query,
                    "golden_doc_ids": [gd.get("doc_id") for gd in golden_docs],
                    "golden_docs": golden_docs,
                }) + "\n")

    def _build_cmd(
        self, artifact_dir: str, queries_path: str, predictions_path: str,
        output_dir: str, corpus_path: str,
    ) -> list[str]:
        # --artifact-dir is required by the CLI even though --predictions means the
        # pipeline is NOT re-run; pass the candidate's artifact_dir for traceability.
        cmd = [
            self.retrieval_test_python, self._evaluate_script,
            "--artifact-dir", artifact_dir,
            "--queries", queries_path,
            "--predictions", predictions_path,
            "-k", str(self.k),
            "--output", output_dir,
        ]
        # corpus is split-specific and comes from the data inst at runtime.
        if corpus_path:
            cmd.extend(["--corpus", corpus_path])
        return cmd

    def _subprocess_env(self) -> dict:
        env = os.environ.copy()
        src_dir = os.path.join(self.retrieval_test_dir, "src")
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = src_dir + (os.pathsep + existing if existing else "")
        return env

    @staticmethod
    def _read_details(details_path: str) -> dict[str, dict]:
        """Read details.jsonl -> {query_id: detail} (each has score/ndcg/recall/reason)."""
        details: dict[str, dict] = {}
        if not os.path.isfile(details_path):
            logger.warning("details.jsonl not found at %s", details_path)
            return details
        with open(details_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                details[str(rec["query_id"])] = rec
        return details

    async def evaluate_batch(
        self,
        data_list: list[DataInst],
        system_results: list[SystemResult],
        *,
        eval_output_dir: str,
        predictions_path: str,
        artifact_dir: str,
        **kwargs,
    ) -> list[EvaluationResult]:
        """Score the batch by running evaluate.py over reused predictions.

        Keyword args (supplied by the optimizer):
            eval_output_dir: where evaluate.py writes eval.json + details.jsonl.
            predictions_path: predictions.jsonl from the system run (reused, not re-run).
            artifact_dir: the candidate's artifact dir (passed to --artifact-dir for traceability).

        The corpus is split-specific and is NOT fixed at construction — it is
        read at runtime from each data inst's ``corpus_path`` (train queries ->
        train corpus, val -> val corpus).
        """
        if len(data_list) != len(system_results):
            raise ValueError(
                f"data_list length ({len(data_list)}) != "
                f"system_results length ({len(system_results)})"
            )
        if not data_list:
            return []

        # If generate.py failed to produce predictions.jsonl (subprocess crashed
        # before the write stage), don't call evaluate.py — it would FileNotFoundError.
        # Return 0-score results with a clear reason so the trajectory explains it.
        if not os.path.isfile(predictions_path):
            logger.error(
                "predictions.jsonl not found at %s — generate.py may have failed; "
                "skipping evaluate.py", predictions_path,
            )
            return [
                EvaluationResult(
                    data_id=d.id,
                    metric_name=f"RetrievalScore@{self.k}",
                    score=0.0,
                    reason="predictions file missing (generate.py failed to produce output)",
                )
                for d in data_list
            ]

        os.makedirs(eval_output_dir, exist_ok=True)
        queries_path = os.path.join(eval_output_dir, "queries.jsonl")
        self._write_queries(data_list, queries_path)

        effective_corpus = getattr(data_list[0], "corpus_path", "")
        cmd = self._build_cmd(artifact_dir, queries_path, predictions_path, eval_output_dir, effective_corpus)
        logger.info(
            "Running evaluate.py: %d queries, k=%d, predictions=%s, corpus=%s",
            len(data_list), self.k, predictions_path, effective_corpus or "(none)",
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
            logger.error("evaluate.py timed out after %.0fs", self.subprocess_timeout)
            return [
                EvaluationResult(
                    data_id=d.id, metric_name=f"RetrievalScore@{self.k}",
                    score=0.0, reason="error: evaluate.py timed out",
                )
                for d in data_list
            ]
        elapsed = time.monotonic() - t0

        if process.returncode != 0:
            logger.error(
                "evaluate.py failed (exit %d) in %.1fs:\nstdout: %s\nstderr: %s",
                process.returncode, elapsed,
                stdout.decode("utf-8", errors="replace")[:2000],
                stderr.decode("utf-8", errors="replace")[:2000],
            )
        else:
            logger.info("evaluate.py completed in %.1fs", elapsed)

        details = self._read_details(os.path.join(eval_output_dir, "details.jsonl"))
        results: list[EvaluationResult] = []
        for d in data_list:
            det = details.get(d.id, {})
            ndcg = float(det.get("ndcg_at_k", 0.0))
            recall = float(det.get("recall_at_k", 0.0))
            score = self.ndcg_weight * ndcg + self.recall_weight * recall
            reason = det.get("reason", "no detail record (evaluate.py produced nothing)")
            results.append(EvaluationResult(
                data_id=d.id,
                metric_name=f"RetrievalScore@{self.k}",
                score=score,
                reason=reason,
            ))

        avg = sum(r.score for r in results) / len(results) if results else 0.0
        logger.info(
            "eval batch: %d queries, mean score@%d=%.4f (%.1f*nDCG + %.1f*Recall)",
            len(results), self.k, avg, self.ndcg_weight, self.recall_weight,
        )
        return results
