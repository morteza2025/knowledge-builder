from pathlib import Path
from typing import Optional

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
    ocr_language: str = "fas"
    ocr_render_resolution: int = 200

    # Concept extraction (Knowledge Graph roadmap — see ADR-002).
    # ANTHROPIC_API_KEY is read from the environment by the Anthropic SDK
    # itself; this field just lets settings.py report whether one is
    # configured without importing the SDK here. Leave it unset until
    # you're ready to actually run concept extraction — every other part
    # of this pipeline works fine without it.
    anthropic_api_key: Optional[str] = None
    concept_extraction_model: str = "claude-sonnet-5"
    concept_extraction_max_tokens: int = 4096

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
            self.knowledge_graph_output_dir,
            self.log_dir,
        ]:
            path.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_directories()
