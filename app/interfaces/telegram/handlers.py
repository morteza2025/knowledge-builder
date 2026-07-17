from __future__ import annotations

from app.core.logger import app_logger
from app.core.settings import Settings
from app.interfaces.telegram.caption_parser import parse_caption_metadata
from app.interfaces.telegram.job_models import JobState, TelegramJob
from app.interfaces.telegram.job_queue import QueueCapacityError, TelegramJobQueue
from app.interfaces.telegram.job_repository import SQLiteJobRepository
from app.interfaces.telegram.messages import (
    HELP_TEXT,
    NO_CANCELLABLE_JOB_TEXT,
    NO_JOB_TEXT,
    NON_PDF_TEXT,
    QUEUE_FULL_TEXT,
    START_TEXT,
    UNAUTHORIZED_TEXT,
    format_status,
)
from app.interfaces.telegram.security import (
    AuthorizationPolicy,
    TelegramSecurityError,
    require_free_disk_space,
    sanitize_pdf_filename,
    validate_document_metadata,
)


class TelegramHandlers:
    def __init__(
        self,
        *,
        settings: Settings,
        repository: SQLiteJobRepository,
        queue: TelegramJobQueue,
        authorization: AuthorizationPolicy,
    ):
        self._settings = settings
        self._repository = repository
        self._queue = queue
        self._authorization = authorization

    async def start(self, update, context) -> None:
        if not await self._authorize(update):
            return
        await update.effective_message.reply_text(START_TEXT)

    async def help(self, update, context) -> None:
        if not await self._authorize(update):
            return
        await update.effective_message.reply_text(HELP_TEXT)

    async def status(self, update, context) -> None:
        if not await self._authorize(update):
            return
        user_id = update.effective_user.id
        job = self._repository.latest_for_user(user_id)
        if job is None:
            await update.effective_message.reply_text(NO_JOB_TEXT)
            return
        await update.effective_message.reply_text(
            format_status(job, self._repository.queue_position(job.id))
        )

    async def cancel(self, update, context) -> None:
        if not await self._authorize(update):
            return
        user_id = update.effective_user.id
        job = self._repository.latest_for_user(user_id)
        if job is None:
            await update.effective_message.reply_text(NO_CANCELLABLE_JOB_TEXT)
            return
        cancelled = self._repository.request_cancel(job.id, user_id)
        if cancelled is None:
            await update.effective_message.reply_text(NO_CANCELLABLE_JOB_TEXT)
            return
        if cancelled.state == JobState.cancelled:
            text = "🛑 کار در صف لغو شد."
        else:
            text = "🛑 درخواست لغو ثبت شد؛ پردازش در نزدیک‌ترین مرز امن متوقف می‌شود."
        await update.effective_message.reply_text(text)

    async def document(self, update, context) -> None:
        if not await self._authorize(update):
            return
        message = update.effective_message
        document = getattr(message, "document", None)
        if document is None:
            await message.reply_text(NON_PDF_TEXT)
            return

        max_bytes = self._settings.telegram_max_file_size_mb * 1024 * 1024
        try:
            validate_document_metadata(
                filename=document.file_name,
                mime_type=document.mime_type,
                file_size=document.file_size,
                max_file_size_bytes=max_bytes,
            )
            safe_name = sanitize_pdf_filename(
                document.file_name, document.file_unique_id
            )
            reserve = self._settings.telegram_min_free_disk_space_mb * 1024 * 1024
            require_free_disk_space(
                self._settings.telegram_input_dir,
                document.file_size or 0,
                reserve,
            )
        except TelegramSecurityError:
            await message.reply_text(NON_PDF_TEXT)
            return

        duplicate = self._repository.find_active_duplicate(document.file_unique_id)
        if duplicate is not None:
            await message.reply_text(
                f"⏳ این فایل هم‌اکنون با شناسه {duplicate.id} در حال پردازش است."
            )
            return

        metadata = parse_caption_metadata(getattr(message, "caption", None))
        status_message = await message.reply_text("✅ فایل دریافت شد")
        forwarded = bool(
            getattr(message, "forward_origin", None)
            or getattr(message, "forward_date", None)
        )
        job = TelegramJob(
            user_id=update.effective_user.id,
            chat_id=update.effective_chat.id,
            source_message_id=message.message_id,
            filename=safe_name,
            telegram_file_id=document.file_id,
            telegram_file_unique_id=document.file_unique_id,
            file_size=document.file_size or 0,
            source_type="forwarded" if forwarded else "direct",
            book_title=metadata["book_title"] or safe_name.rsplit(".", 1)[0],
            course=metadata["course"],
            grade=metadata["grade"],
            state=JobState.queued,
            status_message_id=status_message.message_id,
        )
        self._repository.create(job)
        try:
            self._queue.submit(job.id)
        except QueueCapacityError:
            self._repository.update(
                job.id,
                state=JobState.failed,
                error_summary="queue is full",
            )
            await status_message.edit_text(QUEUE_FULL_TEXT)
            return

        await status_message.edit_text(
            format_status(job, self._repository.queue_position(job.id))
        )
        app_logger.info(
            "Telegram job %s queued: filename=%s size=%s source=%s",
            job.id,
            job.filename,
            job.file_size,
            job.source_type,
        )

    async def unknown_document(self, update, context) -> None:
        if not await self._authorize(update):
            return
        await update.effective_message.reply_text(NON_PDF_TEXT)

    async def _authorize(self, update) -> bool:
        user = update.effective_user
        if user is not None and self._authorization.is_allowed(user.id):
            return True
        user_id = getattr(user, "id", None)
        app_logger.warning("Denied Telegram access attempt user_id=%s", user_id)
        if update.effective_message is not None:
            await update.effective_message.reply_text(UNAUTHORIZED_TEXT)
        return False
