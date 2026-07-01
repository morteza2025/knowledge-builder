from pathlib import Path
from typing import List
import fitz

from processor.config import MIN_TEXT_LENGTH_FOR_TEXT_PAGE, MAX_PAGES_PER_REQUEST
from processor.schemas import PageData
from processor.services.persian_cleaner import clean_persian_text


class PDFExtractionError(Exception):
    pass


def validate_pdf_path(pdf_path: Path) -> None:
    if not pdf_path.exists():
        raise PDFExtractionError(f"File not found: {pdf_path}")

    if pdf_path.suffix.lower() != ".pdf":
        raise PDFExtractionError("Only PDF files are supported right now.")


def extract_text_from_page(page: fitz.Page) -> str:
    """
    استخراج متن با PyMuPDF.
    فعلاً OCR ندارد.
    OCR را مرحله بعد به همین فایل اضافه می‌کنیم.
    """
    text = page.get_text("text")
    return clean_persian_text(text)


def extract_pdf_pages(pdf_path: Path, use_ocr: bool = False) -> List[PageData]:
    validate_pdf_path(pdf_path)

    pages: List[PageData] = []

    try:
        doc = fitz.open(pdf_path)
    except Exception as exc:
        raise PDFExtractionError(f"Cannot open PDF: {exc}") from exc

    if len(doc) > MAX_PAGES_PER_REQUEST:
        raise PDFExtractionError(
            f"PDF has too many pages: {len(doc)}. Max allowed: {MAX_PAGES_PER_REQUEST}"
        )

    for page_index, page in enumerate(doc, start=1):
        warnings = []

        try:
            text = extract_text_from_page(page)
            method = "pymupdf_text"

            if len(text) < MIN_TEXT_LENGTH_FOR_TEXT_PAGE:
                warnings.append("LOW_TEXT_PAGE_MAY_NEED_OCR")

                if use_ocr:
                    # مرحله بعد اینجا OCR واقعی اضافه می‌کنیم
                    warnings.append("OCR_REQUESTED_BUT_NOT_IMPLEMENTED_YET")

        except Exception as exc:
            text = ""
            method = "failed"
            warnings.append(f"PAGE_EXTRACTION_FAILED: {exc}")

        pages.append(
            PageData(
                page=page_index,
                text=text,
                char_count=len(text),
                extraction_method=method,
                warnings=warnings,
            )
        )

    doc.close()
    return pages