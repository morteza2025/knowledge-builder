"""
Domain models for raw document structure.

These models represent a PDF (or other source document) after text extraction,
before any educational/knowledge interpretation happens. Pure data — no
FastAPI, no pdfplumber, no OCR library imports allowed here (Clean
Architecture: Domain has zero framework dependencies).
"""

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class BlockType(str, Enum):
    heading = "heading"
    paragraph = "paragraph"
    table = "table"
    image = "image"
    formula = "formula"
    unknown = "unknown"


class ExtractionMethod(str, Enum):
    """How a page's text was produced. Kept as an enum (not a free string) so
    downstream consumers (e.g. the future Knowledge Graph confidence scoring)
    can reason about extraction quality without string-matching."""

    pdfplumber_positional = "pdfplumber_positional"
    ocr_tesseract = "ocr_tesseract"
    failed = "failed"
    empty = "empty"


class SourceRef(BaseModel):
    """Traceability pointer back to the exact origin of a piece of content.
    Design Principle #10 (Source Traceability) requires every derived object
    to carry one of these."""

    filename: str
    page: Optional[int] = None
    block_id: Optional[str] = None


class DocumentMetadata(BaseModel):
    filename: str
    title: Optional[str] = None
    course: Optional[str] = None
    grade: Optional[str] = None
    language: str = "fa"
    total_pages: int = 0


class DocumentBlock(BaseModel):
    id: str
    type: BlockType = BlockType.paragraph
    text: str = ""
    page: Optional[int] = None
    source: Optional[SourceRef] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentPage(BaseModel):
    page_number: int
    text: str = ""
    char_count: int = 0
    extraction_method: ExtractionMethod = ExtractionMethod.empty
    needs_review: bool = False
    warnings: list[str] = Field(default_factory=list)
    blocks: list[DocumentBlock] = Field(default_factory=list)


class KnowledgeDocument(BaseModel):
    """The output of the extraction pipeline for a single source document.
    This is document-scoped. Concepts and relationships that span multiple
    documents live in KnowledgeGraph (see app/domain/knowledge.py), not here.
    """

    metadata: DocumentMetadata
    pages: list[DocumentPage] = Field(default_factory=list)
    blocks: list[DocumentBlock] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    processing_version: str = "1.0.0"

    @property
    def pages_with_text(self) -> int:
        return sum(1 for page in self.pages if page.char_count > 0)

    @property
    def pages_without_text(self) -> int:
        return sum(1 for page in self.pages if page.char_count == 0)

    @property
    def pages_needing_review(self) -> int:
        return sum(1 for page in self.pages if page.needs_review)
