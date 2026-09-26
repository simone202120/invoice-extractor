from decimal import Decimal

import pytest

from invoice_extractor.core.models import Invoice, LineItem, Party
from invoice_extractor.core.validation import is_valid_italian_vat, validate_invoice


def _line(qty: str, price: str, rate: str, total: str) -> LineItem:
    return LineItem(
        description="item",
        quantity=Decimal(qty),
        unit_price=Decimal(price),
        vat_rate=Decimal(rate),
        line_total=Decimal(total),
    )


def _invoice(**overrides: object) -> Invoice:
    fields: dict[str, object] = {
        "document_type": "invoice",
        "number": "1",
        "issue_date": "2026-01-15",
        "currency": "EUR",
        "supplier": Party(name="Supplier", vat_number="IT01234567897", country="IT"),
        "line_items": [
            _line("2", "100.00", "22", "200.00"),
            _line("3", "33.33", "10", "99.99"),
        ],
        "net_total": Decimal("299.99"),
        "vat_total": Decimal("54.00"),
        "gross_total": Decimal("353.99"),
    }
    return Invoice.model_validate(fields | overrides)


def test_consistent_invoice_has_no_errors() -> None:
    assert validate_invoice(_invoice()) == []


def test_line_total_mismatch_is_reported_with_line_number() -> None:
    lines = [_line("2", "100.00", "22", "210.00")]
    invoice = _invoice(
        line_items=lines,
        net_total=Decimal("210.00"),
        vat_total=Decimal("46.20"),
        gross_total=Decimal("256.20"),
    )
    errors = validate_invoice(invoice)
    assert len(errors) == 1
    assert "line 1" in errors[0]
    assert "200.00" in errors[0]


def test_line_total_within_rounding_tolerance_is_accepted() -> None:
    lines = [_line("3", "0.335", "22", "1.01")]
    invoice = _invoice(
        line_items=lines,
        net_total=Decimal("1.01"),
        vat_total=Decimal("0.22"),
        gross_total=Decimal("1.23"),
    )
    assert validate_invoice(invoice) == []


def test_net_total_must_match_sum_of_lines() -> None:
    errors = validate_invoice(_invoice(net_total=Decimal("300.99"), gross_total=Decimal("354.99")))
    assert any("net_total" in e for e in errors)


def test_vat_total_must_match_rates() -> None:
    errors = validate_invoice(_invoice(vat_total=Decimal("50.00"), gross_total=Decimal("349.99")))
    assert len(errors) == 1
    assert "vat_total" in errors[0]


def test_vat_is_rounded_per_rate_group() -> None:
    # Per-line rounding gives 3 x 0.07 = 0.21; per-rate rounding gives 0.99 x 22% = 0.22.
    lines = [_line("1", "0.33", "22", "0.33") for _ in range(3)]
    invoice = _invoice(
        line_items=lines,
        net_total=Decimal("0.99"),
        vat_total=Decimal("0.22"),
        gross_total=Decimal("1.21"),
    )
    assert validate_invoice(invoice) == []


def test_gross_must_equal_net_plus_vat() -> None:
    errors = validate_invoice(_invoice(gross_total=Decimal("360.00")))
    assert errors == [
        "gross_total 360.00 does not equal net_total + vat_total = 353.99",
    ]


def test_invalid_italian_vat_number_is_reported() -> None:
    supplier = Party(name="S", vat_number="IT01234567890", country="IT")
    errors = validate_invoice(_invoice(supplier=supplier))
    assert errors == ["supplier vat_number 'IT01234567890' is not a valid Italian VAT number"]


def test_customer_vat_number_is_checked_too() -> None:
    customer = Party(name="C", vat_number="123", country="IT")
    errors = validate_invoice(_invoice(customer=customer))
    assert len(errors) == 1
    assert errors[0].startswith("customer")


def test_non_italian_vat_number_is_not_checked() -> None:
    supplier = Party(name="S", vat_number="GB123456789", country="GB")
    assert validate_invoice(_invoice(supplier=supplier)) == []


def test_it_prefix_triggers_check_without_country() -> None:
    supplier = Party(name="S", vat_number="IT 01234567890")
    assert len(validate_invoice(_invoice(supplier=supplier))) == 1


@pytest.mark.parametrize(
    ("vat", "valid"),
    [
        ("01234567897", True),
        ("IT01234567897", True),
        ("IT 012 345 678 97", True),
        ("12345678903", True),
        ("01234567890", False),
        ("0123456789", False),
        ("0123456789A", False),
        ("", False),
    ],
)
def test_italian_vat_checksum(vat: str, valid: bool) -> None:
    assert is_valid_italian_vat(vat) is valid
