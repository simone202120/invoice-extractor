"""Optional Langfuse tracing: builds per-extraction LangChain callbacks when keys are configured."""

import logging

from langchain_core.runnables import RunnableConfig
from langfuse import Langfuse, get_client
from langfuse.langchain import CallbackHandler

from invoice_extractor.config import Settings

logger = logging.getLogger(__name__)


def init_tracing(settings: Settings) -> None:
    """Create the Langfuse client once per process; a no-op when tracing is disabled."""
    if not settings.tracing_enabled:
        logger.info("Langfuse keys not set: tracing disabled")
        return
    Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key.get_secret_value(),
        host=settings.langfuse_host,
    )


def shutdown_tracing(settings: Settings) -> None:
    """Flush pending traces before the process exits."""
    if settings.tracing_enabled:
        get_client(public_key=settings.langfuse_public_key).shutdown()


def tracing_config(settings: Settings, document_name: str) -> RunnableConfig:
    """Run config for one extraction: one trace, with each LLM attempt as a generation."""
    config = RunnableConfig(run_name="extract_invoice", metadata={"document": document_name})
    if settings.tracing_enabled:
        config["callbacks"] = [CallbackHandler(public_key=settings.langfuse_public_key)]
    return config


def trace_url(settings: Settings, config: RunnableConfig) -> str | None:
    """Langfuse UI link of the trace recorded with `config`, when tracing is enabled."""
    callbacks = config.get("callbacks")
    if not isinstance(callbacks, list):
        return None
    handlers = [cb for cb in callbacks if isinstance(cb, CallbackHandler)]
    if not handlers or handlers[0].last_trace_id is None:
        return None
    try:
        return get_client(public_key=settings.langfuse_public_key).get_trace_url(
            trace_id=handlers[0].last_trace_id
        )
    except Exception:
        # The link is a convenience: a Langfuse outage must not fail an extraction that succeeded.
        logger.warning("Could not build the Langfuse trace URL", exc_info=True)
        return None
