from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class JobState(str, Enum):
    received = "received"
    validating = "validating"
    queued = "queued"
    downloading = "downloading"
    ready = "ready"
    processing = "processing"
    extracting = "extracting"
    ocr = "ocr"
    exporting = "exporting"
    completed = "completed"
    failed = "failed"
    cancel_requested = "cancel_requested"
    cancelled = "cancelled"


TERMINAL_STATES = {JobState.completed, JobState.failed, JobState.cancelled}
RUNNING_STATES = {
    JobState.downloading,
    JobState.ready,
    JobState.processing,
    JobState.extracting,
    JobState.ocr,
    JobState.exporting,
    JobState.cancel_requested,
}


@dataclass
class TelegramJob:
    user_id: int
    chat_id: int
    source_message_id: int
    filename: str
    telegram_file_id: str
    telegram_file_unique_id: str
    file_size: int
    source_type: str
    book_title: Optional[str] = None
    course: Optional[str] = None
    grade: Optional[str] = None
    id: str = field(default_factory=lambda: uuid4().hex[:12])
    state: JobState = JobState.received
    created_at: datetime = field(default_factory=utc_now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_summary: Optional[str] = None
    local_input_path: Optional[Path] = None
    output_paths: list[Path] = field(default_factory=list)
    total_pages: Optional[int] = None
    processed_pages: Optional[int] = None
    ocr_page_count: Optional[int] = None
    warnings: list[str] = field(default_factory=list)
    cancellation_requested: bool = False
    status_message_id: Optional[int] = None
    file_sha256: Optional[str] = None

    @property
    def elapsed_seconds(self) -> int:
        end = self.completed_at or utc_now()
        start = self.started_at or self.created_at
        return max(0, int((end - start).total_seconds()))
