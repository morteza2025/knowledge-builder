import sys
from loguru import logger

from app.core.settings import settings


def setup_logger():
    logger.remove()

    logger.add(
        sys.stdout,
        level="DEBUG" if settings.debug else "INFO",
        colorize=True,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
               "<level>{level}</level> | "
               "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
               "<level>{message}</level>",
    )

    logger.add(
        settings.log_dir / "knowledge-builder.log",
        level="INFO",
        rotation="10 MB",
        retention="14 days",
        encoding="utf-8",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} | {message}",
    )

    return logger


app_logger = setup_logger()