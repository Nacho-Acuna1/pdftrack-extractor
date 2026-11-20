"""Orchestrates PDF extraction with Zero-Copy IPC and a ProcessPoolExecutor."""

import asyncio
import logging
from concurrent.futures import ProcessPoolExecutor
from multiprocessing.shared_memory import SharedMemory

from extractor.services.worker import extract_pdf_from_shm

logger = logging.getLogger("extractor.services.extractor")


class ExtractionService:
    """Manages a pool of worker processes for PDF text extraction.

    PDF bytes are placed into a ``SharedMemory`` segment so the worker can
    access them directly by name, avoiding pickle serialisation of the
    (potentially large) payload.
    """

    def __init__(self, max_workers: int, timeout: float) -> None:
        self._max_workers = max_workers
        self._timeout = timeout
        self._pool: ProcessPoolExecutor | None = None

    # -- lifecycle ------------------------------------------------------------

    def start(self) -> None:
        """Create the process pool (called during app lifespan startup)."""
        self._pool = ProcessPoolExecutor(max_workers=self._max_workers)
        logger.info("ProcessPoolExecutor started with %d workers", self._max_workers)

    def stop(self) -> None:
        """Shut down the process pool (called during app lifespan shutdown)."""
        if self._pool is not None:
            self._pool.shutdown(wait=True, cancel_futures=True)
            self._pool = None
            logger.info("ProcessPoolExecutor stopped")

    @property
    def is_ready(self) -> bool:
        """``True`` when the pool is alive and accepting work."""
        return self._pool is not None

    # -- extraction -----------------------------------------------------------

    async def extract(self, pdf_data: bytes) -> dict:
        """Extract Markdown text from raw *pdf_data* via a pool worker.

        Raises:
            RuntimeError: If the service has not been started.
            asyncio.TimeoutError: If extraction exceeds the configured timeout.
        """
        if self._pool is None:
            raise RuntimeError("ExtractionService is not started")

        size = len(pdf_data)
        shm = SharedMemory(create=True, size=size)
        try:
            shm.buf[:size] = pdf_data

            loop = asyncio.get_running_loop()
            future = loop.run_in_executor(
                self._pool,
                extract_pdf_from_shm,
                shm.name,
                size,
            )
            return await asyncio.wait_for(future, timeout=self._timeout)
        except asyncio.TimeoutError:
            logger.error("Extraction timed out after %.1f s", self._timeout)
            raise
        finally:
            # Cleanup is shielded so that a cancellation of the parent
            # coroutine does not leak the shared-memory segment.
            async def _cleanup_shm() -> None:
                try:
                    try:
                        shm.buf.release()
                    except Exception:
                        pass
                    shm.close()
                    shm.unlink()
                except Exception:
                    logger.warning(
                        "SharedMemory cleanup failed for %s",
                        shm.name,
                        exc_info=True,
                    )

            try:
                await asyncio.shield(_cleanup_shm())
            except asyncio.CancelledError:
                pass
