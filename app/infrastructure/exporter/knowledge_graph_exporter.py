import json
from pathlib import Path

from app.core.settings import settings
from app.domain.concept import KnowledgeGraph
from app.domain.document import DocumentMetadata


class KnowledgeGraphExporter:
    def __init__(self, output_dir: Path = settings.knowledge_graph_output_dir):
        self._output_dir = output_dir

    def export(self, graph: KnowledgeGraph, metadata: DocumentMetadata) -> Path:
        output_name = Path(metadata.filename).stem
        path = self._output_dir / f"{output_name}.graph.json"

        payload = {
            "book_title": metadata.title,
            "course": metadata.course,
            "grade": metadata.grade,
            "version": graph.version,
            "concepts": [concept.model_dump(mode="json") for concept in graph.concepts],
            "relationships": [
                relationship.model_dump(mode="json")
                for relationship in graph.relationships
            ],
        }

        with open(path, "w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)

        return path
