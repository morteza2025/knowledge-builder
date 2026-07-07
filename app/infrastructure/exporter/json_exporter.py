import json
from pathlib import Path

from app.application.ports import ExporterPort
from app.core.settings import settings
from app.domain.document import KnowledgeDocument


class JsonExporter(ExporterPort):
    def __init__(self, output_dir: Path = settings.json_output_dir):
        self._output_dir = output_dir

    def export(self, document: KnowledgeDocument) -> Path:
        output_name = Path(document.metadata.filename).stem
        path = self._output_dir / f"{output_name}.json"

        with open(path, "w", encoding="utf-8") as file:
            json.dump(
                document.model_dump(mode="json"),
                file,
                ensure_ascii=False,
                indent=2,
            )

        return path
