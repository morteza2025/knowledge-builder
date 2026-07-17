from __future__ import annotations

import shutil
import unicodedata
from dataclasses import dataclass
from pathlib import Path


class TelegramSecurityError(ValueError):
    pass


@dataclass(frozen=True)
class AuthorizationPolicy:
    allowed_user_ids: tuple[int, ...]
    allow_all_development: bool = False

    def is_allowed(self, user_id: int) -> bool:
        return self.allow_all_development or user_id in self.allowed_user_ids

    @property
    def is_fail_closed(self) -> bool:
        return not self.allow_all_development and not self.allowed_user_ids


_UNSAFE_SEPARATORS = {"/", "\\", "\u2044", "\u2215", "\u29f8"}


def sanitize_pdf_filename(filename: str | None, fallback_id: str) -> str:
    candidate = filename or f"document-{fallback_id}.pdf"
    candidate = unicodedata.normalize("NFKC", candidate)
    safe_chars = []
    for char in candidate:
        category = unicodedata.category(char)
        if char in _UNSAFE_SEPARATORS or category.startswith("C"):
            safe_chars.append("_")
        elif char.isalnum() or char in {" ", "-", "_", ".", "(", ")"}:
            safe_chars.append(char)
        else:
            safe_chars.append("_")
    safe = "".join(safe_chars).strip(" ._")
    safe = Path(safe).name[:180].strip(" .")
    if not safe:
        safe = f"document-{fallback_id}.pdf"
    if not safe.lower().endswith(".pdf"):
        safe = f"{Path(safe).stem or f'document-{fallback_id}'}.pdf"
    return safe


def validate_document_metadata(
    *,
    filename: str | None,
    mime_type: str | None,
    file_size: int | None,
    max_file_size_bytes: int,
) -> None:
    if filename and not filename.lower().endswith(".pdf"):
        raise TelegramSecurityError("Only PDF files are accepted")
    accepted_mime_types = {
        "application/pdf",
        "application/x-pdf",
        "application/octet-stream",
    }
    if mime_type and mime_type.lower() not in accepted_mime_types:
        raise TelegramSecurityError("Document MIME type is not application/pdf")
    if file_size is not None and file_size > max_file_size_bytes:
        raise TelegramSecurityError("Document exceeds the configured size limit")
    if file_size is not None and file_size <= 0:
        raise TelegramSecurityError("Document is empty")


def ensure_within(path: Path, root: Path) -> Path:
    resolved_root = root.resolve()
    resolved = path.resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise TelegramSecurityError("Path escapes the configured directory") from exc
    return resolved


def validate_pdf_file(path: Path, max_file_size_bytes: int) -> None:
    if path.is_symlink() or not path.is_file():
        raise TelegramSecurityError("Downloaded file is not a regular file")
    size = path.stat().st_size
    if size <= 0 or size > max_file_size_bytes:
        raise TelegramSecurityError("Downloaded file size is invalid")
    with path.open("rb") as stream:
        if stream.read(5) != b"%PDF-":
            raise TelegramSecurityError("File content is not a PDF")


def require_free_disk_space(root: Path, required_bytes: int, reserve_bytes: int) -> None:
    root.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(root).free
    if free < required_bytes + reserve_bytes:
        raise TelegramSecurityError("Insufficient free disk space")
