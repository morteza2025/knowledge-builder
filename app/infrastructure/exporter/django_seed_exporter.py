"""
Writes a BookOutline to JSON in the exact shape the existing Django seeding
pattern expects:

    Book.update_or_create(subject, grade, field)
    structure = [(chapter_title, [(order, lesson_title, page)])]

Subtopics are included as additional nested data beyond that base shape —
the seeding script can use them or ignore them. `field` (humanities /
science / math / common) is deliberately left null: this pipeline has no
reliable way to infer it (it depends on curriculum placement, not the PDF
content), so it's left for whoever runs the seed script to fill in, per
existing project convention.
"""

import json
from pathlib import Path

from app.core.settings import settings
from app.domain.document import DocumentMetadata
from app.domain.outline import BookOutline


class DjangoSeedExporter:
    def __init__(self, output_dir: Path = settings.django_seed_output_dir):
        self._output_dir = output_dir

    def export(self, outline: BookOutline, metadata: DocumentMetadata) -> Path:
        output_name = Path(metadata.filename).stem
        path = self._output_dir / f"{output_name}.seed.json"

        payload = {
            "book_title": metadata.title,
            "course": metadata.course,
            "grade": metadata.grade,
            "field": None,
            "source": outline.source,
            "chapters": [
                {
                    "order": chapter.order,
                    "title": chapter.title,
                    "page": chapter.page,
                    "lessons": [
                        {
                            "order": lesson.order,
                            "title": lesson.title,
                            "page": lesson.page,
                            "subtopics": [
                                {"title": subtopic.title, "page": subtopic.page}
                                for subtopic in lesson.subtopics
                            ],
                        }
                        for lesson in chapter.lessons
                    ],
                }
                for chapter in outline.chapters
            ],
        }

        with open(path, "w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)

        return path
