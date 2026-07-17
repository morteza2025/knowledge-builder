from __future__ import annotations

import zipfile
from pathlib import Path

from app.core.settings import Settings
from app.interfaces.telegram.job_models import TelegramJob
from app.interfaces.telegram.messages import completion_summary
from app.interfaces.telegram.security import TelegramSecurityError, ensure_within


class TelegramResultDelivery:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._roots = tuple(
            path.resolve()
            for path in (
                settings.json_output_dir,
                settings.markdown_output_dir,
                settings.django_seed_output_dir,
                settings.knowledge_graph_output_dir,
            )
        )

    async def deliver(self, bot, job: TelegramJob) -> None:
        paths = [self._validate_output(path) for path in job.output_paths]
        await bot.send_message(job.chat_id, completion_summary(job))

        send_paths = paths
        if len(paths) > 4:
            send_paths = [self._create_archive(job, paths)]

        max_bytes = self._settings.telegram_max_file_size_mb * 1024 * 1024
        for path in send_paths:
            if path.stat().st_size > max_bytes:
                raise TelegramSecurityError("Generated output is too large to send")
            await bot.send_document(
                chat_id=job.chat_id,
                document=path,
                filename=path.name,
            )

        if job.warnings:
            safe_warnings = "\n".join(f"• {warning[:180]}" for warning in job.warnings[:8])
            await bot.send_message(
                job.chat_id,
                f"⚠️ خلاصه هشدارها:\n{safe_warnings}",
            )

    def _validate_output(self, path: Path) -> Path:
        if path.is_symlink() or not path.is_file():
            raise TelegramSecurityError("Output is not a regular file")
        resolved = path.resolve()
        for root in self._roots:
            try:
                resolved.relative_to(root)
                return resolved
            except ValueError:
                continue
        raise TelegramSecurityError("Output path is outside configured directories")

    def _create_archive(self, job: TelegramJob, paths: list[Path]) -> Path:
        archive_dir = self._settings.telegram_work_dir / "archives"
        archive_dir.mkdir(parents=True, exist_ok=True)
        archive = ensure_within(archive_dir / f"{job.id}.telegram.zip", archive_dir)
        partial = archive.with_suffix(archive.suffix + ".part")
        partial.unlink(missing_ok=True)
        with zipfile.ZipFile(partial, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            for path in paths:
                bundle.write(path, arcname=Path(path.name).name)
        partial.replace(archive)
        return archive
