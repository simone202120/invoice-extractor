"""Streamlit entry point: page setup, sidebar with backend status, and the two tabs."""

import streamlit as st

from invoice_extractor.config import get_settings
from invoice_extractor.ui import batch, client, single


def _sidebar() -> None:
    settings = get_settings()
    with st.sidebar:
        st.subheader("Backend")
        try:
            status = client.health(settings)
        except client.ApiError as exc:
            st.error(str(exc), icon=":material/cloud_off:")
        else:
            st.success("API online", icon=":material/cloud_done:")
            st.caption("Langfuse tracing " + ("on" if status["tracing"] else "off"))
        st.caption(f"`{settings.api_url}`")
        st.divider()
        st.caption(
            "Each document is extracted by an LLM, then its numbers are checked: line totals, "
            "VAT per rate, gross = net + VAT, Italian VAT numbers. Failed checks are sent back "
            f"to the model, up to {settings.max_retries} times."
        )


def main() -> None:
    st.set_page_config(
        page_title="Invoice Extractor", page_icon=":material/receipt_long:", layout="wide"
    )
    st.title("Invoice Extractor")
    st.caption("PDF or text invoices and receipts → validated JSON, with self-correcting retries.")
    _sidebar()
    single_tab, batch_tab = st.tabs(["Single document", "Batch"])
    with single_tab:
        single.render(get_settings())
    with batch_tab:
        batch.render(get_settings())


main()
