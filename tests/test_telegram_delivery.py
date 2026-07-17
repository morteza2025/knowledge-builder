import asyncio
from pathlib import Path

import pytest

from app.core.settings import Settings
from app.interfaces.telegram.job_models import JobState, TelegramJob
from app.interfaces.telegram.result_delivery import TelegramResultDelivery
from app.interfaces.telegram.security import TelegramSecurityError


class FakeBot:
    def __init__(self):
        self.messages = []
        self.documents = []

    async def send_message(self, chat_id, text):
        self.messages.append((chat_id, text))

    async def send_document(self, **kwargs):
        self.documents.append(kwargs)


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        telegram_work_dir=tmp_path / "work",
        json_output_dir=tmp_path / "json",
        markdown_output_dir=tmp_path / "markdown",
        django_seed_output_dir=tmp_path / "seed",
        knowledge_graph_output_dir=tmp_path / "graph",
        telegram_max_file_size_mb=10,
    )


def _job(paths):
    return TelegramJob(
        user_id=123,
        chat_id=123,
        source_message_id=1,
        filename="book.pdf",
        telegram_file_id="file-id",
        telegram_file_unique_id="unique",
        file_size=10,
        source_type="direct",
        state=JobState.completed,
        output_paths=paths,
        total_pages=2,
        ocr_page_count=1,
    )


def test_successful_json_and_markdown_delivery(tmp_path):
    settings = _settings(tmp_path)
    json_path = settings.json_output_dir / "book.json"
    markdown_path = settings.markdown_output_dir / "book.md"
    json_path.parent.mkdir()
    markdown_path.parent.mkdir()
    json_path.write_text("{}", encoding="utf-8")
    markdown_path.write_text("# book", encoding="utf-8")
    bot = FakeBot()

    asyncio.run(
        TelegramResultDelivery(settings).deliver(bot, _job([json_path, markdown_path]))
    )

    assert len(bot.documents) == 2
    assert {item["filename"] for item in bot.documents} == {"book.json", "book.md"}
    assert "پردازش با موفقیت" in bot.messages[0][1]


def test_output_path_outside_export_roots_is_rejected(tmp_path):
    settings = _settings(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    with pytest.raises(TelegramSecurityError, match="outside"):
        asyncio.run(TelegramResultDelivery(settings).deliver(FakeBot(), _job([outside])))


def test_many_outputs_are_sent_as_safe_zip_without_original_pdf(tmp_path):
    settings = _settings(tmp_path)
    settings.json_output_dir.mkdir()
    paths = []
    for index in range(5):
        path = settings.json_output_dir / f"output-{index}.json"
        path.write_text("{}", encoding="utf-8")
        paths.append(path)
    bot = FakeBot()

    asyncio.run(TelegramResultDelivery(settings).deliver(bot, _job(paths)))

    assert len(bot.documents) == 1
    archive = Path(bot.documents[0]["document"])
    assert archive.name.endswith(".telegram.zip")
    assert archive.is_file()
