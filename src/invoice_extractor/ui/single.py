"""Single-document page: upload or pick a sample, then show the extracted invoice."""

from typing import Any

import streamlit as st

from invoice_extractor.config import Settings
from invoice_extractor.ui import client
from invoice_extractor.ui.components import (
    call_api,
    invoice_card,
    raw_response,
    run_metrics,
    sample_files,
)

EXAMPLES = [
    ("fattura_it_split_vat.pdf", "Italian invoice, 22% + 10% VAT", ":material/picture_as_pdf:"),
    ("invoice_arithmetic_error.txt", "Invoice with a wrong line total", ":material/error:"),
    ("receipt_coworking.txt", "Coworking receipt", ":material/receipt_long:"),
]


def _examples(settings: Settings) -> tuple[str, bytes] | None:
    st.caption("No invoice at hand? Try one of the samples:")
    available = set(sample_files(settings))
    chosen = None
    for column, (name, label, icon) in zip(st.columns(len(EXAMPLES)), EXAMPLES, strict=True):
        if column.button(label, icon=icon, width="stretch", disabled=name not in available):
            chosen = name, (settings.samples_dir / name).read_bytes()
    return chosen


def _show(result: dict[str, Any]) -> None:
    run_metrics(result["usage"], result.get("trace_url"))
    document, extracted = st.columns([2, 3], gap="large")
    with document:
        st.caption(f"Document text · {st.session_state['single_name']}")
        st.code(result["document_text"], language=None, height=520, wrap_lines=True)
    with extracted:
        invoice_card(result)
    raw_response(result)


def render(settings: Settings) -> None:
    upload = st.file_uploader(
        "Drop an invoice or receipt",
        type=["pdf", "txt"],
        help=f"PDF with a text layer or plain text, up to {settings.max_upload_mb} MB.",
    )
    chosen = (upload.name, upload.getvalue()) if upload else None
    if example := _examples(settings):
        chosen = example
    if chosen and chosen[0] != st.session_state.get("single_name"):
        name, content = chosen
        result = call_api(f"Extracting {name}", client.extract_file, settings, name, content)
        st.session_state["single_name"] = name
        st.session_state["single_result"] = result
    if result := st.session_state.get("single_result"):
        _show(result)
