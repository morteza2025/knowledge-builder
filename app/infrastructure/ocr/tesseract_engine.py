"""
OCR fallback for pages with no usable text layer (scanned/photographed
pages). Uses Tesseract with configurable Persian/English language packs.

Setup this required on the host machine (not a Python dependency alone):
  sudo apt-get install tesseract-ocr tesseract-ocr-fas
  pip install pytesseract

If Tesseract or the Persian traineddata isn't installed, is_available()
returns False and the pipeline simply skips OCR (falls back to whatever
text pdfplumber found, flagged with a warning) rather than crashing.
"""

from functools import lru_cache
import statistics

from PIL import Image, ImageOps

from app.application.ports import OCREnginePort, OCRExtractionResult
from app.core.logger import app_logger
from app.core.settings import settings
from app.infrastructure.text.persian_cleaner import clean_persian_text

try:
    import pytesseract

    _PYTESSERACT_IMPORT_ERROR: Exception | None = None
except ImportError as exc:  # pragma: no cover - environment dependent
    pytesseract = None  # type: ignore[assignment]
    _PYTESSERACT_IMPORT_ERROR = exc


class TesseractOCREngine(OCREnginePort):
    def __init__(
        self,
        *,
        psm: int = settings.ocr_tesseract_psm,
        preprocessing_mode: str = settings.ocr_preprocessing_mode,
        threshold: int | None = settings.ocr_threshold,
    ):
        self._config = f"--psm {psm}"
        self._preprocessing_mode = preprocessing_mode
        self._threshold = threshold

    @lru_cache(maxsize=1)
    def is_available(self) -> bool:
        if pytesseract is None:
            app_logger.warning(
                "pytesseract not installed (%s) — OCR disabled.",
                _PYTESSERACT_IMPORT_ERROR,
            )
            return False

        try:
            langs = pytesseract.get_languages(config="")
        except Exception as exc:
            app_logger.warning("Tesseract binary not found or broken: %s", exc)
            return False

        required_languages = {
            part.strip() for part in settings.ocr_language.split("+") if part.strip()
        }
        missing_languages = required_languages.difference(langs)
        if missing_languages:
            app_logger.warning(
                "Tesseract language packs are missing: %s. Install Persian "
                "with: sudo apt-get install tesseract-ocr-fas",
                ", ".join(sorted(missing_languages)),
            )
            return False

        return True

    def _preprocess(self, image: Image.Image) -> Image.Image:
        if self._preprocessing_mode == "none":
            processed = image.convert("RGB")
        else:
            processed = ImageOps.grayscale(image)
            if self._preprocessing_mode == "autocontrast":
                processed = ImageOps.autocontrast(processed)
        if self._threshold is not None:
            threshold = self._threshold
            processed = processed.point(lambda value: 255 if value >= threshold else 0)
        return processed

    def extract_text(self, image: Image.Image, language: str = "fas+eng") -> str:
        return self.extract_with_quality(image, language).text

    def extract_with_quality(
        self, image: Image.Image, language: str = "fas+eng"
    ) -> OCRExtractionResult:
        if pytesseract is None:
            raise RuntimeError("pytesseract is not installed")
        processed = self._preprocess(image)
        text = pytesseract.image_to_string(
            processed, lang=language, config=self._config
        )
        data = pytesseract.image_to_data(
            processed,
            lang=language,
            config=self._config,
            output_type=pytesseract.Output.DICT,
        )
        confidence_values = []
        for raw_value in data.get("conf", []):
            try:
                value = float(raw_value)
            except (TypeError, ValueError):
                continue
            if value >= 0:
                confidence_values.append(value)

        confidence = (
            statistics.fmean(confidence_values) if confidence_values else None
        )
        return OCRExtractionResult(
            text=clean_persian_text(text), confidence=confidence
        )
