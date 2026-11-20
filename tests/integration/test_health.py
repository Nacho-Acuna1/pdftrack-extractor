"""Integration tests for health-check and documentation endpoints."""

from httpx import AsyncClient
import pytest

from extractor.main import app


class TestHealthLive:
    @pytest.mark.asyncio
    async def test_liveness_returns_alive(self, client: AsyncClient) -> None:
        response = await client.get("/health/live")
        assert response.status_code == 200
        assert response.json() == {"status": "alive"}


class TestHealthReady:
    @pytest.mark.asyncio
    async def test_readiness_returns_ready(self, client: AsyncClient) -> None:
        response = await client.get("/health/ready")
        assert response.status_code == 200
        assert response.json() == {"status": "ready"}

    @pytest.mark.asyncio
    async def test_readiness_fails_when_service_not_ready(
        self, client: AsyncClient
    ) -> None:
        service = app.state.extraction_service
        saved_pool = service._pool
        service._pool = None
        try:
            response = await client.get("/health/ready")
            assert response.status_code == 503
            assert response.json() == {"status": "not ready"}
        finally:
            service._pool = saved_pool


class TestDocumentation:
    @pytest.mark.asyncio
    async def test_docs_returns_200(self, client: AsyncClient) -> None:
        response = await client.get("/docs")
        assert response.status_code == 200
        assert "swagger" in response.text.lower() or "html" in response.text.lower()
