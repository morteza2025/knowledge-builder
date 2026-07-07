"""
Primary text-extraction engine, implementing TextExtractionPort with
pdfplumber.

Replaces the previous PyMuPDF-based extractor (`page.get_text("text")`),
which was verified to produce word-order- and character-order-scrambled
Persian text (see git history / prior code review). See
app/infrastructure/text/persian_cleaner.py for why the RTL fix needs two
axes, not one.
"""

from pathlib import Path
from typing import Optional

import pdfplumber

from app.application.ports import OCREnginePort, TextExtractionPort
from app.core.exceptions import PDFExtractionError, UnsupportedFileTypeError
from app.core.logger import app_logger
from app.core.settings import settings
from app.domain.document import DocumentPage, ExtractionMethod
from app.infrastructure.text.persian_cleaner import (
    clean_persian_text,
    fix_word_glyph_order,
)

_LINE_BAND_PX = 3  # words within this many points of `top` are one line


def _reconstruct_page_text(page: "pdfplumber.page.Page") -> str:
    """The verified fix: group words into lines by vertical position, sort
    each line right-to-left by x0, and un-mirror each Arabic-script word."""

    words = page.extract_words(use_text_flow=False)
    if not words:
        return ""

    lines: dict[int, list] = {}
    for word in words:
        line_key = round(word["top"] / _LINE_BAND_PX) * _LINE_BAND_PX
        lines.setdefault(line_key, []).append(word)

    text_lines = []
    for line_key in sorted(lines.keys()):
        line_words = sorted(lines[line_key], key=lambda w: -w["x0"])
        line_text = " ".join(fix_word_glyph_order(w["text"]) for w in line_words)
        text_lines.append(line_text)

    return "\n".join(text_lines)


class PdfPlumberTextExtractor(TextExtractionPort):
    def __init__(
        self,
        ocr_engine: Optional[OCREnginePort] = None,
        use_ocr: bool = True,
        min_chars_for_valid_page: int = settings.min_text_chars_for_valid_page,
        ocr_language: str = settings.ocr_language,
        ocr_resolution: int = settings.ocr_render_resolution,
        max_pages: int = settings.max_pages_per_pdf,
    ):
        self._ocr_engine = ocr_engine
        self._use_ocr = use_ocr
        self._min_chars = min_chars_for_valid_page
        self._ocr_language = ocr_language
        self._ocr_resolution = ocr_resolution
        self._max_pages = max_pages

    def extract_pages(self, pdf_path: Path) -> list[DocumentPage]:
        self._validate_path(pdf_path)

        pages: list[DocumentPage] = []

        try:
            with pdfplumber.open(pdf_path) as pdf:
                if len(pdf.pages) > self._max_pages:
                    raise PDFExtractionError(
                        f"PDF has too many pages: {len(pdf.pages)}. "
                        f"Max allowed: {self._max_pages}"
                    )

                for page_number, page in enumerate(pdf.pages, start=1):
                    pages.append(self._extract_single_page(page, page_number))

        except PDFExtractionError:
            raise
        except Exception as exc:
            raise PDFExtractionError(f"Cannot open PDF: {exc}") from exc

        return pages

    def _extract_single_page(self, page, page_number: int) -> DocumentPage:
        warnings: list[str] = []
        method = ExtractionMethod.pdfplumber_positional
        needs_review = False

        try:
            raw_text = _reconstruct_page_text(page)
            cleaned = clean_persian_text(raw_text)
        except Exception as exc:
            app_logger.warning("Page %s extraction failed: %s", page_number, exc)
            cleaned = ""
            method = ExtractionMethod.failed
            warnings.append(f"PAGE_EXTRACTION_FAILED: {exc}")

        if method != ExtractionMethod.failed and len(cleaned) < self._min_chars:
            warnings.append("LOW_TEXT_MAY_NEED_OCR")
            cleaned, method, warnings, needs_review = self._maybe_run_ocr(
                page, page_number, cleaned, method, warnings
            )

        if method != ExtractionMethod.failed and not cleaned:
            method = ExtractionMethod.empty
            needs_review = True

        return DocumentPage(
            page_number=page_number,
            text=cleaned,
            char_count=len(cleaned),
            extraction_method=method,
            needs_review=needs_review,
            warnings=warnings,
        )

    def _maybe_run_ocr(self, page, page_number, cleaned, method, warnings):
        needs_review = len(cleaned) < self._min_chars

        if not (self._use_ocr and self._ocr_engine and self._ocr_engine.is_available()):
            if self._use_ocr and self._ocr_engine and not self._ocr_engine.is_available():
                warnings.append("OCR_UNAVAILABLE_ON_THIS_MACHINE")
            return cleaned, method, warnings, needs_review

        try:
            image = page.to_image(resolution=self._ocr_resolution).original
            ocr_raw = self._ocr_engine.extract_text(image, self._ocr_language)
            ocr_cleaned = clean_persian_text(ocr_raw)

            if len(ocr_cleaned) > len(cleaned):
                warnings.append("RECOVERED_VIA_OCR")
                return ocr_cleaned, ExtractionMethod.ocr_tesseract, warnings, len(ocr_cleaned) < self._min_chars

        except Exception as exc:
            app_logger.warning("OCR failed on page %s: %s", page_number, exc)
            warnings.append(f"OCR_FAILED: {exc}")

        return cleaned, method, warnings, needs_review

    @staticmethod
    def _validate_path(pdf_path: Path) -> None:
        if not pdf_path.exists():
            raise PDFExtractionError(f"File not found: {pdf_path}")
        if pdf_path.suffix.lower() != ".pdf":
            raise UnsupportedFileTypeError(f"Only PDF files are supported: {pdf_path.suffix}")
