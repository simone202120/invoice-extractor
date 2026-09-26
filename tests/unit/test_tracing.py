from langfuse.langchain import CallbackHandler

from invoice_extractor.config import Settings
from invoice_extractor.infra.tracing import (
    init_tracing,
    shutdown_tracing,
    trace_url,
    tracing_config,
)


def test_disabled_tracing_has_no_callbacks() -> None:
    settings = Settings(_env_file=None, langfuse_public_key="", langfuse_secret_key="")
    init_tracing(settings)
    config = tracing_config(settings, "a.pdf")
    assert "callbacks" not in config
    assert config["run_name"] == "extract_invoice"
    assert config["metadata"] == {"document": "a.pdf"}
    shutdown_tracing(settings)


def test_enabled_tracing_adds_a_langfuse_handler() -> None:
    settings = Settings(
        _env_file=None,
        langfuse_public_key="pk-test",
        langfuse_secret_key="sk-test",
        langfuse_host="http://localhost:1",
    )
    init_tracing(settings)
    try:
        callbacks = tracing_config(settings, "a.pdf")["callbacks"]
        assert isinstance(callbacks, list)
        assert isinstance(callbacks[0], CallbackHandler)
    finally:
        shutdown_tracing(settings)


def test_trace_url_is_none_without_tracing() -> None:
    settings = Settings(_env_file=None, langfuse_public_key="", langfuse_secret_key="")
    assert trace_url(settings, tracing_config(settings, "a.pdf")) is None


def test_trace_url_is_none_before_any_run() -> None:
    settings = Settings(
        _env_file=None,
        langfuse_public_key="pk-test",
        langfuse_secret_key="sk-test",
        langfuse_host="http://localhost:1",
    )
    init_tracing(settings)
    try:
        assert trace_url(settings, tracing_config(settings, "a.pdf")) is None
    finally:
        shutdown_tracing(settings)
