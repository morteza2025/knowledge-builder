from pathlib import Path

from app.application.ports import (
    ConceptRelationExtractorPort,
    ExporterPort,
    TextExtractionPort,
)
from app.application.use_cases.process_book import (
    ProcessingContext,
    build_default_process_book_use_case,
)
from app.domain.concept import EducationalConcept
from app.domain.document import (
    BlockType,
    DocumentBlock,
    DocumentPage,
    ExtractionMethod,
    KnowledgeDocument,
)
from app.infrastructure.exporter.knowledge_graph_exporter import KnowledgeGraphExporter


class FakeTextExtractor(TextExtractionPort):
    def extract_pages(self, pdf_path: Path) -> list[DocumentPage]:
        return [
            DocumentPage(
                page_number=1,
                text="متن نمونه",
                char_count=9,
                extraction_method=ExtractionMethod.pdfplumber_positional,
            ),
            DocumentPage(
                page_number=2,
                text="",
                char_count=0,
                extraction_method=ExtractionMethod.empty,
                needs_review=True,
            ),
        ]


class FakeExporter(ExporterPort):
    def __init__(self):
        self.exported: KnowledgeDocument | None = None

    def export(self, document: KnowledgeDocument) -> Path:
        self.exported = document
        return Path("/fake/output.json")


def test_process_book_pipeline_builds_document_and_exports():
    fake_exporter = FakeExporter()
    use_case = build_default_process_book_use_case(
        text_extractor=FakeTextExtractor(),
        exporters=[fake_exporter],
    )

    context = ProcessingContext(
        pdf_path=Path("fake.pdf"),
        filename="fake.pdf",
        book_title="کتاب نمونه",
    )

    result = use_case.execute(context)

    assert result.document is not None
    assert result.document.metadata.title == "کتاب نمونه"
    assert result.document.pages_with_text == 1
    assert result.document.pages_without_text == 1
    assert result.document.pages_needing_review == 1
    assert any("no extractable text" in w for w in result.document.warnings)

    assert fake_exporter.exported is result.document
    assert "FakeExporter" in result.export_paths


def test_concept_extraction_is_skipped_by_default_even_with_a_fake_extractor():
    """extract_concepts defaults to False -- the stage must not run at all,
    not even calling the (fake, harmless) extractor."""

    class ExplodingConceptExtractor(ConceptRelationExtractorPort):
        def extract(self, lesson):
            raise AssertionError("should never be called when extract_concepts=False")

    use_case = build_default_process_book_use_case(
        text_extractor=FakeTextExtractor(),
        exporters=[FakeExporter()],
        concept_extractor=ExplodingConceptExtractor(),
    )

    context = ProcessingContext(
        pdf_path=Path("fake.pdf"), filename="fake.pdf", book_title="کتاب نمونه"
    )
    result = use_case.execute(context)

    assert result.knowledge_graph is None
    assert "KnowledgeGraphExporter" not in result.export_paths


class _OutlinedTextExtractor(TextExtractionPort):
    """Produces a small but complete synthetic book: a TOC page plus one
    chapter/lesson, enough for BuildOutlineStage and build_lesson_extracts
    to succeed for real (not mocked) — so this test exercises the actual
    outline -> lesson-extract -> concept-extraction wiring end to end."""

    def extract_pages(self, pdf_path: Path) -> list[DocumentPage]:
        toc_text = (
            "فهرست\n"
            "فصل اول: عنوان فصل .............. 1\n"
            "درس اول: عنوان درس .............. 1\n"
        )
        return [
            DocumentPage(
                page_number=1,
                text=toc_text,
                char_count=len(toc_text),
                extraction_method=ExtractionMethod.pdfplumber_positional,
                blocks=[
                    DocumentBlock(id="1-1", type=BlockType.heading, text="فهرست", page=1),
                    DocumentBlock(
                        id="1-2",
                        type=BlockType.paragraph,
                        text=toc_text.split("\n", 1)[1],
                        page=1,
                    ),
                ],
            ),
            DocumentPage(
                page_number=2,
                text="فصل اول\nمتن فصل",
                char_count=20,
                extraction_method=ExtractionMethod.pdfplumber_positional,
                blocks=[
                    DocumentBlock(id="2-1", type=BlockType.heading, text="فصل اول", page=2),
                    DocumentBlock(id="2-2", type=BlockType.paragraph, text="متن فصل", page=2),
                ],
            ),
            DocumentPage(
                page_number=3,
                text="متن نمونه‌ی درس یک درباره‌ی یک مفهوم آموزشی.",
                char_count=40,
                extraction_method=ExtractionMethod.pdfplumber_positional,
                blocks=[
                    DocumentBlock(
                        id="3-1",
                        type=BlockType.paragraph,
                        text="متن نمونه‌ی درس یک درباره‌ی یک مفهوم آموزشی.",
                        page=3,
                    )
                ],
            ),
        ]


class FakeConceptExtractor(ConceptRelationExtractorPort):
    def __init__(self):
        self.calls: list = []

    def extract(self, lesson):
        self.calls.append(lesson)
        concept = EducationalConcept(
            id=f"fake-{lesson.lesson_order}", title=f"مفهوم درس {lesson.lesson_order}"
        )
        return [concept], []


def test_concept_extraction_runs_end_to_end_when_requested(tmp_path):
    fake_concept_extractor = FakeConceptExtractor()

    use_case = build_default_process_book_use_case(
        text_extractor=_OutlinedTextExtractor(),
        exporters=[FakeExporter()],
        concept_extractor=fake_concept_extractor,
        knowledge_graph_exporter=KnowledgeGraphExporter(output_dir=tmp_path),
    )

    context = ProcessingContext(
        pdf_path=Path("fake.pdf"),
        filename="fake.pdf",
        book_title="کتاب نمونه",
        extract_concepts=True,
    )
    result = use_case.execute(context)

    assert len(fake_concept_extractor.calls) == 1  # exactly one lesson resolved
    lesson_called = fake_concept_extractor.calls[0]
    assert lesson_called.lesson_order == 1
    assert lesson_called.start_page == 2  # printed page 1 + resolved offset 1

    assert result.knowledge_graph is not None
    assert len(result.knowledge_graph.concepts) == 1
    assert result.knowledge_graph.concepts[0].title == "مفهوم درس 1"

    assert "KnowledgeGraphExporter" in result.export_paths
    assert (tmp_path / "fake.graph.json").exists()


def test_concept_extraction_skips_gracefully_when_no_outline_is_found():
    use_case = build_default_process_book_use_case(
        text_extractor=FakeTextExtractor(),  # no TOC page at all
        exporters=[FakeExporter()],
        concept_extractor=FakeConceptExtractor(),
    )

    context = ProcessingContext(
        pdf_path=Path("fake.pdf"),
        filename="fake.pdf",
        book_title="کتاب نمونه",
        extract_concepts=True,
    )
    result = use_case.execute(context)

    assert result.knowledge_graph is None
    assert any("no table-of-contents outline" in w for w in result.document.warnings)


def test_concept_extraction_does_not_export_an_empty_graph_when_never_configured():
    from app.application.ports import ConceptRelationExtractorPort
    from app.core.exceptions import ConceptExtractionNotConfiguredError

    class NotConfiguredExtractor(ConceptRelationExtractorPort):
        def extract(self, lesson):
            raise ConceptExtractionNotConfiguredError("no key configured")

    use_case = build_default_process_book_use_case(
        text_extractor=_OutlinedTextExtractor(),
        exporters=[FakeExporter()],
        concept_extractor=NotConfiguredExtractor(),
    )

    context = ProcessingContext(
        pdf_path=Path("fake.pdf"),
        filename="fake.pdf",
        book_title="کتاب نمونه",
        extract_concepts=True,
    )
    result = use_case.execute(context)

    assert result.knowledge_graph is None
    assert "KnowledgeGraphExporter" not in result.export_paths
    assert any("Concept extraction skipped" in w for w in result.document.warnings)
