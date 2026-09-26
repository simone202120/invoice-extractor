"""Turns an uploaded document (PDF or plain text) into text, rejecting unusable input."""

import io
import logging
from pathlib import PurePath

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from invoice_extractor.core.errors import (
    DocumentTooLargeError,
    EmptyDocumentError,
    UnsupportedDocumentError,
)

logger = logging.getLogger(__name__)

PDF_MAGIC = b"%PDF-"
TEXT_SUFFIXES = {".txt", ".text", ".md", ""}


def _pdf_to_text(content: bytes, max_pages: int) -> str:
    try:
        reader = PdfReader(io.BytesIO(content))
        # Checked before extraction: text extraction is the expensive part on hostile PDFs.
        if len(reader.pages) > max_pages:
            raise DocumentTooLargeError(f"the PDF has more than {max_pages} pages")
        pages = [page.extract_text() for page in reader.pages]
    except (PyPdfError, ValueError, KeyError) as exc:
        logger.warning("Unreadable PDF: %s", exc)
        raise UnsupportedDocumentError("the PDF is corrupt or encrypted") from exc
    text = "\n".join(pages).strip()
    if not text:
        raise EmptyDocumentError("the PDF has no text layer (scanned images need OCR)")
    return text


def _bytes_to_text(content: bytes) -> str:
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise UnsupportedDocumentError("text files must be UTF-8 encoded") from exc


def load_document(
    content: bytes, filename: str, *, max_bytes: int, max_chars: int, max_pages: int
) -> str:
    """Return the document text; PDFs are recognised by their header, not their extension."""
    if len(content) > max_bytes:
        raise DocumentTooLargeError(f"file is larger than {max_bytes} bytes")
    if content.startswith(PDF_MAGIC):
        text = _pdf_to_text(content, max_pages)
    elif PurePath(filename).suffix.lower() in TEXT_SUFFIXES:
        text = _bytes_to_text(content).strip()
    else:
        raise UnsupportedDocumentError("only PDF and plain-text documents are supported")
    if not text:
        raise EmptyDocumentError("the document is empty")
    if len(text) > max_chars:
        raise DocumentTooLargeError(f"document text is longer than {max_chars} characters")
    return text
