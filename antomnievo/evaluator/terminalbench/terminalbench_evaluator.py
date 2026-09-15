from __future__ import annotations

import json
import logging
import os
import re

from antomnievo.dataset.terminalbench.terminalbench_data_inst import TerminalBenchDataInst
from antomnievo.interface.data_inst import DataInst
from antomnievo.interface.evaluator import Evaluator
from antomnievo.model.evaluation_result import EvaluationResult
from antomnievo.model.system_result import SystemResult

logger = logging.getLogger(__name__)

_TERMINALBENCH_SCORING_CRITERIA = """\
Terminal-Bench pass rate: average pass@1 across all Harbor trial attempts for the same task.

- Each trial's Harbor ``result.json`` contains a ``verifier_result.rewards`` \
dict — a mapping from checker name to reward (float or int). A trial counts \
as PASS iff every reward in the dict is >= 1 (Harbor's own pass definition, \
mirroring ``harbor.utils.pass_at_k``).
- A trial with ``verifier_result == null`` (agent errored before verifier ran) \
counts as FAIL (score 0).
- Final score = mean of {1.0 if pass else 0.0} across all trials for the task.
- No trials found → 0.0 with reason "No data found".

The reason string encodes each trial's outcome (``trial_name=score``) plus the \
final mean, for downstream analyzer prompts.
"""


def _parse_verifier_reason(stdout_path: str) -> str | None:
    """Extract a concise failure reason from a verifier's ``test-stdout.txt``.

    The default ``reason`` only carries ``rewards={'reward': 0.0}``, which tells
    you *that* a trial failed but not *why*. This parses the verifier's pytest
    output (or a non-pytest verify.sh's failure markers) to surface the failing
    test name plus the real assertion/cause.

    Order of preference:
      1. pytest ``short test summary info`` lines (``PASSED``/``FAILED <file>::<test>``)
      2. the real assertion message from the ``FAILURES`` section (``E   ...`` line;
         pytest's summary truncates it as ``AssertionError: ...``)
      3. a free-form ``❌ TEST FAILED: <reason>`` / ``HTTP <code>`` line from an
         inner verify.sh printed to captured stdout

    Returns ``None`` if nothing parseable is found (e.g. stdout missing).
    """
    if not os.path.isfile(stdout_path):
        return None
    try:
        with open(stdout_path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return None

    parts: list[str] = []

    # 1) pytest short summary: PASSED/FAILED/ERROR test-name lines
    m = re.search(r"=+\s*short test summary info\s*=+\n((?:.+\n?){0,40})", text)
    if m:
        raw = [line.rstrip() for line in m.group(1).splitlines() if line.strip()]
        stat = None
        if raw and re.match(r"=+\s*\d+ (failed|passed|error)", raw[-1]):
            stat = raw[-1].strip("= ").strip()
            raw = raw[:-1]
        # Drop the truncated 'AssertionError: ...' tail — the real message comes
        # from the FAILURES section below.
        summary_lines = [re.sub(r"\s*-\s*AssertionError:\s*\.\.\.?\s*$", "", line) for line in raw]
        if summary_lines:
            parts.append(" | ".join(summary_lines))
        if stat:
            parts.append(stat)

    # 2) First non-trivial assertion message from the FAILURES section
    if "FAILURES" in text or "short test summary info" in text:
        for line in re.findall(r"^E\s+(.+)$", text, re.M):
            line = line.strip()
            if not line or "assert False" in line:
                continue
            parts.append("assert: " + line[:200])
            break

    # 3) Inner verify.sh failure markers (e.g. when pytest wraps a shell script
    #    that prints the real cause). Only strict "TEST FAILED: <reason>" /
    #    "❌ <reason>: <detail>" conclusion lines, not pytest's own code lines.
    marks: list[str] = []
    for line in text.splitlines():
        ls = line.strip()
        if re.match(r"^(TEST FAILED|❌|✗):\s*.+", ls):
            marks.append(ls)
        if len(marks) >= 3:
            break
    if marks:
        parts.append("detail: " + " | ".join(marks))

    return " | ".join(parts) if parts else None


def _find_trial_dirs(job_dir: str, data_id: str) -> list[str]:
    """Same convention as TerminalBenchSystem: ``<task_id>__<hash>`` or exact match."""
    if not os.path.isdir(job_dir):
        return []

    prefix = f"{data_id}__"
    results: list[str] = []
    for entry in os.listdir(job_dir):
        full = os.path.join(job_dir, entry)
        if not os.path.isdir(full):
            continue
        if entry.startswith(prefix) or entry == data_id:
            results.append(full)
    return sorted(results)


def _read_trial_pass(trial_dir: str) -> tuple[float | None, str]:
    """Read a single trial's pass/fail from ``result.json``.

    Returns ``(score, reason)`` where score is 1.0 (pass), 0.0 (fail), or None
    (no result). A trial passes iff every reward in
    ``verifier_result.rewards`` is >= 1.
    """
    result_path = os.path.join(trial_dir, "result.json")
    if not os.path.isfile(result_path):
        return (None, "result.json missing")
    try:
        with open(result_path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        return (None, f"result.json unreadable: {e}")

    exc_info = data.get("exception_info")
    verifier_result = data.get("verifier_result")

    if not verifier_result:
        exc_type = (exc_info or {}).get("exception_type") if isinstance(exc_info, dict) else None
        reason = f"verifier did not run (exception={exc_type})" if exc_type else "verifier did not run"
        return (0.0, reason)

    rewards = verifier_result.get("rewards")
    if not isinstance(rewards, dict) or not rewards:
        return (0.0, "verifier_result.rewards empty")

    passed = all(v >= 1 for v in rewards.values() if isinstance(v, (int, float)))
    reason = f"rewards={rewards}"
    if not passed:
        # Surface *why* it failed by parsing the verifier's pytest/verify.sh
        # stdout (e.g. "FAILED ...::test_clean_html_unchanged | assert:
        # AssertionError: Filter modified 5 clean HTML files..."). The raw
        # rewards above only say it failed, not the cause.
        detail = _parse_verifier_reason(os.path.join(trial_dir, "verifier", "test-stdout.txt"))
        if detail:
            reason = f"{reason} | {detail}"
    return (1.0 if passed else 0.0, reason)


def _compute_pass_at_1(job_dir: str, data_id: str) -> tuple[float, str]:
    trial_dirs = _find_trial_dirs(job_dir, data_id)
    if not trial_dirs:
        return (0.0, "No data found")

    scores: list[float] = []
    trial_summaries: list[str] = []
    for trial_dir in trial_dirs:
        name = os.path.basename(trial_dir)
        score, reason = _read_trial_pass(trial_dir)
        if score is None:
            scores.append(0.0)
            trial_summaries.append(f"{name}=0.0(no result)")
            continue
        scores.append(score)
        summary = f"{name}={score:.1f}"
        if reason:
            summary += f"({reason})"
        trial_summaries.append(summary)

    if not scores:
        return (0.0, "No verifier results")
    avg = sum(scores) / len(scores)
    return (avg, "avg(" + ", ".join(trial_summaries) + f")={avg:.2f}")


class TerminalBenchEvaluator(Evaluator):
    """Evaluator for Terminal-Bench 2 tasks — reads Harbor ``verifier_result.rewards``.

    Trial output directory layout is the same as TerminalBenchSystem produces
    (``<output_dir>/<job_name>/<task_id>__<suffix>/result.json``).
    """

    def __init__(self):
        super().__init__()

    def scoring_criteria(self) -> str:
        return _TERMINALBENCH_SCORING_CRITERIA

    async def _evaluate(
        self,
        data_inst: DataInst,
        _: SystemResult,
    ) -> EvaluationResult:
        pass  # Not used; evaluate_batch is the real entry point.

    async def evaluate_batch(
        self,
        data_list: list[DataInst],
        system_results: list[SystemResult],
        *,
        job_name: str,
        output_dir: str,
        **kwargs,
    ) -> list[EvaluationResult]:
        if len(data_list) != len(system_results):
            raise ValueError(
                f"data_list length ({len(data_list)}) != "
                f"system_results length ({len(system_results)})"
            )

        job_dir = os.path.join(output_dir, job_name)

        results: list[EvaluationResult] = []
        for data_inst in data_list:
            assert isinstance(data_inst, TerminalBenchDataInst)
            score, reason = _compute_pass_at_1(job_dir, data_inst.id)
            results.append(EvaluationResult(
                data_id=data_inst.id,
                metric_name="TerminalBenchPass",
                score=score,
                reason=reason,
            ))
        return results
