"""Health-check endpoints."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel


class HealthStatus(BaseModel):
    """Health status response payload."""

    status: str


router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", response_model=HealthStatus)
async def liveness() -> HealthStatus:
    """Liveness probe — always responds if the process is up."""
    return HealthStatus(status="alive")


@router.get(
    "/ready",
    response_model=HealthStatus,
    responses={503: {"description": "ProcessPool is not ready"}},
)
async def readiness(request: Request):
    """Readiness probe — verifies the ProcessPool is operational."""
    service = request.app.state.extraction_service
    if service.is_ready:
        return HealthStatus(status="ready")
    return JSONResponse(status_code=503, content={"status": "not ready"})
