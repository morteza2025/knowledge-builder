from pathlib import Path

from app.application.ports import ExporterPort
from app.core.settings import settings
from app.domain.document import BlockType, DocumentPage, KnowledgeDocument


def _render_table_block(rows: list[list[str]]) -> str:
    if not rows:
        return ""

    col_count = max(len(row) for row in rows)
    normalized = [row + [""] * (col_count - len(row)) for row in rows]

    def render_row(row: list[str]) -> str:
        cells = [cell.replace("\n", " ").replace("|", "\\|") or " " for cell in row]
        return "| " + " | ".join(cells) + " |"

    lines = [render_row(normalized[0]), "|" + " --- |" * col_count]
    lines.extend(render_row(row) for row in normalized[1:])

    return "\n".join(lines)


def _render_page_blocks(page: DocumentPage) -> str:
    parts = []

    for block in page.blocks:
        if block.type == BlockType.heading:
            parts.append(f"### {block.text}\n")
        elif block.type == BlockType.table:
            rows = block.metadata.get("rows")
            if rows:
                parts.append(_render_table_block(rows) + "\n")
            else:
                parts.append(block.text + "\n")
        else:
            parts.append(block.text + "\n")

    return "\n".join(parts)


class MarkdownExporter(ExporterPort):
    def __init__(self, output_dir: Path = settings.markdown_output_dir):
        self._output_dir = output_dir

    def export(self, document: KnowledgeDocument) -> Path:
        output_name = Path(document.metadata.filename).stem
        path = self._output_dir / f"{output_name}.md"

        meta = document.metadata

        with open(path, "w", encoding="utf-8") as file:
            file.write(f"# {meta.title or output_name}\n\n")
            file.write(f"- فایل: {meta.filename}\n")
            file.write(f"- درس: {meta.course or '-'}\n")
            file.write(f"- پایه: {meta.grade or '-'}\n")
            file.write(f"- تعداد صفحات: {meta.total_pages}\n")
            file.write(f"- صفحات دارای متن: {document.pages_with_text}\n")
            file.write(f"- صفحات بدون متن: {document.pages_without_text}\n")
            file.write(f"- صفحات نیازمند بازبینی: {document.pages_needing_review}\n\n")

            if document.warnings:
                file.write("### هشدارهای کلی سند\n\n")
                for warning in document.warnings:
                    file.write(f"- {warning}\n")
                file.write("\n")

            file.write("---\n\n")

            for page in document.pages:
                file.write(f"## صفحه {page.page_number}\n\n")
                file.write(f"_روش استخراج: {page.extraction_method.value}_\n\n")

                if page.warnings:
                    file.write("### هشدارهای استخراج\n\n")
                    for warning in page.warnings:
                        file.write(f"- {warning}\n")
                    file.write("\n")

                if page.blocks:
                    file.write(_render_page_blocks(page))
                    file.write("\n\n")
                elif page.text:
                    file.write(page.text)
                    file.write("\n\n")
                else:
                    file.write(
                        "> متنی از این صفحه استخراج نشد (حتی با OCR). "
                        "نیاز به بررسی دستی دارد.\n\n"
                    )

        return path
