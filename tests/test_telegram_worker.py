import asyncio
from pathlib import Path

from app.core.settings import Settings
from app.domain.document import (
    DocumentMetadata,
    DocumentPage,
    ExtractionMethod,
    KnowledgeDocument,
)
from app.interfaces.telegram.job_models import JobState, TelegramJob
from app.interfaces.telegram.job_repository import SQLiteJobRepository
from app.interfaces.telegram.worker import TelegramJobWorker


class FakeIngestion:
    def __init__(self, path):
        self.path = path

    async def ingest(self, job, bot):
        return self.path, "a" * 64


class FakeDelivery:
    def __init__(self):
        self.jobs = []

    async def deliver(self, bot, job):
        self.jobs.append(job)


class FakeBot:
    def __init__(self):
        self.edits = []

    async def edit_message_text(self, **kwargs):
        self.edits.append(kwargs)


class FakeUseCase:
    def __init__(self, output_path):
        self.output_path = output_path
        self.context = None

    def execute(self, context):
        self.context = context
        context.progress_callback("extract_pages")
        context.document = KnowledgeDocument(
            metadata=DocumentMetadata(filename=context.filename, total_pages=2),
            pages=[
                DocumentPage(
                    page_number=1,
                    text="متن",
                    char_count=3,
                    extraction_method=ExtractionMethod.pdfplumber_positional,
                ),
                DocumentPage(
                    page_number=2,
                    text="متن OCR",
                    char_count=7,
                    extraction_method=ExtractionMethod.ocr_tesseract,
                ),
            ],
            warnings=["sample warning"],
        )
        context.export_paths = {"JsonExporter": self.output_path}
        return context


def test_worker_invokes_existing_use_case_and_preserves_results(tmp_path):
    input_path = tmp_path / "input" / "job-book.pdf"
    input_path.parent.mkdir()
    input_path.write_bytes(b"%PDF-1.4\n%%EOF")
    output_path = tmp_path / "json" / "job-book.json"
    output_path.parent.mkdir()
    output_path.write_text("{}", encoding="utf-8")
    settings = Settings(
        _env_file=None,
        telegram_input_dir=input_path.parent,
        telegram_work_dir=tmp_path / "work",
        telegram_processing_timeout_seconds=10,
        telegram_status_update_interval_seconds=1,
    )
    repo = SQLiteJobRepository(tmp_path / "jobs.sqlite3")
    job = repo.create(
        TelegramJob(
            user_id=123,
            chat_id=123,
            source_message_id=1,
            filename="book.pdf",
            telegram_file_id="file-id",
            telegram_file_unique_id="unique",
            file_size=14,
            source_type="direct",
            book_title="کتاب",
            state=JobState.queued,
            status_message_id=99,
        )
    )
    use_case = FakeUseCase(output_path)
    delivery = FakeDelivery()
    worker = TelegramJobWorker(
        settings=settings,
        repository=repo,
        ingestion=FakeIngestion(input_path),
        delivery=delivery,
        use_case_factory=lambda: use_case,
    )

    result = asyncio.run(worker.process(job, FakeBot()))

    assert result.state == JobState.completed
    assert result.total_pages == 2
    assert result.processed_pages == 2
    assert result.ocr_page_count == 1
    assert result.warnings == ["sample warning"]
    assert result.output_paths == [output_path]
    assert use_case.context.use_ocr is True
    assert use_case.context.book_title == "کتاب"
    assert delivery.jobs[0].id == job.id
    repo.close()


def test_worker_failure_does_not_expose_exception_details(tmp_path):
    class ExplodingUseCase:
        def execute(self, context):
            raise RuntimeError("C:\\secret\\path token=do-not-show")

    input_path = tmp_path / "book.pdf"
    input_path.write_bytes(b"%PDF-1.4\n%%EOF")
    settings = Settings(
        _env_file=None,
        telegram_input_dir=tmp_path / "input",
        telegram_work_dir=tmp_path / "work",
        telegram_processing_timeout_seconds=10,
    )
    repo = SQLiteJobRepository(tmp_path / "jobs.sqlite3")
    job = repo.create(
        TelegramJob(
            user_id=123,
            chat_id=123,
            source_message_id=1,
            filename="book.pdf",
            telegram_file_id="file-id",
            telegram_file_unique_id="unique",
            file_size=14,
            source_type="direct",
            state=JobState.queued,
        )
    )
    worker = TelegramJobWorker(
        settings=settings,
        repository=repo,
        ingestion=FakeIngestion(input_path),
        delivery=FakeDelivery(),
        use_case_factory=lambda: ExplodingUseCase(),
    )

    result = asyncio.run(worker.process(job, FakeBot()))

    assert result.state == JobState.failed
    assert "secret" not in result.error_summary
    assert "path" not in result.error_summary
    repo.close()
