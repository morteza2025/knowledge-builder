from typing import Optional

from pydantic import BaseModel, field_validator

from app.core.encoding_guard import assert_clean_text


class ProcessRequest(BaseModel):
    filename: str
    book_title: Optional[str] = None
    course: Optional[str] = None
    grade: Optional[str] = None
    use_ocr: bool = True

    @field_validator("book_title", "course", "grade")
    @classmethod
    def _reject_corrupted_encoding(cls, value: Optional[str], info):
        if value is None:
            return value
        return assert_clean_text(value, info.field_name)


class ProcessResult(BaseModel):
    ok: bool
    book_title: str
    filename: str
    course: Optional[str] = None
    grade: Optional[str] = None
    total_pages: int
    pages_with_text: int
    pages_without_text: int
    pages_needing_review: int
    json_output: str
    markdown_output: str
    outline_chapters: int = 0
    outline_lessons: int = 0
    django_seed_output: Optional[str] = None
    warnings: list[str] = []


class BatchProcessRequest(BaseModel):
    filenames: Optional[list[str]] = None
    use_ocr: bool = True

    @field_validator("filenames")
    @classmethod
    def _reject_empty_list(cls, value):
        if value is not None and len(value) == 0:
            raise ValueError(
                "filenames was given as an empty list — omit it entirely to "
                "auto-discover every PDF in input/, or list at least one file."
            )
        return value


class BatchItemResultSchema(BaseModel):
    filename: str
    ok: bool
    result: Optional[ProcessResult] = None
    error: Optional[str] = None


class BatchProcessResult(BaseModel):
    total: int
    succeeded: int
    failed: int
    items: list[BatchItemResultSchema]
