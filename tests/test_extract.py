import builtins
import subprocess
import sys
import zipfile
from collections.abc import Mapping, Sequence
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

import playsipps.extract as extract
from playsipps.extract import (
    CSV_FIELDNAMES,
    SPREADSHEET_FIELDNAMES,
    PayslipFields,
    calendar_month,
    dump_pdf_texts,
    extract_payslips,
    ocr_pdf_text,
    parse_money,
    parse_payslip_text,
    pdf_paths,
    write_payslips_csv,
    write_payslips_xlsx,
)


def test_pdf_paths_returns_pdfs_sorted_by_name(tmp_path: Path) -> None:
    (tmp_path / "2026-03.pdf").write_text("three", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("ignore", encoding="utf-8")
    (tmp_path / "2026-01.PDF").write_text("one", encoding="utf-8")

    assert pdf_paths(tmp_path) == [
        tmp_path / "2026-01.PDF",
        tmp_path / "2026-03.pdf",
    ]


def test_pdf_paths_returns_empty_list_when_downloads_dir_is_missing(
    tmp_path: Path,
) -> None:
    assert pdf_paths(tmp_path / "missing") == []


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("£1,234.56", Decimal("1234.56")),
        ("(123.45)", Decimal("-123.45")),
        ("-99.00", Decimal("-99.00")),
        ("", None),
    ],
)
def test_parse_money(raw: str, expected: Decimal | None) -> None:
    assert parse_money(raw) == expected


def test_parse_payslip_text_extracts_known_fields() -> None:
    text = """
    Gross Pay £5,000.00
    Tax £1,000.00
    Employee NI £250.50
    Pension £300.00
    Net Pay £3,449.50
    Employer Pension £600.00
    """

    fields = parse_payslip_text(Path("downloads/2026-04.pdf"), text)

    assert fields == PayslipFields(
        payroll_period="2026-04",
        gross_salary=Decimal("5000.00"),
        tax_deducted=Decimal("1000.00"),
        ni_deducted=Decimal("250.50"),
        pension_deducted=Decimal("300.00"),
        net_salary=Decimal("3449.50"),
        employers_pension=Decimal("600.00"),
    )


def test_parse_payslip_text_ignores_tax_code_and_ni_number() -> None:
    text = """
    Tax Code 0000T
    National Insurance No. QQ000000Q
    TAX 12.34 56.78
    N.I. 9.87 65.43
    """

    fields = parse_payslip_text(Path("downloads/2026-03.pdf"), text)

    assert fields.payroll_period == "2026-03"
    assert fields.tax_deducted == Decimal("12.34")
    assert fields.ni_deducted == Decimal("9.87")


def test_parse_payslip_text_ignores_lines_before_pay_item_section() -> None:
    text = """
    TAX 999.99 999.99
    N.I. 888.88 888.88
    Cost Centre 01
    Pay Item
    Pay Item Units Rate This Period Year To Date
    SALARY 1234.56 2469.12
    Deduction Item
    TAX 234.00 468.00
    N.I. 0.56 1.12
    EMPLOYEE PEN CON 100.00 200.00
    Pay Method NET PAY
    BANK 900.00
    Other Information
    Employers Pens 200.00 400.00
    """

    fields = parse_payslip_text(Path("downloads/2026-03.pdf"), text)

    assert fields.payroll_period == "2026-03"
    assert fields.tax_deducted == Decimal("234.00")
    assert fields.ni_deducted == Decimal("0.56")


def test_parse_payslip_text_parses_synthetic_ocr_text() -> None:
    text = """
    Pay Item
    Pay Item Units Rate This Period Year To Date
    SALARY 1234.56 2469.12
    PAYMENT TOTAL 1234.56 2469.12
    Deduction Item
    Deduction Item This Period Year To Date
    TAX 234.00 468.00
    N.I. 12.34 24.68
    EMPLOYEE PEN CON 100.00 200.00
    DEDUCTION TOTAL 346.34 692.68
    Pay Method NET PAY
    BANK 888.22
    Other Information
    Other Information This Period Year To Date
    Employers Pens 200.00 400.00
    Messages
    Synthetic fixture text
    """

    fields = parse_payslip_text(Path("downloads/2026-03.pdf"), text)

    assert fields == PayslipFields(
        payroll_period="2026-03",
        gross_salary=Decimal("1234.56"),
        tax_deducted=Decimal("234.00"),
        ni_deducted=Decimal("12.34"),
        pension_deducted=Decimal("100.00"),
        net_salary=Decimal("888.22"),
        employers_pension=Decimal("200.00"),
    )


def test_parse_payslip_text_extracts_net_salary() -> None:
    fields = parse_payslip_text(Path("downloads/2026-04.pdf"), "Net Pay £1.00")

    assert fields.net_salary == Decimal("1.00")


def test_parse_payslip_text_ignores_money_label_without_money_value() -> None:
    fields = parse_payslip_text(Path("downloads/2026-04.pdf"), "Gross Pay withheld")

    assert fields.gross_salary is None


def test_extract_payslips_reads_each_pdf_with_injected_reader(tmp_path: Path) -> None:
    first = tmp_path / "2026-01.pdf"
    second = tmp_path / "2026-02.pdf"
    first.write_text("not a real pdf", encoding="utf-8")
    second.write_text("not a real pdf", encoding="utf-8")

    rows = extract_payslips(
        tmp_path,
        text_reader=lambda path: f"Period {path.stem.replace('-', ' ')}\nNet Pay £2.00",
    )

    assert [(row.payroll_period, row.net_salary) for row in rows] == [
        ("2026-01", Decimal("2.00")),
        ("2026-02", Decimal("2.00")),
    ]


@pytest.mark.parametrize(
    ("payroll_period", "expected"),
    [
        ("2026-01", "2026-04"),
        ("2026-04", "2026-07"),
        ("2026-09", "2026-12"),
        ("2026-10", "2027-01"),
        (None, None),
    ],
)
def test_calendar_month_maps_uk_monthly_payroll_periods(
    payroll_period: str | None,
    expected: str | None,
) -> None:
    assert calendar_month(payroll_period) == expected


def test_extract_payslips_reports_pdf_progress(tmp_path: Path) -> None:
    first = tmp_path / "2026-01.pdf"
    second = tmp_path / "2026-02.pdf"
    first.write_text("not a real pdf", encoding="utf-8")
    second.write_text("not a real pdf", encoding="utf-8")
    progressed_paths: list[Path] = []

    def progress(paths: list[Path]) -> list[Path]:
        progressed_paths.extend(paths)
        return paths

    extract_payslips(
        tmp_path,
        text_reader=lambda path: f"Period {path.stem.replace('-', ' ')}\nNet Pay £2.00",
        progress=progress,
    )

    assert progressed_paths == [first, second]


def test_dump_pdf_texts_writes_one_txt_file_per_pdf(tmp_path: Path) -> None:
    downloads_dir = tmp_path / "downloads"
    output_dir = tmp_path / "text"
    downloads_dir.mkdir()
    (downloads_dir / "2026-01.pdf").write_text("not a real pdf", encoding="utf-8")
    (downloads_dir / "2026-02.pdf").write_text("not a real pdf", encoding="utf-8")

    paths = dump_pdf_texts(
        downloads_dir,
        output_dir,
        text_reader=lambda path: f"text for {path.name}",
    )

    assert paths == [output_dir / "2026-01.txt", output_dir / "2026-02.txt"]
    assert (output_dir / "2026-01.txt").read_text(encoding="utf-8") == (
        "text for 2026-01.pdf"
    )
    assert (output_dir / "2026-02.txt").read_text(encoding="utf-8") == (
        "text for 2026-02.pdf"
    )


def test_dump_pdf_texts_reports_pdf_progress(tmp_path: Path) -> None:
    downloads_dir = tmp_path / "downloads"
    output_dir = tmp_path / "text"
    downloads_dir.mkdir()
    first = downloads_dir / "2026-01.pdf"
    second = downloads_dir / "2026-02.pdf"
    first.write_text("not a real pdf", encoding="utf-8")
    second.write_text("not a real pdf", encoding="utf-8")
    progressed_paths: list[Path] = []

    def progress(paths: list[Path]) -> list[Path]:
        progressed_paths.extend(paths)
        return paths

    dump_pdf_texts(
        downloads_dir,
        output_dir,
        text_reader=lambda path: f"text for {path.name}",
        progress=progress,
    )

    assert progressed_paths == [first, second]


def test_ocr_pdf_text_runs_ocrmypdf_and_reads_sidecar(tmp_path: Path) -> None:
    pdf_path = tmp_path / "2026-04.pdf"
    pdf_path.write_text("not a real pdf", encoding="utf-8")
    commands: list[list[str]] = []

    def fake_runner(command: list[str]) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        sidecar_path = Path(command[3])
        sidecar_path.write_text("OCR text", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    text = ocr_pdf_text(pdf_path, ocrmypdf_command="ocrmypdf-test", runner=fake_runner)

    assert text == "OCR text"
    assert commands == [
        [
            "ocrmypdf-test",
            "--force-ocr",
            "--sidecar",
            commands[0][3],
            str(pdf_path),
            commands[0][5],
        ]
    ]
    assert Path(commands[0][3]).name == "2026-04.txt"
    assert Path(commands[0][5]).name == "2026-04.pdf"


def test_ocr_pdf_text_raises_when_ocrmypdf_fails(tmp_path: Path) -> None:
    pdf_path = tmp_path / "2026-04.pdf"
    pdf_path.write_text("not a real pdf", encoding="utf-8")

    def fake_runner(command: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="bad pdf")

    with pytest.raises(RuntimeError, match=r"OCRmyPDF failed.*bad pdf"):
        ocr_pdf_text(pdf_path, runner=fake_runner)


def test_write_payslips_csv_writes_stable_headers_and_decimal_values(
    tmp_path: Path,
) -> None:
    output = tmp_path / "nested" / "payslips.csv"
    rows = [
        PayslipFields(
            payroll_period="2026-04",
            gross_salary=Decimal("5000.00"),
            tax_deducted=Decimal("1000.00"),
            ni_deducted=Decimal("250.50"),
            pension_deducted=None,
            net_salary=Decimal("3449.50"),
            employers_pension=Decimal("600.00"),
        )
    ]

    write_payslips_csv(rows, output)

    assert output.read_text(encoding="utf-8").splitlines() == [
        ",".join(CSV_FIELDNAMES),
        "2026-04,2026-07,5000.00,1000.00,250.50,,3449.50,600.00",
    ]


def test_write_payslips_xlsx_writes_data_and_validation_formulas(
    tmp_path: Path,
) -> None:
    output = tmp_path / "nested" / "payslips.xlsx"
    rows = [
        PayslipFields(
            payroll_period="2026-04",
            gross_salary=Decimal("5000.00"),
            tax_deducted=Decimal("1000.00"),
            ni_deducted=Decimal("250.50"),
            pension_deducted=Decimal("300.00"),
            net_salary=Decimal("3449.50"),
            employers_pension=Decimal("600.00"),
        ),
        PayslipFields(),
    ]

    write_payslips_xlsx(rows, output)

    with zipfile.ZipFile(output) as workbook:
        worksheet = workbook.read("xl/worksheets/sheet1.xml").decode()
        assert set(workbook.namelist()) == {
            "[Content_Types].xml",
            "_rels/.rels",
            "xl/workbook.xml",
            "xl/_rels/workbook.xml.rels",
            "xl/worksheets/sheet1.xml",
        }
    for heading in SPREADSHEET_FIELDNAMES:
        assert f"<ns0:t>{heading}</ns0:t>" in worksheet
    assert '<ns0:c r="A2" t="inlineStr"><ns0:is><ns0:t>2026-04</ns0:t>' in worksheet
    assert '<ns0:c r="B2" t="inlineStr"><ns0:is><ns0:t>2026-07</ns0:t>' in worksheet
    assert '<ns0:c r="C2"><ns0:v>5000.00</ns0:v></ns0:c>' in worksheet
    assert '<ns0:c r="A3" t="inlineStr"><ns0:is><ns0:t /></ns0:is></ns0:c>' in worksheet
    assert '<ns0:c r="B3" t="inlineStr"><ns0:is><ns0:t /></ns0:is></ns0:c>' in worksheet
    assert "<ns0:f>SUM(D2:F2)</ns0:f>" in worksheet
    assert "<ns0:f>C2-I2-G2</ns0:f>" in worksheet
    assert "<ns0:f>ABS(J2)&lt;0.01</ns0:f>" in worksheet


def test_basic_ocr_text_matches_target_output_files(tmp_path: Path) -> None:
    text_path = Path("tests/text/basic.txt")
    expected_csv_path = Path("tests/output/basic.csv")
    expected_xlsx_path = Path("tests/output/basic.xlsx")
    output_csv_path = tmp_path / "basic.csv"
    output_xlsx_path = tmp_path / "basic.xlsx"
    rows = [parse_payslip_text(Path("downloads/2026-03.pdf"), text_path.read_text())]

    write_payslips_csv(rows, output_csv_path)
    write_payslips_xlsx(rows, output_xlsx_path)

    assert output_csv_path.read_text(encoding="utf-8") == expected_csv_path.read_text(
        encoding="utf-8"
    )
    assert workbook_contents(output_xlsx_path) == workbook_contents(expected_xlsx_path)


def workbook_contents(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as workbook:
        return {name: workbook.read(name) for name in sorted(workbook.namelist())}


def test_read_pdf_text_raises_clear_error_when_pypdf_is_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def blocked_import(
        name: str,
        globals: Mapping[str, object] | None = None,
        locals: Mapping[str, object] | None = None,
        fromlist: Sequence[str] | None = (),
        level: int = 0,
    ) -> object:
        if name == "pypdf":
            raise ImportError("missing")
        return original_import(name, globals, locals, fromlist, level)

    original_import = builtins.__import__
    monkeypatch.setattr("builtins.__import__", blocked_import)

    with pytest.raises(RuntimeError, match="Install the pypdf dependency"):
        extract.read_pdf_text(tmp_path / "payslip.pdf")


def test_read_pdf_text_joins_page_text(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class FakePage:
        def __init__(self, text: str | None) -> None:
            self.text = text

        def extract_text(self) -> str | None:
            return self.text

    class FakeReader:
        def __init__(self, path: Path) -> None:
            self.path = path
            self.pages = [FakePage("one"), FakePage(None), FakePage("three")]

    monkeypatch.setitem(
        sys.modules,
        "pypdf",
        SimpleNamespace(PdfReader=FakeReader),
    )

    assert extract.read_pdf_text(tmp_path / "payslip.pdf") == "one\n\nthree"


def test_read_pdf_text_raises_when_pdf_has_no_embedded_text(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class FakePage:
        def extract_text(self) -> str:
            return ""

    class FakeReader:
        def __init__(self, path: Path) -> None:
            self.path = path
            self.pages = [FakePage()]

    monkeypatch.setitem(
        sys.modules,
        "pypdf",
        SimpleNamespace(PdfReader=FakeReader),
    )

    with pytest.raises(RuntimeError, match="Try again with --ocr"):
        extract.read_pdf_text(tmp_path / "payslip.pdf")


def test_run_ocr_command_raises_clear_error_when_ocrmypdf_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing_command(
        *args: object,
        **kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError

    monkeypatch.setattr("subprocess.run", missing_command)

    with pytest.raises(RuntimeError, match="Install OCRmyPDF"):
        extract._run_ocr_command(["ocrmypdf"])


def test_run_ocr_command_returns_completed_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completed = subprocess.CompletedProcess(["ocrmypdf"], 0, stdout="ok", stderr="")

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return completed

    monkeypatch.setattr("subprocess.run", fake_run)

    assert extract._run_ocr_command(["ocrmypdf"]) == completed
