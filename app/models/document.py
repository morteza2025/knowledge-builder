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


class SourceRef(BaseModel):
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
    extraction_method: str = "unknown"
    warnings: list[str] = Field(default_factory=list)
    blocks: list[DocumentBlock] = Field(default_factory=list)


class EducationalConcept(BaseModel):
    id: str
    title: str
    definition: Optional[str] = None
    explanation: Optional[str] = None
    examples: list[str] = Field(default_factory=list)
    common_misconceptions: list[str] = Field(default_factory=list)
    socratic_questions: list[str] = Field(default_factory=list)
    source_refs: list[SourceRef] = Field(default_factory=list)


class KnowledgeDocument(BaseModel):
    metadata: DocumentMetadata
    pages: list[DocumentPage] = Field(default_factory=list)
    blocks: list[DocumentBlock] = Field(default_factory=list)
    concepts: list[EducationalConcept] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def pages_with_text(self) -> int:
        return sum(1 for page in self.pages if page.char_count > 0)

    @property
    def pages_without_text(self) -> int:
        return sum(1 for page in self.pages if page.char_count == 0)