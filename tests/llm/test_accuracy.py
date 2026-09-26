"""Real-LLM accuracy on the samples (costs money: run manually with `pytest -m llm -s`)."""

from decimal import Decimal

import pytest

from invoice_extractor.config import get_settings
from invoice_extractor.core.extraction import extract_invoice
from invoice_extractor.core.loader import load_document
from invoice_extractor.core.models import Invoice
from invoice_extractor.infra.tracing import init_tracing, shutdown_tracing, tracing_config
from invoice_extractor.llm.factory import create_extractor
from tests.fakes import SAMPLES, expected_invoice

pytestmark = pytest.mark.llm

ACCURACY_THRESHOLD = 0.9


def _normalize(value: object) -> object:
    if isinstance(value, str):
        return "".join(value.split()).casefold().rstrip(".")
    return value


def _key_fields(invoice: Invoice) -> dict[str, object]:
    fields: dict[str, object] = {
        "document_type": invoice.document_type,
        "number": invoice.number,
        "issue_date": invoice.issue_date,
        "currency": invoice.currency,
        "supplier.name": invoice.supplier.name,
        "supplier.vat_number": invoice.supplier.vat_number,
        "customer.name": invoice.customer.name if invoice.customer else None,
        "net_total": invoice.net_total,
        "vat_total": invoice.vat_total,
        "gross_total": invoice.gross_total,
        "line_count": len(invoice.line_items),
    }
    for index, line in enumerate(invoice.line_items):
        for name in ("quantity", "unit_price", "vat_rate", "line_total"):
            value: Decimal = getattr(line, name)
            fields[f"line{index}.{name}"] = value.normalize()
    return {key: _normalize(value) for key, value in fields.items()}


async def test_sample_accuracy() -> None:
    settings = get_settings()
    init_tracing(settings)
    extractor = create_extractor(settings)
    correct = total = 0
    rows = []
    for path in sorted(p for p in SAMPLES.iterdir() if p.is_file()):
        text = load_document(
            path.read_bytes(),
            path.name,
            max_bytes=settings.max_upload_mb * 1024 * 1024,
            max_chars=settings.max_text_chars,
        )
        result = await extract_invoice(
            text,
            extractor,
            max_retries=settings.max_retries,
            config=tracing_config(settings, path.name),
        )
        expected = _key_fields(Invoice.model_validate(expected_invoice(path.stem)))
        actual = _key_fields(result.invoice)
        wrong = [key for key in expected if expected[key] != actual.get(key)]
        correct += len(expected) - len(wrong)
        total += len(expected)
        rows.append(
            f"{path.name:32} {len(expected) - len(wrong):3}/{len(expected):<3} "
            f"retries={result.validation.retries} valid={result.validation.valid} wrong={wrong}"
        )
    shutdown_tracing(settings)
    print("\n" + "\n".join(rows) + f"\naccuracy: {correct}/{total} = {correct / total:.1%}")
    assert correct / total >= ACCURACY_THRESHOLD
