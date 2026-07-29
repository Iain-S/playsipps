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
uv run sipps
```

The command uses a persistent browser profile at `.playwright/moorepay-profile`
so a successful login can be reused on later runs.

Save the payslips page HTML after navigation:

```sh
uv run sipps --save-html fixtures/moorepay/payslips.html
```

That saved HTML can be used to add fixture-backed selector tests without storing
credentials or session cookies.

By default, `sipps` waits up to 60 seconds for the payslip `View` buttons. If
Moorepay is unusually slow, increase the timeout:

```sh
uv run sipps --timeout-ms 120000
```

By default, the CLI processes all payslips. To limit a test run:

```sh
uv run sipps --limit 10
```

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
