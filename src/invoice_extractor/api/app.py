"""FastAPI application: lifespan (tracing), domain-error to HTTP mapping and routes."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import openai
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from invoice_extractor.api.routes import router
from invoice_extractor.config import get_settings
from invoice_extractor.core.errors import (
    ConfigurationError,
    DocumentTooLargeError,
    EmptyDocumentError,
    ExtractionError,
    InvoiceExtractorError,
    UnsupportedDocumentError,
)
from invoice_extractor.infra.tracing import init_tracing, shutdown_tracing

logger = logging.getLogger(__name__)

ERROR_STATUS: dict[type[Exception], int] = {
    DocumentTooLargeError: status.HTTP_413_CONTENT_TOO_LARGE,
    UnsupportedDocumentError: status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
    EmptyDocumentError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    ExtractionError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    ConfigurationError: status.HTTP_503_SERVICE_UNAVAILABLE,
}


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    init_tracing(settings)
    yield
    shutdown_tracing(settings)


async def domain_error(_: Request, exc: Exception) -> JSONResponse:
    code = next(
        (ERROR_STATUS[cls] for cls in type(exc).__mro__ if cls in ERROR_STATUS),
        status.HTTP_400_BAD_REQUEST,
    )
    if code >= 500:
        logger.error("Service misconfigured: %s", exc)
    return JSONResponse(status_code=code, content={"detail": str(exc)})


async def llm_error(_: Request, exc: Exception) -> JSONResponse:
    logger.error("LLM provider error: %s", exc)
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content={"detail": "the LLM provider failed; try again later"},
    )


def create_app() -> FastAPI:
    app = FastAPI(title="invoice-extractor", version="0.1.0", lifespan=lifespan)
    app.add_exception_handler(InvoiceExtractorError, domain_error)
    app.add_exception_handler(openai.APIError, llm_error)
    app.include_router(router)
    return app


logging.basicConfig(level=logging.INFO)
app = create_app()
