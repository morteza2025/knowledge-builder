"""
The verified RTL reconstruction algorithm, factored out so it can run on
either a full page or a cropped region (pdfplumber's CroppedPage supports
the same .extract_words() interface, so this works unmodified on table
cells too — verified against input/C110220.pdf: a raw cell string like
")میهد یم ماجنا هچنآ( ام یاه شنِکُ" only reads correctly as "کُنش‌های ما
(آنچه انجام می‌دهیم)" after the SAME line-grouping + right-to-left word
sort + per-word character reversal used for body text. Table.extract()'s
built-in cell text does not apply this fix, which is why table extraction
uses this function directly on cropped cell bboxes instead.
"""

from app.infrastructure.text.persian_cleaner import fix_word_glyph_order

LINE_BAND_PX = 3  # words within this many points of `top` are one line


def reconstruct_text(page_like) -> str:
    """`page_like` is anything exposing pdfplumber's .extract_words() —
    a full Page or a CroppedPage (e.g. page.crop(bbox))."""

    words = page_like.extract_words(use_text_flow=False)
    if not words:
        return ""

    lines: dict[int, list] = {}
    for word in words:
        line_key = round(word["top"] / LINE_BAND_PX) * LINE_BAND_PX
        lines.setdefault(line_key, []).append(word)

    text_lines = []
    for line_key in sorted(lines.keys()):
        line_words = sorted(lines[line_key], key=lambda w: -w["x0"])
        line_text = " ".join(fix_word_glyph_order(w["text"]) for w in line_words)
        text_lines.append(line_text)

    return "\n".join(text_lines)
