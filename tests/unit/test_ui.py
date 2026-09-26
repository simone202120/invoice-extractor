import csv
import io
from pathlib import Path
from typing import Any

import httpx
import pytest
from streamlit.testing.v1 import AppTest

from invoice_extractor.config import Settings
from invoice_extractor.core.models import ExtractionResult, RunUsage, ValidationReport
from invoice_extractor.ui import client
from invoice_extractor.ui.components import batch_rows, to_csv
from tests.fakes import expected_invoice

APP = str(Path(__file__).parents[2] / "src" / "invoice_extractor" / "ui" / "app.py")
SETTINGS = Settings(_env_file=None, api_url="http://api.test")


def _result(name: str, valid: bool = True, trace_url: str | None = None) -> dict[str, Any]:
    errors = [] if valid else ["line 1: wrong total"]
    result = ExtractionResult.model_validate(
        {
            "invoice": expected_invoice(name),
            "validation": ValidationReport(valid=valid, errors=errors, retries=0 if valid else 2),
            "usage": RunUsage(input_tokens=100, output_tokens=20, cost_usd=0.001, latency_ms=900),
        }
    )
    return result.model_dump(mode="json") | {"document_text": "text", "trace_url": trace_url}


def test_batch_rows_and_csv() -> None:
    items = [
        {"filename": "a.txt", "result": _result("invoice_en_clean")},
        {"filename": "b.txt", "result": _result("invoice_arithmetic_error", valid=False)},
        {"filename": "c.docx", "result": None, "error": "unsupported"},
    ]
    rows = batch_rows(items)
    assert [row["status"] for row in rows] == ["valid", "issues", "failed"]
    assert rows[0]["gross_total"] == 2424.0
    parsed = list(csv.DictReader(io.StringIO(to_csv(rows))))
    assert parsed[1]["issues"] == "line 1: wrong total"
    assert parsed[2]["number"] == ""


def _respond(monkeypatch: pytest.MonkeyPatch, response: httpx.Response | Exception) -> None:
    def fake_request(method: str, url: str, **kwargs: Any) -> httpx.Response:
        if isinstance(response, Exception):
            raise response
        response.request = httpx.Request(method, url)
        return response

    monkeypatch.setattr(client.httpx, "request", fake_request)


def test_client_returns_json(monkeypatch: pytest.MonkeyPatch) -> None:
    _respond(monkeypatch, httpx.Response(200, json={"status": "ok", "tracing": False}))
    assert client.health(SETTINGS) == {"status": "ok", "tracing": False}


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (httpx.Response(415, json={"detail": "only PDF"}), "Only PDF and plain-text"),
        (httpx.Response(503, json={"detail": "no key"}), "OPENROUTER_API_KEY"),
        (httpx.Response(500, text="boom"), "The backend rejected the request. (boom)"),
        (httpx.Response(422, json={"detail": [{"msg": "x"}]}), "could not be turned"),
        (httpx.ConnectError("refused"), "Cannot reach the backend at http://api.test"),
    ],
)
def test_client_errors_are_friendly(
    monkeypatch: pytest.MonkeyPatch, response: httpx.Response | Exception, message: str
) -> None:
    _respond(monkeypatch, response)
    with pytest.raises(client.ApiError, match=message.replace("(", r"\(").replace(")", r"\)")):
        client.extract_file(SETTINGS, "a.txt", b"x")


@pytest.fixture
def backend(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []

    def extract_file(settings: Settings, name: str, content: bytes) -> dict[str, Any]:
        calls.append(name)
        return _result("invoice_arithmetic_error", valid=False, trace_url="https://trace")

    def extract_batch(settings: Settings, files: list[tuple[str, bytes]]) -> list[dict[str, Any]]:
        calls.extend(name for name, _ in files)
        return [{"filename": name, "result": _result("invoice_en_clean")} for name, _ in files]

    monkeypatch.setattr(client, "health", lambda settings: {"status": "ok", "tracing": True})
    monkeypatch.setattr(client, "extract_file", extract_file)
    monkeypatch.setattr(client, "extract_batch", extract_batch)
    return calls


def test_app_shows_empty_state_with_examples(backend: list[str]) -> None:
    app = AppTest.from_file(APP, default_timeout=30).run()
    assert not app.exception
    assert app.title[0].value == "Invoice Extractor"
    assert len([b for b in app.button if "invoice" in b.label.lower()]) == 2
    assert app.sidebar.success[0].value == "API online"


def test_app_extracts_an_example(backend: list[str]) -> None:
    app = AppTest.from_file(APP, default_timeout=30).run()
    next(b for b in app.button if b.label.startswith("Invoice with")).click().run()
    assert not app.exception
    assert backend == ["invoice_arithmetic_error.txt"]
    assert app.subheader[0].value == "Invoice 2026-117"
    assert app.warning[0].value == "line 1: wrong total"
    assert [m.label for m in app.metric][:3] == ["Latency", "Tokens", "Cost"]


def test_app_runs_batch_on_samples(backend: list[str]) -> None:
    app = AppTest.from_file(APP, default_timeout=30).run()
    app.button(key="batch-samples").click().run()
    assert not app.exception
    assert len(backend) >= 5
    assert app.dataframe[-1].value.shape[0] == len(backend)


def test_app_explains_an_offline_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    def offline(settings: Settings) -> dict[str, Any]:
        raise client.ApiError("Cannot reach the backend")

    monkeypatch.setattr(client, "health", offline)
    app = AppTest.from_file(APP, default_timeout=30).run()
    assert app.sidebar.error[0].value == "Cannot reach the backend"
