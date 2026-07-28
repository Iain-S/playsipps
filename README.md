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

## Development

Run tests:

```sh
uv run pytest
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
