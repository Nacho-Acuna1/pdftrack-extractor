"""FastAPI application, lifespan management, and middleware wiring."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from extractor.config import settings
from extractor.core.concurrency import BackpressureController
from extractor.core.logging import RequestLoggingMiddleware, setup_logging
from extractor.routes import extract, health
from extractor.services.extractor import ExtractionService

# ── Singleton services (created once, started/stopped by lifespan) ──────────

extraction_service = ExtractionService(
    max_workers=settings.EXTRACTION_WORKERS,
    timeout=settings.EXTRACTION_TIMEOUT_SECONDS,
)

backpressure = BackpressureController(
    max_slots=settings.EXTRACTION_WORKERS + settings.EXTRACTION_QUEUE_SIZE,
    wait_timeout=settings.QUEUE_WAIT_TIMEOUT_SECONDS,
)


# ── Lifespan (Factor IX — graceful startup / shutdown) ──────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    setup_logging(settings.LOG_LEVEL)
    extraction_service.start()
    app.state.extraction_service = extraction_service
    app.state.backpressure = backpressure
    yield
    extraction_service.stop()


# ── Application ─────────────────────────────────────────────────────────────

app = FastAPI(
    title="PDFtrack Extractor",
    description="Stateless PDF to Markdown extraction microservice",
    version="1.0.0",
    lifespan=lifespan,
)

app.state.extraction_service = extraction_service
app.state.backpressure = backpressure

app.add_middleware(RequestLoggingMiddleware)
app.include_router(health.router)
app.include_router(extract.router)
