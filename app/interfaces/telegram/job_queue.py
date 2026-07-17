from __future__ import annotations

import asyncio

from app.core.logger import app_logger
from app.interfaces.telegram.job_models import JobState
from app.interfaces.telegram.job_repository import SQLiteJobRepository
from app.interfaces.telegram.worker import TelegramJobWorker


class QueueCapacityError(RuntimeError):
    pass


class TelegramJobQueue:
    def __init__(
        self,
        repository: SQLiteJobRepository,
        worker: TelegramJobWorker,
        *,
        maxsize: int,
        concurrency: int,
    ):
        self._repository = repository
        self._worker = worker
        self._queue: asyncio.Queue[str] = asyncio.Queue(maxsize=maxsize)
        self._concurrency = concurrency
        self._tasks: list[asyncio.Task] = []
        self._accepting = False
        self._bot = None

    async def start(self, bot) -> None:
        self._bot = bot
        self._accepting = True
        recovered = self._repository.recover_after_restart()
        for job in recovered:
            try:
                self._queue.put_nowait(job.id)
            except asyncio.QueueFull:
                self._repository.update(
                    job.id,
                    state=JobState.failed,
                    error_summary="queue capacity exceeded during restart",
                )
        self._tasks = [
            asyncio.create_task(self._run_worker(index), name=f"telegram-worker-{index}")
            for index in range(self._concurrency)
        ]

    def submit(self, job_id: str) -> None:
        if not self._accepting:
            raise QueueCapacityError("queue is not accepting jobs")
        try:
            self._queue.put_nowait(job_id)
        except asyncio.QueueFull as exc:
            raise QueueCapacityError("queue is full") from exc

    async def stop(self) -> None:
        self._accepting = False
        try:
            await asyncio.wait_for(self._queue.join(), timeout=30)
        except asyncio.TimeoutError:
            app_logger.warning("Telegram queue shutdown timed out; requesting cancellation")
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    async def _run_worker(self, worker_index: int) -> None:
        while True:
            job_id = await self._queue.get()
            try:
                job = self._repository.get(job_id)
                if job and job.state != JobState.cancelled:
                    await self._worker.process(job, self._bot)
            except Exception:
                app_logger.exception(
                    "Telegram worker %s failed outside job boundary", worker_index
                )
            finally:
                self._queue.task_done()
