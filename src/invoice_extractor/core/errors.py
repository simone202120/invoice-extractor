"""Domain exceptions raised by the core pipeline and mapped to HTTP errors by the API."""


class InvoiceExtractorError(Exception):
    """Base class for all domain errors."""


class DocumentError(InvoiceExtractorError):
    """The uploaded document cannot be turned into text."""


class EmptyDocumentError(DocumentError):
    pass


class DocumentTooLargeError(DocumentError):
    pass


class UnsupportedDocumentError(DocumentError):
    pass


class ExtractionError(InvoiceExtractorError):
    """The LLM never produced output that parses as an invoice."""


class ConfigurationError(InvoiceExtractorError):
    """A required setting (such as the LLM API key) is missing."""
