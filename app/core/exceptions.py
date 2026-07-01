class KnowledgeBuilderError(Exception):
    """Base exception for Knowledge Builder."""


class DocumentNotFoundError(KnowledgeBuilderError):
    """Raised when requested document does not exist."""


class UnsupportedFileTypeError(KnowledgeBuilderError):
    """Raised when file type is not supported."""


class PipelineStageError(KnowledgeBuilderError):
    """Raised when a pipeline stage fails."""