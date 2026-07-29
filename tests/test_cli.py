from decimal import Decimal
from pathlib import Path

import pytest

import playsipps.cli as cli
from playsipps.extract import PayslipFields


def test_main_without_subcommand_shows_usage(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit):
        cli.main([])

    assert "usage:" in capsys.readouterr().err


def test_main_download_subcommand_runs_download(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[dict[str, object]] = []

    def fake_run(**kwargs: object) -> list[str]:
        calls.append(kwargs)
        return ["2026 04"]

    monkeypatch.setattr(cli.moorepay, "run", fake_run)

    cli.main(["download", "--limit", "2", "--profile-dir", str(tmp_path)])

    assert calls == [
        {
            "headless": False,
            "profile_dir": tmp_path,
            "save_html_path": None,
            "skip_login_prompt": False,
            "timeout_ms": cli.moorepay.DEFAULT_TIMEOUT_MS,
            "limit": 2,
        }
    ]
    assert capsys.readouterr().out == "2026 04\n"


def test_main_download_subcommand_accepts_short_options(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[dict[str, object]] = []

    def fake_run(**kwargs: object) -> list[str]:
        calls.append(kwargs)
        return []

    monkeypatch.setattr(cli.moorepay, "run", fake_run)

    cli.main(
        [
            "download",
            "-H",
            "-p",
            str(tmp_path / "profile"),
            "-s",
            str(tmp_path / "page.html"),
            "-t",
            "999",
            "-l",
            "8",
        ]
    )

    assert calls == [
        {
            "headless": True,
            "profile_dir": tmp_path / "profile",
            "save_html_path": tmp_path / "page.html",
            "skip_login_prompt": True,
            "timeout_ms": 999,
            "limit": 8,
        }
    ]


def test_main_extract_subcommand_writes_csv(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    downloads_dir = tmp_path / "downloads"
    output = tmp_path / "payslips.csv"
    spreadsheet = tmp_path / "payslips.xlsx"
    calls: list[tuple[Path, object, object]] = []
    spreadsheet_calls: list[tuple[list[PayslipFields], Path]] = []
    rows = [PayslipFields()]

    def fake_extract_payslips(
        downloads_dir_arg: Path,
        *,
        text_reader: object,
        progress: object,
    ) -> list[PayslipFields]:
        calls.append((downloads_dir_arg, text_reader, progress))
        return rows

    def fake_write_payslips_xlsx(
        rows_arg: list[PayslipFields],
        output_path_arg: Path,
    ) -> None:
        spreadsheet_calls.append((rows_arg, output_path_arg))

    monkeypatch.setattr(cli, "extract_payslips", fake_extract_payslips)
    monkeypatch.setattr(cli, "write_payslips_xlsx", fake_write_payslips_xlsx)

    cli.main(
        [
            "extract",
            "--downloads-dir",
            str(downloads_dir),
            "--output",
            str(output),
            "--spreadsheet",
            str(spreadsheet),
        ]
    )

    assert len(calls) == 1
    assert calls[0][0] == downloads_dir
    assert calls[0][1] == cli.ocr_pdf_text
    assert calls[0][2] is not None
    assert spreadsheet_calls == [(rows, spreadsheet)]
    assert output.read_text(encoding="utf-8").splitlines() == [
        "yyyy-mm,gross salary,tax deducted,ni deducted,pension deducted,net salary,"
        "employers pension",
        ",,,,,,",
    ]
    assert capsys.readouterr().out == (
        f"Wrote 1 payslip row to {output} and {spreadsheet}\n"
    )


def test_main_extract_subcommand_can_dump_text(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    downloads_dir = tmp_path / "downloads"
    text_dir = tmp_path / "text"
    output = tmp_path / "payslips.csv"
    spreadsheet = tmp_path / "payslips.xlsx"
    calls: list[tuple[Path, Path, object, object]] = []
    spreadsheet_calls: list[tuple[list[PayslipFields], Path]] = []

    def fake_dump_pdf_texts(
        downloads_dir_arg: Path,
        output_dir_arg: Path,
        *,
        text_reader: object,
        progress: object,
    ) -> list[Path]:
        calls.append((downloads_dir_arg, output_dir_arg, text_reader, progress))
        text_path = output_dir_arg / "2026-04.txt"
        text_path.parent.mkdir(parents=True)
        text_path.write_text("Net Pay £2.00", encoding="utf-8")
        return [text_path]

    def fake_write_payslips_xlsx(
        rows_arg: list[PayslipFields],
        output_path_arg: Path,
    ) -> None:
        spreadsheet_calls.append((rows_arg, output_path_arg))

    monkeypatch.setattr(cli, "dump_pdf_texts", fake_dump_pdf_texts)
    monkeypatch.setattr(cli, "write_payslips_xlsx", fake_write_payslips_xlsx)

    cli.main(
        [
            "extract",
            "--downloads-dir",
            str(downloads_dir),
            "--dump-text",
            str(text_dir),
            "--output",
            str(output),
            "--spreadsheet",
            str(spreadsheet),
        ]
    )

    assert len(calls) == 1
    assert calls[0][0] == downloads_dir
    assert calls[0][1] == text_dir
    assert calls[0][2] == cli.ocr_pdf_text
    assert calls[0][3] is not None
    assert len(spreadsheet_calls) == 1
    assert spreadsheet_calls[0][0] == [
        PayslipFields(yyyy_mm="2026-04", net_salary=Decimal("2.00"))
    ]
    assert spreadsheet_calls[0][1] == spreadsheet
    assert output.read_text(encoding="utf-8").splitlines() == [
        "yyyy-mm,gross salary,tax deducted,ni deducted,pension deducted,net salary,"
        "employers pension",
        "2026-04,,,,,2.00,",
    ]
    assert capsys.readouterr().out == (
        f"Wrote 1 text file to {text_dir}\n"
        f"Wrote 1 payslip row to {output} and {spreadsheet}\n"
    )


def test_main_extract_subcommand_can_dump_text_without_ocr(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    downloads_dir = tmp_path / "downloads"
    text_dir = tmp_path / "text"
    output = tmp_path / "payslips.csv"
    spreadsheet = tmp_path / "payslips.xlsx"
    calls: list[tuple[Path, Path, object, object]] = []

    def fake_dump_pdf_texts(
        downloads_dir_arg: Path,
        output_dir_arg: Path,
        *,
        text_reader: object,
        progress: object,
    ) -> list[Path]:
        calls.append((downloads_dir_arg, output_dir_arg, text_reader, progress))
        return []

    monkeypatch.setattr(cli, "dump_pdf_texts", fake_dump_pdf_texts)

    cli.main(
        [
            "extract",
            "-d",
            str(downloads_dir),
            "-t",
            str(text_dir),
            "-o",
            str(output),
            "-x",
            str(spreadsheet),
            "-n",
        ]
    )

    assert len(calls) == 1
    assert calls[0][0] == downloads_dir
    assert calls[0][1] == text_dir
    assert calls[0][2] == cli.read_pdf_text
    assert calls[0][3] is not None


def test_main_extract_subcommand_accepts_short_options(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    downloads_dir = tmp_path / "downloads"
    text_dir = tmp_path / "text"
    output = tmp_path / "payslips.csv"
    spreadsheet = tmp_path / "payslips.xlsx"
    calls: list[tuple[Path, Path, object, object]] = []

    def fake_dump_pdf_texts(
        downloads_dir_arg: Path,
        output_dir_arg: Path,
        *,
        text_reader: object,
        progress: object,
    ) -> list[Path]:
        calls.append((downloads_dir_arg, output_dir_arg, text_reader, progress))
        return []

    monkeypatch.setattr(cli, "dump_pdf_texts", fake_dump_pdf_texts)

    args = cli.parse_extract_args(["-d", str(downloads_dir), "-x", str(spreadsheet)])

    assert args.downloads_dir == downloads_dir
    assert args.spreadsheet == spreadsheet

    cli.main(
        [
            "extract",
            "-d",
            str(downloads_dir),
            "-t",
            str(text_dir),
            "-o",
            str(output),
            "-x",
            str(spreadsheet),
        ]
    )
    assert len(calls) == 1
    assert calls[0][0] == downloads_dir
    assert calls[0][1] == text_dir
    assert calls[0][2] == cli.ocr_pdf_text
    assert calls[0][3] is not None


def test_extract_progress_uses_tqdm_pdf_progress(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    paths = [tmp_path / "2026-01.pdf"]
    tqdm_calls: list[tuple[list[Path], str, str]] = []

    def fake_tqdm(paths_arg: list[Path], *, desc: str, unit: str) -> list[Path]:
        tqdm_calls.append((paths_arg, desc, unit))
        return paths_arg

    monkeypatch.setattr(cli, "tqdm", fake_tqdm)

    assert list(cli.extract_progress(paths)) == paths
    assert tqdm_calls == [(paths, "Processing PDFs", "pdf")]


def test_main_rejects_unknown_subcommand() -> None:
    with pytest.raises(SystemExit):
        cli.main(["missing"])


def test_main_help_lists_subcommands(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as error:
        cli.main(["--help"])

    assert error.value.code == 0
    output = capsys.readouterr().out
    assert "download" in output
    assert "extract" in output


def test_parse_extract_args_uses_defaults() -> None:
    args = cli.parse_extract_args([])

    assert args.downloads_dir == Path("downloads")
    assert args.output == Path("payslips.csv")
    assert args.spreadsheet == Path("payslips.xlsx")
    assert args.dump_text_dir is None
    assert args.ocr is True


def test_parse_extract_args_accepts_no_ocr() -> None:
    args = cli.parse_extract_args(["--no-ocr"])

    assert args.ocr is False


def test_parse_extract_args_rejects_ocr_and_no_ocr_together() -> None:
    with pytest.raises(SystemExit):
        cli.parse_extract_args(["--ocr", "--no-ocr"])


def test_row_count_message_uses_plural() -> None:
    assert cli.row_count_message(0) == "0 payslip rows"
    assert cli.row_count_message(1) == "1 payslip row"
    assert cli.row_count_message(2) == "2 payslip rows"


def test_text_file_count_message_uses_plural() -> None:
    assert cli.text_file_count_message(0) == "0 text files"
    assert cli.text_file_count_message(1) == "1 text file"
    assert cli.text_file_count_message(2) == "2 text files"
