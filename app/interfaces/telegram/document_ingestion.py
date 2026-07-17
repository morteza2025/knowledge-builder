from __future__ import annotations

import hashlib
import os
from pathlib import Path
from urllib.parse import quote, urlparse

import httpx

from app.core.settings import Settings
from app.interfaces.telegram.job_models import TelegramJob
from app.interfaces.telegram.security import (
    TelegramSecurityError,
    ensure_within,
    require_free_disk_space,
    validate_pdf_file,
)


class TelegramDocumentIngestion:
    def __init__(self, settings: Settings, http_client_factory=None):
        self._settings = settings
        self._http_client_factory = http_client_factory or httpx.AsyncClient

    async def ingest(self, job: TelegramJob, bot) -> tuple[Path, str]:
        input_dir = self._settings.telegram_input_dir
        input_dir.mkdir(parents=True, exist_ok=True)
        max_bytes = self._settings.telegram_max_file_size_mb * 1024 * 1024
        reserve_bytes = self._settings.telegram_min_free_disk_space_mb * 1024 * 1024
        require_free_disk_space(input_dir, job.file_size, reserve_bytes)

        destination = ensure_within(input_dir / f"{job.id}-{job.filename}", input_dir)
        partial = ensure_within(destination.with_suffix(destination.suffix + ".part"), input_dir)
        partial.unlink(missing_ok=True)

        telegram_file = await bot.get_file(job.telegram_file_id)
        try:
            source_path = self._usable_local_path(telegram_file.file_path)
            if source_path is not None:
                digest = await self._copy_local(source_path, partial, max_bytes)
            else:
                digest = await self._stream_remote(
                    str(telegram_file.file_path), partial, max_bytes
                )
            validate_pdf_file(partial, max_bytes)
            os.replace(partial, destination)
            return destination, digest
        except Exception:
            partial.unlink(missing_ok=True)
            raise

    @staticmethod
    def _usable_local_path(raw_path: str | None) -> Path | None:
        if not raw_path:
            return None
        path = Path(raw_path)
        if not path.is_absolute() or not path.exists():
            return None
        if path.is_symlink() or not path.is_file():
            raise TelegramSecurityError("Local Bot API path is not a regular file")
        return path.resolve(strict=True)

    async def _copy_local(
        self, source: Path, destination: Path, max_bytes: int
    ) -> str:
        import asyncio

        return await asyncio.to_thread(
            self._copy_local_sync, source, destination, max_bytes
        )

    def _copy_local_sync(
        self, source: Path, destination: Path, max_bytes: int
    ) -> str:
        digest = hashlib.sha256()
        total = 0
        with source.open("rb") as reader, destination.open("xb") as writer:
            while chunk := reader.read(self._settings.telegram_download_chunk_size):
                total += len(chunk)
                if total > max_bytes:
                    raise TelegramSecurityError("Downloaded file exceeds size limit")
                digest.update(chunk)
                writer.write(chunk)
            writer.flush()
            os.fsync(writer.fileno())
        return digest.hexdigest()

    async def _stream_remote(
        self, file_path: str, destination: Path, max_bytes: int
    ) -> str:
        token = self._settings.telegram_bot_token
        if token is None:
            raise TelegramSecurityError("Telegram token is not configured")
        if file_path.startswith(("http://", "https://")):
            url = file_path
            expected = urlparse(self._settings.telegram_bot_api_file_url)
            actual = urlparse(url)
            if (actual.scheme, actual.netloc) != (expected.scheme, expected.netloc):
                raise TelegramSecurityError("Unexpected Telegram file URL host")
        else:
            encoded_path = "/".join(quote(part) for part in file_path.split("/"))
            url = (
                f"{self._settings.telegram_bot_api_file_url}"
                f"{token.get_secret_value()}/{encoded_path.lstrip('/')}"
            )

        digest = hashlib.sha256()
        total = 0
        timeout = httpx.Timeout(60.0, read=None)
        async with self._http_client_factory(
            timeout=timeout, follow_redirects=False
        ) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                with destination.open("xb") as writer:
                    async for chunk in response.aiter_bytes(
                        self._settings.telegram_download_chunk_size
                    ):
                        total += len(chunk)
                        if total > max_bytes:
                            raise TelegramSecurityError(
                                "Downloaded file exceeds size limit"
                            )
                        digest.update(chunk)
                        writer.write(chunk)
                    writer.flush()
                    os.fsync(writer.fileno())
        return digest.hexdigest()
