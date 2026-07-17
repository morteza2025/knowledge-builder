from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Callable

from app.application.use_cases.process_book import ProcessingContext
from app.core.exceptions import ProcessingCancelledError
from app.core.logger import app_logger
from app.core.settings import Settings
from app.domain.document import ExtractionMethod
from app.interfaces.telegram.document_ingestion import TelegramDocumentIngestion
from app.interfaces.telegram.job_models import JobState, TelegramJob, utc_now
from app.interfaces.telegram.job_repository import SQLiteJobRepository
from app.interfaces.telegram.progress import PIPELINE_STAGE_STATES
from app.interfaces.telegram.result_delivery import TelegramResultDelivery


def _safe_error_summary(exc: Exception) -> str:
    if isinstance(exc, ProcessingCancelledError):
        return "پردازش به درخواست کاربر متوقف شد"
    return "خطای پردازش فایل"


class TelegramJobWorker:
    def __init__(
        self,
        *,
        settings: Settings,
        repository: SQLiteJobRepository,
        ingestion: TelegramDocumentIngestion,
        delivery: TelegramResultDelivery,
        use_case_factory: Callable,
    ):
        self._settings = settings
        self._repository = repository
        self._ingestion = ingestion
        self._delivery = delivery
        self._use_case_factory = use_case_factory

    async def process(self, job: TelegramJob, bot) -> TelegramJob:
        try:
            self._raise_if_cancelled(job.id)
            job = self._repository.update(
                job.id, state=JobState.downloading, started_at=utc_now()
            )
            await self._edit_status(bot, job)

            local_path, digest = await self._ingestion.ingest(job, bot)
            job = self._repository.update(
                job.id,
                state=JobState.ready,
                local_input_path=local_path,
                file_sha256=digest,
            )
            self._raise_if_cancelled(job.id)

            event_loop = asyncio.get_running_loop()
            last_status_update = 0.0
            deadline = (
                time.monotonic()
                + self._settings.telegram_processing_timeout_seconds
            )
            timed_out = False

            def progress(stage_name: str) -> None:
                nonlocal last_status_update
                if self._repository.is_cancel_requested(job.id):
                    return
                state = PIPELINE_STAGE_STATES.get(stage_name, JobState.processing)
                self._repository.update(job.id, state=state)
                now = time.monotonic()
                if (
                    now - last_status_update
                    >= self._settings.telegram_status_update_interval_seconds
                ):
                    last_status_update = now
                    asyncio.run_coroutine_threadsafe(
                        self._edit_current_status(bot, job.id), event_loop
                    )

            def should_cancel() -> bool:
                nonlocal timed_out
                if self._repository.is_cancel_requested(job.id):
                    return True
                if time.monotonic() >= deadline:
                    timed_out = True
                    return True
                return False

            context = ProcessingContext(
                pdf_path=local_path,
                filename=local_path.name,
                book_title=job.book_title or Path(job.filename).stem,
                course=job.course,
                grade=job.grade,
                use_ocr=True,
                progress_callback=progress,
                cancellation_callback=should_cancel,
            )
            self._repository.update(job.id, state=JobState.processing)
            use_case = self._use_case_factory()
            result_context = await asyncio.to_thread(use_case.execute, context)

            document = result_context.document
            assert document is not None
            output_paths = list(result_context.export_paths.values())
            ocr_pages = sum(
                1
                for page in document.pages
                if page.extraction_method == ExtractionMethod.ocr_tesseract
            )
            job = self._repository.update(
                job.id,
                state=JobState.completed,
                completed_at=utc_now(),
                output_paths=output_paths,
                total_pages=document.metadata.total_pages,
                processed_pages=len(document.pages),
                ocr_page_count=ocr_pages,
                warnings=document.warnings,
            )
            await self._edit_status(bot, job)
            await self._delivery.deliver(bot, job)
            app_logger.info(
                "Telegram job %s completed: pages=%s ocr_pages=%s warnings=%s",
                job.id,
                job.total_pages,
                job.ocr_page_count,
                len(job.warnings),
            )
            return job
        except ProcessingCancelledError:
            if "timed_out" in locals() and timed_out:
                job = self._repository.update(
                    job.id,
                    state=JobState.failed,
                    completed_at=utc_now(),
                    error_summary="processing timeout reached",
                )
            else:
                job = self._repository.update(
                    job.id,
                    state=JobState.cancelled,
                    completed_at=utc_now(),
                    error_summary="cancelled by user",
                )
            await self._edit_status(bot, job)
            return job
        except Exception as exc:
            app_logger.exception("Telegram job %s failed", job.id)
            job = self._repository.update(
                job.id,
                state=JobState.failed,
                completed_at=utc_now(),
                error_summary=_safe_error_summary(exc),
            )
            await self._edit_status(bot, job)
            return job

    def _raise_if_cancelled(self, job_id: str) -> None:
        if self._repository.is_cancel_requested(job_id):
            raise ProcessingCancelledError("cancel requested")

    async def _edit_status(self, bot, job: TelegramJob) -> None:
        if job.status_message_id is None:
            return
        from app.interfaces.telegram.messages import format_status

        try:
            await bot.edit_message_text(
                chat_id=job.chat_id,
                message_id=job.status_message_id,
                text=format_status(job, self._repository.queue_position(job.id)),
            )
        except Exception:
            app_logger.debug("Could not edit Telegram status for job %s", job.id)

    async def _edit_current_status(self, bot, job_id: str) -> None:
        job = self._repository.get(job_id)
        if job is not None:
            await self._edit_status(bot, job)
