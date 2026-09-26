"""Pure consistency checks on an extracted invoice; each returns human-readable error messages."""

from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from invoice_extractor.core.models import Invoice, Party

TOLERANCE = Decimal("0.01")
CENT = Decimal("0.01")


def _differs(actual: Decimal, expected: Decimal, tolerance: Decimal = TOLERANCE) -> bool:
    return abs(actual - expected) > tolerance


def _round(amount: Decimal) -> Decimal:
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


def check_line_totals(invoice: Invoice) -> list[str]:
    errors = []
    for index, line in enumerate(invoice.line_items, start=1):
        expected = line.quantity * line.unit_price
        if _differs(line.line_total, expected):
            errors.append(
                f"line {index} ({line.description!r}): line_total {line.line_total} does not equal "
                f"quantity {line.quantity} x unit_price {line.unit_price} = {_round(expected)}"
            )
    return errors


def check_net_total(invoice: Invoice) -> list[str]:
    expected = sum((line.line_total for line in invoice.line_items), Decimal(0))
    if _differs(invoice.net_total, expected):
        return [f"net_total {invoice.net_total} does not equal the sum of line totals {expected}"]
    return []


def check_vat_total(invoice: Invoice) -> list[str]:
    # VAT is computed on the taxable amount of each rate and rounded once per rate (as in the
    # VAT summary printed on invoices), so each rate group may contribute one cent of rounding.
    taxable_by_rate: dict[Decimal, Decimal] = defaultdict(Decimal)
    for line in invoice.line_items:
        taxable_by_rate[line.vat_rate] += line.line_total
    expected = sum(
        (_round(taxable * rate / 100) for rate, taxable in taxable_by_rate.items()), Decimal(0)
    )
    tolerance = TOLERANCE * max(len(taxable_by_rate), 1)
    if _differs(invoice.vat_total, expected, tolerance):
        rates = ", ".join(f"{rate}%" for rate in sorted(taxable_by_rate))
        return [
            f"vat_total {invoice.vat_total} is not consistent with the line VAT rates "
            f"({rates}): expected {expected}"
        ]
    return []


def check_gross_total(invoice: Invoice) -> list[str]:
    expected = invoice.net_total + invoice.vat_total
    if _differs(invoice.gross_total, expected):
        return [
            f"gross_total {invoice.gross_total} does not equal net_total + vat_total = {expected}"
        ]
    return []


def is_valid_italian_vat(vat_number: str) -> bool:
    """Check an Italian partita IVA: 11 digits with a Luhn-style check digit."""
    digits = vat_number.upper().removeprefix("IT").replace(" ", "")
    if len(digits) != 11 or not digits.isdigit():
        return False
    total = 0
    for index, char in enumerate(digits[:10]):
        value = int(char)
        if index % 2 == 1:
            value *= 2
            value = value - 9 if value > 9 else value
        total += value
    return (10 - total % 10) % 10 == int(digits[10])


def _is_italian(party: Party) -> bool:
    vat = (party.vat_number or "").strip().upper()
    return (party.country or "").upper() == "IT" or vat.startswith("IT")


def check_vat_numbers(invoice: Invoice) -> list[str]:
    errors = []
    for role, party in (("supplier", invoice.supplier), ("customer", invoice.customer)):
        if party is None or not party.vat_number or not _is_italian(party):
            continue
        if not is_valid_italian_vat(party.vat_number.strip()):
            errors.append(
                f"{role} vat_number {party.vat_number!r} is not a valid Italian VAT number"
            )
    return errors


def validate_invoice(invoice: Invoice) -> list[str]:
    return [
        *check_line_totals(invoice),
        *check_net_total(invoice),
        *check_vat_total(invoice),
        *check_gross_total(invoice),
        *check_vat_numbers(invoice),
    ]
