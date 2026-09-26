"""Full pipeline (load -> extract -> validate -> retry) on every sample with a scripted model."""

from pathlib import Path

import pytest

from invoice_extractor.config import Settings
from invoice_extractor.core.extraction import extract_invoice
from invoice_extractor.core.loader import load_document
from invoice_extractor.core.models import Invoice
from tests.fakes import SAMPLES, expected_invoice, fake_extractor, invoice_call

pytestmark = pytest.mark.integration

SAMPLE_FILES = sorted(p for p in SAMPLES.iterdir() if p.is_file())
INCONSISTENT_SAMPLES = {"invoice_arithmetic_error"}


def _load(path: Path) -> str:
    settings = Settings(_env_file=None)
    return load_document(
        path.read_bytes(),
        path.name,
        max_bytes=settings.max_upload_bytes,
        max_chars=settings.max_text_chars,
        max_pages=settings.max_pdf_pages,
    )


def test_every_sample_has_expected_json() -> None:
    assert len(SAMPLE_FILES) >= 5
    for path in SAMPLE_FILES:
        assert (SAMPLES / "expected" / f"{path.stem}.json").exists()


@pytest.mark.parametrize("path", SAMPLE_FILES, ids=lambda p: p.name)
async def test_pipeline_on_sample(path: Path) -> None:
    expected = expected_invoice(path.stem)
    text = _load(path)
    extractor, model = fake_extractor(*(invoice_call(expected) for _ in range(3)))

    result = await extract_invoice(text, extractor, max_retries=2)

    assert result.invoice == Invoice.model_validate(expected)
    assert text in str(model.received[0][-1].content)
    if path.stem in INCONSISTENT_SAMPLES:
        assert result.validation.valid is False
        assert result.validation.retries == 2
    else:
        assert result.validation.valid is True
        assert result.validation.retries == 0


async def test_misread_split_vat_invoice_is_corrected() -> None:
    path = SAMPLES / "fattura_it_split_vat.pdf"
    expected = expected_invoice(path.stem)
    misread = expected | {"vat_total": "30.29", "gross_total": "376.19"}  # only the 22% VAT
    extractor, model = fake_extractor(invoice_call(misread), invoice_call(expected))

    result = await extract_invoice(_load(path), extractor, max_retries=2)

    assert result.validation.valid is True
    assert result.validation.retries == 1
    assert "10%" in str(model.received[1][-1].content)
