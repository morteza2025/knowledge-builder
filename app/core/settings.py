from pathlib import Path

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
    log_dir: Path = base_dir / "logs"

    max_pages_per_pdf: int = 5000
    min_text_chars_for_valid_page: int = 30

    default_language: str = "fa"

    # OCR
    ocr_enabled: bool = True
    ocr_language: str = "fas"
    ocr_render_resolution: int = 200

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def ensure_directories(self) -> None:
        for path in [
            self.input_dir,
            self.output_dir,
            self.json_output_dir,
            self.markdown_output_dir,
            self.django_seed_output_dir,
            self.log_dir,
        ]:
            path.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_directories()
