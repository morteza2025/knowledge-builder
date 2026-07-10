"""
Resolves the book's own printed page numbers (from BookOutline, parsed
from the table of contents) against this PDF's actual absolute page
index, then slices out each lesson's text — the unit concept extraction
(app/application/ports.py: ConceptRelationExtractorPort) operates on.

Why an offset exists at all: the TOC lists page numbers as printed in the
book itself (e.g. "3"), which is what a student would actually look up —
but the PDF file also has cover/foreword/TOC pages before the book's own
page 1 begins, so the PDF's absolute page index for that same content is
higher (e.g. PDF page 11). Verified against input/C110220.pdf: this book
uses a CONSTANT offset of 8 throughout (checked at 3 independent points —
chapter 1's heading, chapter 2's heading, and lesson 1's title box all
agree on offset=8) — but this is a per-book property, not something to
hardcode. It's computed fresh for every document from structural evidence
already available: heading blocks whose text contains a recognizable
"فصل N" / "درس N" label are matched against the SAME chapter/lesson
(by kind + order, not by title text — chapter heading blocks are often
just the bare label with no title attached) in the outline, and
offset = pdf_page - printed_page for each such match.
"""

import statistics
from typing import Optional

from app.domain.document import KnowledgeDocument, LessonTextExtract, SourceRef
from app.domain.outline import BookOutline
from app.infrastructure.text.ordinal_labels import find_label


def resolve_page_offset(
    document: KnowledgeDocument, outline: BookOutline
) -> Optional[int]:
    """Returns the most common (pdf_page - printed_page) offset found by
    matching heading blocks against the outline, or None if no heading
    block could be matched to any chapter/lesson label at all."""

    printed_pages: dict[tuple[str, int], int] = {}
    for chapter in outline.chapters:
        if chapter.page is not None:
            printed_pages[("فصل", chapter.order)] = chapter.page
        for lesson in chapter.lessons:
            if lesson.page is not None:
                printed_pages[("درس", lesson.order)] = lesson.page

    offsets = []
    for page in document.pages:
        for block in page.blocks:
            if block.type.value != "heading":
                continue
            label = find_label(block.text)
            if label is None:
                continue
            key = (label.kind, label.order)
            if key in printed_pages:
                offsets.append(page.page_number - printed_pages[key])

    if not offsets:
        return None

    return statistics.mode(offsets)


def build_lesson_extracts(
    document: KnowledgeDocument, outline: BookOutline
) -> list[LessonTextExtract]:
    """Returns one LessonTextExtract per lesson that has a resolvable page
    range, in book order. Returns an empty list (not an error) if the
    offset can't be resolved or the outline has no lessons with page
    numbers — concept extraction is optional enrichment, same as the
    outline itself."""

    offset = resolve_page_offset(document, outline)
    if offset is None:
        return []

    flat: list[tuple] = [
        (chapter, lesson)
        for chapter in outline.chapters
        for lesson in chapter.lessons
        if lesson.page is not None
    ]
    if not flat:
        return []

    total_pdf_pages = len(document.pages)
    extracts: list[LessonTextExtract] = []

    for index, (chapter, lesson) in enumerate(flat):
        start_page = lesson.page + offset

        if index + 1 < len(flat):
            end_page = flat[index + 1][1].page + offset - 1
        else:
            end_page = total_pdf_pages

        start_page = max(start_page, 1)
        end_page = min(max(end_page, start_page), total_pdf_pages)

        pages_in_range = [
            page
            for page in document.pages
            if start_page <= page.page_number <= end_page
        ]
        text = "\n\n".join(page.text for page in pages_in_range if page.text)

        source_refs = [
            SourceRef(filename=document.metadata.filename, page=page.page_number)
            for page in pages_in_range
        ]

        extracts.append(
            LessonTextExtract(
                book_title=document.metadata.title or document.metadata.filename,
                course=document.metadata.course,
                grade=document.metadata.grade,
                chapter_order=chapter.order,
                chapter_title=chapter.title,
                lesson_order=lesson.order,
                lesson_title=lesson.title,
                start_page=start_page,
                end_page=end_page,
                text=text,
                source_refs=source_refs,
            )
        )

    return extracts
