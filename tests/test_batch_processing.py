from pathlib import Path

from app.application.ports import ExporterPort, TextExtractionPort
from app.application.use_cases.process_batch import ProcessBatchUseCase
from app.application.use_cases.process_book import (
    ProcessingContext,
    build_default_process_book_use_case,
)
from app.core.exceptions import PDFExtractionError
from app.domain.document import DocumentPage, ExtractionMethod


class FakeTextExtractor(TextExtractionPort):
    def __init__(self, fail_for: frozenset = frozenset()):
        self._fail_for = fail_for

    def extract_pages(self, pdf_path: Path) -> list[DocumentPage]:
        if pdf_path.name in self._fail_for:
            raise PDFExtractionError(f"simulated failure for {pdf_path.name}")
        return [
            DocumentPage(
                page_number=1,
                text="متن نمونه",
                char_count=9,
                extraction_method=ExtractionMethod.pdfplumber_positional,
            )
        ]


class FakeExporter(ExporterPort):
    def export(self, document) -> Path:
        return Path("/fake/output.json")


def _make_use_case(fail_for: frozenset = frozenset()):
    return build_default_process_book_use_case(
        text_extractor=FakeTextExtractor(fail_for=fail_for),
        exporters=[FakeExporter()],
    )


def _context(name: str) -> ProcessingContext:
    return ProcessingContext(
        pdf_path=Path(name), filename=name, book_title=f"کتاب {name}"
    )


def test_batch_isolates_one_failure_and_continues_processing_the_rest():
    use_case = _make_use_case(fail_for=frozenset({"bad.pdf"}))
    contexts = [_context("good1.pdf"), _context("bad.pdf"), _context("good2.pdf")]

    result = ProcessBatchUseCase(use_case).execute(contexts)

    assert result.total == 3
    assert result.succeeded == 2
    assert result.failed == 1

    outcomes = {item.filename: item.ok for item in result.items}
    assert outcomes == {"good1.pdf": True, "bad.pdf": False, "good2.pdf": True}

    failed_item = next(item for item in result.items if item.filename == "bad.pdf")
    assert failed_item.context is None
    assert "simulated failure" in failed_item.error

    succeeded_item = next(item for item in result.items if item.filename == "good1.pdf")
    assert succeeded_item.error is None
    assert succeeded_item.context is not None
    assert succeeded_item.context.document is not None


def test_batch_with_no_failures():
    use_case = _make_use_case()
    contexts = [_context(f"book{i}.pdf") for i in range(3)]

    result = ProcessBatchUseCase(use_case).execute(contexts)

    assert result.total == 3
    assert result.succeeded == 3
    assert result.failed == 0


def test_empty_batch_returns_zeroed_counts_not_an_error():
    use_case = _make_use_case()
    result = ProcessBatchUseCase(use_case).execute([])

    assert result.total == 0
    assert result.succeeded == 0
    assert result.failed == 0
    assert result.items == []


# --- API-level tests (real sample PDF via FastAPI TestClient) --------------


def test_batch_api_isolates_a_missing_file_from_a_real_success(tmp_path):
    """API-level test against the real sample PDF. Uses dependency_overrides
    to redirect exports to a tmp directory rather than the real outputs/ —
    otherwise this test would overwrite the committed reference sample
    output as a side effect of merely running the test suite."""

    import pytest
    from fastapi.testclient import TestClient

    from app.api.dependencies import get_process_book_use_case
    from app.application.use_cases.process_book import (
        build_default_process_book_use_case,
    )
    from app.core.settings import settings
    from app.infrastructure.exporter.django_seed_exporter import DjangoSeedExporter
    from app.infrastructure.exporter.json_exporter import JsonExporter
    from app.infrastructure.exporter.markdown_exporter import MarkdownExporter
    from app.infrastructure.pdf.pdfplumber_engine import PdfPlumberTextExtractor
    from app.main import app

    if not (settings.input_dir / "C110220.pdf").exists():
        pytest.skip("sample PDF not present")

    (tmp_path / "json").mkdir()
    (tmp_path / "markdown").mkdir()
    (tmp_path / "seed").mkdir()

    test_use_case = build_default_process_book_use_case(
        text_extractor=PdfPlumberTextExtractor(ocr_engine=None, use_ocr=False),
        exporters=[
            JsonExporter(output_dir=tmp_path / "json"),
            MarkdownExporter(output_dir=tmp_path / "markdown"),
        ],
        outline_exporter=DjangoSeedExporter(output_dir=tmp_path / "seed"),
    )

    app.dependency_overrides[get_process_book_use_case] = lambda: test_use_case
    try:
        client = TestClient(app)
        response = client.post(
            "/process/batch",
            json={
                "filenames": ["C110220.pdf", "does_not_exist.pdf"],
                "use_ocr": False,
            },
        )
    finally:
        app.dependency_overrides.pop(get_process_book_use_case, None)

    assert response.status_code == 200
    data = response.json()

    assert data["total"] == 2
    assert data["succeeded"] == 1
    assert data["failed"] == 1

    by_filename = {item["filename"]: item for item in data["items"]}
    assert by_filename["C110220.pdf"]["ok"] is True
    assert by_filename["C110220.pdf"]["result"]["total_pages"] == 152
    assert by_filename["does_not_exist.pdf"]["ok"] is False
    assert "does_not_exist.pdf" in by_filename["does_not_exist.pdf"]["error"]

    # Confirm exports actually landed in the tmp dir, not the real outputs/
    assert (tmp_path / "json" / "C110220.json").exists()


def test_batch_api_rejects_an_explicitly_empty_filenames_list():
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    response = client.post("/process/batch", json={"filenames": []})

    assert response.status_code == 422


def test_batch_api_returns_400_when_nothing_to_process(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app.core.settings import settings
    from app.main import app

    monkeypatch.setattr(settings, "input_dir", tmp_path)

    client = TestClient(app)
    response = client.post("/process/batch", json={})

    assert response.status_code == 400
