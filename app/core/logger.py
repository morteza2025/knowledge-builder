import logging
from logging.handlers import RotatingFileHandler

from app.core.settings import settings

LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


def _build_logger() -> logging.Logger:
    logger = logging.getLogger("knowledge_builder")
    logger.setLevel(logging.DEBUG if settings.debug else logging.INFO)

    if logger.handlers:
        # Avoid duplicate handlers if this module is imported more than once
        # (e.g. by both the API process and a test runner).
        return logger

    formatter = logging.Formatter(LOG_FORMAT)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    log_file = settings.log_dir / "knowledge-builder.log"
    file_handler = RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


app_logger = _build_logger()
