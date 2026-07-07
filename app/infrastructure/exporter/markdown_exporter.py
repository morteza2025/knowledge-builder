from pathlib import Path

from app.application.ports import ExporterPort
from app.core.settings import settings
from app.domain.document import KnowledgeDocument


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

                if page.text:
                    file.write(page.text)
                    file.write("\n\n")
                else:
                    file.write(
                        "> متنی از این صفحه استخراج نشد (حتی با OCR). "
                        "نیاز به بررسی دستی دارد.\n\n"
                    )

        return path
