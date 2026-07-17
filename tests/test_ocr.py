from types import SimpleNamespace

import pytest
from PIL import Image

from app.application.ports import OCRExtractionResult
from app.domain.document import ExtractionMethod
from app.infrastructure.ocr import tesseract_engine as module
from app.infrastructure.ocr.tesseract_engine import TesseractOCREngine
from app.infrastructure.pdf.pdfplumber_engine import PdfPlumberTextExtractor
from app.infrastructure.pdf.structure_analyzer import LineInfo


class FakePytesseract:
    class Output:
        DICT = "dict"

    def __init__(self, languages=("fas", "eng"), confidence="80"):
        self.languages = list(languages)
        self.confidence = confidence
        self.calls = []

    def get_languages(self, config=""):
        return self.languages

    def image_to_string(self, image, **kwargs):
        self.calls.append(("string", kwargs))
        return "این یک آزمایش فارسی است. جامعه‌شناسی و آموزش"

    def image_to_data(self, image, **kwargs):
        self.calls.append(("data", kwargs))
        return {"conf": [self.confidence, "-1", "invalid"]}


def test_tesseract_configuration_passes_fas_eng_and_psm(monkeypatch):
    fake = FakePytesseract()
    monkeypatch.setattr(module, "pytesseract", fake)
    engine = TesseractOCREngine(psm=6, preprocessing_mode="autocontrast")

    result = engine.extract_with_quality(Image.new("RGB", (20, 20), "white"), "fas+eng")

    assert "آزمایش فارسی" in result.text
    assert result.confidence == 80.0
    assert all(call[1]["lang"] == "fas+eng" for call in fake.calls)
    assert all(call[1]["config"] == "--psm 6" for call in fake.calls)


def test_missing_language_pack_makes_tesseract_unavailable(monkeypatch):
    fake = FakePytesseract(languages=("eng",))
    monkeypatch.setattr(module, "pytesseract", fake)
    TesseractOCREngine.is_available.cache_clear()
    assert TesseractOCREngine().is_available() is False


def test_broken_tesseract_binary_is_reported_unavailable(monkeypatch):
    class BrokenPytesseract(FakePytesseract):
        def get_languages(self, config=""):
            raise OSError("binary unavailable")

    monkeypatch.setattr(module, "pytesseract", BrokenPytesseract())
    TesseractOCREngine.is_available.cache_clear()
    assert TesseractOCREngine().is_available() is False


def test_ocr_is_not_called_when_disabled():
    class ExplodingOCR:
        def is_available(self):
            raise AssertionError("OCR availability must not be checked")

        def extract_with_quality(self, image, language):
            raise AssertionError("OCR must not run")

    extractor = PdfPlumberTextExtractor(ocr_engine=ExplodingOCR(), use_ocr=True)
    cleaned, method, warnings, needs_review = extractor._maybe_run_ocr(
        None,
        1,
        "",
        ExtractionMethod.pdfplumber_positional,
        [],
        False,
    )
    assert cleaned == ""
    assert needs_review is True


def test_low_confidence_ocr_emits_warning():
    class LowConfidenceOCR:
        def is_available(self):
            return True

        def extract_with_quality(self, image, language):
            return OCRExtractionResult(text="متن فارسی بازیابی شده", confidence=10.0)

    class Page:
        def to_image(self, resolution):
            return SimpleNamespace(original=Image.new("RGB", (20, 20), "white"))

    extractor = PdfPlumberTextExtractor(ocr_engine=LowConfidenceOCR(), use_ocr=True)
    cleaned, method, warnings, needs_review = extractor._maybe_run_ocr(
        Page(),
        1,
        "",
        ExtractionMethod.pdfplumber_positional,
        [],
        True,
    )
    assert "متن فارسی" in cleaned
    assert method == ExtractionMethod.ocr_tesseract
    assert any(warning.startswith("OCR_LOW_CONFIDENCE:") for warning in warnings)


def test_ocr_exception_is_captured_as_page_warning():
    class FailingOCR:
        def is_available(self):
            return True

        def extract_with_quality(self, image, language):
            raise RuntimeError("simulated OCR failure")

    class Page:
        def to_image(self, resolution):
            return SimpleNamespace(original=Image.new("RGB", (20, 20), "white"))

    extractor = PdfPlumberTextExtractor(ocr_engine=FailingOCR(), use_ocr=True)
    cleaned, method, warnings, needs_review = extractor._maybe_run_ocr(
        Page(),
        1,
        "",
        ExtractionMethod.pdfplumber_positional,
        [],
        True,
    )
    assert cleaned == ""
    assert method == ExtractionMethod.pdfplumber_positional
    assert any(warning.startswith("OCR_FAILED:") for warning in warnings)


def test_usable_text_layer_skips_ocr():
    class ExplodingOCR:
        def is_available(self):
            raise AssertionError("OCR should not be consulted for usable text")

    class Page:
        width = 100
        height = 100

        def find_tables(self):
            return []

    line = LineInfo(
        page_number=1,
        text="این یک متن فارسی کافی برای عبور از آستانه استخراج است",
        top=0,
        bottom=10,
        x0=0,
        x1=100,
        avg_size=12,
        is_bold=False,
        is_colored=False,
    )
    extractor = PdfPlumberTextExtractor(
        ocr_engine=ExplodingOCR(), use_ocr=True, min_chars_for_valid_page=10
    )
    page = extractor._extract_single_page(Page(), 1, [line], 12.0, True)
    assert page.extraction_method == ExtractionMethod.pdfplumber_positional
    assert not any(warning.startswith("OCR_") for warning in page.warnings)


@pytest.mark.ocr_integration
def test_real_persian_ocr_fixture_has_expected_quality():
    pytest.skip(
        "requires Tesseract with fas+eng and a deterministic Persian-capable font fixture"
    )
