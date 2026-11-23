"""POST /extract — PDF to Markdown extraction endpoint."""

import asyncio
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from extractor.config import settings

logger = logging.getLogger("extractor.routes.extract")

router = APIRouter()

PDF_MAGIC = b"%PDF"
MAX_SIZE_BYTES: int = settings.MAX_PDF_SIZE_MB * 1024 * 1024


class ExtractResponse(BaseModel):
    """Extraction response payload."""

    content: str
    page_count: int


@router.post(
    "/extract",
    response_model=ExtractResponse,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "file": {
                                "type": "string",
                                "format": "binary",
                                "description": "Archivo PDF a extraer a Markdown",
                            }
                        },
                        "required": ["file"],
                    }
                },
                "application/pdf": {
                    "schema": {
                        "type": "string",
                        "format": "binary",
                        "description": "Payload binario directo del PDF",
                    }
                },
            },
        }
    },
    responses={
        200: {
            "description": "Successful extraction",
            "model": ExtractResponse,
        },
        400: {"description": "Empty file or missing form field"},
        413: {"description": "File exceeds maximum size"},
        415: {"description": "File is not a valid PDF"},
        503: {"description": "Service saturated, backpressure applied"},
        504: {"description": "Extraction timed out"},
        422: {"description": "Failed to extract PDF content"},
    },
)
async def extract_pdf(request: Request):
    """Accept a PDF (multipart *or* raw binary) and return extracted Markdown.

    The backpressure semaphore is acquired **before** the request body is
    read so that memory is not consumed when the service is saturated.
    """
    backpressure = request.app.state.backpressure

    # ── 1. Backpressure gate ────────────────────────────────────────────
    acquired = await backpressure.try_acquire()
    if not acquired:
        return JSONResponse(
            status_code=503,
            content={"detail": "Service saturated, try again later"},
            headers={"Retry-After": "1"},
        )

    try:
        # ── 2. Read payload ─────────────────────────────────────────────
        content_type = request.headers.get("content-type", "")

        if "multipart/form-data" in content_type:
            form = await request.form()
            upload = form.get("file")
            if upload is None:
                return JSONResponse(
                    status_code=400,
                    content={"detail": "Missing 'file' field in multipart form"},
                )
            pdf_data: bytes = await upload.read()  # type: ignore[union-attr]
            await form.close()
        else:
            pdf_data = await request.body()

        # ── 3. Validate ────────────────────────────────────────────────
        if not pdf_data:
            return JSONResponse(
                status_code=400,
                content={"detail": "Empty file"},
            )

        if len(pdf_data) > MAX_SIZE_BYTES:
            return JSONResponse(
                status_code=413,
                content={
                    "detail": f"File exceeds maximum size of {settings.MAX_PDF_SIZE_MB} MB",
                },
            )

        if not pdf_data[:4].startswith(PDF_MAGIC):
            return JSONResponse(
                status_code=415,
                content={"detail": "File is not a valid PDF"},
            )

        # ── 4. Extract ─────────────────────────────────────────────────
        service = request.app.state.extraction_service
        try:
            result = await service.extract(pdf_data)
        except asyncio.TimeoutError:
            return JSONResponse(
                status_code=504,
                content={"detail": "Extraction timed out"},
            )
        except Exception:
            logger.exception("Extraction failed")
            return JSONResponse(
                status_code=422,
                content={"detail": "Failed to extract PDF content"},
            )

        return result

    finally:
        backpressure.release()
