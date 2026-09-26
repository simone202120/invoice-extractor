"""Batch page: extract several documents concurrently and download the results as CSV."""

import streamlit as st

from invoice_extractor.config import Settings
from invoice_extractor.ui import client
from invoice_extractor.ui.components import (
    BATCH_LABELS,
    batch_rows,
    call_api,
    sample_files,
    to_csv,
)


def _summary(rows: list[dict[str, object]]) -> None:
    total, valid, issues, failed = st.columns(4)
    total.metric("Files", len(rows))
    valid.metric("Valid", sum(row["status"] == "valid" for row in rows))
    issues.metric("With issues", sum(row["status"] == "issues" for row in rows))
    failed.metric("Failed", sum(row["status"] == "failed" for row in rows))


def render(settings: Settings) -> None:
    uploads = st.file_uploader(
        "Drop several invoices",
        type=["pdf", "txt"],
        accept_multiple_files=True,
        help=f"Up to {settings.max_batch_files} files, processed concurrently by the API.",
    )
    run_uploads, run_samples = st.columns(2)
    files: list[tuple[str, bytes]] = []
    if run_uploads.button(
        "Extract uploaded files",
        type="primary",
        disabled=not uploads,
        icon=":material/play_arrow:",
        width="stretch",
    ):
        files = [(upload.name, upload.getvalue()) for upload in uploads or []]
    if run_samples.button(
        "Run all samples",
        key="batch-samples",
        icon=":material/folder_open:",
        width="stretch",
        disabled=not sample_files(settings),
    ):
        files = [
            (name, (settings.samples_dir / name).read_bytes()) for name in sample_files(settings)
        ]
    if files:
        items = call_api(
            f"Extracting {len(files)} documents", client.extract_batch, settings, files
        )
        st.session_state["batch_rows"] = batch_rows(items) if items is not None else None
    rows = st.session_state.get("batch_rows")
    if not rows:
        st.info(
            "Upload a few documents, or run the batch on the bundled samples.",
            icon=":material/info:",
        )
        return
    _summary(rows)
    st.dataframe(
        rows,
        hide_index=True,
        width="stretch",
        column_config={
            **BATCH_LABELS,
            "gross_total": st.column_config.NumberColumn("Total", format="%.2f"),
            "issues": st.column_config.TextColumn("Issues", width="large"),
        },
    )
    st.download_button(
        "Download CSV",
        to_csv(rows),
        file_name="invoices.csv",
        mime="text/csv",
        icon=":material/download:",
    )
