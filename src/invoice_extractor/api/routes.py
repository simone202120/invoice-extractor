"""Extraction endpoints: single document (file or JSON text), concurrent batch and health."""

import asyncio
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from pydantic import ValidationError
from starlette.datastructures import UploadFile as FormFile

from invoice_extractor.api.dependencies import get_extractor
from invoice_extractor.api.schemas import BatchItem, ExtractResponse, Health, TextRequest
from invoice_extractor.config import Settings, get_settings
from invoice_extractor.core.errors import InvoiceExtractorError
from invoice_extractor.core.extraction import Extractor, extract_invoice
from invoice_extractor.core.loader import load_document
from invoice_extractor.infra.tracing import trace_url, tracing_config

logger = logging.getLogger(__name__)
router = APIRouter()

SettingsDep = Annotated[Settings, Depends(get_settings)]
ExtractorDep = Annotated[Extractor, Depends(get_extractor)]

EXTRACT_BODY: dict[str, Any] = {
    "requestBody": {
        "required": True,
        "content": {
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "properties": {"file": {"type": "string", "format": "binary"}},
                    "required": ["file"],
                }
            },
            "application/json": {"schema": TextRequest.model_json_schema()},
        },
    }
}


async def _process(
    filename: str, content: bytes, settings: Settings, extractor: Extractor
) -> ExtractResponse:
    text = await asyncio.to_thread(
        load_document,
        content,
        filename,
        max_bytes=settings.max_upload_bytes,
        max_chars=settings.max_text_chars,
    )
    config = tracing_config(settings, filename)
    result = await extract_invoice(text, extractor, max_retries=settings.max_retries, config=config)
    url = await asyncio.to_thread(trace_url, settings, config)
    return ExtractResponse(**dict(result), document_text=text, trace_url=url)


async def _read_upload(upload: FormFile, settings: Settings) -> bytes:
    # Read one byte past the limit so the loader can reject oversized files without reading them.
    return await upload.read(settings.max_upload_bytes + 1)


async def _read_single_input(request: Request, settings: Settings) -> tuple[str, bytes]:
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        upload = form.get("file")
        if not isinstance(upload, FormFile):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "missing 'file' field")
        return upload.filename or "upload", await _read_upload(upload, settings)
    if content_type.startswith("application/json"):
        try:
            body = TextRequest.model_validate_json(await request.body())
        except ValidationError as exc:
            detail = exc.errors(include_url=False, include_input=False, include_context=False)
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail) from exc
        return "text.txt", body.text.encode()
    raise HTTPException(
        status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "send multipart/form-data or application/json"
    )


@router.get("/health")
async def health(settings: SettingsDep) -> Health:
    return Health(status="ok", tracing=settings.tracing_enabled)


@router.post("/extract", openapi_extra=EXTRACT_BODY)
async def extract(
    request: Request, settings: SettingsDep, extractor: ExtractorDep
) -> ExtractResponse:
    filename, content = await _read_single_input(request, settings)
    return await _process(filename, content, settings, extractor)


@router.post("/extract/batch")
async def extract_batch(
    files: Annotated[list[UploadFile], File()], settings: SettingsDep, extractor: ExtractorDep
) -> list[BatchItem]:
    if len(files) > settings.max_batch_files:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE, f"at most {settings.max_batch_files} files"
        )
    limit = asyncio.Semaphore(settings.batch_concurrency)

    async def run(upload: UploadFile) -> BatchItem:
        filename = upload.filename or "upload"
        async with limit:
            try:
                content = await _read_upload(upload, settings)
                return BatchItem(
                    filename=filename,
                    result=await _process(filename, content, settings, extractor),
                )
            except InvoiceExtractorError as exc:
                return BatchItem(filename=filename, error=str(exc))
            except Exception:
                # One failing LLM call must not fail the whole batch; it is logged and reported.
                logger.exception("Batch extraction failed for %s", filename)
                return BatchItem(filename=filename, error="extraction failed (LLM error)")

    return list(await asyncio.gather(*(run(upload) for upload in files)))
