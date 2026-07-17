from pathlib import Path

import pytest

from app.core.settings import Settings
from app.interfaces.telegram.application import (
    build_telegram_application,
    validate_runtime_configuration,
)


def _settings(tmp_path: Path, **overrides) -> Settings:
    values = {
        "telegram_bot_token": "123456:OBVIOUSLY_FAKE_TEST_TOKEN",
        "telegram_allowed_user_ids_csv": "123,456",
        "telegram_input_dir": tmp_path / "input",
        "telegram_work_dir": tmp_path / "work",
        "json_output_dir": tmp_path / "json",
        "markdown_output_dir": tmp_path / "markdown",
        "django_seed_output_dir": tmp_path / "seed",
        "knowledge_graph_output_dir": tmp_path / "graph",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_valid_allowlist_is_parsed_and_deduplicated(tmp_path):
    settings = _settings(tmp_path, telegram_allowed_user_ids_csv="123, 456,123")
    assert settings.telegram_allowed_user_ids == (123, 456)


def test_allowlist_parses_from_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "123,456")
    settings = Settings(
        _env_file=None,
        telegram_input_dir=tmp_path / "input",
        telegram_work_dir=tmp_path / "work",
    )
    assert settings.telegram_allowed_user_ids == (123, 456)


def test_malformed_allowlist_fails_closed(tmp_path):
    settings = _settings(tmp_path, telegram_allowed_user_ids_csv="123,not-an-id")
    assert settings.telegram_allowed_user_ids == ()
    with pytest.raises(RuntimeError, match="TELEGRAM_ALLOWED_USER_IDS"):
        validate_runtime_configuration(settings)


def test_missing_token_is_allowed_for_api_import_but_required_at_bot_runtime(tmp_path):
    settings = _settings(tmp_path, telegram_bot_token=None)
    with pytest.raises(RuntimeError, match="TELEGRAM_BOT_TOKEN"):
        validate_runtime_configuration(settings)


def test_settings_repr_does_not_reveal_token(tmp_path):
    secret = "123456:OBVIOUSLY_FAKE_TEST_TOKEN"
    settings = _settings(tmp_path, telegram_bot_token=secret)
    assert secret not in repr(settings)
    assert "**********" in repr(settings)


def test_api_base_urls_use_ptb_token_append_contract(tmp_path):
    settings = _settings(tmp_path)
    application, runtime = build_telegram_application(settings)
    try:
        assert str(application.bot.base_url).startswith("http://127.0.0.1:8081/bot")
        assert str(application.bot.base_file_url).startswith(
            "http://127.0.0.1:8081/file/bot"
        )
        assert application.bot.local_mode is True
    finally:
        runtime.repository.close()


def test_base_url_requires_documented_suffix(tmp_path):
    with pytest.raises(ValueError, match="end with '/bot'"):
        _settings(tmp_path, telegram_bot_api_base_url="http://localhost:8081")
