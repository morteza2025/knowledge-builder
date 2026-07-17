from __future__ import annotations

from typing import Optional

from app.core.encoding_guard import assert_clean_text
from app.core.exceptions import SuspiciousEncodingError


_KEYS = {
    "title": "book_title",
    "book_title": "book_title",
    "عنوان": "book_title",
    "course": "course",
    "درس": "course",
    "رشته": "course",
    "grade": "grade",
    "پایه": "grade",
}


def parse_caption_metadata(caption: Optional[str]) -> dict[str, Optional[str]]:
    result: dict[str, Optional[str]] = {
        "book_title": None,
        "course": None,
        "grade": None,
    }
    if not caption or len(caption) > 2000:
        return result

    for line in caption.splitlines():
        if ":" not in line:
            continue
        raw_key, raw_value = line.split(":", 1)
        key = _KEYS.get(raw_key.strip().lower())
        value = raw_value.strip()
        if not key or not value or len(value) > 200:
            continue
        try:
            result[key] = assert_clean_text(value, key)
        except SuspiciousEncodingError:
            continue
    return result
