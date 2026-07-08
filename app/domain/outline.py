"""
Domain models for a book's chapter -> lesson -> subtopic outline, extracted
from the book's own table-of-contents page(s). This is the bridge toward
Django seeding's established pattern (see project notes):

    Book.update_or_create(subject, grade, field)
    structure = [(chapter_title, [(order, lesson_title, page)])]

Page numbers here are the book's own PRINTED page numbers as they appear in
the table of contents — NOT the PDF file's absolute page index, which is
offset by however many cover/foreword/TOC pages precede the book's own
page 1. Printed page numbers are what a student or teacher would actually
look up, and what this pipeline's downstream (Django `Lesson.page` field,
per project notes) is expected to store.
"""

from typing import Optional

from pydantic import BaseModel, Field


class SubtopicOutline(BaseModel):
    title: str
    page: Optional[int] = None


class LessonOutline(BaseModel):
    order: int  # global order across the whole book, not per-chapter
    title: str
    page: Optional[int] = None
    subtopics: list[SubtopicOutline] = Field(default_factory=list)


class ChapterOutline(BaseModel):
    order: int
    title: str
    page: Optional[int] = None
    lessons: list[LessonOutline] = Field(default_factory=list)


class BookOutline(BaseModel):
    chapters: list[ChapterOutline] = Field(default_factory=list)
    source: str = "table_of_contents"

    def to_django_seed_structure(self) -> list[tuple[str, list[tuple[int, str, Optional[int]]]]]:
        """Exact shape used by the existing Django seeding pattern:
        structure=[(chapter_title, [(order, lesson_title, page)])]."""

        return [
            (
                chapter.title,
                [
                    (lesson.order, lesson.title, lesson.page)
                    for lesson in chapter.lessons
                ],
            )
            for chapter in self.chapters
        ]
