from __future__ import annotations

from typing import NamedTuple

from pydantic import BaseModel, Field


class BudgetUsage(NamedTuple):
    """The runtime usage figures a ``Budget`` checks against.

    Callers (the optimizer) assemble this from :class:`OptimizationStatistics` so
    the ``Budget`` model does not have to depend on the whole statistics object —
    it only needs the five scalar figures it actually compares against.
    """

    current_iteration: int
    current_rollouts: int
    current_system_runs: int
    used_tokens: int
    elapsed_seconds: float


class Budget(BaseModel):
    """Hard caps for an optimization run.

    Any field left ``None`` means unlimited on that axis. Stopping policy: the
    optimizer opens no new slots once ANY set limit is reached; in-flight slots
    drain to completion (see ``Optimizer.optimize`` main loop).

    - ``max_iterations``: cap on total slot occupations.
    - ``max_rollouts``: cap on total rollouts, i.e. the cumulative number of
      TRAINING data instances the ``System`` has executed. Counted in
      :meth:`Optimizer._run_and_evaluate_wrapper` as ``len(data_list)``
      per call, but only for training-split calls (parent batch, child batch,
      each mara-chain child run); validation runs and the root baseline
      run on the val split and are excluded. Use ``max_system_runs`` to cap
      all splits.
    - ``max_system_runs``: cap on total system runs, i.e. the cumulative number of
      data instances the ``System`` has executed across ALL splits. Counted in
      :meth:`Optimizer._run_and_evaluate_wrapper` as ``len(data_list)``
      per call, so every invocation (parent batch, child batch, each validation
      run, each mara-chain child run) contributes its instance count.
    - ``max_tokens``: cap on cumulative input + output tokens across all phases
      (proposer + system + eval; cache-creation/cache-read tokens excluded).
    - ``max_elapsed_seconds``: wall-clock cap since run start.
    """

    max_iterations: int | None = Field(default=None, description="Cap on total slot occupations")
    max_rollouts: int | None = Field(default=None, description="Cap on total rollouts (cumulative TRAINING data instances executed by System; val/baseline excluded)")
    max_system_runs: int | None = Field(default=None, description="Cap on total system runs (cumulative data instances executed by System across ALL splits)")
    max_tokens: int | None = Field(
        default=None,
        description="Cap on cumulative input+output tokens (proposer+system+eval)",
    )
    max_elapsed_seconds: float | None = Field(
        default=None, description="Wall-clock cap in seconds since run start"
    )

    def is_exhausted(self, usage: BudgetUsage) -> str | None:
        """Return a description of the first exhausted limit, or ``None`` if none hit.

        The returned string is suitable for a ``logger.info`` line (e.g.
        ``"max_iterations(5/1000)"``, ``"max_rollouts(12/100)"``,
        ``"max_system_runs(48/1000)"``, ``"max_tokens(used=12345/10000)"``,
        ``"max_elapsed_seconds(612.3s/600s)"``).
        Checks iteration → rollouts → system_runs → tokens → elapsed in that order.
        """
        if self.max_iterations is not None and usage.current_iteration >= self.max_iterations:
            return f"max_iterations({usage.current_iteration}/{self.max_iterations})"

        if self.max_rollouts is not None and usage.current_rollouts >= self.max_rollouts:
            return f"max_rollouts({usage.current_rollouts}/{self.max_rollouts})"

        if self.max_system_runs is not None and usage.current_system_runs >= self.max_system_runs:
            return f"max_system_runs({usage.current_system_runs}/{self.max_system_runs})"

        if self.max_tokens is not None and usage.used_tokens >= self.max_tokens:
            return f"max_tokens(used={usage.used_tokens}/{self.max_tokens})"

        if self.max_elapsed_seconds is not None and usage.elapsed_seconds >= self.max_elapsed_seconds:
            return f"max_elapsed_seconds({usage.elapsed_seconds:.1f}s/{self.max_elapsed_seconds}s)"

        return None
