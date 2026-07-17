from __future__ import annotations

from telegram import Update
from telegram.ext import Application, ApplicationBuilder, CommandHandler, MessageHandler, filters

from app.api.dependencies import get_process_book_use_case
from app.core.logger import app_logger
from app.core.settings import Settings
from app.interfaces.telegram.cleanup import (
    cleanup_expired_job_artifacts,
    cleanup_old_runtime_files,
)
from app.interfaces.telegram.document_ingestion import TelegramDocumentIngestion
from app.interfaces.telegram.handlers import TelegramHandlers
from app.interfaces.telegram.job_queue import TelegramJobQueue
from app.interfaces.telegram.job_repository import SQLiteJobRepository
from app.interfaces.telegram.result_delivery import TelegramResultDelivery
from app.interfaces.telegram.security import AuthorizationPolicy
from app.interfaces.telegram.worker import TelegramJobWorker


class TelegramRuntime:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.repository = SQLiteJobRepository(settings.telegram_database_path)
        self.authorization = AuthorizationPolicy(
            settings.telegram_allowed_user_ids,
            settings.telegram_allow_all_development,
        )
        self.worker = TelegramJobWorker(
            settings=settings,
            repository=self.repository,
            ingestion=TelegramDocumentIngestion(settings),
            delivery=TelegramResultDelivery(settings),
            use_case_factory=get_process_book_use_case,
        )
        self.queue = TelegramJobQueue(
            self.repository,
            self.worker,
            maxsize=settings.telegram_job_queue_size,
            concurrency=settings.telegram_processing_concurrency,
        )
        self.handlers = TelegramHandlers(
            settings=settings,
            repository=self.repository,
            queue=self.queue,
            authorization=self.authorization,
        )

    async def start(self, application: Application) -> None:
        from datetime import datetime, timedelta, timezone

        removed = cleanup_old_runtime_files(
            (
                self.settings.telegram_input_dir,
                self.settings.telegram_work_dir / "archives",
            ),
            self.settings.telegram_output_retention_hours,
        )
        cutoff = datetime.now(timezone.utc) - timedelta(
            hours=self.settings.telegram_output_retention_hours
        )
        removed += cleanup_expired_job_artifacts(
            self.repository.terminal_before(cutoff),
            (
                self.settings.telegram_input_dir,
                self.settings.json_output_dir,
                self.settings.markdown_output_dir,
                self.settings.django_seed_output_dir,
                self.settings.knowledge_graph_output_dir,
            ),
        )
        app_logger.info("Telegram runtime cleanup removed %s file(s)", removed)
        await self.queue.start(application.bot)

    async def stop(self, application: Application) -> None:
        await self.queue.stop()
        self.repository.close()


def validate_runtime_configuration(settings: Settings) -> None:
    if settings.telegram_bot_token is None:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required to start the bot")
    policy = AuthorizationPolicy(
        settings.telegram_allowed_user_ids,
        settings.telegram_allow_all_development,
    )
    if policy.is_fail_closed:
        raise RuntimeError(
            "TELEGRAM_ALLOWED_USER_IDS must contain at least one valid user ID "
            "unless TELEGRAM_ALLOW_ALL_DEVELOPMENT=true"
        )


def build_telegram_application(settings: Settings) -> tuple[Application, TelegramRuntime]:
    validate_runtime_configuration(settings)
    runtime = TelegramRuntime(settings)
    token = settings.telegram_bot_token
    assert token is not None

    builder = (
        ApplicationBuilder()
        .token(token.get_secret_value())
        .base_url(settings.telegram_bot_api_base_url)
        .base_file_url(settings.telegram_bot_api_file_url)
        .local_mode(settings.telegram_local_mode)
        .concurrent_updates(False)
        .post_init(runtime.start)
        .post_shutdown(runtime.stop)
    )
    application = builder.build()
    application.add_handler(CommandHandler("start", runtime.handlers.start))
    application.add_handler(CommandHandler("help", runtime.handlers.help))
    application.add_handler(CommandHandler("status", runtime.handlers.status))
    application.add_handler(CommandHandler("cancel", runtime.handlers.cancel))
    application.add_handler(
        MessageHandler(filters.Document.PDF, runtime.handlers.document)
    )
    application.add_handler(
        MessageHandler(filters.Document.ALL, runtime.handlers.unknown_document)
    )
    return application, runtime


def run_bot(settings: Settings) -> None:
    application, _runtime = build_telegram_application(settings)
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=False,
        close_loop=True,
    )
