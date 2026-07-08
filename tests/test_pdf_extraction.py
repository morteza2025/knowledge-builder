"""
Regression tests for the RTL word/character-order bug and structural block
detection, run against the real sample PDF committed in input/ — not a
mock — because the bug only reproduces against actual pdfplumber output.

Extraction runs once per test session (session-scoped fixture) since a full
152-page pass, including table detection, is expensive; re-running it once
per assertion would make the suite unnecessarily slow.
"""

import pytest

from app.application.use_cases.build_outline import build_outline
from app.core.settings import settings
from app.domain.document import DocumentMetadata, ExtractionMethod, KnowledgeDocument
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


def test_sparse_lesson_title_boxes_are_preserved_not_dropped(sample_pages):
    """Regression test for a real bug found during review: lesson-title
    boxes (e.g. "درس اول" + a short theme phrase) have a low filled-cell
    ratio (~0.33, mostly empty icon-placeholder cells) and were being
    silently dropped by an earlier version of the fill-ratio filter —
    losing exactly the lesson-boundary markers this pipeline exists to
    capture. They must now survive as a heading (or at minimum a
    paragraph) block, never disappear entirely."""

    all_blocks_text = [
        b.text for p in sample_pages for b in p.blocks
    ]

    assert any("درس اول" in text for text in all_blocks_text)
    assert any("درس دوم" in text for text in all_blocks_text)


def test_chapter_headings_are_clean_of_tatweel_justification_marks(sample_pages):
    """Regression test: publishers insert tatweel/kashida (U+0640) to
    justify lines, which previously broke substring matching (extracted
    text read "فصـل" instead of "فصل"). Must be stripped by cleaning."""

    heading_texts = [
        b.text
        for p in sample_pages
        for b in p.blocks
        if b.type.value == "heading"
    ]

    assert any(text.strip() == "فصل اول" for text in heading_texts)
    assert any(text.strip() == "فصل دوم" for text in heading_texts)
    assert not any("\u0640" in text for text in heading_texts)


def test_toc_page_is_not_swallowed_by_a_false_positive_full_page_table(sample_pages):
    """Regression test: pdfplumber's find_tables() misreads this book's
    dotted TOC leaders as table rules, producing one "table" whose bbox
    covers ~63% of the page with 27 newlines flattened into a single
    cell — which used to replace the page's entire real heading/paragraph
    structure with one giant merged block. The "فهرست" (table of contents)
    heading must survive as its own heading block, separate from the
    entries below it."""

    toc_pages = [
        p
        for p in sample_pages
        if any(
            b.type.value == "heading" and b.text.strip() == "فهرست"
            for b in p.blocks
        )
    ]

    assert len(toc_pages) >= 1
    assert all(len(p.blocks) >= 2 for p in toc_pages)


def test_outline_builder_finds_the_complete_chapter_lesson_structure(sample_pages):
    """Integration test for the full TOC -> BookOutline path against the
    real book: 2 chapters, 16 lessons total, globally numbered across
    chapters (not restarting at 1 in chapter 2) — cross-checked against
    the book's own printed structure."""

    document = KnowledgeDocument(
        metadata=DocumentMetadata(filename="C110220.pdf", total_pages=len(sample_pages)),
        pages=sample_pages,
    )
    outline = build_outline(document)

    assert outline is not None
    assert len(outline.chapters) == 2

    total_lessons = sum(len(chapter.lessons) for chapter in outline.chapters)
    assert total_lessons == 16

    chapter_1, chapter_2 = outline.chapters
    assert chapter_1.order == 1
    assert len(chapter_1.lessons) == 7
    assert chapter_2.order == 2
    assert len(chapter_2.lessons) == 9

    # Global numbering: chapter 2's first lesson continues from chapter 1's
    # last, it doesn't restart at 1.
    assert chapter_2.lessons[0].order == 8

    lesson_1 = chapter_1.lessons[0]
    assert lesson_1.page == 3
    assert len(lesson_1.subtopics) >= 1
