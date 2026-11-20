"""Integration tests for POST /extract."""

import asyncio

from httpx import AsyncClient
import pymupdf
import pytest

from extractor.main import app


def _make_pdf(text: str = "Hello World", pages: int = 1) -> bytes:
    doc = pymupdf.open()
    for i in range(pages):
        page = doc.new_page()
        tw = pymupdf.TextWriter(page.rect)
        tw.append((72, 72), f"{text} page {i + 1}")
        tw.write_text(page)
    data = doc.tobytes()
    doc.close()
    return data


# ── Multipart upload ───────────────────────────────────────────────────────


class TestExtractMultipart:
    @pytest.mark.asyncio
    async def test_valid_pdf_returns_200(self, client: AsyncClient) -> None:
        pdf = _make_pdf("Test content")
        response = await client.post(
            "/extract",
            files={"file": ("test.pdf", pdf, "application/pdf")},
        )
        assert response.status_code == 200
        body = response.json()
        assert "content" in body
        assert "page_count" in body
        assert body["page_count"] == 1
        assert "## Página 1" in body["content"]
        assert "Test content" in body["content"]

    @pytest.mark.asyncio
    async def test_multi_page_pdf(self, client: AsyncClient) -> None:
        pdf = _make_pdf("Content", pages=3)
        response = await client.post(
            "/extract",
            files={"file": ("test.pdf", pdf, "application/pdf")},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["page_count"] == 3
        assert "## Página 1" in body["content"]
        assert "## Página 2" in body["content"]
        assert "## Página 3" in body["content"]


# ── Binary body upload ─────────────────────────────────────────────────────


class TestExtractBinaryBody:
    @pytest.mark.asyncio
    async def test_valid_pdf_via_binary_returns_200(
        self, client: AsyncClient
    ) -> None:
        pdf = _make_pdf("Binary upload test")
        response = await client.post(
            "/extract",
            content=pdf,
            headers={"content-type": "application/octet-stream"},
        )
        assert response.status_code == 200
        body = response.json()
        assert "content" in body
        assert "page_count" in body
        assert body["page_count"] == 1
        assert "## Página 1" in body["content"]
        assert "Binary upload test" in body["content"]


# ── Validation ──────────────────────────────────────────────────────────────


class TestExtractValidation:
    @pytest.mark.asyncio
    async def test_empty_file_returns_400(self, client: AsyncClient) -> None:
        response = await client.post(
            "/extract",
            files={"file": ("empty.pdf", b"", "application/pdf")},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_empty_binary_returns_400(self, client: AsyncClient) -> None:
        response = await client.post(
            "/extract",
            content=b"",
            headers={"content-type": "application/octet-stream"},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_not_pdf_returns_415(self, client: AsyncClient) -> None:
        response = await client.post(
            "/extract",
            files={"file": ("test.txt", b"This is not a PDF", "text/plain")},
        )
        assert response.status_code == 415

    @pytest.mark.asyncio
    async def test_oversized_pdf_returns_413(self, client: AsyncClient) -> None:
        # MAX_PDF_SIZE_MB is set to 1 in conftest.py
        oversized = b"%PDF" + b"\x00" * (2 * 1024 * 1024)
        response = await client.post(
            "/extract",
            content=oversized,
            headers={"content-type": "application/octet-stream"},
        )
        assert response.status_code == 413


# ── Backpressure / saturation ──────────────────────────────────────────────


class TestExtractSaturation:
    @pytest.mark.asyncio
    async def test_saturation_returns_503(self, client: AsyncClient) -> None:
        """With WORKERS=1 + QUEUE=1 → semaphore capacity = 2.

        Sending 3 concurrent requests (with a patched slow extractor)
        guarantees at least one receives 503 with Retry-After: 1.
        """
        pdf = _make_pdf("Saturation test")
        service = app.state.extraction_service
        original_extract = service.extract

        async def slow_extract(pdf_data: bytes) -> dict:
            await asyncio.sleep(0.5)
            return {"content": "## Página 1\n\nmock", "page_count": 1}

        service.extract = slow_extract  # type: ignore[method-assign]
        try:
            coros = [
                client.post(
                    "/extract",
                    files={"file": ("test.pdf", pdf, "application/pdf")},
                )
                for _ in range(3)
            ]
            responses = await asyncio.gather(*coros)
            status_codes = [r.status_code for r in responses]
            assert 503 in status_codes

            sat_response = next(r for r in responses if r.status_code == 503)
            assert sat_response.headers.get("retry-after") == "1"
        finally:
            service.extract = original_extract  # type: ignore[method-assign]


# ── Timeout ────────────────────────────────────────────────────────────────


class TestExtractTimeout:
    @pytest.mark.asyncio
    async def test_timeout_returns_504(self, client: AsyncClient) -> None:
        pdf = _make_pdf("Timeout test")
        service = app.state.extraction_service
        original_extract = service.extract

        async def timeout_extract(pdf_data: bytes) -> dict:
            raise asyncio.TimeoutError()

        service.extract = timeout_extract  # type: ignore[method-assign]
        try:
            response = await client.post(
                "/extract",
                files={"file": ("test.pdf", pdf, "application/pdf")},
            )
            assert response.status_code == 504
            assert response.json()["detail"] == "Extraction timed out"
        finally:
            service.extract = original_extract  # type: ignore[method-assign]
