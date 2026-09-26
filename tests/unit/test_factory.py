import pytest
from langchain_core.runnables import RunnableSequence

from invoice_extractor.config import Settings
from invoice_extractor.core.errors import ConfigurationError
from invoice_extractor.llm.factory import create_extractor


def test_missing_api_key_is_a_configuration_error() -> None:
    with pytest.raises(ConfigurationError):
        create_extractor(Settings(_env_file=None, openrouter_api_key=""))


def test_extractor_is_built_with_configured_model() -> None:
    settings = Settings(_env_file=None, openrouter_api_key="key", llm_model="vendor/model")
    extractor = create_extractor(settings)
    assert isinstance(extractor, RunnableSequence)
    assert "vendor/model" in repr(extractor)
