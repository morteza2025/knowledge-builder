"""
Shared logic for recognizing "فصل <ordinal>" (chapter N) / "درس <ordinal>"
(lesson N) labels inside Persian text. Used by both
app/infrastructure/text/toc_parser.py (parsing the table of contents) and
app/application/use_cases/build_lesson_extracts.py (matching body-text
heading blocks against the outline to resolve the printed-page-number ->
PDF-page-index offset) — factored out so the ordinal dictionary and label
regex have exactly one definition, not two that could drift apart.
"""

import re
from dataclasses import dataclass
from typing import Optional

ORDINAL_WORDS = {
    "اول": 1,
    "یکم": 1,
    "دوم": 2,
    "سوم": 3,
    "چهارم": 4,
    "پنجم": 5,
    "ششم": 6,
    "هفتم": 7,
    "هشتم": 8,
    "نهم": 9,
    "دهم": 10,
    "یازدهم": 11,
    "دوازدهم": 12,
    "سیزدهم": 13,
    "چهاردهم": 14,
    "پانزدهم": 15,
    "شانزدهم": 16,
    "هفدهم": 17,
    "هجدهم": 18,
    "نوزدهم": 19,
    "بیستم": 20,
}

_LABEL_ANYWHERE = re.compile(r"(?P<kind>فصل|درس)\s+(?P<ord>\S+)\s*:?\s*(?P<rest>.*)$")

# Verified against input/C110220.pdf: "اول" (first) specifically extracts
# with a stray space around its shadda diacritic ("ا ّول"). No other
# ordinal word in this book showed the same artifact.
_AVVAL_ARTIFACT = re.compile(r"ا\s*\u0651?\s*ول\b")


def fix_avval_artifact(text: str) -> str:
    return _AVVAL_ARTIFACT.sub("اول", text)


def _only_arabic_letters(word: str) -> str:
    return re.sub(r"[^\u0600-\u06FF]", "", word)


def parse_ordinal(word: str) -> Optional[int]:
    return ORDINAL_WORDS.get(_only_arabic_letters(word))


@dataclass
class LabelMatch:
    kind: str  # "فصل" or "درس"
    order: int
    start: int  # character offset where the label starts in the searched text
    remainder: str  # text after the label (e.g. the title, if any)


def find_label(text: str, max_prefix_chars: Optional[int] = None) -> Optional[LabelMatch]:
    """Searches for a chapter/lesson label anywhere in `text` (not just at
    the start — see toc_parser.py quirk #2 for why). `max_prefix_chars`
    caps how much text may precede the label match, to avoid mistaking an
    incidental "درس"/"فصل" mid-sentence for a real header; pass None to
    allow a match anywhere."""

    fixed = fix_avval_artifact(text)
    match = _LABEL_ANYWHERE.search(fixed)
    if not match:
        return None

    order = parse_ordinal(match.group("ord"))
    if order is None:
        return None

    if max_prefix_chars is not None and match.start() > max_prefix_chars:
        return None

    return LabelMatch(
        kind=match.group("kind"),
        order=order,
        start=match.start(),
        remainder=match.group("rest").strip(),
    )
