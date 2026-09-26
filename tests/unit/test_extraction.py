import pytest
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage

from invoice_extractor.core.errors import ExtractionError
from invoice_extractor.core.extraction import extract_invoice
from tests.fakes import expected_invoice, fake_extractor, invoice_call


def _with_wrong_gross(data: dict[str, object]) -> dict[str, object]:
    return data | {"gross_total": "9999.00"}


async def test_valid_first_answer_needs_no_retry() -> None:
    extractor, model = fake_extractor(invoice_call(expected_invoice("invoice_en_clean")))
    result = await extract_invoice("doc", extractor, max_retries=2)
    assert result.validation.valid is True
    assert result.validation.retries == 0
    assert result.invoice.number == "NDS-2026-0142"
    assert len(model.received) == 1
    assert "<document>\ndoc\n</document>" in str(model.received[0][-1].content)


async def test_validation_errors_trigger_a_correction_that_succeeds() -> None:
    good = expected_invoice("invoice_en_clean")
    extractor, model = fake_extractor(invoice_call(_with_wrong_gross(good)), invoice_call(good))
    result = await extract_invoice("doc", extractor, max_retries=2)
    assert result.validation.valid is True
    assert result.validation.retries == 1
    correction = str(model.received[1][-1].content)
    assert "gross_total 9999.00" in correction
    assert '"gross_total":"9999.00"' in correction


async def test_invalid_after_all_retries_returns_last_invoice_with_errors() -> None:
    bad = expected_invoice("invoice_arithmetic_error")
    extractor, model = fake_extractor(*(invoice_call(bad) for _ in range(3)))
    result = await extract_invoice("doc", extractor, max_retries=2)
    assert result.validation.valid is False
    assert result.validation.retries == 2
    assert len(result.validation.errors) == 1
    assert "line 1" in result.validation.errors[0]
    assert len(model.received) == 3


async def test_schema_error_is_fed_back_and_corrected() -> None:
    good = expected_invoice("receipt_coworking")
    broken = {key: value for key, value in good.items() if key != "issue_date"}
    extractor, model = fake_extractor(invoice_call(broken), invoice_call(good))
    result = await extract_invoice("doc", extractor, max_retries=1)
    assert result.validation.valid is True
    assert result.validation.retries == 1
    correction = str(model.received[1][-1].content)
    assert "issue_date" in correction
    assert "schema" in correction


async def test_answer_without_tool_call_counts_as_failure() -> None:
    extractor, _ = fake_extractor(AIMessage(content="I cannot help"), AIMessage(content="no"))
    with pytest.raises(ExtractionError):
        await extract_invoice("doc", extractor, max_retries=1)


async def test_last_parsed_invoice_is_kept_when_final_attempt_is_unparsable() -> None:
    bad = expected_invoice("invoice_arithmetic_error")
    extractor, _ = fake_extractor(invoice_call(bad), AIMessage(content="oops"))
    result = await extract_invoice("doc", extractor, max_retries=1)
    assert result.validation.valid is False
    assert result.invoice.number == "2026-117"
    assert result.validation.retries == 1


class _RunNames(BaseCallbackHandler):
    def __init__(self) -> None:
        self.names: list[str] = []

    def on_chain_start(self, serialized: object, inputs: object, **kwargs: object) -> None:
        self.names.append(str(kwargs.get("name")))


async def test_one_trace_with_a_named_run_per_attempt() -> None:
    good = expected_invoice("invoice_en_clean")
    extractor, _ = fake_extractor(invoice_call(_with_wrong_gross(good)), invoice_call(good))
    handler = _RunNames()
    await extract_invoice("doc", extractor, max_retries=2, config={"callbacks": [handler]})
    assert handler.names[0] == "extract_invoice"
    assert "attempt_0" in handler.names
    assert "attempt_1" in handler.names
