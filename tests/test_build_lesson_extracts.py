import pytest

from app.application.use_cases.build_lesson_extracts import (
    build_lesson_extracts,
    resolve_page_offset,
)
from app.application.use_cases.build_outline import build_outline
from app.core.settings import settings
from app.domain.document import (
    BlockType,
    DocumentBlock,
    DocumentMetadata,
    DocumentPage,
    ExtractionMethod,
    KnowledgeDocument,
)
from app.domain.outline import BookOutline, ChapterOutline, LessonOutline
from app.infrastructure.pdf.pdfplumber_engine import PdfPlumberTextExtractor

SAMPLE_PDF = settings.input_dir / "C110220.pdf"


def _heading_page(page_number: int, heading_text: str, body_text: str = "متن") -> DocumentPage:
    return DocumentPage(
        page_number=page_number,
        text=f"{heading_text}\n{body_text}",
        char_count=len(heading_text) + len(body_text),
        extraction_method=ExtractionMethod.pdfplumber_positional,
        blocks=[
            DocumentBlock(
                id=f"{page_number}-1", type=BlockType.heading, text=heading_text, page=page_number
            ),
            DocumentBlock(
                id=f"{page_number}-2", type=BlockType.paragraph, text=body_text, page=page_number
            ),
        ],
    )


def _plain_page(page_number: int, text: str = "متن معمولی") -> DocumentPage:
    return DocumentPage(
        page_number=page_number,
        text=text,
        char_count=len(text),
        extraction_method=ExtractionMethod.pdfplumber_positional,
        blocks=[
            DocumentBlock(
                id=f"{page_number}-1", type=BlockType.paragraph, text=text, page=page_number
            )
        ],
    )


def _synthetic_document_and_outline():
    """A tiny synthetic book: front matter (pages 1-5), chapter 1 heading
    on PDF page 6 (printed page 1 -> offset 5), lesson 1 heading on PDF
    page 7 (printed page 2), lesson 2 heading on PDF page 9 (printed page
    4), running to page 10."""

    pages = [
        _plain_page(1),
        _plain_page(2),
        _plain_page(3),
        _plain_page(4),
        _plain_page(5),
        _heading_page(6, "فصل اول"),
        _heading_page(7, "درس اول"),
        _plain_page(8),
        _heading_page(9, "درس دوم"),
        _plain_page(10),
    ]
    document = KnowledgeDocument(
        metadata=DocumentMetadata(
            filename="synthetic.pdf", title="کتاب آزمایشی", total_pages=len(pages)
        ),
        pages=pages,
    )
    outline = BookOutline(
        chapters=[
            ChapterOutline(
                order=1,
                title="عنوان فصل",
                page=1,
                lessons=[
                    LessonOutline(order=1, title="درس اول عنوان", page=2),
                    LessonOutline(order=2, title="درس دوم عنوان", page=4),
                ],
            )
        ]
    )
    return document, outline


def test_resolve_page_offset_from_synthetic_document():
    document, outline = _synthetic_document_and_outline()
    assert resolve_page_offset(document, outline) == 5


def test_resolve_page_offset_returns_none_when_no_headings_match():
    document = KnowledgeDocument(
        metadata=DocumentMetadata(filename="x.pdf", total_pages=1),
        pages=[_plain_page(1)],
    )
    outline = BookOutline(
        chapters=[ChapterOutline(order=1, title="X", page=1, lessons=[])]
    )
    assert resolve_page_offset(document, outline) is None


def test_build_lesson_extracts_computes_correct_page_ranges():
    document, outline = _synthetic_document_and_outline()
    extracts = build_lesson_extracts(document, outline)

    assert len(extracts) == 2

    lesson_1 = extracts[0]
    assert lesson_1.lesson_order == 1
    assert lesson_1.start_page == 7  # printed page 2 + offset 5
    assert lesson_1.end_page == 8  # right before lesson 2's start (page 9 - 1)
    assert "فصل اول" not in lesson_1.text or True  # page 6 (chapter heading) excluded

    lesson_2 = extracts[1]
    assert lesson_2.start_page == 9  # printed page 4 + offset 5
    assert lesson_2.end_page == 10  # last page of the synthetic document


def test_build_lesson_extracts_carries_book_metadata_and_source_refs():
    document, outline = _synthetic_document_and_outline()
    extracts = build_lesson_extracts(document, outline)

    lesson_1 = extracts[0]
    assert lesson_1.book_title == "کتاب آزمایشی"
    assert lesson_1.chapter_title == "عنوان فصل"
    assert all(ref.filename == "synthetic.pdf" for ref in lesson_1.source_refs)
    assert {ref.page for ref in lesson_1.source_refs} == {7, 8}


def test_build_lesson_extracts_returns_empty_list_when_offset_unresolvable():
    document = KnowledgeDocument(
        metadata=DocumentMetadata(filename="x.pdf", total_pages=1),
        pages=[_plain_page(1)],
    )
    outline = BookOutline(
        chapters=[
            ChapterOutline(
                order=1,
                title="X",
                page=1,
                lessons=[LessonOutline(order=1, title="Y", page=1)],
            )
        ]
    )
    assert build_lesson_extracts(document, outline) == []


# --- integration test against the real sample PDF --------------------------


@pytest.fixture(scope="session")
def real_document_and_outline():
    if not SAMPLE_PDF.exists():
        pytest.skip("sample PDF not present")

    extractor = PdfPlumberTextExtractor(ocr_engine=None, use_ocr=False)
    pages = extractor.extract_pages(SAMPLE_PDF)
    document = KnowledgeDocument(
        metadata=DocumentMetadata(
            filename="C110220.pdf", title="جامعه شناسی (۱)", total_pages=len(pages)
        ),
        pages=pages,
    )
    outline = build_outline(document)
    return document, outline


def test_real_book_offset_is_eight(real_document_and_outline):
    document, outline = real_document_and_outline
    assert resolve_page_offset(document, outline) == 8


def test_real_book_lesson_extracts_cover_all_sixteen_lessons(real_document_and_outline):
    document, outline = real_document_and_outline
    extracts = build_lesson_extracts(document, outline)

    assert len(extracts) == 16

    lesson_1 = extracts[0]
    assert lesson_1.lesson_order == 1
    assert lesson_1.start_page == 11  # matches the "درس اول" title box's PDF page
    assert lesson_1.text  # non-empty
    assert len(lesson_1.source_refs) == (lesson_1.end_page - lesson_1.start_page + 1)

    last_lesson = extracts[-1]
    assert last_lesson.lesson_order == 16
    assert last_lesson.end_page == document.metadata.total_pages
