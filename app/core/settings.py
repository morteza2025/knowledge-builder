from pathlib import Path
from typing import Literal, Optional

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "EduLeague Knowledge Builder"
    app_version: str = "1.0.0"
    debug: bool = True

    base_dir: Path = Path(__file__).resolve().parents[2]
    input_dir: Path = base_dir / "input"
    output_dir: Path = base_dir / "outputs"
    json_output_dir: Path = output_dir / "json"
    markdown_output_dir: Path = output_dir / "markdown"
    django_seed_output_dir: Path = output_dir / "django_seed"
    knowledge_graph_output_dir: Path = output_dir / "knowledge_graph"
    log_dir: Path = base_dir / "logs"

    max_pages_per_pdf: int = 5000
    min_text_chars_for_valid_page: int = 30

    default_language: str = "fa"

    # OCR
    ocr_enabled: bool = True
    ocr_language: str = "fas+eng"
    ocr_render_resolution: int = 200
    ocr_tesseract_psm: int = 6
    ocr_preprocessing_mode: Literal["none", "grayscale", "autocontrast"] = (
        "autocontrast"
    )
    ocr_threshold: Optional[int] = None
    ocr_low_confidence_threshold: float = 45.0

    # Concept extraction (Knowledge Graph roadmap — see ADR-002).
    # ANTHROPIC_API_KEY is read from the environment by the Anthropic SDK
    # itself; this field just lets settings.py report whether one is
    # configured without importing the SDK here. Leave it unset until
    # you're ready to actually run concept extraction — every other part
    # of this pipeline works fine without it.
    anthropic_api_key: Optional[str] = None
    concept_extraction_model: str = "claude-sonnet-5"
    concept_extraction_max_tokens: int = 4096

    # Telegram interface. The token deliberately remains optional at import
    # time so API/CLI users do not need Telegram configuration; the dedicated
    # Telegram entry point validates it at runtime.
    telegram_bot_token: Optional[SecretStr] = None
    telegram_bot_api_base_url: str = "http://127.0.0.1:8081/bot"
    telegram_bot_api_file_url: str = "http://127.0.0.1:8081/file/bot"
    telegram_allowed_user_ids_csv: str = Field(
        default="", validation_alias="TELEGRAM_ALLOWED_USER_IDS", repr=False
    )
    telegram_allow_all_development: bool = False
    telegram_local_mode: bool = True
    telegram_max_file_size_mb: int = 1900
    telegram_processing_concurrency: int = 1
    telegram_job_queue_size: int = 10
    telegram_input_dir: Path = base_dir / "input" / "telegram"
    telegram_work_dir: Path = base_dir / "workspaces" / "telegram"
    telegram_output_retention_hours: int = 24
    telegram_status_update_interval_seconds: int = 5
    telegram_min_free_disk_space_mb: int = 1024
    telegram_processing_timeout_seconds: int = 7200
    telegram_download_chunk_size: int = 1024 * 1024

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    @field_validator("telegram_bot_api_base_url")
    @classmethod
    def _validate_bot_api_url(cls, value: str) -> str:
        normalized = value.rstrip("/")
        if not normalized.endswith("/bot"):
            raise ValueError("Telegram Bot API base URL must end with '/bot'")
        return normalized

    @field_validator("telegram_bot_api_file_url")
    @classmethod
    def _validate_bot_file_url(cls, value: str) -> str:
        normalized = value.rstrip("/")
        if not normalized.endswith("/file/bot"):
            raise ValueError("Telegram Bot API file URL must end with '/file/bot'")
        return normalized

    @field_validator(
        "telegram_max_file_size_mb",
        "telegram_processing_concurrency",
        "telegram_job_queue_size",
        "telegram_output_retention_hours",
        "telegram_status_update_interval_seconds",
        "telegram_processing_timeout_seconds",
        "telegram_download_chunk_size",
    )
    @classmethod
    def _require_positive_telegram_values(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Telegram runtime limits must be positive")
        return value

    @field_validator("ocr_tesseract_psm")
    @classmethod
    def _validate_psm(cls, value: int) -> int:
        if not 0 <= value <= 13:
            raise ValueError("OCR_TESSERACT_PSM must be between 0 and 13")
        return value

    @field_validator("ocr_threshold")
    @classmethod
    def _validate_threshold(cls, value: Optional[int]) -> Optional[int]:
        if value is not None and not 0 <= value <= 255:
            raise ValueError("OCR_THRESHOLD must be between 0 and 255")
        return value

    @property
    def telegram_allowed_user_ids(self) -> tuple[int, ...]:
        """Parse the comma-separated allowlist, failing closed on any error."""

        raw = self.telegram_allowed_user_ids_csv.strip()
        if not raw:
            return ()
        try:
            values = tuple(int(part.strip()) for part in raw.split(","))
        except (TypeError, ValueError):
            return ()
        if not values or any(value <= 0 for value in values):
            return ()
        return tuple(dict.fromkeys(values))

    @property
    def telegram_database_path(self) -> Path:
        return self.telegram_work_dir / "jobs.sqlite3"

    def ensure_directories(self) -> None:
        for path in [
            self.input_dir,
            self.output_dir,
            self.json_output_dir,
            self.markdown_output_dir,
            self.django_seed_output_dir,
            self.knowledge_graph_output_dir,
            self.log_dir,
            self.telegram_input_dir,
            self.telegram_work_dir,
        ]:
            path.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_directories()
