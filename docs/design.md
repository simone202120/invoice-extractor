# invoice-extractor — Design

## Goal
Upload an invoice or receipt (PDF or plain text) and get back validated structured JSON. The pipeline
checks the numbers add up and, when they don't, asks the LLM to fix its own output using the
validation errors.

Demo story (2 minutes): upload two sample invoices (one clean, one tricky), show the JSON, show a
validation-driven retry in the Langfuse trace, run the batch endpoint.

## Data model (Pydantic)
- `Party`: name, vat_number (optional), address (optional).
- `LineItem`: description, quantity, unit_price, vat_rate, line_total.
- `Invoice`: document_type (invoice | receipt), number, issue_date, currency, supplier, customer
  (optional), line_items, net_total, vat_total, gross_total, payment_terms (optional).
- Decimal for money, ISO dates.

## Pipeline (LangChain)
1. Load: PDF → text (`pypdf`); plain text passthrough. Reject empty/oversized files.
2. Extract: `llm.with_structured_output(Invoice)` with a focused prompt (Italian and English invoices,
   decimal comma handling, VAT rates).
3. Validate (pure functions in `core/`):
   - each line_total == quantity * unit_price (tolerance 0.01),
   - net_total == sum(line totals), vat_total consistent with rates, gross == net + vat,
   - Italian VAT number (11 digits, checksum) when country is IT.
4. Self-correct: on validation errors, re-invoke with the previous output + error list, up to
   `MAX_RETRIES`. Return the result with `validation: {valid, errors, retries}`.

## API (FastAPI)
- `POST /extract` (multipart file or JSON `{text}`) → `{invoice, validation}`.
- `POST /extract/batch` (multiple files) → list of results, processed concurrently with a limit.
- `GET /health`.

## Samples
`samples/`: 5-6 fictional invoices (generated, no real companies or people) as PDF/text, including a
receipt, an Italian invoice with split VAT rates and one with an arithmetic error;
`samples/expected/` holds the expected JSON for each.

## UI (Streamlit)
Upload → JSON viewer + validation badges + retry count; batch upload with a results table and CSV
download.

## Observability
Langfuse callback: trace per extraction, retries visible as separate generations, tokens and cost.

## Non-goals
OCR of scanned images, e-invoicing XML (FatturaPA), storage/database.

## Testing
- Unit: every validator (happy and failing cases, rounding), VAT checksum, PDF loading, retry loop
  with a fake LLM that fails first then succeeds, API routes (file type/size errors).
- Integration: full pipeline on sample files with a fake LLM returning expected JSON.
- LLM: accuracy on samples above a threshold.

## Deliverables
Docker compose (api, ui), README with pipeline diagram, `docs/architecture.md`, `docs/code-map.md`,
CI green, coverage >= 80%.
