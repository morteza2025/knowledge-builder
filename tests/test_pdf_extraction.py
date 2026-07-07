"""
Regression tests for the RTL word/character-order bug and structural block
detection, run against the real sample PDF committed in input/ — not a
mock — because the bug only reproduces against actual pdfplumber output.

Extraction runs once per test session (session-scoped fixture) since a full
152-page pass, including table detection, is expensive; re-running it once
per assertion would make the suite unnecessarily slow.
"""

import pytest

from app.core.settings import settings
from app.domain.document import ExtractionMethod
from app.infrastructure.pdf.pdfplumber_engine import PdfPlumberTextExtractor

SAMPLE_PDF = settings.input_dir / "C110220.pdf"


@pytest.fixture(scope="session")
def sample_pages():
    if not SAMPLE_PDF.exists():
        pytest.skip("sample PDF not present")
    extractor = PdfPlumberTextExtractor(ocr_engine=None, use_ocr=False)
    return extractor.extract_pages(SAMPLE_PDF)


def test_first_page_extracts_book_title_in_correct_reading_order(sample_pages):
    assert len(sample_pages) > 0

    first_page_text = sample_pages[0].text
    # Correct reading order: "جامعه شناسی" (Sociology). The pre-fix bug
    # produced the reversed "شناسی جامعه" instead.
    assert "جامعه شناسی" in first_page_text
    assert "شناسی جامعه" not in first_page_text


def test_pages_have_pdfplumber_extraction_method_when_text_is_present(sample_pages):
    pages_with_text = [p for p in sample_pages if p.char_count > 0]
    assert pages_with_text, "expected at least one page with extractable text"
    assert all(
        p.extraction_method == ExtractionMethod.pdfplumber_positional
        for p in pages_with_text
    )


def test_book_title_is_detected_as_a_heading_block(sample_pages):
    first_page_blocks = sample_pages[0].blocks
    heading_texts = [b.text for b in first_page_blocks if b.type.value == "heading"]

    assert any("جامعه شناسی" in text for text in heading_texts)


def test_table_blocks_meet_the_minimum_fill_ratio_quality_bar(sample_pages):
    table_blocks = [
        b for p in sample_pages for b in p.blocks if b.type.value == "table"
    ]

    # Not asserting a specific count (pdfplumber's table detector is a
    # known source of false positives on decorative boxes — see
    # structure_analyzer.py docstring), just that whatever passed the
    # quality filter actually meets the documented bar.
    assert all(b.metadata.get("fill_ratio", 0) >= 0.5 for b in table_blocks)
