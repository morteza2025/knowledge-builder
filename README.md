# EduLeague Knowledge Builder

Local PDF-to-structured-knowledge pipeline for EduLeague. Converts Persian
educational PDFs (textbooks, supplementary books) into clean, structured
JSON/Markdown, correctly ordered and OCR-backed — the foundation feeding
EduLeague's AI Teacher, AI Planner, and future educational AI services.

See `docs/architecture/ADR-001-clean-architecture.md` for the layering
rationale and `docs/architecture/ADR-002-knowledge-graph-roadmap.md` for
where this is headed next.

## Setup

```bash
pip install -r requirements.txt
```

### OCR setup (required for the OCR fallback to work)

Tesseract itself is a system package, not a Python package:

```bash
# Debian/Ubuntu
sudo apt-get install tesseract-ocr tesseract-ocr-fas

# Windows: install the Tesseract binary from
# https://github.com/UB-Mannheim/tesseract/wiki (includes language packs
# during setup — make sure Persian/Farsi is checked), then either add it to
# PATH or point pytesseract at it explicitly:
#   pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
```

If Tesseract or the Persian language pack isn't installed, the pipeline
doesn't crash — `TesseractOCREngine.is_available()` returns `False` and
low-text pages are simply flagged `LOW_TEXT_MAY_NEED_OCR` / `needs_review`
instead of being recovered.

## Running

```bash
uvicorn app.main:app --reload
```

Then either open `/docs` for the interactive Swagger UI, or:

```bash
curl -X POST http://127.0.0.1:8000/process \
  -H "Content-Type: application/json" \
  -d '{"filename": "C110220.pdf", "book_title": "جامعه شناسی (۱)", "course": "انسانی", "grade": "دهم"}'
```

Output lands in `outputs/json/<name>.json` and `outputs/markdown/<name>.md`.

## Avoiding encoding corruption

An earlier version of this project had a real bug: `book_title` came back
from a processing run as literal `"???? ???"` inside the saved JSON. That
wasn't an extraction bug — the Persian text was already replaced with `?`
characters *before* it left the client, almost always because a Windows
terminal (`cmd.exe` / raw PowerShell) wasn't using a UTF-8 codepage when
`curl` sent the request body.

Two ways to avoid this entirely:

1. **Don't hand-type Persian into a Windows terminal command.** Send
   requests from a script (Python `requests`, a `.http` file, Postman,
   Swagger UI at `/docs`) where the body is UTF-8 from the start.
2. **Use a sidecar metadata file instead of request parameters.** Place a
   `<same-name-as-pdf>.meta.json` file next to the PDF in `input/`:

   ```json
   {
     "book_title": "جامعه شناسی (۱)",
     "course": "انسانی",
     "grade": "دهم"
   }
   ```

   Then `POST /process` with just `{"filename": "C110220.pdf"}` — metadata is
   read directly from the UTF-8 JSON file on disk, never through a terminal.

As a second line of defense, the API also rejects any `book_title`/`course`/
`grade` value containing a suspicious run of `?` characters
(`app/core/encoding_guard.py`) with an explanatory error, rather than saving
corrupted text silently.

## The RTL extraction fix (read this before touching the PDF engine)

The previous extractor used PyMuPDF's `page.get_text("text")`, which — for
the actual book PDFs this project processes — produced text with **both**
word order and character order wrong (verified against
`input/C110220.pdf`: "جامعه‌شناسی" came out as "شناسی جامعه"). The current
extractor (`app/infrastructure/pdf/pdfplumber_engine.py`) fixes both axes:

1. Extracts words with their bounding boxes via `pdfplumber`.
2. Groups words into lines by vertical position (`top`, banded to 3pt).
3. Sorts words within each line by **descending** `x0` (right-to-left).
4. Reverses the **character order** of any word containing Arabic-script
   characters (Latin words and numbers are left alone).
5. Fixes short mirrored bracket spans like `)1(` → `(1)`.

Steps 3 and 4 are both required — fixing only one still leaves the output
scrambled. This is covered by a regression test
(`tests/test_pdf_extraction.py`) that runs against the real sample PDF, not
a mock, because the bug only reproduces against actual pdfplumber output.

## Architecture

```
app/
├── domain/            # Pure models. No FastAPI/pdfplumber/OCR imports.
├── application/        # Use cases, pipeline stages, ports (interfaces).
├── infrastructure/     # Concrete adapters: pdfplumber, tesseract, exporters.
├── api/                 # FastAPI routes/schemas/DI wiring only.
└── core/               # Settings, logging, exceptions, cross-cutting utils.
```

Swapping an engine (e.g. adding a Docling-based extractor, or a cloud OCR
API) means writing a new adapter against the existing port in
`app/application/ports.py` — no changes needed in `domain/` or the use case
orchestration in `application/use_cases/`.

## Testing

```bash
pytest
```

Note: the PDF-extraction regression tests run against the real
152-page sample PDF in `input/`, so the full suite takes about a minute.

## Known limitations / next steps

- OCR is a fallback for low-text pages, not a first-class path for fully
  scanned books — no page-deskew, no layout analysis beyond what Tesseract
  does internally.
- Table extraction (`pdfplumber.extract_tables()`) isn't wired in yet —
  needed for the supplementary-book pipeline's syllable/scansion tables.
- Knowledge Graph extraction and cross-book concept merging are modeled
  (`app/domain/concept.py`) but not implemented — see ADR-002.
