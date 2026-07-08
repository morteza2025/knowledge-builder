"""
Persian/Arabic text reconstruction and cleanup.

WHY THIS FILE EXISTS (read before touching it):

pdfplumber's `extract_words()` returns each word's glyphs in the order the
PDF's content stream stores them, which for the Persian book PDFs this
project processes is:
  1. Words on a line are stored left-to-right by x-position, but a Persian
     line reads right-to-left — so words must be re-sorted by descending x0.
  2. Each individual word's *characters* also come out mirrored (verified
     empirically against input/C110220.pdf: pdfplumber returns "هعماج" for
     what should be "جامعه"). So each word also needs its characters
     reversed, but ONLY if it actually contains Arabic-script characters —
     reversing a Latin word or a number would break it.

Both fixes are required together. Fixing only #1 (word order) still leaves
every word internally mirrored. Fixing only #2 (character order) still
leaves the words themselves in the wrong sequence on the line. This
combination was verified page-by-page against the real book PDF in this
repo before being written here — do not simplify it back to a single-axis
fix without re-verifying against a real Persian PDF.

A THIRD fix is needed on top of both: page/reference numbers in this PDF
are sometimes typeset as a MIX of Latin and Persian-Indic (U+06F0-06F9 /
U+0660-0669) digit glyphs in the same token — e.g. page 29 extracts as the
literal token "2٩" (Latin '2' + Persian-Indic '٩'=9), already in the
CORRECT reading order. Persian-Indic digits fall inside the same Unicode
block as Arabic letters, so the naive rule "reverse any word containing an
Arabic-range character" was reversing these already-correct numbers into
garbage ("2٩" -> "٩2", i.e. 29 -> 92). Fix: never reverse a token that is a
number (optionally with light punctuation like a trailing period) — digit
order is never a "reading direction" question, unlike letters.
"""

import re
import unicodedata
from typing import Optional

# Arabic + Persian Unicode ranges, plus ZWNJ (U+200C) and RTL mark (U+200F)
# which commonly appear inside Persian words.
_ARABIC_SCRIPT_PATTERN = re.compile(r"[\u0600-\u06FF\u200c\u200f]")

# Punctuation that can legitimately trail/lead a number (e.g. a TOC line's
# page number followed by a period) without meaning the token isn't "just a
# number" for reversal purposes.
_NUMERIC_STRIP_CHARS = ".,:;()[]{}٫٬"

_ARABIC_TO_PERSIAN_MAP = {
    "ي": "ی",
    "ى": "ی",
    "ك": "ک",
    "ۀ": "ه",
    "ة": "ه",
    "ؤ": "و",
    "إ": "ا",
    "أ": "ا",
    "ٱ": "ا",
}

# Tatweel/kashida (U+0640) is a typographic justification-stretch mark
# publishers insert to fill line width — it is not a real character and
# breaks substring matching (e.g. "فصـل" must match "فصل" for chapter/lesson
# detection in app/infrastructure/pdf/outline_builder.py).
_TATWEEL = "\u0640"

# Short bracketed spans (e.g. chapter/reference numbers like "(1)") can come
# out mirrored as ")1(" even after the per-word fix above, because the
# bracket glyphs and the digit are extracted as one already-LTR "word" that
# our Arabic-detection skips. This targets just that narrow, common case.
_MIRRORED_BRACKET_PATTERNS = [
    (re.compile(r"\)([^()\[\]{}]{1,6})\("), r"(\1)"),
    (re.compile(r"\]([^()\[\]{}]{1,6})\["), r"[\1]"),
    (re.compile(r"\}([^()\[\]{}]{1,6})\{"), r"{\1}"),
]


def contains_arabic_script(text: str) -> bool:
    return bool(_ARABIC_SCRIPT_PATTERN.search(text))


def looks_like_a_number(word: str) -> bool:
    """True for tokens that are a number, possibly with light surrounding
    punctuation (page numbers, list markers) — regardless of whether the
    digits are Latin, Arabic-Indic, or Persian-Indic. Digit order is never
    a reading-direction concern, so these must never be character-reversed
    even though Persian-Indic digits share the Arabic Unicode block."""

    stripped = word.strip(_NUMERIC_STRIP_CHARS)
    return bool(stripped) and all(
        unicodedata.category(ch) == "Nd" for ch in stripped
    )


def normalize_digits_to_int(token: str) -> Optional[int]:
    """Converts a number token to a plain int regardless of digit script —
    Python's unicodedata.digit() maps Latin, Arabic-Indic, and Persian-Indic
    digit characters to the same 0-9 values. Non-digit characters (dot
    leaders, punctuation) are ignored. Returns None if no digits are found.
    """

    digits = [ch for ch in token if unicodedata.category(ch) == "Nd"]
    if not digits:
        return None
    return int("".join(str(unicodedata.digit(ch)) for ch in digits))


def fix_word_glyph_order(word: str) -> str:
    """Reverse character order for words containing Arabic-script
    characters. Numbers (any digit script) and Latin/numeric-only tokens
    are returned unchanged — see module docstring for why numbers need
    their own guard even though Persian-Indic digits are technically
    inside the Arabic Unicode range."""

    if looks_like_a_number(word):
        return word
    if contains_arabic_script(word):
        return word[::-1]
    return word


def fix_mirrored_brackets(text: str) -> str:
    for pattern, replacement in _MIRRORED_BRACKET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def normalize_persian_chars(text: str) -> str:
    text = text.replace(_TATWEEL, "")
    for old, new in _ARABIC_TO_PERSIAN_MAP.items():
        text = text.replace(old, new)
    return text


def normalize_spaces(text: str) -> str:
    text = text.replace("\r", "\n")
    text = text.replace("\t", " ")
    text = re.sub(r"[ ]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def remove_noise_lines(text: str) -> str:
    lines = [line.strip() for line in text.split("\n")]
    cleaned = []

    for line in lines:
        if not line:
            continue
        if len(line) <= 1:
            continue
        # Lines that are only digits/punctuation (page numbers, rules, etc.)
        if re.fullmatch(r"[\d\s\-\u2013\u2014_.:|/\\]+", line):
            continue
        cleaned.append(line)

    return "\n".join(cleaned)


def clean_persian_text(text: str) -> str:
    """Final normalization pass applied to already word/line-reconstructed
    text (see reconstruct_rtl_line below). Does NOT do any reordering —
    that must already have happened."""

    if not text:
        return ""

    text = normalize_persian_chars(text)
    text = fix_mirrored_brackets(text)
    text = normalize_spaces(text)
    text = remove_noise_lines(text)
    text = normalize_spaces(text)

    return text.strip()
