"""
Ports (interfaces) that the application layer depends on and the
infrastructure layer implements. This is what makes the pipeline
"Framework Independent" and "LLM Independent" (Design Principles #3, #4):
swap pdfplumber for Docling, or Tesseract for a cloud OCR API, or a
regex-based relation extractor for an LLM-based one, by writing a new
adapter — no changes needed in application or domain code.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from PIL import Image

from app.domain.concept import ConceptRelationship, EducationalConcept
from app.domain.document import DocumentPage, KnowledgeDocument


class TextExtractionPort(ABC):
    """Produces per-page text + metadata from a source PDF."""

    @abstractmethod
    def extract_pages(self, pdf_path: Path) -> list[DocumentPage]:
        ...


class OCREnginePort(ABC):
    """Recovers text from a rendered page image, for pages where the normal
    text layer is missing or too sparse (scanned books, photographed pages).
    """

    @abstractmethod
    def is_available(self) -> bool:
        ...

    @abstractmethod
    def extract_text(self, image: Image.Image, language: str) -> str:
        ...


class ExporterPort(ABC):
    """Writes a KnowledgeDocument to some output format/location."""

    @abstractmethod
    def export(self, document: KnowledgeDocument) -> Path:
        ...


class ConceptRelationExtractorPort(ABC):
    """Future use (Knowledge Graph roadmap): given a KnowledgeDocument,
    propose EducationalConcepts and ConceptRelationships between them.

    Not implemented yet — this is the seam where an LLM-backed adapter will
    plug in later without the domain or application layer knowing an LLM is
    involved at all.
    """

    @abstractmethod
    def extract(
        self, document: KnowledgeDocument
    ) -> tuple[list[EducationalConcept], list[ConceptRelationship]]:
        ...


class ConceptMergePort(ABC):
    """Future use (Semantic Memory roadmap): merge a newly extracted concept
    into an existing KnowledgeGraph if it's the same canonical concept as one
    already present (e.g. "Society" from Book A and Book B), otherwise add it
    as new. Not implemented yet.
    """

    @abstractmethod
    def find_matching_concept_id(
        self, candidate: EducationalConcept, existing: list[EducationalConcept]
    ) -> Optional[str]:
        ...
