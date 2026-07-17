"""
Primary text-extraction engine, implementing TextExtractionPort with
pdfplumber.

Replaces the previous PyMuPDF-based extractor (`page.get_text("text")`),
which was verified to produce word-order- and character-order-scrambled
Persian text. See app/infrastructure/text/persian_cleaner.py for why the
RTL fix needs two axes, not one, and app/infrastructure/pdf/structure_analyzer.py
for how headings/tables are detected on top of the fixed text.
"""

from pathlib import Path
from typing import Optional

import pdfplumber

from app.application.ports import OCREnginePort, TextExtractionPort
from app.core.exceptions import PDFExtractionError, UnsupportedFileTypeError
from app.core.logger import app_logger
from app.core.settings import settings
from app.domain.document import BlockType, DocumentBlock, DocumentPage, ExtractionMethod
from app.infrastructure.pdf.structure_analyzer import (
    LineInfo,
    build_page_blocks,
    compute_document_baseline_size,
    extract_lines_with_style,
)
from app.infrastructure.text.persian_cleaner import clean_persian_text


class PdfPlumberTextExtractor(TextExtractionPort):
    def __init__(
        self,
        ocr_engine: Optional[OCREnginePort] = None,
        use_ocr: bool = settings.ocr_enabled,
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

    def extract_pages(
        self, pdf_path: Path, *, use_ocr: Optional[bool] = None
    ) -> list[DocumentPage]:
        self._validate_path(pdf_path)
        # The adapter-level setting is the master switch. A caller may
        # disable OCR for one run, but cannot re-enable an adapter that was
        # deliberately constructed with OCR disabled.
        run_ocr = self._use_ocr and use_ocr is not False

        try:
            with pdfplumber.open(pdf_path) as pdf:
                if len(pdf.pages) > self._max_pages:
                    raise PDFExtractionError(
                        f"PDF has too many pages: {len(pdf.pages)}. "
                        f"Max allowed: {self._max_pages}"
                    )

                # Phase 1: extract styled lines for every page up front.
                # Heading detection is relative to THIS document's own body
                # font size (a photo-heavy book and a dense-text book have
                # different baselines), so we need to see every page before
                # classifying any single line.
                pages_lines: dict[int, list[LineInfo]] = {}
                for page_number, page in enumerate(pdf.pages, start=1):
                    try:
                        pages_lines[page_number] = extract_lines_with_style(
                            page, page_number
                        )
                    except Exception as exc:
                        app_logger.warning(
                            "Style extraction failed on page %s: %s",
                            page_number,
                            exc,
                        )
                        pages_lines[page_number] = []

                baseline_size = compute_document_baseline_size(
                    list(pages_lines.values())
                )

                # Phase 2: build the final per-page result, now that the
                # baseline is known. Still inside the same `with` block so
                # page objects (needed for OCR image rendering and table
                # cell cropping) stay valid.
                pages: list[DocumentPage] = []
                for page_number, page in enumerate(pdf.pages, start=1):
                    pages.append(
                        self._extract_single_page(
                            page,
                            page_number,
                            pages_lines[page_number],
                            baseline_size,
                            run_ocr,
                        )
                    )

        except PDFExtractionError:
            raise
        except Exception as exc:
            raise PDFExtractionError(f"Cannot open PDF: {exc}") from exc

        return pages

    def _extract_single_page(
        self,
        page,
        page_number: int,
        lines: list[LineInfo],
        baseline_size: float,
        use_ocr: bool,
    ) -> DocumentPage:
        warnings: list[str] = []
        method = ExtractionMethod.pdfplumber_positional
        needs_review = False
        blocks: list[DocumentBlock] = []

        try:
            raw_text = "\n".join(line.text for line in lines)
            cleaned = clean_persian_text(raw_text)
        except Exception as exc:
            app_logger.warning("Page %s extraction failed: %s", page_number, exc)
            cleaned = ""
            method = ExtractionMethod.failed
            warnings.append(f"PAGE_EXTRACTION_FAILED: {exc}")

        if method != ExtractionMethod.failed and len(cleaned) < self._min_chars:
            warnings.append("LOW_TEXT_MAY_NEED_OCR")
            cleaned, method, warnings, needs_review = self._maybe_run_ocr(
                page, page_number, cleaned, method, warnings, use_ocr
            )

        if method != ExtractionMethod.failed and not cleaned:
            method = ExtractionMethod.empty
            needs_review = True

        if method == ExtractionMethod.pdfplumber_positional:
            try:
                blocks = build_page_blocks(page, page_number, lines, baseline_size)
            except Exception as exc:
                app_logger.warning(
                    "Block structuring failed on page %s: %s", page_number, exc
                )
                warnings.append(f"BLOCK_STRUCTURING_FAILED: {exc}")
        elif method == ExtractionMethod.ocr_tesseract and cleaned:
            # OCR gives plain text with no font/position data, so headings
            # can't be classified — one block beats losing structure
            # entirely.
            blocks = [
                DocumentBlock(
                    id=f"{page_number}-1",
                    type=BlockType.paragraph,
                    text=cleaned,
                    page=page_number,
                    metadata={"source": "ocr_fallback"},
                )
            ]

        return DocumentPage(
            page_number=page_number,
            text=cleaned,
            char_count=len(cleaned),
            extraction_method=method,
            needs_review=needs_review,
            warnings=warnings,
            blocks=blocks,
        )

    def _maybe_run_ocr(
        self, page, page_number, cleaned, method, warnings, use_ocr: bool
    ):
        needs_review = len(cleaned) < self._min_chars

        if not use_ocr:
            return cleaned, method, warnings, needs_review

        if not self._ocr_engine:
            return cleaned, method, warnings, needs_review

        if not self._ocr_engine.is_available():
            warnings.append("OCR_UNAVAILABLE_ON_THIS_MACHINE")
            return cleaned, method, warnings, needs_review

        try:
            image = page.to_image(resolution=self._ocr_resolution).original
            ocr_result = self._ocr_engine.extract_with_quality(
                image, self._ocr_language
            )
            ocr_cleaned = clean_persian_text(ocr_result.text)

            if len(ocr_cleaned) > len(cleaned):
                if (
                    ocr_result.confidence is not None
                    and ocr_result.confidence
                    < settings.ocr_low_confidence_threshold
                ):
                    warnings.append(
                        f"OCR_LOW_CONFIDENCE:{ocr_result.confidence:.1f}"
                    )
                warnings.append("RECOVERED_VIA_OCR")
                return (
                    ocr_cleaned,
                    ExtractionMethod.ocr_tesseract,
                    warnings,
                    len(ocr_cleaned) < self._min_chars,
                )

        except Exception as exc:
            app_logger.warning("OCR failed on page %s: %s", page_number, exc)
            warnings.append(f"OCR_FAILED: {exc}")

        return cleaned, method, warnings, needs_review

    @staticmethod
    def _validate_path(pdf_path: Path) -> None:
        if not pdf_path.exists():
            raise PDFExtractionError(f"File not found: {pdf_path}")
        if pdf_path.suffix.lower() != ".pdf":
            raise UnsupportedFileTypeError(
                f"Only PDF files are supported: {pdf_path.suffix}"
            )
