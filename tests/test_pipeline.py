from pathlib import Path

from app.application.ports import ExporterPort, TextExtractionPort
from app.application.use_cases.process_book import (
    ProcessingContext,
    build_default_process_book_use_case,
)
from app.domain.document import DocumentPage, ExtractionMethod, KnowledgeDocument


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
