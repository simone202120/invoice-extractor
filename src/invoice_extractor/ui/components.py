"""Rendering helpers shared by the UI pages: invoice card, badges, run metrics, batch table."""

import csv
import io
from typing import Any

import streamlit as st

from invoice_extractor.config import Settings
from invoice_extractor.ui import client

BATCH_LABELS = {
    "file": "File",
    "status": "Status",
    "number": "Number",
    "supplier": "Supplier",
    "issue_date": "Date",
    "currency": "Currency",
    "gross_total": "Total",
    "retries": "Retries",
    "issues": "Issues",
}


def sample_files(settings: Settings) -> list[str]:
    if not settings.samples_dir.is_dir():
        return []
    return sorted(p.name for p in settings.samples_dir.iterdir() if p.is_file())


def call_api(action: str, request: Any, *args: Any) -> Any:
    """Run an API call inside a status box; show a friendly error and return None on failure."""
    with st.status(action, expanded=False) as box:
        st.write("Reading the document and asking the model…")
        try:
            result = request(*args)
        except client.ApiError as exc:
            box.update(label="Extraction failed", state="error")
            st.error(str(exc), icon=":material/error:")
            return None
        st.write("Numbers checked against each other.")
        box.update(label=f"{action}: done", state="complete")
    return result


def validation_badges(validation: dict[str, Any]) -> None:
    issues = len(validation["errors"])
    if validation["valid"]:
        st.badge("Valid", icon=":material/check_circle:", color="green")
    else:
        st.badge(f"{issues} issue{'s' * (issues != 1)}", icon=":material/warning:", color="red")
    retries = validation["retries"]
    st.badge(
        f"{retries} retr{'y' if retries == 1 else 'ies'}",
        icon=":material/replay:",
        color="orange" if retries else "gray",
    )


def run_metrics(usage: dict[str, Any], trace_url: str | None) -> None:
    latency, tokens, cost, trace = st.container(border=True).columns(4, vertical_alignment="center")
    latency.metric("Latency", f"{usage['latency_ms'] / 1000:.1f} s")
    tokens.metric("Tokens", f"{usage['input_tokens'] + usage['output_tokens']:,}")
    cost.metric("Cost", f"${usage['cost_usd']:.4f}" if usage["cost_usd"] is not None else "n/a")
    with trace:
        if trace_url:
            st.link_button("Langfuse trace", trace_url, icon=":material/timeline:")
        else:
            st.caption("Tracing off")


def _party(title: str, party: dict[str, Any] | None) -> None:
    st.caption(title)
    if party is None:
        st.write("—")
        return
    st.markdown(f"**{party['name']}**")
    details = [party.get("vat_number") and f"VAT {party['vat_number']}", party.get("address")]
    st.write("  \n".join(d for d in details if d) or "—")


def _money(value: str) -> str:
    return f"{float(value):,.2f}"


def invoice_card(result: dict[str, Any]) -> None:
    invoice = result["invoice"]
    with st.container(border=True):
        title, badges = st.columns([3, 2])
        title.subheader(f"{invoice['document_type'].title()} {invoice['number']}")
        with badges.container(horizontal=True, horizontal_alignment="right"):
            validation_badges(result["validation"])
        st.caption(
            f"Issued {invoice['issue_date']} · {invoice['currency']}"
            + (f" · {invoice['payment_terms']}" if invoice.get("payment_terms") else "")
        )
        supplier, customer = st.columns(2)
        with supplier:
            _party("Supplier", invoice["supplier"])
        with customer:
            _party("Customer", invoice.get("customer"))
        st.dataframe(
            [
                {
                    "Description": line["description"],
                    "Qty": float(line["quantity"]),
                    "Unit price": float(line["unit_price"]),
                    "VAT %": float(line["vat_rate"]),
                    "Total": float(line["line_total"]),
                }
                for line in invoice["line_items"]
            ],
            hide_index=True,
            width="stretch",
            column_config={
                "Qty": st.column_config.NumberColumn(format="%g"),
                "Unit price": st.column_config.NumberColumn(format="%.2f"),
                "VAT %": st.column_config.NumberColumn(format="%g%%"),
                "Total": st.column_config.NumberColumn(format="%.2f"),
            },
        )
        currency = invoice["currency"]
        net, vat, gross = st.columns(3)
        net.metric(f"Net ({currency})", _money(invoice["net_total"]))
        vat.metric(f"VAT ({currency})", _money(invoice["vat_total"]))
        gross.metric(f"Total ({currency})", _money(invoice["gross_total"]))
    for error in result["validation"]["errors"]:
        st.warning(error, icon=":material/rule:")
    if not result["validation"]["valid"]:
        st.caption(
            "The model re-read the document after each failed check. Issues that remain are "
            "most likely errors printed on the document itself."
        )


def raw_response(result: dict[str, Any]) -> None:
    with st.expander("Raw response", icon=":material/data_object:"):
        st.json({k: v for k, v in result.items() if k != "document_text"}, expanded=True)


def batch_rows(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for item in items:
        result = item.get("result")
        if result is None:
            rows.append({"file": item["filename"], "status": "failed", "issues": item["error"]})
            continue
        invoice, validation = result["invoice"], result["validation"]
        rows.append(
            {
                "file": item["filename"],
                "status": "valid" if validation["valid"] else "issues",
                "number": invoice["number"],
                "supplier": invoice["supplier"]["name"],
                "issue_date": invoice["issue_date"],
                "currency": invoice["currency"],
                "gross_total": float(invoice["gross_total"]),
                "retries": validation["retries"],
                "issues": "; ".join(validation["errors"]),
            }
        )
    return rows


def to_csv(rows: list[dict[str, Any]]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(BATCH_LABELS))
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()
