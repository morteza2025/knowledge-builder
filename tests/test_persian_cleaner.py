from app.infrastructure.text.persian_cleaner import (
    clean_persian_text,
    contains_arabic_script,
    fix_mirrored_brackets,
    fix_word_glyph_order,
    normalize_persian_chars,
)


def test_contains_arabic_script_detects_persian():
    assert contains_arabic_script("جامعه")
    assert not contains_arabic_script("Society")
    assert not contains_arabic_script("110220")


def test_fix_word_glyph_order_reverses_only_arabic_words():
    # Verified against input/C110220.pdf: pdfplumber returns "هعماج" for
    # what should read "جامعه".
    assert fix_word_glyph_order("هعماج") == "جامعه"
    assert fix_word_glyph_order("Society") == "Society"
    assert fix_word_glyph_order("110220") == "110220"


def test_fix_mirrored_brackets_swaps_short_reversed_spans():
    assert fix_mirrored_brackets("جامعه شناسی )1(") == "جامعه شناسی (1)"
    assert fix_mirrored_brackets("no brackets here") == "no brackets here"


def test_normalize_persian_chars_maps_arabic_letters_to_persian():
    assert normalize_persian_chars("علي") == "علی"
    assert normalize_persian_chars("مك") == "مک"


def test_clean_persian_text_removes_noise_lines():
    raw = "جامعه شناسی\n\n12\n---\nمتن اصلی"
    cleaned = clean_persian_text(raw)
    assert "جامعه شناسی" in cleaned
    assert "متن اصلی" in cleaned
    assert "12" not in cleaned.split("\n")


def test_clean_persian_text_handles_empty_string():
    assert clean_persian_text("") == ""
    assert clean_persian_text(None) == ""
