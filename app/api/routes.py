from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import (
    get_process_book_use_case,
    resolve_book_metadata,
)
from app.api.schemas import (
    BatchItemResultSchema,
    BatchProcessRequest,
    BatchProcessResult,
    ProcessRequest,
    ProcessResult,
)
from app.application.use_cases.process_batch import BatchItemResult, ProcessBatchUseCase
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


def _build_context(
    filename: str,
    book_title: str | None,
    course: str | None,
    grade: str | None,
    use_ocr: bool,
    extract_concepts: bool = False,
) -> ProcessingContext:
    pdf_path = settings.input_dir / filename
    resolved_title, resolved_course, resolved_grade = resolve_book_metadata(
        pdf_path, book_title, course, grade
    )
    return ProcessingContext(
        pdf_path=pdf_path,
        filename=filename,
        book_title=resolved_title,
        course=resolved_course,
        grade=resolved_grade,
        use_ocr=use_ocr and settings.ocr_enabled,
        extract_concepts=extract_concepts,
    )


def _context_to_result(
    result_context: ProcessingContext, fallback_title: str
) -> ProcessResult:
    document = result_context.document
    assert document is not None

    outline = result_context.outline
    outline_chapters = len(outline.chapters) if outline else 0
    outline_lessons = (
        sum(len(chapter.lessons) for chapter in outline.chapters) if outline else 0
    )

    graph = result_context.knowledge_graph
    concepts_extracted = len(graph.concepts) if graph else 0
    relationships_extracted = len(graph.relationships) if graph else 0

    return ProcessResult(
        ok=True,
        book_title=document.metadata.title or fallback_title,
        filename=result_context.filename,
        course=document.metadata.course,
        grade=document.metadata.grade,
        total_pages=document.metadata.total_pages,
        pages_with_text=document.pages_with_text,
        pages_without_text=document.pages_without_text,
        pages_needing_review=document.pages_needing_review,
        json_output=str(result_context.export_paths.get("JsonExporter", "")),
        markdown_output=str(result_context.export_paths.get("MarkdownExporter", "")),
        outline_chapters=outline_chapters,
        outline_lessons=outline_lessons,
        django_seed_output=(
            str(result_context.export_paths["DjangoSeedExporter"])
            if "DjangoSeedExporter" in result_context.export_paths
            else None
        ),
        concepts_extracted=concepts_extracted,
        relationships_extracted=relationships_extracted,
        knowledge_graph_output=(
            str(result_context.export_paths["KnowledgeGraphExporter"])
            if "KnowledgeGraphExporter" in result_context.export_paths
            else None
        ),
        warnings=document.warnings,
    )


def _discover_pdfs() -> list[str]:
    return sorted(p.name for p in settings.input_dir.glob("*.pdf"))


@router.post("/process", response_model=ProcessResult)
def process_pdf(
    req: ProcessRequest,
    use_case: ProcessBookUseCase = Depends(get_process_book_use_case),
):
    context = _build_context(
        req.filename, req.book_title, req.course, req.grade, req.use_ocr, req.extract_concepts
    )

    try:
        result_context = use_case.execute(context)
    except KnowledgeBuilderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - unexpected failure path
        raise HTTPException(status_code=500, detail=f"Unexpected error: {exc}") from exc

    return _context_to_result(result_context, context.book_title)


@router.post("/process/batch", response_model=BatchProcessResult)
def process_batch(
    req: BatchProcessRequest,
    use_case: ProcessBookUseCase = Depends(get_process_book_use_case),
):
    filenames = req.filenames or _discover_pdfs()

    if not filenames:
        raise HTTPException(
            status_code=400,
            detail=(
                "No PDF files to process — input/ is empty and no "
                "filenames were given."
            ),
        )

    contexts = [
        _build_context(filename, None, None, None, req.use_ocr, req.extract_concepts)
        for filename in filenames
    ]

    batch_result = ProcessBatchUseCase(use_case).execute(contexts)

    def _item_to_schema(item: BatchItemResult) -> BatchItemResultSchema:
        if item.ok and item.context is not None:
            return BatchItemResultSchema(
                filename=item.filename,
                ok=True,
                result=_context_to_result(item.context, item.context.book_title),
            )
        return BatchItemResultSchema(
            filename=item.filename, ok=False, error=item.error
        )

    return BatchProcessResult(
        total=batch_result.total,
        succeeded=batch_result.succeeded,
        failed=batch_result.failed,
        items=[_item_to_schema(item) for item in batch_result.items],
    )
