import re
from pathlib import Path


TOKEN_PATTERN = re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b")


def test_repository_contains_no_telegram_bot_token_pattern():
    root = Path(__file__).resolve().parents[1]
    excluded = {".git", ".pytest_cache", "__pycache__", "input", "outputs", "workspaces"}
    matches = []
    for path in root.rglob("*"):
        if not path.is_file() or any(part in excluded for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if TOKEN_PATTERN.search(text):
            matches.append(path.relative_to(root))
    assert matches == []
