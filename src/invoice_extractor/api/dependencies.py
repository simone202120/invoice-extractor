"""FastAPI dependencies; tests override them to inject settings and a fake model."""

from functools import lru_cache

from invoice_extractor.config import get_settings
from invoice_extractor.core.extraction import Extractor
from invoice_extractor.llm.factory import create_extractor


@lru_cache
def get_extractor() -> Extractor:
    """Build the LLM extractor on first use, so the API starts even without an API key."""
    return create_extractor(get_settings())
