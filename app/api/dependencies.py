import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

from app.application.use_cases.process_book import (
    ProcessBookUseCase,
    build_default_process_book_use_case,
)
from app.infrastructure.exporter.json_exporter import JsonExporter
from app.infrastructure.exporter.markdown_exporter import MarkdownExporter
from app.infrastructure.ocr.tesseract_engine import TesseractOCREngine
from app.infrastructure.pdf.pdfplumber_engine import PdfPlumberTextExtractor


@lru_cache(maxsize=1)
def get_process_book_use_case() -> ProcessBookUseCase:
    ocr_engine = TesseractOCREngine()
    text_extractor = PdfPlumberTextExtractor(ocr_engine=ocr_engine)
    exporters = [JsonExporter(), MarkdownExporter()]

    return build_default_process_book_use_case(
        text_extractor=text_extractor,
        exporters=exporters,
    )


def load_sidecar_metadata(pdf_path: Path) -> dict:
    """Looks for '<stem>.meta.json' next to the PDF. This lets book_title /
    course / grade (which are often Persian text) be supplied via a UTF-8
    file written directly on disk, sidestepping Windows-terminal codepage
    corruption entirely — see README.md 'Avoiding encoding corruption'."""

    meta_path = pdf_path.with_suffix("").with_suffix(".meta.json")
    if not meta_path.exists():
        return {}

    with open(meta_path, "r", encoding="utf-8") as file:
        return json.load(file)


def resolve_book_metadata(
    pdf_path: Path,
    book_title: Optional[str],
    course: Optional[str],
    grade: Optional[str],
) -> tuple[str, Optional[str], Optional[str]]:
    sidecar = load_sidecar_metadata(pdf_path)

    resolved_title = book_title or sidecar.get("book_title") or pdf_path.stem
    resolved_course = course or sidecar.get("course")
    resolved_grade = grade or sidecar.get("grade")

    return resolved_title, resolved_course, resolved_grade
