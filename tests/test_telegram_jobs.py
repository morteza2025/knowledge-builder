import asyncio
from pathlib import Path

import pytest

from app.interfaces.telegram.job_models import JobState, TelegramJob
from app.interfaces.telegram.job_queue import QueueCapacityError, TelegramJobQueue
from app.interfaces.telegram.job_repository import SQLiteJobRepository


def _job(user_id=123, unique="unique") -> TelegramJob:
    return TelegramJob(
        user_id=user_id,
        chat_id=user_id,
        source_message_id=1,
        filename="book.pdf",
        telegram_file_id="file-id",
        telegram_file_unique_id=unique,
        file_size=100,
        source_type="direct",
        state=JobState.queued,
    )


def test_job_persistence_and_history_survive_reopen(tmp_path):
    path = tmp_path / "jobs.sqlite3"
    repo = SQLiteJobRepository(path)
    job = repo.create(_job())
    repo.update(job.id, state=JobState.completed, output_paths=[Path("out.json")])
    repo.close()

    reopened = SQLiteJobRepository(path)
    try:
        restored = reopened.get(job.id)
        assert restored is not None
        assert restored.state == JobState.completed
        assert restored.output_paths == [Path("out.json")]
    finally:
        reopened.close()


def test_restart_marks_running_jobs_interrupted_and_keeps_queued(tmp_path):
    repo = SQLiteJobRepository(tmp_path / "jobs.sqlite3")
    running = repo.create(_job(unique="running"))
    repo.update(running.id, state=JobState.processing)
    queued = repo.create(_job(unique="queued"))

    recovered = repo.recover_after_restart()

    assert [job.id for job in recovered] == [queued.id]
    interrupted = repo.get(running.id)
    assert interrupted.state == JobState.failed
    assert interrupted.error_summary == "interrupted by bot restart"
    repo.close()


def test_job_ownership_is_enforced_for_cancellation(tmp_path):
    repo = SQLiteJobRepository(tmp_path / "jobs.sqlite3")
    job = repo.create(_job(user_id=123))
    assert repo.request_cancel(job.id, 999) is None
    cancelled = repo.request_cancel(job.id, 123)
    assert cancelled.state == JobState.cancelled
    repo.close()


def test_active_duplicate_detection_ignores_completed_jobs(tmp_path):
    repo = SQLiteJobRepository(tmp_path / "jobs.sqlite3")
    first = repo.create(_job(unique="same"))
    assert repo.find_active_duplicate("same").id == first.id
    repo.update(first.id, state=JobState.completed)
    assert repo.find_active_duplicate("same") is None
    repo.close()


def test_bounded_queue_rejects_excess_jobs(tmp_path):
    class NeverWorker:
        async def process(self, job, bot):
            raise AssertionError("no workers should run")

    async def scenario():
        repo = SQLiteJobRepository(tmp_path / "jobs.sqlite3")
        queue = TelegramJobQueue(repo, NeverWorker(), maxsize=1, concurrency=0)
        await queue.start(object())
        first = repo.create(_job(unique="a"))
        second = repo.create(_job(unique="b"))
        queue.submit(first.id)
        with pytest.raises(QueueCapacityError):
            queue.submit(second.id)
        queued_id = queue._queue.get_nowait()
        assert queued_id == first.id
        queue._queue.task_done()
        await queue.stop()
        repo.close()

    asyncio.run(scenario())


def test_jobs_are_processed_sequentially_by_default(tmp_path):
    class RecordingWorker:
        def __init__(self):
            self.active = 0
            self.max_active = 0
            self.order = []

        async def process(self, job, bot):
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            self.order.append(job.id)
            await asyncio.sleep(0.01)
            self.active -= 1

    async def scenario():
        repo = SQLiteJobRepository(tmp_path / "jobs.sqlite3")
        worker = RecordingWorker()
        queue = TelegramJobQueue(repo, worker, maxsize=3, concurrency=1)
        await queue.start(object())
        jobs = [repo.create(_job(unique=str(index))) for index in range(3)]
        for job in jobs:
            queue.submit(job.id)
        await asyncio.wait_for(queue._queue.join(), timeout=2)
        assert worker.max_active == 1
        assert worker.order == [job.id for job in jobs]
        await queue.stop()
        repo.close()

    asyncio.run(scenario())
