from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any


class ProcessRequest(BaseModel):
    filename: str = Field(..., description="PDF filename inside input folder")
    course: Optional[str] = None
    grade: Optional[str] = None
    book_title: Optional[str] = None
    use_ocr: bool = False


class PageData(BaseModel):
    page: int
    text: str
    char_count: int
    extraction_method: str
    warnings: List[str] = []


class ProcessResult(BaseModel):
    ok: bool
    book_title: str
    filename: str
    course: Optional[str]
    grade: Optional[str]
    language: str = "fa"
    total_pages: int
    pages_with_text: int
    pages_without_text: int
    json_output: str
    markdown_output: str
    warnings: List[str] = []