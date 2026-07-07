"""
OCR fallback for pages with no usable text layer (scanned/photographed
pages). Uses Tesseract with the Persian ('fas') language pack.

Setup this required on the host machine (not a Python dependency alone):
  sudo apt-get install tesseract-ocr tesseract-ocr-fas
  pip install pytesseract

If Tesseract or the Persian traineddata isn't installed, is_available()
returns False and the pipeline simply skips OCR (falls back to whatever
text pdfplumber found, flagged with a warning) rather than crashing.
"""

from functools import lru_cache

from PIL import Image

from app.application.ports import OCREnginePort
from app.core.logger import app_logger

try:
    import pytesseract

    _PYTESSERACT_IMPORT_ERROR: Exception | None = None
except ImportError as exc:  # pragma: no cover - environment dependent
    pytesseract = None  # type: ignore[assignment]
    _PYTESSERACT_IMPORT_ERROR = exc


class TesseractOCREngine(OCREnginePort):
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

        if "fas" not in langs:
            app_logger.warning(
                "Tesseract is installed but the Persian ('fas') language "
                "pack is missing. Install it with: "
                "sudo apt-get install tesseract-ocr-fas"
            )
            return False

        return True

    def extract_text(self, image: Image.Image, language: str = "fas") -> str:
        if pytesseract is None:
            raise RuntimeError("pytesseract is not installed")
        return pytesseract.image_to_string(image, lang=language)
