from typing import Optional
from pydantic import BaseModel, Field


class ProcessBookRequest(BaseModel):
    filename: str = Field(..., description="PDF filename inside input folder")
    title: Optional[str] = None
    course: Optional[str] = None
    grade: Optional[str] = None
    use_ocr: bool = False


class ProcessBookResponse(BaseModel):
    ok: bool
    filename: str
    title: Optional[str]
    course: Optional[str]
    grade: Optional[str]
    total_pages: int
    pages_with_text: int
    pages_without_text: int
    json_output: str
    markdown_output: str
    warnings: list[str] = []