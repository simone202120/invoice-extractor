import asyncio
from collections.abc import Iterator
from typing import Any

import httpx
import openai
import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from langchain_core.runnables import Runnable, RunnableLambda

from invoice_extractor.api.app import create_app, domain_error
from invoice_extractor.api.dependencies import get_extractor
from invoice_extractor.config import Settings, get_settings
from invoice_extractor.core.errors import (
    ConfigurationError,
    DocumentTooLargeError,
    ExtractionError,
)
from invoice_extractor.core.models import Invoice
from tests.fakes import SAMPLES, expected_invoice, fake_extractor, invoice_call

CLEAN = expected_invoice("invoice_en_clean")
SETTINGS = Settings(
    _env_file=None,
    langfuse_public_key="",
    langfuse_secret_key="",
    max_upload_mb=1,
    max_batch_files=5,
    batch_concurrency=2,
)


def _client(extractor: Runnable[Any, Any], settings: Settings = SETTINGS) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_extractor] = lambda: extractor
    return TestClient(app)


@pytest.fixture
def client() -> TestClient:
    extractor, _ = fake_extractor(*(invoice_call(CLEAN) for _ in range(10)))
    return _client(extractor)


def _txt(name: str = "invoice.txt", body: bytes = b"Invoice NDS-2026-0142") -> Any:
    return (name, body, "text/plain")


def test_health(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok", "tracing": False}


def test_extract_text_file(client: TestClient) -> None:
    response = client.post("/extract", files={"file": _txt()})
    assert response.status_code == 200
    body = response.json()
    assert body["invoice"]["number"] == "NDS-2026-0142"
    assert body["validation"] == {"valid": True, "errors": [], "retries": 0}
    assert body["document_text"] == "Invoice NDS-2026-0142"
    assert body["trace_url"] is None
    assert set(body["usage"]) == {"input_tokens", "output_tokens", "cost_usd", "latency_ms"}


def test_extract_pdf_file(client: TestClient) -> None:
    content = (SAMPLES / "invoice_en_eur.pdf").read_bytes()
    response = client.post("/extract", files={"file": ("a.pdf", content, "application/pdf")})
    assert response.status_code == 200
    assert "KM-26-0419" in response.json()["document_text"]


def test_extract_json_text(client: TestClient) -> None:
    response = client.post("/extract", json={"text": "Invoice NDS-2026-0142"})
    assert response.status_code == 200
    assert response.json()["invoice"]["gross_total"] == "2424.00"


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"files": {"file": _txt("a.docx", b"PK\x03\x04")}}, 415),
        ({"files": {"file": _txt(body=b"x" * (1024 * 1024 + 1))}}, 413),
        ({"files": {"file": _txt(body=b"  ")}}, 422),
        ({"files": {"other": _txt()}}, 422),
        ({"json": {"text": ""}}, 422),
        ({"json": {"wrong": "field"}}, 422),
        ({"content": b"{not json", "headers": {"content-type": "application/json"}}, 422),
        ({"content": b"hello", "headers": {"content-type": "text/plain"}}, 415),
    ],
)
def test_invalid_input_is_rejected(client: TestClient, kwargs: dict[str, Any], code: int) -> None:
    response = client.post("/extract", **kwargs)
    assert response.status_code == code
    assert response.json()["detail"]


def test_unparsable_model_output_is_422() -> None:
    extractor, _ = fake_extractor(*(AIMessage(content="no") for _ in range(3)))
    response = _client(extractor).post("/extract", files={"file": _txt()})
    assert response.status_code == 422


def _raise_connection_error(_: object) -> None:
    raise openai.APIConnectionError(request=httpx.Request("POST", "https://llm.invalid"))


def test_llm_provider_failure_is_502() -> None:
    response = _client(RunnableLambda(_raise_connection_error)).post(
        "/extract", files={"file": _txt()}
    )
    assert response.status_code == 502
    assert "LLM provider" in response.json()["detail"]


def test_missing_api_key_is_503() -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: SETTINGS

    def missing_key() -> None:
        raise ConfigurationError("OPENROUTER_API_KEY is not set")

    app.dependency_overrides[get_extractor] = missing_key
    response = TestClient(app).post("/extract", files={"file": _txt()})
    assert response.status_code == 503
    assert response.json()["detail"] == "OPENROUTER_API_KEY is not set"


def test_batch_reports_each_file(client: TestClient) -> None:
    files = [("files", _txt("a.txt")), ("files", _txt("b.docx", b"PK")), ("files", _txt("c.txt"))]
    response = client.post("/extract/batch", files=files)
    assert response.status_code == 200
    items = response.json()
    assert [item["filename"] for item in items] == ["a.txt", "b.docx", "c.txt"]
    assert items[0]["result"]["validation"]["valid"] is True
    assert items[1]["result"] is None
    assert "PDF and plain-text" in items[1]["error"]


def test_batch_rejects_too_many_files(client: TestClient) -> None:
    files = [("files", _txt(f"{i}.txt")) for i in range(6)]
    assert client.post("/extract/batch", files=files).status_code == 413


def test_batch_isolates_llm_failures() -> None:
    client = _client(RunnableLambda(_raise_connection_error))
    response = client.post("/extract/batch", files=[("files", _txt())])
    assert response.status_code == 200
    assert response.json()[0]["error"] == "extraction failed (LLM error)"


def test_batch_limits_concurrency() -> None:
    running = peak = 0

    async def slow_extractor(_: object) -> dict[str, Any]:
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.02)
        running -= 1
        return {"raw": AIMessage(content=""), "parsed": Invoice.model_validate(CLEAN)}

    client = _client(RunnableLambda(slow_extractor))
    files = [("files", _txt(f"{i}.txt")) for i in range(5)]
    response = client.post("/extract/batch", files=files)
    assert response.status_code == 200
    assert all(item["result"] for item in response.json())
    assert peak == SETTINGS.batch_concurrency


def test_lifespan_runs_without_tracing_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "")
    get_settings.cache_clear()
    try:
        with TestClient(create_app()) as client:
            assert client.get("/health").status_code == 200
    finally:
        get_settings.cache_clear()


def test_oversized_body_is_rejected_from_content_length(client: TestClient) -> None:
    response = client.post(
        "/extract",
        content=b"{}",
        headers={"content-type": "application/json", "content-length": str(10**9)},
    )
    assert response.status_code == 413


def test_oversized_batch_is_rejected_from_content_length(client: TestClient) -> None:
    response = client.post(
        "/extract/batch",
        content=b"x",
        headers={"content-type": "multipart/form-data; boundary=x", "content-length": str(10**9)},
    )
    assert response.status_code == 413


def test_missing_content_length_is_411(client: TestClient) -> None:
    def chunks() -> Iterator[bytes]:
        yield b'{"text": "hi"}'

    response = client.post(
        "/extract", content=chunks(), headers={"content-type": "application/json"}
    )
    assert response.status_code == 411


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [({"files": [("other", _txt())]}, 422), ({"json": {"text": "x"}}, 415)],
)
def test_invalid_batch_input_is_rejected(
    client: TestClient, kwargs: dict[str, Any], code: int
) -> None:
    assert client.post("/extract/batch", **kwargs).status_code == code


class _MoreSpecificExtractionError(ExtractionError):
    pass


class _TooManyPagesError(DocumentTooLargeError):
    pass


@pytest.mark.parametrize(
    ("error", "code"),
    [(_MoreSpecificExtractionError("x"), 422), (_TooManyPagesError("x"), 413)],
)
async def test_domain_error_subclasses_map_like_their_parent(error: Exception, code: int) -> None:
    request = Request({"type": "http"})
    assert (await domain_error(request, error)).status_code == code
