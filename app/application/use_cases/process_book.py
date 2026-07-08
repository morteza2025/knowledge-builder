"""
The ProcessBook use case: turn one PDF into a KnowledgeDocument, then export
it. Implemented as a Pipeline of named stages (see
app/application/pipeline/) so future stages (concept extraction, relationship
inference, semantic-memory merge) can be inserted without touching this
orchestration logic or the stages that already work.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from app.application.pipeline.pipeline import Pipeline
from app.application.pipeline.stage import PipelineStage
from app.application.ports import ExporterPort, TextExtractionPort
from app.application.use_cases.build_outline import build_outline
from app.core.settings import settings
from app.domain.document import DocumentMetadata, KnowledgeDocument
from app.domain.outline import BookOutline
from app.infrastructure.exporter.django_seed_exporter import DjangoSeedExporter


@dataclass
class ProcessingContext:
    pdf_path: Path
    filename: str
    book_title: str
    course: Optional[str] = None
    grade: Optional[str] = None
    use_ocr: bool = True

    pages: list = field(default_factory=list)
    document: Optional[KnowledgeDocument] = None
    outline: Optional[BookOutline] = None
    export_paths: dict[str, Path] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


class ExtractPagesStage(PipelineStage[ProcessingContext]):
    name = "extract_pages"

    def __init__(self, text_extractor: TextExtractionPort):
        self._text_extractor = text_extractor

    def run(self, context: ProcessingContext) -> ProcessingContext:
        context.pages = self._text_extractor.extract_pages(context.pdf_path)
        return context


class BuildDocumentStage(PipelineStage[ProcessingContext]):
    name = "build_document"

    def run(self, context: ProcessingContext) -> ProcessingContext:
        metadata = DocumentMetadata(
            filename=context.filename,
            title=context.book_title,
            course=context.course,
            grade=context.grade,
            language=settings.default_language,
            total_pages=len(context.pages),
        )

        warnings = list(context.warnings)
        pages_without_text = sum(1 for p in context.pages if p.char_count == 0)
        if pages_without_text:
            warnings.append(
                f"{pages_without_text} page(s) had no extractable text even "
                "after OCR fallback and may need manual review."
            )

        context.document = KnowledgeDocument(
            metadata=metadata,
            pages=context.pages,
            warnings=warnings,
        )
        return context


class BuildOutlineStage(PipelineStage[ProcessingContext]):
    """Optional enrichment: parses the book's own table-of-contents page(s)
    into a chapter/lesson/subtopic outline. Not every source document has a
    TOC page (handouts, supplementary sheets) — when none is found, this is
    a no-op, not an error."""

    name = "build_outline"

    def run(self, context: ProcessingContext) -> ProcessingContext:
        assert context.document is not None, "BuildDocumentStage must run first"
        context.outline = build_outline(context.document)
        return context


class ExportStage(PipelineStage[ProcessingContext]):
    name = "export"

    def __init__(self, exporters: list[ExporterPort]):
        self._exporters = exporters

    def run(self, context: ProcessingContext) -> ProcessingContext:
        assert context.document is not None, "BuildDocumentStage must run first"
        for exporter in self._exporters:
            path = exporter.export(context.document)
            context.export_paths[type(exporter).__name__] = path
        return context


class ExportOutlineStage(PipelineStage[ProcessingContext]):
    name = "export_outline"

    def __init__(self, outline_exporter: DjangoSeedExporter):
        self._outline_exporter = outline_exporter

    def run(self, context: ProcessingContext) -> ProcessingContext:
        if context.outline is not None:
            assert context.document is not None
            path = self._outline_exporter.export(
                context.outline, context.document.metadata
            )
            context.export_paths["DjangoSeedExporter"] = path
        return context


class ProcessBookUseCase:
    def __init__(self, pipeline: Pipeline[ProcessingContext]):
        self._pipeline = pipeline

    def execute(self, context: ProcessingContext) -> ProcessingContext:
        return self._pipeline.run(context)


def build_default_process_book_use_case(
    text_extractor: TextExtractionPort,
    exporters: list[ExporterPort],
    outline_exporter: Optional[DjangoSeedExporter] = None,
) -> ProcessBookUseCase:
    """Wires the standard Extract -> Build -> BuildOutline -> Export ->
    ExportOutline pipeline. This is the one place in the whole codebase
    that knows which concrete adapters are in use — everything upstream
    only ever sees the ports."""

    pipeline: Pipeline[ProcessingContext] = Pipeline()
    pipeline.add(ExtractPagesStage(text_extractor))
    pipeline.add(BuildDocumentStage())
    pipeline.add(BuildOutlineStage())
    pipeline.add(ExportStage(exporters))
    pipeline.add(ExportOutlineStage(outline_exporter or DjangoSeedExporter()))

    return ProcessBookUseCase(pipeline)
