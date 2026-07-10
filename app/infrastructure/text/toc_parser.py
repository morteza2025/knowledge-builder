"""
Parses the book's own table-of-contents page(s) into a BookOutline. The TOC
is the most complete and reliable source of chapter/lesson structure with
page numbers — more complete than scanning body-text heading blocks alone
(verified against input/C110220.pdf: font-size-based heading detection
found lesson-title boxes for only 4 of 7 chapter-1 lessons, while the TOC
lists all 16 lessons across both chapters with page numbers for every
lesson AND every subtopic question beneath it).

Known quirks handled here, all found by testing against the real TOC pages:

1. Page numbers mix Latin and Persian-Indic digits within the same token
   (e.g. "2٩" for page 29) — normalize_digits_to_int handles this.
2. A single logical TOC line occasionally splits across two extracted
   lines (e.g. "کنش" alone, then "های ما ... ٣" on the next line) — this
   parser merges any line that doesn't end in a dot-leader + page number
   into the following line before matching.
3. The word "اول" (first) specifically extracts with a stray space around
   its shadda diacritic ("ا ّول" instead of "اول") in both "فصل اول" and
   "درس اول" — collapsed in app/infrastructure/text/ordinal_labels.py.
   Verified: no other ordinal word in this book showed the same artifact.
"""

from typing import Optional

from app.domain.outline import BookOutline, ChapterOutline, LessonOutline, SubtopicOutline
from app.infrastructure.text.ordinal_labels import find_label
from app.infrastructure.text.persian_cleaner import normalize_digits_to_int

import re

_TOC_LINE = re.compile(
    r"^(?P<title>.+?)\.{2,}\s*(?P<page>[0-9\u0660-\u0669\u06F0-\u06F9]+)\s*$"
)

_TOC_HEADING_TEXT = "فهرست"

# A wrapped fragment (see quirk #2) legitimately precedes the chapter/lesson
# label on rare occasions (verified: "کُنش" — one word — lands on its own
# line ABOVE "درس اول: های ما" due to a diacritic-driven line-band split).
# Cap how much text is allowed before the label match so an unrelated
# subtopic question that happens to contain the word "درس" mid-sentence
# isn't mistaken for a new lesson header.
_MAX_LABEL_PREFIX_CHARS = 15


def parse_toc_text(toc_text: str) -> BookOutline:
    chapters: list[ChapterOutline] = []
    current_chapter: Optional[ChapterOutline] = None
    current_lesson: Optional[LessonOutline] = None
    pending_prefix = ""

    for raw_line in toc_text.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        if line == _TOC_HEADING_TEXT:
            continue  # the TOC page's own heading, not an entry

        match = _TOC_LINE.match(line)
        if not match:
            # No dot-leader + page number at the end — likely a wrapped
            # continuation of the next line's title (see quirk #2).
            pending_prefix = f"{pending_prefix} {line}".strip()
            continue

        raw_title = match.group("title").strip()
        page = normalize_digits_to_int(match.group("page"))

        combined = (
            f"{pending_prefix} {raw_title}".strip() if pending_prefix else raw_title
        )
        pending_prefix = ""

        label = find_label(combined, max_prefix_chars=_MAX_LABEL_PREFIX_CHARS)

        if label is not None:
            prefix_before = combined[: label.start].strip()
            title = (
                f"{prefix_before} {label.remainder}".strip()
                if prefix_before
                else label.remainder
            )
            title = title or combined

            if label.kind == "فصل":
                current_chapter = ChapterOutline(
                    order=label.order, title=title, page=page
                )
                chapters.append(current_chapter)
                current_lesson = None
            else:  # "درس"
                current_lesson = LessonOutline(
                    order=label.order, title=title, page=page
                )
                if current_chapter is not None:
                    current_chapter.lessons.append(current_lesson)
        elif current_lesson is not None:
            current_lesson.subtopics.append(
                SubtopicOutline(title=combined, page=page)
            )
        # else: a page-numbered line before any lesson was seen (rare —
        # e.g. front-matter) has nowhere sensible to attach and is dropped.

    return BookOutline(chapters=chapters)
