"""
Structural block detection: turns a flat page of text into ordered
DocumentBlocks (heading / paragraph / table).

Two independent signals are used, both verified against the real sample PDF
(input/C110220.pdf) before being written here:

1. Headings — detected from font size relative to the document's own body
   baseline size, plus non-black ink color and bold font names. E.g. the
   page-1 title is 30pt against an ~11-12pt body baseline; a colored
   (non-achromatic) run of text on page 5 is a different, deliberately
   styled element, not body prose.

2. Tables — pdfplumber's `page.find_tables()` finds any bordered/ruled
   region, which on real textbook PDFs includes decorative title/activity
   boxes as often as genuine data tables (verified: ~240 "tables" detected
   across 152 pages of a prose-heavy sociology book that has essentially no
   real statistical tables). This module does NOT attempt to semantically
   tell "decorative box" apart from "real data table" — that needs either
   manual review or a book with genuinely tabular content to calibrate
   against. What it does do: reconstruct each cell's text with the same
   verified RTL fix used for body text (Table.extract()'s built-in cell
   text does NOT apply this fix and comes out word-order-scrambled), then
   NEVER silently drops a non-empty region — a bordered box with a low
   filled-cell ratio (verified: lesson-title boxes like "درس اول" plus a
   short theme phrase, ~0.33 fill ratio because most cells are empty icon
   placeholders) is exactly the kind of lesson-boundary marker this
   pipeline exists to capture, not junk to filter out. Regions at/above
   the fill-ratio threshold become `table` blocks; short, sparse regions
   below it become `heading` blocks (title-box case); longer sparse
   regions become `paragraph` blocks. Every case keeps `fill_ratio` in
   metadata so downstream consumers can apply their own threshold instead.
"""

import statistics
from dataclasses import dataclass, field

from app.core.logger import app_logger
from app.domain.document import BlockType, DocumentBlock
from app.infrastructure.pdf.rtl_text import LINE_BAND_PX, reconstruct_text
from app.infrastructure.text.persian_cleaner import (
    clean_persian_text,
    fix_word_glyph_order,
)

# --- heading classification tuning -----------------------------------------

_HEADING_SIZE_RATIO_STRONG = 1.5
_HEADING_SIZE_RATIO_WEAK = 1.15
_HEADING_SCORE_THRESHOLD = 0.5
_HEADING_LONG_LINE_CHARS = 100

# --- table quality tuning ---------------------------------------------------

_TABLE_MIN_ROWS = 2
_TABLE_MIN_COLS = 2
_TABLE_MIN_FILL_RATIO = 0.5
_SPARSE_BOX_TITLE_MAX_CHARS = 60


@dataclass
class LineInfo:
    page_number: int
    text: str
    top: float
    bottom: float
    x0: float
    x1: float
    avg_size: float
    is_bold: bool
    is_colored: bool


@dataclass
class ClassificationResult:
    block_type: BlockType
    confidence: float
    reason: str


def _is_achromatic_color(color) -> bool:
    """True for black/gray/white ink — i.e. NOT a deliberately colored
    heading/callout. Handles pdfplumber's grayscale (1-tuple), RGB
    (3-tuple), and CMYK (4-tuple) color representations."""

    if not color:
        return True

    if len(color) == 1:
        return True

    if len(color) == 3:
        r, g, b = color
        return max(abs(r - g), abs(g - b), abs(r - b)) < 0.08

    if len(color) >= 4:
        c, m, y = color[0], color[1], color[2]
        return max(abs(c - m), abs(m - y), abs(c - y)) < 0.08

    return True


def extract_lines_with_style(page, page_number: int) -> list[LineInfo]:
    words = page.extract_words(
        use_text_flow=False,
        extra_attrs=["size", "non_stroking_color", "fontname"],
    )
    if not words:
        return []

    lines: dict[int, list] = {}
    for word in words:
        line_key = round(word["top"] / LINE_BAND_PX) * LINE_BAND_PX
        lines.setdefault(line_key, []).append(word)

    result: list[LineInfo] = []
    for line_key in sorted(lines.keys()):
        line_words = sorted(lines[line_key], key=lambda w: -w["x0"])
        text = " ".join(fix_word_glyph_order(w["text"]) for w in line_words)

        sizes = [w.get("size") or 0 for w in line_words]
        fontnames = [w.get("fontname") or "" for w in line_words]
        colors = [
            w.get("non_stroking_color")
            for w in line_words
            if w.get("non_stroking_color")
        ]

        result.append(
            LineInfo(
                page_number=page_number,
                text=text,
                top=min(w["top"] for w in line_words),
                bottom=max(w["bottom"] for w in line_words),
                x0=min(w["x0"] for w in line_words),
                x1=max(w["x1"] for w in line_words),
                avg_size=statistics.mean(sizes) if sizes else 0.0,
                is_bold=any("bold" in f.lower() for f in fontnames),
                is_colored=any(not _is_achromatic_color(c) for c in colors),
            )
        )

    return result


def compute_document_baseline_size(all_page_lines: list[list[LineInfo]]) -> float:
    """The document's typical body-text font size, used as the reference
    point for heading detection. Median (not mean) so a handful of large
    titles/captions don't drag the baseline up."""

    sizes = [
        line.avg_size
        for lines in all_page_lines
        for line in lines
        if line.avg_size and line.text.strip()
    ]
    return statistics.median(sizes) if sizes else 12.0


def classify_line(line: LineInfo, baseline_size: float) -> ClassificationResult:
    if not line.text.strip():
        return ClassificationResult(BlockType.paragraph, 1.0, "empty_line")

    baseline = baseline_size if baseline_size > 0 else 12.0
    size_ratio = line.avg_size / baseline

    score = 0.0
    reasons = []

    if size_ratio >= _HEADING_SIZE_RATIO_STRONG:
        score += 0.5
        reasons.append(f"size_ratio={size_ratio:.2f}")
    elif size_ratio >= _HEADING_SIZE_RATIO_WEAK:
        score += 0.25
        reasons.append(f"size_ratio={size_ratio:.2f}")

    if line.is_colored:
        score += 0.35
        reasons.append("colored_ink")

    if line.is_bold:
        score += 0.15
        reasons.append("bold_font")

    if len(line.text) > _HEADING_LONG_LINE_CHARS:
        score -= 0.4
        reasons.append("long_line_penalty")

    reason_text = "; ".join(reasons) if reasons else "body_text"

    if score >= _HEADING_SCORE_THRESHOLD:
        return ClassificationResult(BlockType.heading, min(score, 1.0), reason_text)

    return ClassificationResult(
        BlockType.paragraph, min(max(1.0 - score, 0.5), 1.0), reason_text
    )


def extract_table_blocks(
    page, page_number: int
) -> tuple[list[DocumentBlock], list[tuple]]:
    """Returns (table_blocks, bboxes_to_exclude_from_paragraph_text)."""

    blocks: list[DocumentBlock] = []
    exclude_bboxes: list[tuple] = []

    try:
        tables = page.find_tables()
    except Exception as exc:  # pragma: no cover - pdfplumber internal failure
        app_logger.debug("Table detection failed on page %s: %s", page_number, exc)
        return blocks, exclude_bboxes

    for idx, table in enumerate(tables, start=1):
        try:
            row_cell_bboxes = [row.cells for row in table.rows]
        except Exception:  # pragma: no cover
            continue

        if len(row_cell_bboxes) < _TABLE_MIN_ROWS:
            continue

        col_count = max((len(row) for row in row_cell_bboxes), default=0)
        if col_count < _TABLE_MIN_COLS:
            continue

        fixed_rows: list[list[str]] = []
        for row_cells in row_cell_bboxes:
            row_texts = []
            for cell_bbox in row_cells:
                if cell_bbox is None:
                    row_texts.append("")
                    continue
                try:
                    cell_text = clean_persian_text(
                        reconstruct_text(page.crop(cell_bbox))
                    )
                except Exception:  # pragma: no cover
                    cell_text = ""
                row_texts.append(cell_text)
            fixed_rows.append(row_texts)

        total_cells = sum(len(row) for row in fixed_rows)
        filled_cells = sum(1 for row in fixed_rows for cell in row if cell.strip())
        fill_ratio = filled_cells / total_cells if total_cells else 0.0

        non_empty_texts = [cell for row in fixed_rows for cell in row if cell.strip()]
        if not non_empty_texts:
            continue  # genuinely empty bordered region — nothing to preserve

        top = min(
            (bbox[1] for row in row_cell_bboxes for bbox in row if bbox), default=0
        )

        # A bordered region with a low fill ratio isn't necessarily junk —
        # verified against input/C110220.pdf: lesson-title boxes ("درس
        # اول" + a short theme phrase) have fill_ratio ~0.33 because most
        # cells are empty icon placeholders, not because the content is
        # unimportant. Dropping anything below the data-table threshold
        # would silently lose exactly the lesson-boundary markers this
        # pipeline exists to capture. So: never drop, only relabel.
        combined_text = " — ".join(non_empty_texts)

        if fill_ratio >= _TABLE_MIN_FILL_RATIO:
            block_type = BlockType.table
            text = "\n".join(" | ".join(row) for row in fixed_rows)
            confidence = fill_ratio
        elif len(combined_text) <= _SPARSE_BOX_TITLE_MAX_CHARS:
            # Short + sparse: almost certainly a title/label box, not a
            # data grid or a real paragraph.
            block_type = BlockType.heading
            text = combined_text
            confidence = 0.4
        else:
            block_type = BlockType.paragraph
            text = combined_text
            confidence = 0.3

        blocks.append(
            DocumentBlock(
                id=f"{page_number}-table-{idx}",
                type=block_type,
                text=text,
                page=page_number,
                metadata={
                    "rows": fixed_rows,
                    "fill_ratio": round(fill_ratio, 2),
                    "top": top,
                    "confidence": round(confidence, 2),
                    "source": "bordered_region",
                },
            )
        )
        exclude_bboxes.append(table.bbox)

    return blocks, exclude_bboxes


def build_page_blocks(
    page, page_number: int, lines: list[LineInfo], baseline_size: float
) -> list[DocumentBlock]:
    table_blocks, exclude_bboxes = extract_table_blocks(page, page_number)

    def is_within_excluded(line: LineInfo) -> bool:
        for x0, top, x1, bottom in exclude_bboxes:
            if line.top >= top - 1 and line.bottom <= bottom + 1:
                return True
        return False

    # Unified, top-position-ordered stream of (position, kind, payload) so
    # tables end up interleaved with surrounding paragraphs/headings in
    # actual page order, not appended at the end.
    items: list[tuple[float, str, object]] = []

    for line in lines:
        if not line.text.strip() or is_within_excluded(line):
            continue
        items.append((line.top, "line", line))

    for block in table_blocks:
        items.append((block.metadata.get("top", 0.0), "table", block))

    items.sort(key=lambda item: item[0])

    blocks: list[DocumentBlock] = []
    paragraph_buffer: list[str] = []
    block_index = 0

    def flush_paragraph() -> None:
        nonlocal block_index
        if paragraph_buffer:
            block_index += 1
            blocks.append(
                DocumentBlock(
                    id=f"{page_number}-{block_index}",
                    type=BlockType.paragraph,
                    text=clean_persian_text("\n".join(paragraph_buffer)),
                    page=page_number,
                )
            )
            paragraph_buffer.clear()

    for _, kind, payload in items:
        if kind == "table":
            flush_paragraph()
            block_index += 1
            table_block = payload
            table_block.id = f"{page_number}-{block_index}"
            blocks.append(table_block)
            continue

        line: LineInfo = payload
        result = classify_line(line, baseline_size)

        if result.block_type == BlockType.heading:
            flush_paragraph()
            block_index += 1
            blocks.append(
                DocumentBlock(
                    id=f"{page_number}-{block_index}",
                    type=BlockType.heading,
                    text=clean_persian_text(line.text),
                    page=page_number,
                    metadata={
                        "confidence": round(result.confidence, 2),
                        "reason": result.reason,
                    },
                )
            )
        else:
            paragraph_buffer.append(line.text)

    flush_paragraph()
    return blocks
