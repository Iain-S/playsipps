# playsipps

Python project scaffold using `uv`, `pytest`, `hypothesis`, `ruff`, and `ty`.

## Requirements

- Python 3.14+
- uv

## Setup

```sh
uv venv
uv sync --all-groups
```

Install Playwright browser binaries for local Moorepay automation:

```sh
uv run playwright install chromium
```

## Development

Run tests:

```sh
uv run pytest
```

## Moorepay Automation

Open Moorepay, complete login interactively, go directly to the payslips SPA,
count the `View` buttons, process the payslips in parallel, download each PDF to
`downloads/`, and print the sorted Period values:

```sh
uv run sipps download
```

The command uses a persistent browser profile at `.playwright/moorepay-profile`
so a successful login can be reused on later runs.

Save the payslips page HTML after navigation:

```sh
uv run sipps download --save-html fixtures/moorepay/payslips.html
uv run sipps download -s fixtures/moorepay/payslips.html
```

That saved HTML can be used to add fixture-backed selector tests without storing
credentials or session cookies.

By default, `sipps` waits up to 60 seconds for the payslip `View` buttons. If
Moorepay is unusually slow, increase the timeout:

```sh
uv run sipps download --timeout-ms 120000
uv run sipps download -t 120000
```

By default, the CLI processes all payslips. To limit a test run:

```sh
uv run sipps download --limit 10
uv run sipps download -l 10
```

Extract fields from the downloaded PDF files and write them to CSV plus an XLSX
workbook with validation formulas:

```sh
uv run sipps extract --downloads-dir downloads --output payslips.csv
uv run sipps extract -d downloads -o payslips.csv
```

The workbook defaults to `payslips.xlsx`. Set its path explicitly:

```sh
uv run sipps extract --downloads-dir downloads --spreadsheet payslips.xlsx
uv run sipps extract -d downloads -x payslips.xlsx
```

The spreadsheet checks that tax, NI, pension, and net pay add up to gross pay.

The extract command uses OCRmyPDF by default. It can also dump the extracted PDF
text to one `.txt` file per payslip while still writing the CSV and XLSX output:

```sh
uv run sipps extract --downloads-dir downloads --dump-text extracted-text
uv run sipps extract -d downloads -t extracted-text
```

To bypass OCR and use embedded PDF text extraction:

```sh
uv run sipps extract --downloads-dir downloads --output payslips.csv --no-ocr
uv run sipps extract -d downloads -o payslips.csv -n
```

Review and replace private details before committing any text fixtures.

Run linting:

```sh
uv run ruff check .
uv run ruff format --check .
```

Run type checking:

```sh
uv run ty check src tests
```

Run all checks:

```sh
uv run ruff check .
uv run ruff format --check .
uv run ty check src tests
uv run pytest
```
