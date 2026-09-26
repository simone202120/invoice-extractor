"""Extraction pipeline: structured LLM extraction, validation and self-correcting retries."""

import json
import logging
import time
from typing import Any

from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import AIMessage
from langchain_core.runnables import Runnable, RunnableConfig, RunnableLambda

from invoice_extractor.core.errors import ExtractionError
from invoice_extractor.core.models import ExtractionResult, Invoice, RunUsage, ValidationReport
from invoice_extractor.core.validation import validate_invoice
from invoice_extractor.llm.prompts import CORRECTION_PROMPT, EXTRACTION_PROMPT

logger = logging.getLogger(__name__)

# A chat model wrapped with `with_structured_output(Invoice, include_raw=True)`.
Extractor = Runnable[LanguageModelInput, Any]


def _raw_text(raw: object) -> str:
    if isinstance(raw, AIMessage) and raw.tool_calls:
        return json.dumps(raw.tool_calls[0]["args"], ensure_ascii=False)
    return str(raw.content) if isinstance(raw, AIMessage) else ""


def _add_usage(usage: RunUsage, raw: object) -> None:
    if not isinstance(raw, AIMessage):
        return
    if raw.usage_metadata:
        usage.input_tokens += raw.usage_metadata["input_tokens"]
        usage.output_tokens += raw.usage_metadata["output_tokens"]
    # OpenRouter reports the billed cost in the raw usage block; other providers do not.
    cost = (raw.response_metadata.get("token_usage") or {}).get("cost")
    if isinstance(cost, int | float):
        usage.cost_usd = (usage.cost_usd or 0.0) + cost


def _evaluate(output: dict[str, Any]) -> tuple[Invoice | None, list[str], str]:
    """Return the parsed invoice (if any), its problems and the text to show in a correction."""
    parsed = output.get("parsed")
    if isinstance(parsed, Invoice):
        return parsed, validate_invoice(parsed), parsed.model_dump_json()
    error = output.get("parsing_error")
    problem = (
        f"the output does not match the invoice schema: {error}"
        if error
        else "the response did not contain an invoice"
    )
    return None, [problem], _raw_text(output.get("raw"))


async def _extract_with_retries(
    text: str, extractor: Extractor, max_retries: int
) -> ExtractionResult:
    started = time.perf_counter()
    usage = RunUsage()
    last_invoice: tuple[Invoice, list[str]] | None = None
    messages = EXTRACTION_PROMPT.format_messages(document=text)
    for attempt in range(max_retries + 1):
        output = await extractor.ainvoke(messages, config={"run_name": f"attempt_{attempt}"})
        _add_usage(usage, output.get("raw"))
        usage.latency_ms = round((time.perf_counter() - started) * 1000)
        invoice, errors, previous = _evaluate(output)
        if invoice is not None and not errors:
            report = ValidationReport(valid=True, errors=[], retries=attempt)
            return ExtractionResult(invoice=invoice, validation=report, usage=usage)
        if invoice is not None:
            last_invoice = (invoice, errors)
        logger.info("Extraction attempt %d failed: %s", attempt, errors)
        messages = CORRECTION_PROMPT.format_messages(
            document=text, previous=previous, errors="\n".join(f"- {e}" for e in errors)
        )
    if last_invoice is None:
        raise ExtractionError(f"no valid invoice structure after {max_retries + 1} attempts")
    invoice, errors = last_invoice
    report = ValidationReport(valid=False, errors=errors, retries=max_retries)
    return ExtractionResult(invoice=invoice, validation=report, usage=usage)


async def extract_invoice(
    text: str,
    extractor: Extractor,
    *,
    max_retries: int,
    config: RunnableConfig | None = None,
) -> ExtractionResult:
    """Extract and validate an invoice; all attempts are grouped under one traced run."""

    async def run(document: str) -> ExtractionResult:
        return await _extract_with_retries(document, extractor, max_retries)

    pipeline = RunnableLambda(run, name="extract_invoice")
    result: ExtractionResult = await pipeline.ainvoke(text, config=config)
    return result
