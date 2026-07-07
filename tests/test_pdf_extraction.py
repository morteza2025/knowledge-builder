"""
Regression test for the RTL word/character-order bug found during code
review. Runs against the real sample PDF committed in input/, not a mock,
because the bug only reproduces against real pdfplumber output.
"""

import pytest

from app.core.settings import settings
from app.domain.document import ExtractionMethod
from app.infrastructure.pdf.pdfplumber_engine import PdfPlumberTextExtractor

SAMPLE_PDF = settings.input_dir / "C110220.pdf"


@pytest.mark.skipif(not SAMPLE_PDF.exists(), reason="sample PDF not present")
def test_first_page_extracts_book_title_in_correct_reading_order():
    extractor = PdfPlumberTextExtractor(ocr_engine=None, use_ocr=False)
    pages = extractor.extract_pages(SAMPLE_PDF)

    assert len(pages) > 0

    first_page_text = pages[0].text
    # Correct reading order: "جامعه شناسی" (Sociology). The pre-fix bug
    # produced the reversed "شناسی جامعه" instead.
    assert "جامعه شناسی" in first_page_text
    assert "شناسی جامعه" not in first_page_text


@pytest.mark.skipif(not SAMPLE_PDF.exists(), reason="sample PDF not present")
def test_pages_have_pdfplumber_extraction_method_when_text_is_present():
    extractor = PdfPlumberTextExtractor(ocr_engine=None, use_ocr=False)
    pages = extractor.extract_pages(SAMPLE_PDF)

    pages_with_text = [p for p in pages if p.char_count > 0]
    assert pages_with_text, "expected at least one page with extractable text"
    assert all(
        p.extraction_method == ExtractionMethod.pdfplumber_positional
        for p in pages_with_text
    )
