"""Offline payslip PDF extraction and CSV export."""

import csv
import re
import subprocess
import tempfile
import zipfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Final
from xml.etree.ElementTree import Element, SubElement, tostring

DOWNLOADS_DIR: Final = Path("downloads")
DEFAULT_CSV_PATH: Final = Path("payslips.csv")
DEFAULT_SPREADSHEET_PATH: Final = Path("payslips.xlsx")
CSV_FIELDNAMES: Final = (
    "payroll period",
    "calendar month",
    "gross salary",
    "tax deducted",
    "ni deducted",
    "pension deducted",
    "net salary",
    "employers pension",
)
SPREADSHEET_FIELDNAMES: Final = (
    *CSV_FIELDNAMES,
    "deductions total",
    "gross minus deductions and net",
    "valid",
)
MONEY_PATTERN: Final = re.compile(r"-?\(?£?\s*\d[\d,]*(?:\.\d{2})?\)?")
OCRMYPDF_COMMAND: Final = "ocrmypdf"
OcrRunner = Callable[[list[str]], subprocess.CompletedProcess[str]]
PdfProgress = Callable[[list[Path]], Iterable[Path]]
SPREADSHEET_NS: Final = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
RELATIONSHIPS_NS: Final = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
)


@dataclass(frozen=True)
class PayslipFields:
    payroll_period: str | None = None
    gross_salary: Decimal | None = None
    tax_deducted: Decimal | None = None
    ni_deducted: Decimal | None = None
    pension_deducted: Decimal | None = None
    net_salary: Decimal | None = None
    employers_pension: Decimal | None = None


def pdf_paths(downloads_dir: Path = DOWNLOADS_DIR) -> list[Path]:
    """Return payslip PDF paths sorted by filename."""
    if not downloads_dir.exists():
        return []
    return sorted(
        path for path in downloads_dir.iterdir() if path.suffix.lower() == ".pdf"
    )


def read_pdf_text(path: Path) -> str:
    """Extract text from a PDF using pypdf."""
    try:
        from pypdf import PdfReader
    except ImportError as error:
        raise RuntimeError(
            "Install the pypdf dependency before extracting payslip PDFs."
        ) from error

    reader = PdfReader(path)
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    if not text.strip():
        raise RuntimeError(f"No embedded text found in {path}. Try again with --ocr.")
    return text


def ocr_pdf_text(
    path: Path,
    *,
    ocrmypdf_command: str = OCRMYPDF_COMMAND,
    runner: OcrRunner | None = None,
) -> str:
    """Extract PDF text by running OCRmyPDF and reading its sidecar output."""
    command_runner = _run_ocr_command if runner is None else runner
    with tempfile.TemporaryDirectory() as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        sidecar_path = temp_dir / f"{path.stem}.txt"
        output_pdf_path = temp_dir / f"{path.stem}.pdf"
        result = command_runner(
            [
                ocrmypdf_command,
                "--force-ocr",
                "--sidecar",
                str(sidecar_path),
                str(path),
                str(output_pdf_path),
            ]
        )
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(f"OCRmyPDF failed for {path}: {detail}")
        return sidecar_path.read_text(encoding="utf-8")


def parse_money(value: str) -> Decimal | None:
    """Parse a payslip money value into a Decimal."""
    raw = value.strip()
    if not raw:
        return None
    negative = raw.startswith("(") and raw.endswith(")")
    cleaned = raw.replace("£", "").replace(",", "").replace("(", "").replace(")", "")
    amount = Decimal(cleaned.strip())
    return -amount if negative else amount


def parse_payslip_text(path: Path, text: str) -> PayslipFields:
    """Parse known payslip fields from extracted PDF text."""
    lines = [" ".join(line.split()) for line in text.splitlines() if line.split()]
    table_lines = _payslip_table_lines(lines)
    return PayslipFields(
        payroll_period=path.stem,
        gross_salary=_money_field(
            table_lines,
            ("SALARY", "Gross Pay", "Total Gross Pay"),
        ),
        tax_deducted=_money_field(table_lines, ("TAX", "PAYE Tax")),
        ni_deducted=_money_field(
            table_lines,
            ("N.I.", "N.L.", "Employee NI", "Empl NIC"),
        ),
        pension_deducted=_money_field(
            table_lines,
            ("EMPLOYEE PEN CON", "Pension", "Employee Pension"),
        ),
        net_salary=_money_field(table_lines, ("BANK", "Net Pay", "Take Home Pay")),
        employers_pension=_money_field(
            table_lines,
            ("Employers Pens", "Employer Pension"),
        ),
    )


def extract_payslips(
    downloads_dir: Path = DOWNLOADS_DIR,
    *,
    text_reader: Callable[[Path], str] = read_pdf_text,
    progress: PdfProgress | None = None,
) -> list[PayslipFields]:
    """Extract payslip fields from every PDF in a downloads directory."""
    paths = pdf_paths(downloads_dir)
    progressed_paths = paths if progress is None else progress(paths)
    return [parse_payslip_text(path, text_reader(path)) for path in progressed_paths]


def dump_pdf_texts(
    downloads_dir: Path,
    output_dir: Path,
    *,
    text_reader: Callable[[Path], str] = read_pdf_text,
    progress: PdfProgress | None = None,
) -> list[Path]:
    """Write extracted PDF text to one txt file per payslip."""
    output_dir.mkdir(parents=True, exist_ok=True)
    dumped_paths: list[Path] = []
    paths = pdf_paths(downloads_dir)
    progressed_paths = paths if progress is None else progress(paths)
    for pdf_path in progressed_paths:
        text_path = output_dir / f"{pdf_path.stem}.txt"
        text_path.write_text(text_reader(pdf_path), encoding="utf-8")
        dumped_paths.append(text_path)
    return dumped_paths


def write_payslips_csv(rows: Iterable[PayslipFields], output_path: Path) -> None:
    """Write extracted payslip fields to a CSV file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow(_csv_row(row))


def write_payslips_xlsx(rows: Iterable[PayslipFields], output_path: Path) -> None:
    """Write extracted payslip fields and validation formulas to an XLSX file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as workbook:
        workbook.writestr("[Content_Types].xml", _content_types_xml())
        workbook.writestr("_rels/.rels", _root_relationships_xml())
        workbook.writestr("xl/workbook.xml", _workbook_xml())
        workbook.writestr("xl/_rels/workbook.xml.rels", _workbook_relationships_xml())
        workbook.writestr("xl/worksheets/sheet1.xml", _worksheet_xml(rows))


def _csv_row(row: PayslipFields) -> dict[str, str]:
    return {
        "payroll period": _csv_value(row.payroll_period),
        "calendar month": _csv_value(calendar_month(row.payroll_period)),
        "gross salary": _csv_value(row.gross_salary),
        "tax deducted": _csv_value(row.tax_deducted),
        "ni deducted": _csv_value(row.ni_deducted),
        "pension deducted": _csv_value(row.pension_deducted),
        "net salary": _csv_value(row.net_salary),
        "employers pension": _csv_value(row.employers_pension),
    }


def _csv_value(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def calendar_month(payroll_period: str | None) -> str | None:
    """Return the calendar month for a UK monthly payroll period."""
    if payroll_period is None:
        return None
    year_text, period_text = payroll_period.split("-", maxsplit=1)
    year = int(year_text)
    month = int(period_text) + 3
    if month > 12:
        year += 1
        month -= 12
    return f"{year:04d}-{month:02d}"


def _worksheet_xml(rows: Iterable[PayslipFields]) -> str:
    worksheet = Element(f"{{{SPREADSHEET_NS}}}worksheet")
    sheet_data = SubElement(worksheet, f"{{{SPREADSHEET_NS}}}sheetData")
    _append_header_row(sheet_data)
    for index, row in enumerate(rows, start=2):
        _append_data_row(sheet_data, index, row)
    return _xml_document(worksheet)


def _append_header_row(sheet_data: Element) -> None:
    row = SubElement(sheet_data, f"{{{SPREADSHEET_NS}}}row", {"r": "1"})
    for column, heading in enumerate(SPREADSHEET_FIELDNAMES, start=1):
        _append_text_cell(row, column, 1, heading)


def _append_data_row(
    sheet_data: Element,
    row_number: int,
    row_data: PayslipFields,
) -> None:
    row = SubElement(sheet_data, f"{{{SPREADSHEET_NS}}}row", {"r": str(row_number)})
    _append_text_cell(row, 1, row_number, _csv_value(row_data.payroll_period))
    _append_text_cell(
        row,
        2,
        row_number,
        _csv_value(calendar_month(row_data.payroll_period)),
    )
    values = (
        row_data.gross_salary,
        row_data.tax_deducted,
        row_data.ni_deducted,
        row_data.pension_deducted,
        row_data.net_salary,
        row_data.employers_pension,
    )
    for column, value in enumerate(values, start=3):
        _append_number_cell(row, column, row_number, value)
    _append_formula_cell(row, 9, row_number, f"SUM(D{row_number}:F{row_number})")
    _append_formula_cell(
        row,
        10,
        row_number,
        f"C{row_number}-I{row_number}-G{row_number}",
    )
    _append_formula_cell(row, 11, row_number, f"ABS(J{row_number})<0.01")


def _append_text_cell(row: Element, column: int, row_number: int, value: str) -> None:
    cell = SubElement(
        row,
        f"{{{SPREADSHEET_NS}}}c",
        {"r": _cell_reference(column, row_number), "t": "inlineStr"},
    )
    inline_string = SubElement(cell, f"{{{SPREADSHEET_NS}}}is")
    text = SubElement(inline_string, f"{{{SPREADSHEET_NS}}}t")
    text.text = value


def _append_number_cell(
    row: Element,
    column: int,
    row_number: int,
    value: Decimal | None,
) -> None:
    cell = SubElement(
        row,
        f"{{{SPREADSHEET_NS}}}c",
        {"r": _cell_reference(column, row_number)},
    )
    if value is not None:
        cell_value = SubElement(cell, f"{{{SPREADSHEET_NS}}}v")
        cell_value.text = str(value)


def _append_formula_cell(
    row: Element,
    column: int,
    row_number: int,
    formula: str,
) -> None:
    cell = SubElement(
        row,
        f"{{{SPREADSHEET_NS}}}c",
        {"r": _cell_reference(column, row_number)},
    )
    cell_formula = SubElement(cell, f"{{{SPREADSHEET_NS}}}f")
    cell_formula.text = formula


def _cell_reference(column: int, row: int) -> str:
    letters = ""
    current = column
    while current:
        current, remainder = divmod(current - 1, 26)
        letters = f"{chr(65 + remainder)}{letters}"
    return f"{letters}{row}"


def _content_types_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/'
        'content-types">\n'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-'
        'package.relationships+xml"/>\n'
        '<Default Extension="xml" ContentType="application/xml"/>\n'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.'
        'openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>\n'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/'
        'vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>\n'
        "</Types>"
    )


def _root_relationships_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
        'relationships">\n'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/'
        'officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/>\n'
        "</Relationships>"
    )


def _workbook_xml() -> str:
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="{SPREADSHEET_NS}" xmlns:r="{RELATIONSHIPS_NS}">
<sheets><sheet name="Payslips" sheetId="1" r:id="rId1"/></sheets>
<calcPr fullCalcOnLoad="1"/>
</workbook>"""


def _workbook_relationships_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
        'relationships">\n'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/'
        'officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/>\n'
        "</Relationships>"
    )


def _xml_document(element: Element) -> str:
    return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + tostring(
        element,
        encoding="unicode",
    )


def _payslip_table_lines(lines: list[str]) -> list[str]:
    for index, line in enumerate(lines[:-1]):
        if (
            re.fullmatch(r"Cost Centre \d{2}", line, re.IGNORECASE) is not None
            and lines[index + 1].casefold() == "pay item"
        ):
            return lines[index + 2 :]
    return lines


def _money_field(lines: list[str], labels: tuple[str, ...]) -> Decimal | None:
    for line in lines:
        for label in labels:
            match = re.match(
                rf"{re.escape(label)}\s*:?\s+({MONEY_PATTERN.pattern})(?:\s|$)",
                line,
                re.IGNORECASE,
            )
            if match is not None:
                return parse_money(match.group(1))
    return None


def _run_ocr_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, capture_output=True, text=True, check=False)
    except FileNotFoundError as error:
        raise RuntimeError(
            "Install OCRmyPDF before using OCR extraction. On macOS, try "
            "`brew install ocrmypdf`."
        ) from error
