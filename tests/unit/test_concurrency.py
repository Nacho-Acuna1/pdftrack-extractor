"""Unit tests for the BackpressureController."""

import asyncio

import pytest

from extractor.core.concurrency import BackpressureController


class TestBackpressureController:
    """Verifies semaphore-based admission control."""

    @pytest.mark.asyncio
    async def test_acquire_succeeds_when_slots_available(self) -> None:
        bp = BackpressureController(max_slots=2, wait_timeout=0)
        assert await bp.try_acquire() is True
        bp.release()

    @pytest.mark.asyncio
    async def test_acquire_fails_when_no_slots(self) -> None:
        bp = BackpressureController(max_slots=1, wait_timeout=0)
        assert await bp.try_acquire() is True
        assert await bp.try_acquire() is False
        bp.release()

    @pytest.mark.asyncio
    async def test_release_frees_slot(self) -> None:
        bp = BackpressureController(max_slots=1, wait_timeout=0)
        assert await bp.try_acquire() is True
        bp.release()
        assert await bp.try_acquire() is True
        bp.release()

    @pytest.mark.asyncio
    async def test_acquire_with_wait_timeout_succeeds(self) -> None:
        bp = BackpressureController(max_slots=1, wait_timeout=0.5)
        assert await bp.try_acquire() is True

        async def release_later() -> None:
            await asyncio.sleep(0.1)
            bp.release()

        task = asyncio.create_task(release_later())
        assert await bp.try_acquire() is True
        bp.release()
        await task

    @pytest.mark.asyncio
    async def test_acquire_with_wait_timeout_fails(self) -> None:
        bp = BackpressureController(max_slots=1, wait_timeout=0.1)
        assert await bp.try_acquire() is True
        assert await bp.try_acquire() is False
        bp.release()

    @pytest.mark.asyncio
    async def test_multiple_slots(self) -> None:
        bp = BackpressureController(max_slots=3, wait_timeout=0)
        assert await bp.try_acquire() is True
        assert await bp.try_acquire() is True
        assert await bp.try_acquire() is True
        assert await bp.try_acquire() is False
        bp.release()
        bp.release()
        bp.release()
