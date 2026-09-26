"""Creates the chat model (OpenRouter, OpenAI-compatible) wrapped for structured invoice output."""

from langchain_openai import ChatOpenAI

from invoice_extractor.config import Settings
from invoice_extractor.core.errors import ConfigurationError
from invoice_extractor.core.extraction import Extractor
from invoice_extractor.core.models import Invoice


def create_extractor(settings: Settings) -> Extractor:
    if not settings.openrouter_api_key.get_secret_value():
        raise ConfigurationError("OPENROUTER_API_KEY is not set")
    llm = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        temperature=0,
        timeout=settings.llm_timeout_seconds,
    )
    # Function calling is the structured-output mode most widely supported across OpenRouter
    # models; include_raw keeps parsing errors so they can be fed back to the model.
    return llm.with_structured_output(Invoice, method="function_calling", include_raw=True)
