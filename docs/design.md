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

## UI and demo polish

The UI is what the interviewer sees first: it must look clean and deliberate, not like a default
Streamlit script.

- Custom theme in `.streamlit/config.toml` (`[theme]`: base, primaryColor, backgroundColor,
  secondaryBackgroundColor, textColor, font, baseRadius) using the palette below. No heavy CSS hacks;
  at most a few lines of `st.markdown(..., unsafe_allow_html=True)` for spacing.
- `st.set_page_config` with title, icon and `layout="wide"`; a short header with the project name and
  a one-line description; a sidebar for settings and state.
- Long operations show progress (`st.status` / `st.progress` / `st.spinner`) with human-readable steps.
- Every screen has a useful empty state: 3 clickable example inputs that run a real demo.
- Results are presented, not dumped: containers with borders, badges, metrics, expanders. Raw JSON
  only in a collapsed "Raw response" expander.
- Show cost and speed of each run (tokens, estimated cost, latency) as small metrics: it proves the
  observability story. Link to the Langfuse trace when tracing is enabled.
- Errors are friendly `st.error` messages that say what to do, never stack traces.
- The UI talks to the FastAPI backend over HTTP (backend URL from settings), never imports `core/`.
- Keep it one file per page under `ui/`, small helpers in one module; no duplicated rendering code.

Palette: light base, background `#F6F8F7`, surface `#FFFFFF`, text `#17211B`, primary `#0E8A5F`.
Layout: drag-and-drop upload plus "Try a sample" buttons for the files in `samples/`. Result view in
two columns: left the document text preview, right the extracted invoice as a readable card (supplier,
number, date, line items table with `st.dataframe` column formatting, totals) and validation badges
(valid / errors / retries used). Batch tab: results table with status per file and CSV download.
