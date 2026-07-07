class KnowledgeBuilderError(Exception):
    """Base class for all application-specific errors."""


class PDFExtractionError(KnowledgeBuilderError):
    """Raised when a PDF cannot be opened or read at all."""


class UnsupportedFileTypeError(KnowledgeBuilderError):
    """Raised when a file extension isn't in the supported set."""


class SuspiciousEncodingError(KnowledgeBuilderError):
    """Raised when incoming request text looks like it was corrupted before
    reaching the API (e.g. Persian text sent through a non-UTF-8 Windows
    terminal codepage, arriving as literal '?' replacement characters).

    This is a request-input problem, not a PDF-extraction problem — see
    README.md 'Avoiding encoding corruption' for the underlying cause and the
    recommended fix (sidecar metadata file or a UTF-8-safe HTTP client).
    """
