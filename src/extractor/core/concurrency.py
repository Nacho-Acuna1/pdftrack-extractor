"""Deterministic backpressure via ``asyncio.Semaphore``.

When all slots are occupied and the wait timeout expires (or is zero),
the caller is told immediately that there is no capacity so the route
can return **503 Service Unavailable** without consuming request memory.
"""

import asyncio


class BackpressureController:
    """Semaphore-based admission control for the extraction pipeline."""

    def __init__(self, max_slots: int, wait_timeout: float) -> None:
        self._semaphore = asyncio.Semaphore(max_slots)
        self._wait_timeout = wait_timeout
        self._max_slots = max_slots

    async def try_acquire(self) -> bool:
        """Try to reserve a slot.

        Returns ``True`` if a slot was acquired, ``False`` otherwise.
        When *wait_timeout* ≤ 0 the check is non-blocking.
        """
        if self._wait_timeout <= 0:
            # Fast path — no waiting.  ``_value`` is a stable CPython
            # attribute and reading it in the same tick is race-free.
            if self._semaphore._value <= 0:  # noqa: SLF001
                return False
            await self._semaphore.acquire()
            return True

        try:
            await asyncio.wait_for(
                self._semaphore.acquire(),
                timeout=self._wait_timeout,
            )
            return True
        except asyncio.TimeoutError:
            return False

    def release(self) -> None:
        """Return a previously acquired slot to the pool."""
        self._semaphore.release()

    @property
    def is_healthy(self) -> bool:
        """Liveness probe for the controller itself."""
        return self._semaphore is not None
