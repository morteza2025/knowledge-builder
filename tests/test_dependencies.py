import json
from pathlib import Path

from app.api.routes import _build_context
from app.api.dependencies import resolve_book_metadata
from app.core.settings import settings


def test_resolve_book_metadata_prefers_explicit_over_sidecar(tmp_path: Path):
    pdf_path = tmp_path / "book.pdf"
    pdf_path.touch()

    sidecar_path = tmp_path / "book.meta.json"
    sidecar_path.write_text(
        json.dumps({"book_title": "از سایدکار", "course": "ریاضی", "grade": "یازدهم"}),
        encoding="utf-8",
    )

    title, course, grade = resolve_book_metadata(pdf_path, "عنوان صریح", None, None)

    assert title == "عنوان صریح"  # explicit request value wins
    assert course == "ریاضی"  # falls back to sidecar
    assert grade == "یازدهم"


def test_resolve_book_metadata_falls_back_to_filename_stem(tmp_path: Path):
    pdf_path = tmp_path / "unlabeled_book.pdf"
    pdf_path.touch()

    title, course, grade = resolve_book_metadata(pdf_path, None, None, None)

    assert title == "unlabeled_book"
    assert course is None
    assert grade is None


def test_global_ocr_switch_cannot_be_overridden_per_request(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "input_dir", tmp_path)
    monkeypatch.setattr(settings, "ocr_enabled", False)

    context = _build_context(
        filename="book.pdf",
        book_title=None,
        course=None,
        grade=None,
        use_ocr=True,
    )

    assert context.use_ocr is False
