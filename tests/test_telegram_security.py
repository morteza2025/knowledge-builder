from pathlib import Path

import pytest

from app.interfaces.telegram.caption_parser import parse_caption_metadata
from app.interfaces.telegram.security import (
    AuthorizationPolicy,
    TelegramSecurityError,
    ensure_within,
    sanitize_pdf_filename,
    validate_document_metadata,
    validate_pdf_file,
)


def test_access_control_allows_only_configured_users():
    policy = AuthorizationPolicy((123, 456))
    assert policy.is_allowed(123)
    assert not policy.is_allowed(999)


def test_empty_allowlist_fails_closed():
    policy = AuthorizationPolicy(())
    assert policy.is_fail_closed
    assert not policy.is_allowed(123)


def test_development_override_must_be_explicit():
    policy = AuthorizationPolicy((), allow_all_development=True)
    assert not policy.is_fail_closed
    assert policy.is_allowed(999)


@pytest.mark.parametrize(
    "unsafe",
    ["../../secret.pdf", "C:\\secret.pdf", "bad\x00name.pdf", "..∕secret.pdf"],
)
def test_unsafe_filename_is_sanitized(unsafe):
    safe = sanitize_pdf_filename(unsafe, "abc")
    assert safe.lower().endswith(".pdf")
    assert "/" not in safe and "\\" not in safe
    assert "\x00" not in safe
    assert len(safe) <= 184


def test_missing_filename_is_generated():
    assert sanitize_pdf_filename(None, "abc") == "document-abc.pdf"


def test_spoofed_pdf_header_is_rejected(tmp_path):
    path = tmp_path / "fake.pdf"
    path.write_bytes(b"not a pdf")
    with pytest.raises(TelegramSecurityError, match="not a PDF"):
        validate_pdf_file(path, 1024)


def test_valid_pdf_header_is_accepted(tmp_path):
    path = tmp_path / "book.pdf"
    path.write_bytes(b"%PDF-1.4\n%%EOF")
    validate_pdf_file(path, 1024)


def test_non_pdf_metadata_and_oversized_file_are_rejected():
    with pytest.raises(TelegramSecurityError):
        validate_document_metadata(
            filename="image.png",
            mime_type="image/png",
            file_size=10,
            max_file_size_bytes=100,
        )
    with pytest.raises(TelegramSecurityError):
        validate_document_metadata(
            filename="book.pdf",
            mime_type="application/pdf",
            file_size=101,
            max_file_size_bytes=100,
        )


def test_path_traversal_is_rejected(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    with pytest.raises(TelegramSecurityError, match="escapes"):
        ensure_within(tmp_path / "outside.pdf", root)


def test_persian_caption_parsing_and_unknown_key_ignoring():
    parsed = parse_caption_metadata(
        "title: جامعه‌شناسی ۱\ncourse: علوم انسانی\ngrade: دهم\nunknown: ignored"
    )
    assert parsed == {
        "book_title": "جامعه‌شناسی ۱",
        "course": "علوم انسانی",
        "grade": "دهم",
    }
