from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]

INPUT_DIR = BASE_DIR / "input"
OUTPUT_DIR = BASE_DIR / "outputs"
OUTPUT_JSON_DIR = OUTPUT_DIR / "json"
OUTPUT_MARKDOWN_DIR = OUTPUT_DIR / "markdown"
LOG_DIR = BASE_DIR / "logs"

MAX_PAGES_PER_REQUEST = 5000
MIN_TEXT_LENGTH_FOR_TEXT_PAGE = 30

SUPPORTED_EXTENSIONS = {".pdf"}

for directory in [INPUT_DIR, OUTPUT_JSON_DIR, OUTPUT_MARKDOWN_DIR, LOG_DIR]:
    directory.mkdir(parents=True, exist_ok=True)