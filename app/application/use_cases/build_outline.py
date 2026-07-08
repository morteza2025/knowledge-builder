"""
Finds the book's own table-of-contents page(s) (by locating a heading block
labeled "فهرست" / "فهرست مطالب") and parses them into a BookOutline. Returns
None if no TOC page is found or nothing parseable came out of it — this is
an optional enrichment on top of the base extraction, not a hard
requirement (some supplementary books/handouts may not have a TOC page).
"""

from typing import Optional

from app.domain.document import KnowledgeDocument
from app.domain.outline import BookOutline
from app.infrastructure.text.toc_parser import parse_toc_text

_TOC_HEADING_LABELS = {"فهرست", "فهرست مطالب"}


def find_toc_page_texts(document: KnowledgeDocument) -> list[str]:
    texts = []
    for page in document.pages:
        is_toc_page = any(
            block.type.value == "heading" and block.text.strip() in _TOC_HEADING_LABELS
            for block in page.blocks
        )
        if is_toc_page:
            texts.append(page.text)
    return texts


def build_outline(document: KnowledgeDocument) -> Optional[BookOutline]:
    toc_texts = find_toc_page_texts(document)
    if not toc_texts:
        return None

    outline = parse_toc_text("\n".join(toc_texts))
    if not outline.chapters:
        return None

    return outline
