"""Pydantic models for extracted invoices and the extraction result returned to callers."""

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, Field, WithJsonSchema

_NON_NUMERIC = re.compile(r"[^\d.,-]")


def parse_decimal(value: object) -> Decimal:
    """Parse an amount written with either decimal comma (1.234,56) or decimal dot (1,234.56)."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int | float) and not isinstance(value, bool):
        # str() avoids binary float artefacts such as Decimal(0.1) == 0.1000000000000000055...
        return Decimal(str(value))
    text = _NON_NUMERIC.sub("", str(value))
    if "," in text and "." in text:
        decimal_sep = "," if text.rfind(",") > text.rfind(".") else "."
        thousands_sep = "." if decimal_sep == "," else ","
        text = text.replace(thousands_sep, "").replace(",", ".")
    elif text.count(",") > 1 or text.count(".") > 1:
        text = text.replace(",", "").replace(".", "")
    else:
        text = text.replace(",", ".")
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"{value!r} is not a valid amount") from exc


def _upper(value: object) -> object:
    return value.strip().upper() if isinstance(value, str) else value


# The LLM sees money as a plain number; strings with decimal commas are still accepted on input.
Money = Annotated[Decimal, BeforeValidator(parse_decimal), WithJsonSchema({"type": "number"})]


class DocumentType(StrEnum):
    INVOICE = "invoice"
    RECEIPT = "receipt"


class Party(BaseModel):
    name: str = Field(description="Legal or trading name as printed on the document.")
    vat_number: str | None = Field(
        default=None, description="VAT / tax id exactly as printed, without the label."
    )
    address: str | None = Field(default=None, description="Full address on one line.")
    country: str | None = Field(
        default=None,
        description="ISO 3166-1 alpha-2 country code of the party (e.g. IT, GB), if determinable.",
    )


class LineItem(BaseModel):
    description: str
    quantity: Money = Field(default=Decimal(1), description="Quantity; 1 when not printed.")
    unit_price: Money = Field(description="Unit price excluding VAT.")
    vat_rate: Money = Field(description="VAT rate in percent, e.g. 22 for 22%.")
    line_total: Money = Field(description="Line amount excluding VAT, as printed.")


class Invoice(BaseModel):
    document_type: DocumentType
    number: str = Field(description="Invoice or receipt number as printed.")
    issue_date: date = Field(description="Issue date in ISO format YYYY-MM-DD.")
    currency: Annotated[str, BeforeValidator(_upper)] = Field(
        pattern=r"^[A-Z]{3}$", description="ISO 4217 code, e.g. EUR."
    )
    supplier: Party
    customer: Party | None = None
    line_items: list[LineItem]
    net_total: Money = Field(description="Total excluding VAT.")
    vat_total: Money = Field(description="Total VAT amount.")
    gross_total: Money = Field(description="Total amount due including VAT.")
    payment_terms: str | None = None


class ValidationReport(BaseModel):
    valid: bool
    errors: list[str]
    retries: int


class RunUsage(BaseModel):
    """Cost and speed of one extraction, summed over all attempts."""

    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float | None = None
    latency_ms: int = 0


class ExtractionResult(BaseModel):
    invoice: Invoice
    validation: ValidationReport
    usage: RunUsage
