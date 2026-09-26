"""HTTP client for the extraction API, turning failures into messages a user can act on."""

from typing import Any

import httpx

from invoice_extractor.config import Settings

FRIENDLY_STATUS = {
    411: "The upload was sent without a size; try again.",
    413: "The file is too large.",
    415: "Only PDF and plain-text (.txt) documents are supported.",
    422: "The document could not be turned into an invoice.",
    502: "The LLM provider is not responding. Try again in a minute.",
    503: "The backend is not configured: set OPENROUTER_API_KEY and restart the API.",
}


class ApiError(Exception):
    """A request to the backend failed; the message is safe to show to the user."""


def _detail(response: httpx.Response) -> str:
    try:
        detail = response.json().get("detail", "")
    except ValueError:
        detail = response.text
    return detail if isinstance(detail, str) else ""


def _request(settings: Settings, method: str, path: str, **kwargs: Any) -> Any:
    try:
        response = httpx.request(
            method, f"{settings.api_url}{path}", timeout=settings.api_timeout_seconds, **kwargs
        )
    except httpx.HTTPError as exc:
        raise ApiError(
            f"Cannot reach the backend at {settings.api_url}. Is the API running?"
        ) from exc
    if response.is_success:
        return response.json()
    message = FRIENDLY_STATUS.get(response.status_code, "The backend rejected the request.")
    detail = _detail(response)
    raise ApiError(f"{message} ({detail})" if detail else message)


def health(settings: Settings) -> dict[str, Any]:
    result: dict[str, Any] = _request(settings, "GET", "/health")
    return result


def extract_file(settings: Settings, filename: str, content: bytes) -> dict[str, Any]:
    result: dict[str, Any] = _request(
        settings, "POST", "/extract", files={"file": (filename, content)}
    )
    return result


def extract_batch(settings: Settings, files: list[tuple[str, bytes]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = _request(
        settings, "POST", "/extract/batch", files=[("files", file) for file in files]
    )
    return result
