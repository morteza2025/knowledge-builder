"""
Runs ProcessBookUseCase over multiple books in one call. Each book is
isolated from the others -- one corrupt/oversized/unreadable PDF fails
that item and gets recorded with an error, it does not abort the rest of
the batch. This matters in practice: a Drive folder of 15 books is exactly
the kind of batch where one bad file (wrong format, truncated download,
password-protected) shouldn't cost you the other 14 results.

Sequential by design, not parallel: pdfplumber parsing and Tesseract OCR
are both CPU-heavy, and this is a local single-machine tool, not a
scaled-out service -- running N books at once would mostly contend for the
same CPU cores rather than genuinely speed things up, while adding real
complexity (thread-safety of the shared OCR engine instance, interleaved
log output, harder-to-read progress). If batches grow large enough that
this becomes a real bottleneck, a ProcessPoolExecutor over independent
worker processes (not threads, since pdfplumber/Tesseract are CPU-bound
and won't benefit from Python threads) would be the right upgrade -- but
that's premature for the batch sizes this pipeline sees today.
"""

from dataclasses import dataclass, field
from typing import Optional

from app.application.use_cases.process_book import ProcessBookUseCase, ProcessingContext
from app.core.logger import app_logger


@dataclass
class BatchItemResult:
    filename: str
    ok: bool
    context: Optional[ProcessingContext] = None
    error: Optional[str] = None


@dataclass
class BatchResult:
    total: int
    succeeded: int
    failed: int
    items: list[BatchItemResult] = field(default_factory=list)


class ProcessBatchUseCase:
    def __init__(self, book_use_case: ProcessBookUseCase):
        self._book_use_case = book_use_case

    def execute(self, contexts: list[ProcessingContext]) -> BatchResult:
        items: list[BatchItemResult] = []

        for context in contexts:
            app_logger.info("Batch: starting %s", context.filename)
            try:
                result_context = self._book_use_case.execute(context)
                items.append(
                    BatchItemResult(
                        filename=context.filename, ok=True, context=result_context
                    )
                )
                app_logger.info("Batch: finished %s", context.filename)
            except Exception as exc:
                app_logger.warning(
                    "Batch: %s failed: %s", context.filename, exc
                )
                items.append(
                    BatchItemResult(
                        filename=context.filename, ok=False, error=str(exc)
                    )
                )

        succeeded = sum(1 for item in items if item.ok)
        return BatchResult(
            total=len(items),
            succeeded=succeeded,
            failed=len(items) - succeeded,
            items=items,
        )
