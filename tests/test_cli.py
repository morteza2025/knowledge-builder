import json
from pathlib import Path

import cli as cli_module
from app.application.ports import ExporterPort, TextExtractionPort
from app.application.use_cases.process_book import build_default_process_book_use_case
from app.core.exceptions import PDFExtractionError
from app.domain.document import DocumentPage, ExtractionMethod


class FakeTextExtractor(TextExtractionPort):
    def __init__(self, fail_for: frozenset = frozenset()):
        self._fail_for = fail_for

    def extract_pages(
        self, pdf_path: Path, *, use_ocr: bool | None = None
    ) -> list[DocumentPage]:
        if pdf_path.name in self._fail_for:
            raise PDFExtractionError(f"simulated failure for {pdf_path.name}")
        return [
            DocumentPage(
                page_number=1,
                text="متن نمونه",
                char_count=9,
                extraction_method=ExtractionMethod.pdfplumber_positional,
            )
        ]


class FakeExporter(ExporterPort):
    def export(self, document) -> Path:
        return Path("/fake/output.json")


def _fake_use_case(fail_for: frozenset = frozenset()):
    return build_default_process_book_use_case(
        text_extractor=FakeTextExtractor(fail_for=fail_for),
        exporters=[FakeExporter()],
    )


# --- argument parsing (no I/O) ----------------------------------------------


def test_process_args_have_expected_defaults():
    args = cli_module.build_parser().parse_args(["process", "book.pdf"])
    assert args.filename == "book.pdf"
    assert args.title is None
    assert args.course is None
    assert args.grade is None
    assert args.no_ocr is False
    assert args.json is False


def test_process_args_parses_all_flags():
    args = cli_module.build_parser().parse_args(
        [
            "process",
            "book.pdf",
            "--title",
            "کتاب تست",
            "--course",
            "ریاضی",
            "--grade",
            "یازدهم",
            "--no-ocr",
            "--json",
        ]
    )
    assert args.title == "کتاب تست"
    assert args.course == "ریاضی"
    assert args.grade == "یازدهم"
    assert args.no_ocr is True
    assert args.json is True


def test_batch_args_default_to_empty_filenames_list():
    args = cli_module.build_parser().parse_args(["batch"])
    assert args.filenames == []


def test_batch_args_accept_multiple_filenames():
    args = cli_module.build_parser().parse_args(["batch", "a.pdf", "b.pdf"])
    assert args.filenames == ["a.pdf", "b.pdf"]


# --- cmd_process -------------------------------------------------------------


def test_process_success_prints_json_with_requested_title(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli_module, "get_process_book_use_case", lambda: _fake_use_case())
    monkeypatch.setattr(cli_module.settings, "input_dir", tmp_path)

    exit_code = cli_module.main(
        ["process", "book.pdf", "--title", "کتاب تست", "--json"]
    )

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["book_title"] == "کتاب تست"
    assert output["total_pages"] == 1
    assert output["filename"] == "book.pdf"


def test_process_success_human_readable_summary(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli_module, "get_process_book_use_case", lambda: _fake_use_case())
    monkeypatch.setattr(cli_module.settings, "input_dir", tmp_path)

    exit_code = cli_module.main(["process", "book.pdf", "--title", "کتاب تست"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "book.pdf" in out
    assert "کتاب تست" in out


def test_process_failure_returns_nonzero_and_reports_on_stderr(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setattr(
        cli_module,
        "get_process_book_use_case",
        lambda: _fake_use_case(fail_for=frozenset({"bad.pdf"})),
    )
    monkeypatch.setattr(cli_module.settings, "input_dir", tmp_path)

    exit_code = cli_module.main(["process", "bad.pdf"])

    assert exit_code == 1
    err = capsys.readouterr().err
    assert "bad.pdf" in err
    assert "simulated failure" in err


# --- cmd_batch ----------------------------------------------------------------


def test_batch_isolates_one_failure(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(
        cli_module,
        "get_process_book_use_case",
        lambda: _fake_use_case(fail_for=frozenset({"bad.pdf"})),
    )
    monkeypatch.setattr(cli_module.settings, "input_dir", tmp_path)

    exit_code = cli_module.main(["batch", "good.pdf", "bad.pdf", "--json"])

    assert exit_code == 1  # non-zero: at least one item failed
    output = json.loads(capsys.readouterr().out)
    assert output["total"] == 2
    assert output["succeeded"] == 1
    assert output["failed"] == 1

    by_name = {item["filename"]: item for item in output["items"]}
    assert by_name["good.pdf"]["ok"] is True
    assert by_name["bad.pdf"]["ok"] is False
    assert "simulated failure" in by_name["bad.pdf"]["error"]


def test_batch_all_succeed_returns_zero_exit_code(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli_module, "get_process_book_use_case", lambda: _fake_use_case())
    monkeypatch.setattr(cli_module.settings, "input_dir", tmp_path)

    exit_code = cli_module.main(["batch", "a.pdf", "b.pdf", "--json"])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["succeeded"] == 2
    assert output["failed"] == 0


def test_batch_auto_discovers_pdfs_and_ignores_non_pdf_files(
    monkeypatch, tmp_path, capsys
):
    (tmp_path / "a.pdf").touch()
    (tmp_path / "b.pdf").touch()
    (tmp_path / "notes.txt").touch()

    monkeypatch.setattr(cli_module, "get_process_book_use_case", lambda: _fake_use_case())
    monkeypatch.setattr(cli_module.settings, "input_dir", tmp_path)

    exit_code = cli_module.main(["batch", "--json"])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["total"] == 2
    filenames = {item["filename"] for item in output["items"]}
    assert filenames == {"a.pdf", "b.pdf"}


def test_batch_with_empty_input_dir_and_no_filenames_returns_error(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setattr(cli_module, "get_process_book_use_case", lambda: _fake_use_case())
    monkeypatch.setattr(cli_module.settings, "input_dir", tmp_path)

    exit_code = cli_module.main(["batch"])

    assert exit_code == 1
    assert "input/" in capsys.readouterr().err
