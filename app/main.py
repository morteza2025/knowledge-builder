from fastapi import FastAPI

from app.core.settings import settings
from app.core.logger import app_logger


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug,
)


@app.get("/")
def root():
    return {
        "ok": True,
        "service": settings.app_name,
        "version": settings.app_version,
    }


@app.get("/health")
def health():
    app_logger.info("Health check requested")

    return {
        "ok": True,
        "input_dir": str(settings.input_dir),
        "output_dir": str(settings.output_dir),
        "log_dir": str(settings.log_dir),
    }