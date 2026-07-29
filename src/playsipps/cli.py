"""Command line interface for playsipps."""

import argparse
from collections.abc import Iterable
from pathlib import Path
from typing import Final

from tqdm import tqdm

import playsipps.moorepay as moorepay
from playsipps.extract import (
    DEFAULT_CSV_PATH,
    DEFAULT_SPREADSHEET_PATH,
    DOWNLOADS_DIR,
    PayslipFields,
    dump_pdf_texts,
    extract_payslips,
    ocr_pdf_text,
    parse_payslip_text,
    read_pdf_text,
    write_payslips_csv,
    write_payslips_xlsx,
)

DOWNLOAD_COMMAND: Final = "download"
EXTRACT_COMMAND: Final = "extract"


def main(argv: list[str] | None = None) -> None:
    """Run the playsipps CLI."""
    args = parse_args(argv)
    if args.command == DOWNLOAD_COMMAND:
        run_download(args)
        return
    run_extract(args)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse top-level CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    download_parser = subparsers.add_parser(
        DOWNLOAD_COMMAND,
        help="Download payslip PDFs from Moorepay.",
        description="Download payslip PDFs from Moorepay.",
    )
    moorepay.add_download_arguments(download_parser)

    extract_parser = subparsers.add_parser(
        EXTRACT_COMMAND,
        help="Extract downloaded payslip PDFs to CSV.",
        description="Extract downloaded payslip PDFs to CSV.",
    )
    add_extract_arguments(extract_parser)

    return parser.parse_args(argv)


def parse_extract_args(argv: list[str]) -> argparse.Namespace:
    """Parse arguments for the extract subcommand."""
    parser = argparse.ArgumentParser(description="Extract payslip PDFs to CSV.")
    add_extract_arguments(parser)
    return parser.parse_args(argv)


def add_extract_arguments(parser: argparse.ArgumentParser) -> None:
    """Add extract arguments to an argparse parser."""
    parser.add_argument(
        "-d",
        "--downloads-dir",
        type=Path,
        default=DOWNLOADS_DIR,
        help="Optional. Directory containing downloaded payslip PDFs. "
        f"Defaults to {DOWNLOADS_DIR}.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_CSV_PATH,
        help="Optional. CSV path to write extracted payslip fields to. "
        f"Defaults to {DEFAULT_CSV_PATH}.",
    )
    parser.add_argument(
        "-x",
        "--spreadsheet",
        type=Path,
        default=DEFAULT_SPREADSHEET_PATH,
        help="Optional. XLSX path to write extracted payslip fields and "
        f"validation formulas to. Defaults to {DEFAULT_SPREADSHEET_PATH}.",
    )
    parser.add_argument(
        "-t",
        "--dump-text",
        type=Path,
        dest="dump_text_dir",
        default=None,
        help="Optional. Directory to write extracted PDF text files to, "
        "in addition to writing CSV/XLSX output.",
    )
    ocr_group = parser.add_mutually_exclusive_group()
    ocr_group.add_argument(
        "-r",
        "--ocr",
        dest="ocr",
        action="store_true",
        default=True,
        help="Optional. Use OCRmyPDF to extract PDF text. Enabled by "
        "default. Mutually exclusive with --no-ocr.",
    )
    ocr_group.add_argument(
        "-n",
        "--no-ocr",
        dest="ocr",
        action="store_false",
        help="Optional. Use embedded PDF text extraction instead of "
        "OCRmyPDF. Mutually exclusive with --ocr.",
    )


def run_download(args: argparse.Namespace) -> None:
    """Run the Moorepay download flow from parsed CLI arguments."""
    periods = moorepay.run(
        headless=args.headless,
        profile_dir=args.profile_dir,
        save_html_path=args.save_html,
        skip_login_prompt=moorepay.effective_skip_login_prompt(
            headless=args.headless,
            skip_login_prompt=args.skip_login_prompt,
        ),
        timeout_ms=args.timeout_ms,
        limit=args.limit,
    )
    for period in periods:
        print(period)


def run_extract(args: argparse.Namespace) -> None:
    """Extract payslip PDFs and write the CSV output."""
    text_reader = ocr_pdf_text if args.ocr else read_pdf_text
    rows: list[PayslipFields]
    if args.dump_text_dir is not None:
        paths = dump_pdf_texts(
            args.downloads_dir,
            args.dump_text_dir,
            text_reader=text_reader,
            progress=extract_progress,
        )
        print(f"Wrote {text_file_count_message(len(paths))} to {args.dump_text_dir}")
        rows = rows_from_text_paths(paths)
    else:
        rows = extract_payslips(
            args.downloads_dir,
            text_reader=text_reader,
            progress=extract_progress,
        )
    write_payslips_csv(rows, args.output)
    write_payslips_xlsx(rows, args.spreadsheet)
    print(
        f"Wrote {row_count_message(len(rows))} to {args.output} and {args.spreadsheet}"
    )


def row_count_message(count: int) -> str:
    """Return a grammatically correct payslip row count."""
    suffix = "row" if count == 1 else "rows"
    return f"{count} payslip {suffix}"


def text_file_count_message(count: int) -> str:
    """Return a grammatically correct extracted text file count."""
    suffix = "file" if count == 1 else "files"
    return f"{count} text {suffix}"


def rows_from_text_paths(paths: Iterable[Path]) -> list[PayslipFields]:
    """Parse payslip rows from dumped text files."""
    return [
        parse_payslip_text(
            Path(f"{path.stem}.pdf"),
            path.read_text(encoding="utf-8"),
        )
        for path in paths
    ]


def extract_progress(paths: list[Path]) -> Iterable[Path]:
    """Show PDF extraction progress on stderr."""
    return tqdm(paths, desc="Processing PDFs", unit="pdf")
