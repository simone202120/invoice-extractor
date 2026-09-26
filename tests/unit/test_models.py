from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from invoice_extractor.core.models import MAX_LINE_ITEMS, DocumentType, Invoice, parse_decimal


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1.234,56", Decimal("1234.56")),
        ("1,234.56", Decimal("1234.56")),
        ("12,5", Decimal("12.5")),
        ("12.50", Decimal("12.50")),
        ("€ 1.000,00", Decimal("1000.00")),
        ("-3,20", Decimal("-3.20")),
        (0.1, Decimal("0.1")),
        (22, Decimal("22")),
        (Decimal("7.5"), Decimal("7.5")),
    ],
)
def test_parse_decimal_handles_comma_and_dot_formats(raw: object, expected: Decimal) -> None:
    assert parse_decimal(raw) == expected


@pytest.mark.parametrize("raw", ["", "abc", "1,2,3.4.5"])
def test_parse_decimal_rejects_garbage(raw: str) -> None:
    with pytest.raises(ValueError, match="not a valid amount"):
        parse_decimal(raw)


def _invoice_payload() -> dict[str, object]:
    return {
        "document_type": "invoice",
        "number": "A-1",
        "issue_date": "2026-03-01",
        "currency": "eur",
        "supplier": {"name": "Acme"},
        "line_items": [
            {
                "description": "x",
                "quantity": "2",
                "unit_price": "10,00",
                "vat_rate": 22,
                "line_total": "20,00",
            }
        ],
        "net_total": "20.00",
        "vat_total": "4.40",
        "gross_total": "24.40",
    }


def test_invoice_parses_iso_date_and_normalizes_currency() -> None:
    invoice = Invoice.model_validate(_invoice_payload())
    assert invoice.issue_date == date(2026, 3, 1)
    assert invoice.currency == "EUR"
    assert invoice.document_type is DocumentType.INVOICE
    assert invoice.line_items[0].unit_price == Decimal("10.00")
    assert invoice.customer is None


def test_invoice_rejects_invalid_currency() -> None:
    payload = _invoice_payload() | {"currency": "euro"}
    with pytest.raises(ValidationError):
        Invoice.model_validate(payload)


def test_invoice_money_schema_is_plain_number() -> None:
    schema = Invoice.model_json_schema()
    assert schema["properties"]["net_total"]["type"] == "number"


def test_invoice_rejects_oversized_llm_output() -> None:
    payload = _invoice_payload() | {"number": "x" * 101}
    with pytest.raises(ValidationError):
        Invoice.model_validate(payload)


def test_invoice_rejects_too_many_line_items() -> None:
    items = _invoice_payload()["line_items"]
    assert isinstance(items, list)
    payload = _invoice_payload() | {"line_items": items * (MAX_LINE_ITEMS + 1)}
    with pytest.raises(ValidationError, match="line items"):
        Invoice.model_validate(payload)


def test_invoice_schema_has_no_max_items_so_gemini_accepts_it() -> None:
    assert "maxItems" not in str(Invoice.model_json_schema())
