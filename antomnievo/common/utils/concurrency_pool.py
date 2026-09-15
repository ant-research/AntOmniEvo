"""Async concurrency slot pool.

Unlike ``asyncio.Semaphore``, supports acquiring/releasing N slots atomically,
so callers can reserve a variable-sized chunk of a shared budget.
"""
from __future__ import annotations

import asyncio


class ConcurrencyPool:
    """Shared async slot pool. Acquire/release N slots atomically."""

    def __init__(self, total: int):
        if total <= 0:
            raise ValueError(f"total must be > 0, got {total}")
        self._total = total
        self._available = total
        self._cond = asyncio.Condition()

    @property
    def total(self) -> int:
        return self._total

    @property
    def available(self) -> int:
        return self._available

    async def set_total(self, total: int) -> None:
        if total <= 0:
            raise ValueError(f"total must be > 0, got {total}")
        async with self._cond:
            delta = total - self._total
            self._total = total
            self._available += delta
            if delta > 0:
                self._cond.notify_all()

    async def acquire(self, n: int) -> None:
        if n <= 0:
            return
        if n > self._total:
            raise ValueError(f"requested {n} slots exceeds total {self._total}")
        async with self._cond:
            while self._available < n:
                await self._cond.wait()
            self._available -= n

    async def release(self, n: int) -> None:
        if n <= 0:
            return
        async with self._cond:
            self._available = min(self._total, self._available + n)
            self._cond.notify_all()

    def slot(self, n: int) -> _PoolSlot:
        """Async context manager that holds *n* slots for its scope."""
        return _PoolSlot(self, n)


class _PoolSlot:
    def __init__(self, pool: ConcurrencyPool, n: int):
        self._pool = pool
        self._n = n

    async def __aenter__(self) -> ConcurrencyPool:
        await self._pool.acquire(self._n)
        return self._pool

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self._pool.release(self._n)
