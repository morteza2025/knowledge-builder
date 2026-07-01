import json
from pathlib import Path
from typing import List, Optional, Dict, Any

from processor.config import OUTPUT_JSON_DIR, OUTPUT_MARKDOWN_DIR
from processor.schemas import PageData


def build_book_payload(
    filename: str,
    book_title: str,
    course: Optional[str],
    grade: Optional[str],
    pages: List[PageData],
) -> Dict[str, Any]:
    pages_with_text = sum(1 for p in pages if p.char_count > 0)
    pages_without_text = len(pages) - pages_with_text

    return {
        "book_title": book_title,
        "filename": filename,
        "course": course,
        "grade": grade,
        "language": "fa",
        "total_pages": len(pages),
        "pages_with_text": pages_with_text,
        "pages_without_text": pages_without_text,
        "processing_version": "0.2.0",
        "content_type": "raw_extracted_pdf_content",
        "pages": [p.model_dump() for p in pages],
    }


def save_json(output_name: str, payload: Dict[str, Any]) -> Path:
    path = OUTPUT_JSON_DIR / f"{output_name}.json"

    with open(path, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)

    return path


def save_markdown(output_name: str, payload: Dict[str, Any]) -> Path:
    path = OUTPUT_MARKDOWN_DIR / f"{output_name}.md"

    with open(path, "w", encoding="utf-8") as file:
        file.write(f"# {payload['book_title']}\n\n")
        file.write(f"- فایل: {payload['filename']}\n")
        file.write(f"- درس: {payload.get('course') or '-'}\n")
        file.write(f"- پایه: {payload.get('grade') or '-'}\n")
        file.write(f"- تعداد صفحات: {payload['total_pages']}\n")
        file.write(f"- صفحات دارای متن: {payload['pages_with_text']}\n")
        file.write(f"- صفحات بدون متن: {payload['pages_without_text']}\n\n")

        file.write("---\n\n")

        for page in payload["pages"]:
            file.write(f"## صفحه {page['page']}\n\n")

            if page["warnings"]:
                file.write("### هشدارهای استخراج\n\n")
                for warning in page["warnings"]:
                    file.write(f"- {warning}\n")
                file.write("\n")

            if page["text"]:
                file.write(page["text"])
                file.write("\n\n")
            else:
                file.write("> متنی از این صفحه استخراج نشد. احتمالاً نیاز به OCR دارد.\n\n")

    return path