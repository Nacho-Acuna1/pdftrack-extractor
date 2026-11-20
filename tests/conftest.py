"""Shared test fixtures and environment configuration.

Environment variables are set **before** any application module is imported
so that ``pydantic-settings`` picks up test-friendly defaults.
"""

from collections.abc import AsyncGenerator
import os

os.environ.setdefault("EXTRACTION_WORKERS", "1")
os.environ.setdefault("EXTRACTION_QUEUE_SIZE", "1")
os.environ.setdefault("QUEUE_WAIT_TIMEOUT_SECONDS", "0")
os.environ.setdefault("EXTRACTION_TIMEOUT_SECONDS", "30")
os.environ.setdefault("MAX_PDF_SIZE_MB", "1")
os.environ.setdefault("LOG_LEVEL", "WARNING")

from httpx import ASGITransport, AsyncClient
import pymupdf  # noqa: E402
import pytest  # noqa: E402

from extractor.main import app, lifespan  # noqa: E402


@pytest.fixture
def sample_pdf_bytes() -> bytes:
    """Minimal single-page PDF with known text content."""
    doc = pymupdf.open()
    page = doc.new_page()
    tw = pymupdf.TextWriter(page.rect)
    tw.append((72, 72), "Hello World from PDFtrack")
    tw.write_text(page)
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def multi_page_pdf_bytes() -> bytes:
    """Three-page PDF with distinct per-page content."""
    doc = pymupdf.open()
    for i in range(1, 4):
        page = doc.new_page()
        tw = pymupdf.TextWriter(page.rect)
        tw.append((72, 72), f"Content of page {i}")
        tw.write_text(page)
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Async test client running inside the app lifespan."""
    async with lifespan(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
