"""Request and response bodies of the HTTP API."""

from pydantic import BaseModel, Field

from invoice_extractor.core.models import ExtractionResult


class TextRequest(BaseModel):
    text: str = Field(description="Invoice or receipt as plain text.")


class ExtractResponse(ExtractionResult):
    document_text: str = Field(description="Text the model read, for previews.")
    trace_url: str | None = Field(default=None, description="Langfuse trace, when tracing is on.")


class BatchItem(BaseModel):
    filename: str
    result: ExtractResponse | None = None
    error: str | None = None


class Health(BaseModel):
    status: str
    tracing: bool
