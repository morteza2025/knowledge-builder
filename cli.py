#!/usr/bin/env python3
"""
Command-line interface for Knowledge Builder.

Runs the exact same use case wiring as the API (app/api/dependencies.py) —
process a book or a batch of books without starting uvicorn at all. Useful
for one-off runs, cron/scheduled jobs, or anywhere spinning up a server
just to make one request is more friction than it's worth.

Usage:
    python cli.py process C110220.pdf
    python cli.py process C110220.pdf --title "جامعه شناسی (۱)" --course انسانی --grade دهم
    python cli.py process C110220.pdf --no-ocr --json

    python cli.py batch
    python cli.py batch C110220.pdf another_book.pdf
    python cli.py batch --no-ocr --json

Book metadata (title/course/grade) is resolved the same way as the API:
explicit --title/--course/--grade first, then a <name>.meta.json sidecar
file next to the PDF, then the filename itself. See README.md "Avoiding
encoding corruption" for why sidecar files are the recommended way to
supply Persian metadata on Windows rather than typing it as a CLI arg.
"""

import argparse
import json
import sys
from typing import Optional

from app.api.dependencies import get_process_book_use_case, resolve_book_metadata
from app.application.use_cases.process_batch import BatchItemResult, ProcessBatchUseCase
from app.application.use_cases.process_book import ProcessBookUseCase, ProcessingContext
from app.core.exceptions import KnowledgeBuilderError
from app.core.settings import settings


def _build_context(
    filename: str,
    title: Optional[str],
    course: Optional[str],
    grade: Optional[str],
    use_ocr: bool,
    extract_concepts: bool = False,
) -> ProcessingContext:
    pdf_path = settings.input_dir / filename
    resolved_title, resolved_course, resolved_grade = resolve_book_metadata(
        pdf_path, title, course, grade
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


def _result_payload(context: ProcessingContext) -> dict:
    document = context.document
    assert document is not None
    outline = context.outline
    graph = context.knowledge_graph

    return {
        "filename": context.filename,
        "book_title": document.metadata.title,
        "course": document.metadata.course,
        "grade": document.metadata.grade,
        "total_pages": document.metadata.total_pages,
        "pages_with_text": document.pages_with_text,
        "pages_without_text": document.pages_without_text,
        "pages_needing_review": document.pages_needing_review,
        "outline_chapters": len(outline.chapters) if outline else 0,
        "outline_lessons": (
            sum(len(chapter.lessons) for chapter in outline.chapters)
            if outline
            else 0
        ),
        "json_output": str(context.export_paths.get("JsonExporter", "")),
        "markdown_output": str(context.export_paths.get("MarkdownExporter", "")),
        "django_seed_output": (
            str(context.export_paths["DjangoSeedExporter"])
            if "DjangoSeedExporter" in context.export_paths
            else None
        ),
        "concepts_extracted": len(graph.concepts) if graph else 0,
        "relationships_extracted": len(graph.relationships) if graph else 0,
        "knowledge_graph_output": (
            str(context.export_paths["KnowledgeGraphExporter"])
            if "KnowledgeGraphExporter" in context.export_paths
            else None
        ),
        "warnings": document.warnings,
    }


def _print_human_summary(context: ProcessingContext) -> None:
    payload = _result_payload(context)

    print(f"✓ {payload['filename']}")
    print(f"  عنوان: {payload['book_title']}")
    print(
        f"  صفحات: {payload['total_pages']} "
        f"(متن‌دار: {payload['pages_with_text']}, "
        f"بدون متن: {payload['pages_without_text']}, "
        f"نیاز به بازبینی: {payload['pages_needing_review']})"
    )
    if payload["outline_chapters"]:
        print(
            f"  ساختار: {payload['outline_chapters']} فصل، "
            f"{payload['outline_lessons']} درس"
        )
    else:
        print("  ساختار: فهرست پیدا/پارس نشد")
    print(f"  JSON: {payload['json_output']}")
    print(f"  Markdown: {payload['markdown_output']}")
    if payload["django_seed_output"]:
        print(f"  Django seed: {payload['django_seed_output']}")
    if payload["knowledge_graph_output"]:
        print(
            f"  گراف دانش: {payload['concepts_extracted']} مفهوم، "
            f"{payload['relationships_extracted']} رابطه -> "
            f"{payload['knowledge_graph_output']}"
        )
    if payload["warnings"]:
        print("  هشدارها:")
        for warning in payload["warnings"]:
            print(f"    - {warning}")


def cmd_process(args: argparse.Namespace) -> int:
    use_case = get_process_book_use_case()
    context = _build_context(
        args.filename,
        args.title,
        args.course,
        args.grade,
        not args.no_ocr,
        args.extract_concepts,
    )

    try:
        result_context = use_case.execute(context)
    except KnowledgeBuilderError as exc:
        print(f"✗ {args.filename}: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # pragma: no cover - unexpected failure path
        print(f"✗ {args.filename}: unexpected error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(_result_payload(result_context), ensure_ascii=False, indent=2))
    else:
        _print_human_summary(result_context)

    return 0


def cmd_batch(args: argparse.Namespace) -> int:
    use_case = get_process_book_use_case()
    filenames = args.filenames or sorted(
        p.name for p in settings.input_dir.glob("*.pdf")
    )

    if not filenames:
        print(
            "هیچ فایل PDF ای برای پردازش پیدا نشد (input/ خالیه).",
            file=sys.stderr,
        )
        return 1

    contexts = [
        _build_context(name, None, None, None, not args.no_ocr, args.extract_concepts)
        for name in filenames
    ]
    batch_result = ProcessBatchUseCase(use_case).execute(contexts)

    if args.json:
        payload = {
            "total": batch_result.total,
            "succeeded": batch_result.succeeded,
            "failed": batch_result.failed,
            "items": [
                {
                    "filename": item.filename,
                    "ok": item.ok,
                    "result": _result_payload(item.context) if item.ok else None,
                    "error": item.error,
                }
                for item in batch_result.items
            ],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(
            f"مجموع: {batch_result.total} | "
            f"موفق: {batch_result.succeeded} | "
            f"ناموفق: {batch_result.failed}\n"
        )
        for item in batch_result.items:
            _print_batch_item(item)
            print()

    return 0 if batch_result.failed == 0 else 1


def _print_batch_item(item: BatchItemResult) -> None:
    if item.ok and item.context is not None:
        _print_human_summary(item.context)
    else:
        print(f"✗ {item.filename}: {item.error}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cli.py", description="Knowledge Builder command-line interface"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    process_parser = subparsers.add_parser("process", help="Process a single PDF")
    process_parser.add_argument("filename", help="PDF filename inside input/")
    process_parser.add_argument(
        "--title",
        default=None,
        help="Book title (falls back to <name>.meta.json, then the filename)",
    )
    process_parser.add_argument("--course", default=None)
    process_parser.add_argument("--grade", default=None)
    process_parser.add_argument(
        "--no-ocr", action="store_true", help="Disable the OCR fallback"
    )
    process_parser.add_argument(
        "--extract-concepts",
        action="store_true",
        help="Also run LLM-based concept/relationship extraction per lesson "
        "(requires ANTHROPIC_API_KEY — see README.md)",
    )
    process_parser.add_argument(
        "--json", action="store_true", help="Print machine-readable JSON"
    )
    process_parser.set_defaults(func=cmd_process)

    batch_parser = subparsers.add_parser(
        "batch", help="Process multiple PDFs (all of input/ if none are named)"
    )
    batch_parser.add_argument(
        "filenames",
        nargs="*",
        help="PDF filenames inside input/ (omit to process every PDF there)",
    )
    batch_parser.add_argument("--no-ocr", action="store_true")
    batch_parser.add_argument(
        "--extract-concepts",
        action="store_true",
        help="Also run LLM-based concept/relationship extraction per lesson, "
        "for every book in the batch (requires ANTHROPIC_API_KEY)",
    )
    batch_parser.add_argument("--json", action="store_true")
    batch_parser.set_defaults(func=cmd_batch)

    return parser


def main(argv: Optional[list] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
