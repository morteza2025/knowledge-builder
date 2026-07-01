from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from processor.config import INPUT_DIR, SUPPORTED_EXTENSIONS
from processor.schemas import ProcessRequest, ProcessResult
from processor.services.pdf_extractor import extract_pdf_pages, PDFExtractionError
from processor.services.exporter import build_book_payload, save_json, save_markdown


app = FastAPI(
    title="EduLeague Knowledge Builder",
    description="Local Persian PDF processor for EduLeague AI Teacher content pipeline.",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {
        "ok": True,
        "service": "EduLeague Knowledge Builder",
        "version": "0.2.0",
        "docs": "/docs",
    }


@app.get("/health")
def health():
    return {
        "ok": True,
        "input_dir": str(INPUT_DIR),
    }


@app.post("/process", response_model=ProcessResult)
def process_pdf(req: ProcessRequest):
    pdf_path = INPUT_DIR / req.filename

    if pdf_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {pdf_path.suffix}",
        )

    try:
        pages = extract_pdf_pages(pdf_path, use_ocr=req.use_ocr)
    except PDFExtractionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {exc}") from exc

    output_name = Path(req.filename).stem
    book_title = req.book_title or output_name

    payload = build_book_payload(
        filename=req.filename,
        book_title=book_title,
        course=req.course,
        grade=req.grade,
        pages=pages,
    )

    json_path = save_json(output_name, payload)
    markdown_path = save_markdown(output_name, payload)

    warnings = []
    pages_without_text = payload["pages_without_text"]

    if pages_without_text > 0:
        warnings.append(
            f"{pages_without_text} page(s) had no extractable text and may need OCR."
        )

    return ProcessResult(
        ok=True,
        book_title=book_title,
        filename=req.filename,
        course=req.course,
        grade=req.grade,
        total_pages=payload["total_pages"],
        pages_with_text=payload["pages_with_text"],
        pages_without_text=payload["pages_without_text"],
        json_output=str(json_path),
        markdown_output=str(markdown_path),
        warnings=warnings,
    )