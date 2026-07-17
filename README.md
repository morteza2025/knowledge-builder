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

## Command-line interface (no server needed)

For a one-off run, `cli.py` does everything the API does without starting
uvicorn:

```bash
python cli.py process C110220.pdf --title "جامعه شناسی (۱)" --course انسانی --grade دهم

python cli.py process C110220.pdf --json   # machine-readable output

python cli.py batch                         # every PDF in input/
python cli.py batch book1.pdf book2.pdf     # just these
```

Exit code is `0` when everything succeeded, `1` if any book failed (`batch`
still processes every book regardless — see below). Same metadata
resolution as the API: `--title`/`--course`/`--grade` first, then each
book's own `<name>.meta.json` sidecar file, then the filename.

## Batch processing multiple books

Via the API:

```bash
# Process specific files
curl -X POST http://127.0.0.1:8000/process/batch \
  -H "Content-Type: application/json" \
  -d '{"filenames": ["C110220.pdf", "another_book.pdf"]}'

# Or process every PDF currently in input/ — omit "filenames" entirely
curl -X POST http://127.0.0.1:8000/process/batch \
  -H "Content-Type: application/json" \
  -d '{}'
```

Or, without a running server: `python cli.py batch` (see above).

Each book uses its own `<name>.meta.json` sidecar file for title/course/grade
(see "Avoiding encoding corruption" above) — batch requests don't take
per-book metadata directly, since typing several books' Persian titles into
one request is exactly the kind of thing that risks terminal-encoding
corruption. Drop PDFs into `input/` with their sidecar files and batch-run
the whole folder.

One bad file (missing, corrupt, wrong format) fails only that item — the
response reports `total` / `succeeded` / `failed` counts plus a per-file
result-or-error, and the rest of the batch still completes:

```json
{
  "total": 3, "succeeded": 2, "failed": 1,
  "items": [
    {"filename": "book1.pdf", "ok": true, "result": { "...": "..." }},
    {"filename": "book2.pdf", "ok": false, "error": "File not found: ..."},
    {"filename": "book3.pdf", "ok": true, "result": { "...": "..." }}
  ]
}
```

Processing is sequential, not parallel — see
`app/application/use_cases/process_batch.py` for why (short version: this
is a local single-machine tool, and both pdfplumber parsing and Tesseract
OCR are CPU-bound, so threads wouldn't meaningfully speed things up without
adding real complexity). A large enough batch would be the point to
revisit this with a process pool.

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

## Structural block detection (headings + tables)

Beyond flat page text, each `DocumentPage.blocks` now holds an ordered list
of `heading` / `paragraph` / `table` blocks:

- **Headings** are detected from font size relative to the document's own
  body-text baseline (median size across the whole PDF, not a fixed number —
  a photo-heavy book and a dense-text book have different baselines), plus
  non-black ink color and bold font names as secondary signals. This is a
  heuristic, not a semantic understanding of the text — section labels
  styled only through spacing/context rather than typography (e.g. a
  same-size-as-body label like "بخوانیم و بدانیم") won't be caught. Verified
  against `input/C110220.pdf`: the 30pt cover title is correctly classified
  as a heading against an ~11-12pt body baseline.

- **Tables** come from `pdfplumber.page.find_tables()`, with each cell's
  text reconstructed using the *same* RTL fix as body text — `Table.extract()`'s
  built-in cell text is NOT RTL-safe and comes out word-order-scrambled
  (verified: a raw cell string only reads correctly after the same
  line-grouping + right-to-left sort + per-word character reversal used
  everywhere else in this pipeline).

  **Known limitation:** `find_tables()` detects any bordered/ruled region,
  which on real textbook PDFs includes decorative title/activity boxes as
  often as genuine data tables — verified empirically (~240 raw "tables"
  detected across 152 pages of `C110220.pdf`, most of them lesson-title
  boxes, not data grids). A bordered region is never silently dropped,
  though: regions at/above a minimum filled-cell ratio (`fill_ratio >= 0.5`)
  become `table` blocks; regions below that bar but short are relabeled as
  `heading` blocks instead of being discarded. This matters in practice —
  lesson-title boxes (e.g. "درس اول" + a short theme phrase) have
  `fill_ratio` around 0.33 because most cells are empty icon placeholders,
  and an earlier version of this filter was silently dropping them,
  losing exactly the lesson-boundary markers this pipeline exists to
  capture. Every table/relabeled-heading block still exposes `fill_ratio`
  in `metadata` so downstream consumers can apply their own threshold.

Also: Persian text extracted from this PDF contains tatweel/kashida
characters (U+0640, inserted by the publisher to justify line width — e.g.
"فصل" extracts as "فصـل"). These are stripped during cleaning
(`persian_cleaner.normalize_persian_chars`) since they're not real
characters and would otherwise break substring matching against plain
"فصل"/"درس" chapter/lesson markers.

## Chapter/lesson/subtopic outline extraction (Django seeding bridge)

Beyond per-page blocks, the pipeline now produces a full book outline —
chapters, lessons (globally numbered across chapters, not restarting per
chapter), and subtopic questions, each with the book's own printed page
number — parsed from the book's own table-of-contents page(s), and exports
it as JSON in the shape the existing Django seeding pattern expects:

```python
Book.update_or_create(subject, grade, field)
structure = [(chapter_title, [(order, lesson_title, page)])]
```

**Why the TOC page, not body-text heading detection:** font-size-based
heading detection alone is incomplete — verified against `C110220.pdf`,
only 4 of 7 chapter-1 lesson-title boxes survived detection as distinct
blocks. The book's own TOC page, by contrast, lists all 16 lessons across
both chapters completely, each with an explicit page number — and even the
subtopic-level questions beneath each lesson, also with page numbers. That
granularity is exactly what `app/infrastructure/text/toc_parser.py` parses.

**Quirks found and fixed while building this** (all verified against the
real TOC pages in `C110220.pdf`, and covered by regression tests):

1. **Mixed-script page numbers were being corrupted by this pipeline's own
   RTL fix.** Page 29 extracts from the PDF as the token "2٩" (Latin '2' +
   Persian-Indic '٩'=9) — already in correct reading order. But
   Persian-Indic digits fall inside the same Unicode block as Arabic
   letters, so the "reverse any word containing an Arabic-range character"
   rule was reversing already-correct numbers into garbage ("2٩" -> "٩2",
   i.e. 29 -> 92). Fixed in `persian_cleaner.py`: a token that's a number
   (any digit script, with light punctuation) is never character-reversed
   — digit order is never a reading-direction question. This bug affected
   every Persian-Indic number in the whole pipeline, not just the TOC.
2. **A single logical TOC line occasionally splits across two extracted
   lines** — e.g. the word "کنش" lands alone on its own line, sometimes
   ABOVE the "درس اول: های ما ... ٣" line it belongs with, due to a
   diacritic-driven line-band split. The parser merges any line that
   doesn't end in a dot-leader + page number into the correct position
   relative to the next chapter/lesson label it finds (before or after,
   whichever the raw extraction order implies).
3. **A specific diacritic artifact on the word "اول" (first)** — both
   "فصل اول" and "درس اول" extract with a stray space around the shadda
   mark ("فصل ا ّول") that breaks exact-word matching. Fixed with a
   targeted regex; no other ordinal word in this book showed the same
   artifact.
4. **A false-positive full-page "table."** `pdfplumber.find_tables()`
   misreads this book's dotted TOC leaders (`عنوان .......... 29`) as table
   rules, producing one "table" whose bbox covers ~63% of the page with
   the entire page's real content flattened into a single cell (27
   newlines). This used to replace the TOC page's real heading/paragraph
   structure with one giant merged block, hiding the "فهرست" heading
   entirely. Fixed with a guard in `structure_analyzer.py`: a bordered
   region is only rejected as a false positive when BOTH its area ratio
   AND its max single-cell newline count exceed a threshold together —
   verified against this book's actual largest genuine title box (48% of
   page area, 1 newline) and largest genuine content table (35% of page
   area, 22 newlines) to make sure neither gets caught by the same guard.

`field` (humanities/science/math/common) is deliberately left `null` in
the exported seed JSON — it depends on curriculum placement, not PDF
content, so this pipeline has no reliable way to infer it; it's left for
whoever runs the seed script, per existing project convention.

If no TOC page is found (or nothing parses out of it — e.g. a
supplementary handout with no table of contents), outline export is
silently skipped; this is treated as optional enrichment, not a hard
requirement of a successful run.

The Markdown exporter renders `heading` blocks as `###` headers and `table`
blocks as real Markdown tables when blocks are present, falling back to the
flat `page.text` otherwise (e.g. for OCR-recovered pages, which have no
font/position data to classify from).

## Concept extraction (Knowledge Graph)

Optional, opt-in, and off by default — set `extract_concepts: true` (API),
`--extract-concepts` (CLI), or `"extract_concepts": true` in a batch
request. Uses the Anthropic Claude API to read each lesson (see below for
how "lesson" is resolved) and propose `EducationalConcept`s and the
`ConceptRelationship`s between them (prerequisite, depends_on, parent,
child, related, similar, opposite, frequently_confused — see
`docs/architecture/ADR-002-knowledge-graph-roadmap.md`), exported to
`outputs/knowledge_graph/<name>.graph.json`.

### Setup

```bash
# .env, or export directly — read automatically by the Anthropic SDK
ANTHROPIC_API_KEY=sk-ant-...
```

Nothing else in this pipeline requires this key. Every other endpoint,
the CLI's `process`/`batch` without `--extract-concepts`, and every test
except the ones that inject a fake client, work exactly the same with or
without it configured. Requesting `extract_concepts` without a key doesn't
crash the run either — it adds one warning
(`"Concept extraction skipped: ..."`) and every other output (JSON,
Markdown, Django seed) is produced normally.

Model and token limit are configurable (`CONCEPT_EXTRACTION_MODEL`,
`CONCEPT_EXTRACTION_MAX_TOKENS` in `.env`), defaulting to `claude-sonnet-5`
— check Anthropic's current model list if you want to swap in something
cheaper/faster for bulk runs across many books.

### How a "lesson" is resolved for one LLM call

A whole book is too large for one LLM call to reason about coherently; a
single raw PDF page is too small to capture a lesson's concepts (which
routinely span several pages). So each lesson from the outline (see above)
becomes exactly one call, via `app/application/use_cases/build_lesson_extracts.py`.

This needed solving a real problem first: the outline's page numbers are
the book's own **printed** page numbers (page 3, as a student would look
it up), but the PDF file has cover/foreword/TOC pages before the book's own
page 1 begins, so the actual PDF page index for that same content is
higher (PDF page 11). The offset between the two isn't hardcoded — it's
computed per document from structural evidence already available: heading
blocks whose text contains a recognizable "فصل N" / "درس N" label are
matched (by chapter/lesson number, not by title text — chapter heading
blocks are often just the bare label with no title attached) against the
outline's printed page number for that same chapter/lesson, and
`offset = pdf_page - printed_page` for each such match. The most common
offset across all matches wins. Verified against `C110220.pdf`: 3
independent matches (both chapter headings, one lesson-title box) all
agree on offset=8, and lesson 1's resolved start page (PDF page 11)
lands exactly where that lesson's title box was independently found
during structural block detection.

### What's implemented vs. not (see ADR-002 for the full roadmap)

- **Implemented:** per-lesson concept + relationship extraction via tool
  use (forced function-calling, not "ask the model to return JSON in
  prose" — the response is guaranteed schema-shaped, no markdown-fence
  parsing fragility).
- **Not implemented:** merging the same concept found across multiple
  books into one canonical record (`ConceptMergePort` in
  `app/application/ports.py` — the seam exists, the logic doesn't yet).
  Concept ids are lesson-scoped for now (`lesson-3:social-action`, not a
  bare canonical id), which is an honest reflection of that: nothing here
  claims cross-book canonicalization it doesn't actually do.

## Known limitations / next steps

- Heading detection is a font-size/color heuristic, not layout/semantic
  understanding — see above.
- Table quality filtering is structural (row/col count, fill ratio), not
  semantic — see above.
- OCR is a fallback for low-text pages, not a first-class path for fully
  scanned books — no page-deskew, no layout analysis beyond what Tesseract
  does internally.
- Per-lesson concept/relationship extraction is implemented (see "Concept
  extraction (Knowledge Graph)" above); cross-book canonical merging
  (`ConceptMergePort` in `app/application/ports.py`) is not — see ADR-002.
- The outline builder assumes a TOC page labeled "فهرست" or "فهرست مطالب"
  exists and follows a "label: title .... page" line format with dot
  leaders — a book with a differently-formatted TOC (no dot leaders, a
  different heading label, etc.) won't parse until that variant is seen
  and handled.
- `field` (subject track) is not inferred — see above.

## Telegram bot interface

The optional Telegram adapter accepts direct or forwarded PDFs, places them
in a bounded persistent queue, and processes them through the same
`ProcessBookUseCase` used by the API and CLI. Large (200–300 MB) documents
require a self-hosted Telegram Local Bot API Server running with `--local`.

```bash
python telegram_bot.py
```

The bot fails closed unless `TELEGRAM_BOT_TOKEN` and a valid
`TELEGRAM_ALLOWED_USER_IDS` allowlist are supplied at runtime. Tokens are
stored as `SecretStr` and must never be committed. See
[`docs/telegram-bot.md`](docs/telegram-bot.md) for Local Bot API migration,
Docker Compose, systemd, Tesseract, security, testing, and operations.
