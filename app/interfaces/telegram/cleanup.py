from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.core.logger import app_logger
from app.interfaces.telegram.job_models import TelegramJob


def cleanup_old_runtime_files(roots: tuple[Path, ...], retention_hours: int) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=retention_hours)
    removed = 0
    for root in roots:
        if not root.exists():
            continue
        resolved_root = root.resolve()
        for path in root.rglob("*"):
            if path.is_symlink() or not path.is_file():
                continue
            try:
                path.resolve().relative_to(resolved_root)
                modified = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
                if modified < cutoff:
                    path.unlink(missing_ok=True)
                    removed += 1
            except (OSError, ValueError):
                app_logger.debug("Skipped Telegram cleanup candidate")
    return removed


def cleanup_expired_job_artifacts(
    jobs: list[TelegramJob], allowed_roots: tuple[Path, ...]
) -> int:
    resolved_roots = tuple(root.resolve() for root in allowed_roots)
    removed = 0
    for job in jobs:
        candidates = ([job.local_input_path] if job.local_input_path else []) + list(
            job.output_paths
        )
        for path in candidates:
            if path is None or path.is_symlink() or not path.is_file():
                continue
            resolved = path.resolve()
            if not any(
                _is_relative_to(resolved, root) for root in resolved_roots
            ):
                continue
            # Telegram-controlled artifacts are always prefixed with the job
            # ID; this prevents retention from deleting API/CLI outputs.
            if not resolved.name.startswith(f"{job.id}-"):
                continue
            resolved.unlink(missing_ok=True)
            removed += 1
    return removed


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
