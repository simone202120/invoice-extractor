import io
from pathlib import Path

import pytest
from pypdf import PdfWriter

from invoice_extractor.core.errors import (
    DocumentTooLargeError,
    EmptyDocumentError,
    UnsupportedDocumentError,
)
from invoice_extractor.core.loader import load_document

SAMPLES = Path(__file__).parents[2] / "samples"
LIMITS = {"max_bytes": 1_000_000, "max_chars": 20_000}


def test_pdf_text_is_extracted() -> None:
    content = (SAMPLES / "fattura_it_split_vat.pdf").read_bytes()
    text = load_document(content, "fattura.pdf", **LIMITS)
    assert "FATTURA n. 2026/087" in text
    assert "397,01" in text


def test_pdf_is_detected_by_content_not_extension() -> None:
    content = (SAMPLES / "invoice_en_eur.pdf").read_bytes()
    assert "KM-26-0419" in load_document(content, "upload.bin", **LIMITS)


def test_plain_text_passes_through() -> None:
    text = load_document("Fattura n. 1\nTotale 10,00 €".encode(), "a.txt", **LIMITS)
    assert text == "Fattura n. 1\nTotale 10,00 €"


def test_text_with_bom_is_decoded() -> None:
    assert load_document("﻿hello".encode(), "a.txt", **LIMITS) == "hello"


@pytest.mark.parametrize("content", [b"", b"   \n\t "])
def test_empty_document_is_rejected(content: bytes) -> None:
    with pytest.raises(EmptyDocumentError):
        load_document(content, "a.txt", **LIMITS)


def test_oversized_file_is_rejected() -> None:
    with pytest.raises(DocumentTooLargeError):
        load_document(b"x" * 11, "a.txt", max_bytes=10, max_chars=100)


def test_too_much_text_is_rejected() -> None:
    with pytest.raises(DocumentTooLargeError):
        load_document(b"x" * 101, "a.txt", max_bytes=1000, max_chars=100)


def test_unsupported_extension_is_rejected() -> None:
    with pytest.raises(UnsupportedDocumentError):
        load_document(b"PK\x03\x04", "invoice.docx", **LIMITS)


def test_binary_content_is_rejected() -> None:
    with pytest.raises(UnsupportedDocumentError):
        load_document(b"\xff\xfe\x00\x81", "a.txt", **LIMITS)


def test_corrupt_pdf_is_rejected() -> None:
    with pytest.raises(UnsupportedDocumentError):
        load_document(b"%PDF-1.4\ngarbage", "a.pdf", **LIMITS)


def test_pdf_without_text_is_rejected_as_empty() -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    buffer = io.BytesIO()
    writer.write(buffer)
    with pytest.raises(EmptyDocumentError, match="OCR"):
        load_document(buffer.getvalue(), "scan.pdf", **LIMITS)
