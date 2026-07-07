from app.domain.document import BlockType
from app.infrastructure.pdf.structure_analyzer import (
    LineInfo,
    _is_achromatic_color,
    classify_line,
    compute_document_baseline_size,
)


def _line(text="متن نمونه", avg_size=12.0, is_bold=False, is_colored=False):
    return LineInfo(
        page_number=1,
        text=text,
        top=0.0,
        bottom=10.0,
        x0=0.0,
        x1=100.0,
        avg_size=avg_size,
        is_bold=is_bold,
        is_colored=is_colored,
    )


def test_is_achromatic_color_handles_all_color_space_shapes():
    assert _is_achromatic_color(None)
    assert _is_achromatic_color((0.5,))  # grayscale
    assert _is_achromatic_color((0.0, 0.0, 0.0))  # RGB black
    assert _is_achromatic_color((0.1, 0.12, 0.09))  # near-gray RGB
    assert not _is_achromatic_color((1.0, 0.0, 0.0))  # RGB red

    assert _is_achromatic_color((0.0, 0.0, 0.0, 1.0))  # CMYK black
    assert not _is_achromatic_color((0.2, 0.35, 1.0, 0.0))  # CMYK orange-ish


def test_large_font_is_classified_as_heading():
    line = _line(text="جامعه شناسی", avg_size=30.0)
    result = classify_line(line, baseline_size=12.0)
    assert result.block_type == BlockType.heading


def test_body_sized_text_is_classified_as_paragraph():
    line = _line(text="این یک متن معمولی است", avg_size=12.0)
    result = classify_line(line, baseline_size=12.0)
    assert result.block_type == BlockType.paragraph


def test_colored_ink_pushes_toward_heading_even_at_body_size():
    line = _line(text="نکته", avg_size=12.0, is_colored=True, is_bold=True)
    result = classify_line(line, baseline_size=12.0)
    assert result.block_type == BlockType.heading


def test_long_line_is_never_classified_as_heading_even_if_large():
    long_text = "کلمه " * 30
    line = _line(text=long_text, avg_size=16.0)
    result = classify_line(line, baseline_size=12.0)
    assert result.block_type == BlockType.paragraph


def test_empty_line_is_paragraph_with_full_confidence():
    line = _line(text="   ", avg_size=30.0, is_colored=True)
    result = classify_line(line, baseline_size=12.0)
    assert result.block_type == BlockType.paragraph
    assert result.confidence == 1.0


def test_compute_document_baseline_size_uses_median_not_mean():
    lines_page_1 = [_line(avg_size=12.0), _line(avg_size=12.0), _line(avg_size=12.0)]
    lines_page_2 = [_line(avg_size=30.0)]  # one large title shouldn't skew it
    baseline = compute_document_baseline_size([lines_page_1, lines_page_2])
    assert baseline == 12.0


def test_compute_document_baseline_size_falls_back_when_empty():
    assert compute_document_baseline_size([]) == 12.0
    assert compute_document_baseline_size([[]]) == 12.0
