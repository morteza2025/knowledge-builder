import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.settings import Settings
from app.interfaces.telegram.document_ingestion import TelegramDocumentIngestion
from app.interfaces.telegram.handlers import TelegramHandlers
from app.interfaces.telegram.job_models import TelegramJob
from app.interfaces.telegram.job_repository import SQLiteJobRepository
from app.interfaces.telegram.security import AuthorizationPolicy, TelegramSecurityError


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        telegram_bot_token="123456:OBVIOUSLY_FAKE_TEST_TOKEN",
        telegram_allowed_user_ids_csv="123",
        telegram_input_dir=tmp_path / "input",
        telegram_work_dir=tmp_path / "work",
        telegram_min_free_disk_space_mb=1,
        telegram_max_file_size_mb=10,
        telegram_download_chunk_size=4,
    )


def _job() -> TelegramJob:
    return TelegramJob(
        user_id=123,
        chat_id=123,
        source_message_id=1,
        filename="book.pdf",
        telegram_file_id="file-id",
        telegram_file_unique_id="unique",
        file_size=14,
        source_type="direct",
    )


def test_local_absolute_path_is_copied_atomically_and_hashed(tmp_path):
    source = tmp_path / "source.pdf"
    source.write_bytes(b"%PDF-1.4\n%%EOF")

    class Bot:
        async def get_file(self, file_id):
            return SimpleNamespace(file_path=str(source.resolve()))

    async def scenario():
        destination, digest = await TelegramDocumentIngestion(
            _settings(tmp_path)
        ).ingest(_job(), Bot())
        assert destination.read_bytes() == source.read_bytes()
        assert len(digest) == 64
        assert not destination.with_suffix(".pdf.part").exists()

    asyncio.run(scenario())


def test_partial_file_is_removed_after_download_failure(tmp_path):
    class FailingIngestion(TelegramDocumentIngestion):
        async def _stream_remote(self, file_path, destination, max_bytes):
            destination.write_bytes(b"partial")
            raise OSError("simulated download failure")

    class Bot:
        async def get_file(self, file_id):
            return SimpleNamespace(file_path="documents/book.pdf")

    settings = _settings(tmp_path)

    async def scenario():
        with pytest.raises(OSError):
            await FailingIngestion(settings).ingest(_job(), Bot())
        assert list(settings.telegram_input_dir.glob("*.part")) == []

    asyncio.run(scenario())


def test_streamed_fallback_writes_chunks_without_buffering_whole_file(tmp_path):
    chunks = [b"%PDF", b"-1.4", b"\n%%EOF"]

    class Response:
        def raise_for_status(self):
            return None

        async def aiter_bytes(self, chunk_size):
            assert chunk_size == 4
            for chunk in chunks:
                yield chunk

    class StreamContext:
        async def __aenter__(self):
            return Response()

        async def __aexit__(self, *args):
            return False

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def stream(self, method, url):
            assert method == "GET"
            assert "OBVIOUSLY_FAKE_TEST_TOKEN" in url
            return StreamContext()

    class ClientFactory:
        def __call__(self, **kwargs):
            return Client()

    class Bot:
        async def get_file(self, file_id):
            return SimpleNamespace(file_path="documents/book.pdf")

    settings = _settings(tmp_path)

    async def scenario():
        ingestion = TelegramDocumentIngestion(
            settings, http_client_factory=ClientFactory()
        )
        destination, digest = await ingestion.ingest(_job(), Bot())
        assert destination.read_bytes() == b"".join(chunks)
        assert len(digest) == 64

    asyncio.run(scenario())


def test_symlink_local_source_is_rejected_when_supported(tmp_path):
    source = tmp_path / "source.pdf"
    source.write_bytes(b"%PDF-1.4\n%%EOF")
    link = tmp_path / "link.pdf"
    try:
        link.symlink_to(source)
    except OSError:
        pytest.skip("symlink creation is unavailable on this Windows account")

    class Bot:
        async def get_file(self, file_id):
            return SimpleNamespace(file_path=str(link.absolute()))

    async def scenario():
        with pytest.raises(TelegramSecurityError, match="regular file"):
            await TelegramDocumentIngestion(_settings(tmp_path)).ingest(_job(), Bot())

    asyncio.run(scenario())


class FakeStatusMessage:
    def __init__(self, message_id=99):
        self.message_id = message_id
        self.edits = []

    async def edit_text(self, text):
        self.edits.append(text)


class FakeMessage:
    def __init__(self, document, forwarded=False):
        self.document = document
        self.caption = "title: جامعه‌شناسی ۱"
        self.message_id = 10
        self.forward_origin = object() if forwarded else None
        self.forward_date = None
        self.replies = []

    async def reply_text(self, text):
        self.replies.append(text)
        return FakeStatusMessage()


class FakeQueue:
    def __init__(self):
        self.submitted = []

    def submit(self, job_id):
        self.submitted.append(job_id)


def _document():
    return SimpleNamespace(
        file_name="book.pdf",
        mime_type="application/pdf",
        file_size=14,
        file_id="file-id",
        file_unique_id="unique",
    )


def _update(message, user_id=123):
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id),
        effective_chat=SimpleNamespace(id=user_id),
        effective_message=message,
    )


@pytest.mark.parametrize("forwarded", [False, True])
def test_direct_and_forwarded_documents_share_the_same_acceptance_path(
    tmp_path, forwarded
):
    settings = _settings(tmp_path)
    repository = SQLiteJobRepository(tmp_path / "jobs.sqlite3")
    queue = FakeQueue()
    handlers = TelegramHandlers(
        settings=settings,
        repository=repository,
        queue=queue,
        authorization=AuthorizationPolicy((123,)),
    )
    message = FakeMessage(_document(), forwarded=forwarded)

    asyncio.run(handlers.document(_update(message), None))

    job = repository.latest_for_user(123)
    assert job is not None
    assert job.source_type == ("forwarded" if forwarded else "direct")
    assert job.book_title == "جامعه‌شناسی ۱"
    assert queue.submitted == [job.id]
    repository.close()


def test_unauthorized_user_is_rejected_before_queue_or_download(tmp_path):
    settings = _settings(tmp_path)
    repository = SQLiteJobRepository(tmp_path / "jobs.sqlite3")
    queue = FakeQueue()
    handlers = TelegramHandlers(
        settings=settings,
        repository=repository,
        queue=queue,
        authorization=AuthorizationPolicy((123,)),
    )
    message = FakeMessage(_document())

    asyncio.run(handlers.document(_update(message, user_id=999), None))

    assert queue.submitted == []
    assert repository.latest_for_user(999) is None
    repository.close()
