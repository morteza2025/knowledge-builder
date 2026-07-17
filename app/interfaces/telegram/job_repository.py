from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from app.interfaces.telegram.job_models import (
    RUNNING_STATES,
    TERMINAL_STATES,
    JobState,
    TelegramJob,
    utc_now,
)


_COLUMNS = {
    "state",
    "started_at",
    "completed_at",
    "error_summary",
    "local_input_path",
    "output_paths",
    "total_pages",
    "processed_pages",
    "ocr_page_count",
    "warnings",
    "cancellation_requested",
    "status_message_id",
    "file_sha256",
}


class SQLiteJobRepository:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            self._connection.execute("PRAGMA journal_mode=WAL")
            self._connection.execute("PRAGMA foreign_keys=ON")
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS telegram_jobs (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    chat_id INTEGER NOT NULL,
                    source_message_id INTEGER NOT NULL,
                    filename TEXT NOT NULL,
                    telegram_file_id TEXT NOT NULL,
                    telegram_file_unique_id TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    source_type TEXT NOT NULL,
                    book_title TEXT,
                    course TEXT,
                    grade TEXT,
                    state TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    error_summary TEXT,
                    local_input_path TEXT,
                    output_paths TEXT NOT NULL DEFAULT '[]',
                    total_pages INTEGER,
                    processed_pages INTEGER,
                    ocr_page_count INTEGER,
                    warnings TEXT NOT NULL DEFAULT '[]',
                    cancellation_requested INTEGER NOT NULL DEFAULT 0,
                    status_message_id INTEGER,
                    file_sha256 TEXT
                )
                """
            )
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_jobs_user_created "
                "ON telegram_jobs(user_id, created_at DESC)"
            )
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_jobs_unique_state "
                "ON telegram_jobs(telegram_file_unique_id, state)"
            )
            self._connection.commit()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def create(self, job: TelegramJob) -> TelegramJob:
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO telegram_jobs (
                    id, user_id, chat_id, source_message_id, filename,
                    telegram_file_id, telegram_file_unique_id, file_size,
                    source_type, book_title, course, grade, state, created_at,
                    status_message_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job.id,
                    job.user_id,
                    job.chat_id,
                    job.source_message_id,
                    job.filename,
                    job.telegram_file_id,
                    job.telegram_file_unique_id,
                    job.file_size,
                    job.source_type,
                    job.book_title,
                    job.course,
                    job.grade,
                    job.state.value,
                    job.created_at.isoformat(),
                    job.status_message_id,
                ),
            )
            self._connection.commit()
        return job

    def update(self, job_id: str, **changes: Any) -> TelegramJob:
        unknown = set(changes).difference(_COLUMNS)
        if unknown:
            raise ValueError(f"Unsupported job fields: {sorted(unknown)}")
        encoded = {key: self._encode(value) for key, value in changes.items()}
        assignments = ", ".join(f"{key} = ?" for key in encoded)
        with self._lock:
            cursor = self._connection.execute(
                f"UPDATE telegram_jobs SET {assignments} WHERE id = ?",
                (*encoded.values(), job_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(job_id)
            self._connection.commit()
        job = self.get(job_id)
        assert job is not None
        return job

    def get(self, job_id: str) -> Optional[TelegramJob]:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM telegram_jobs WHERE id = ?", (job_id,)
            ).fetchone()
        return self._from_row(row) if row else None

    def latest_for_user(self, user_id: int) -> Optional[TelegramJob]:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM telegram_jobs WHERE user_id = ? "
                "ORDER BY created_at DESC LIMIT 1",
                (user_id,),
            ).fetchone()
        return self._from_row(row) if row else None

    def queued(self) -> list[TelegramJob]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM telegram_jobs WHERE state = ? "
                "ORDER BY created_at ASC",
                (JobState.queued.value,),
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def terminal_before(self, completed_before: datetime) -> list[TelegramJob]:
        terminal = tuple(state.value for state in TERMINAL_STATES)
        placeholders = ",".join("?" for _ in terminal)
        with self._lock:
            rows = self._connection.execute(
                f"SELECT * FROM telegram_jobs WHERE state IN ({placeholders}) "
                "AND completed_at IS NOT NULL AND completed_at < ?",
                (*terminal, completed_before.isoformat()),
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def queue_position(self, job_id: str) -> Optional[int]:
        job = self.get(job_id)
        if not job or job.state != JobState.queued:
            return None
        with self._lock:
            count = self._connection.execute(
                "SELECT COUNT(*) FROM telegram_jobs "
                "WHERE state = ? AND created_at <= ?",
                (JobState.queued.value, job.created_at.isoformat()),
            ).fetchone()[0]
        return int(count)

    def find_active_duplicate(self, file_unique_id: str) -> Optional[TelegramJob]:
        terminal = tuple(state.value for state in TERMINAL_STATES)
        placeholders = ",".join("?" for _ in terminal)
        with self._lock:
            row = self._connection.execute(
                f"SELECT * FROM telegram_jobs WHERE telegram_file_unique_id = ? "
                f"AND state NOT IN ({placeholders}) ORDER BY created_at DESC LIMIT 1",
                (file_unique_id, *terminal),
            ).fetchone()
        return self._from_row(row) if row else None

    def request_cancel(self, job_id: str, user_id: int) -> Optional[TelegramJob]:
        job = self.get(job_id)
        if not job or job.user_id != user_id or job.state in TERMINAL_STATES:
            return None
        state = (
            JobState.cancelled
            if job.state in {JobState.received, JobState.validating, JobState.queued}
            else JobState.cancel_requested
        )
        return self.update(
            job_id,
            state=state,
            cancellation_requested=True,
            completed_at=utc_now() if state == JobState.cancelled else None,
        )

    def is_cancel_requested(self, job_id: str) -> bool:
        job = self.get(job_id)
        return bool(job and job.cancellation_requested)

    def recover_after_restart(self) -> list[TelegramJob]:
        """Queued jobs resume; in-flight work is marked failed/interrupted."""

        running_values = tuple(state.value for state in RUNNING_STATES)
        placeholders = ",".join("?" for _ in running_values)
        with self._lock:
            self._connection.execute(
                f"UPDATE telegram_jobs SET state = ?, completed_at = ?, "
                f"error_summary = ? WHERE state IN ({placeholders})",
                (
                    JobState.failed.value,
                    utc_now().isoformat(),
                    "interrupted by bot restart",
                    *running_values,
                ),
            )
            self._connection.commit()
        return self.queued()

    @staticmethod
    def _encode(value: Any) -> Any:
        if isinstance(value, JobState):
            return value.value
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, list):
            return json.dumps([str(item) for item in value], ensure_ascii=False)
        if isinstance(value, bool):
            return int(value)
        return value

    @staticmethod
    def _from_row(row: sqlite3.Row) -> TelegramJob:
        return TelegramJob(
            id=row["id"],
            user_id=row["user_id"],
            chat_id=row["chat_id"],
            source_message_id=row["source_message_id"],
            filename=row["filename"],
            telegram_file_id=row["telegram_file_id"],
            telegram_file_unique_id=row["telegram_file_unique_id"],
            file_size=row["file_size"],
            source_type=row["source_type"],
            book_title=row["book_title"],
            course=row["course"],
            grade=row["grade"],
            state=JobState(row["state"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            started_at=(
                datetime.fromisoformat(row["started_at"])
                if row["started_at"]
                else None
            ),
            completed_at=(
                datetime.fromisoformat(row["completed_at"])
                if row["completed_at"]
                else None
            ),
            error_summary=row["error_summary"],
            local_input_path=(
                Path(row["local_input_path"]) if row["local_input_path"] else None
            ),
            output_paths=[Path(path) for path in json.loads(row["output_paths"])],
            total_pages=row["total_pages"],
            processed_pages=row["processed_pages"],
            ocr_page_count=row["ocr_page_count"],
            warnings=list(json.loads(row["warnings"])),
            cancellation_requested=bool(row["cancellation_requested"]),
            status_message_id=row["status_message_id"],
            file_sha256=row["file_sha256"],
        )
