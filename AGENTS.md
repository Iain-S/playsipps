# AGENTS.md

## Project Overview

This is a Python project using:

- `uv` for dependency and virtual environment management.
- `ruff` for linting and formatting.
- `ty` for type checking.
- `pytest` and `hypothesis` for tests.

## Common Commands

```sh
uv sync --all-groups
uv run ruff check .
uv run ruff format --check .
uv run ty check src tests
uv run pytest
```

## Development Notes

- Keep source code under `src/playsipps`.
- Keep tests under `tests`.
- Prefer typed functions and small modules with focused tests.
- Use Hypothesis for behavior that can be expressed as general properties.
- Do not commit generated virtual environments, caches, or build artifacts.
