from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import (
    get_process_book_use_case,
    resolve_book_metadata,
)
from app.api.schemas import ProcessRequest, ProcessResult
from app.application.use_cases.process_book import ProcessBookUseCase, ProcessingContext
from app.core.exceptions import KnowledgeBuilderError
from app.core.settings import settings

router = APIRouter()


@router.get("/health")
def health():
    return {
        "ok": True,
        "input_dir": str(settings.input_dir),
        "output_dir": str(settings.output_dir),
    }


@router.post("/process", response_model=ProcessResult)
def process_pdf(
    req: ProcessRequest,
    use_case: ProcessBookUseCase = Depends(get_process_book_use_case),
):
    pdf_path = settings.input_dir / req.filename

    book_title, course, grade = resolve_book_metadata(
        pdf_path, req.book_title, req.course, req.grade
    )

    context = ProcessingContext(
        pdf_path=pdf_path,
        filename=req.filename,
        book_title=book_title,
        course=course,
        grade=grade,
        use_ocr=req.use_ocr,
    )

    try:
        result_context = use_case.execute(context)
    except KnowledgeBuilderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - unexpected failure path
        raise HTTPException(status_code=500, detail=f"Unexpected error: {exc}") from exc

    document = result_context.document
    assert document is not None

    return ProcessResult(
        ok=True,
        book_title=document.metadata.title or book_title,
        filename=req.filename,
        course=document.metadata.course,
        grade=document.metadata.grade,
        total_pages=document.metadata.total_pages,
        pages_with_text=document.pages_with_text,
        pages_without_text=document.pages_without_text,
        pages_needing_review=document.pages_needing_review,
        json_output=str(result_context.export_paths.get("JsonExporter", "")),
        markdown_output=str(result_context.export_paths.get("MarkdownExporter", "")),
        warnings=document.warnings,
    )
