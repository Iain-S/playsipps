# AGENTS.md

## Project Overview

This is a Python project using:

- `uv` for dependency and virtual environment management.
- `ruff` for linting and formatting.
- `ty` for type checking.
- `pytest` and `hypothesis` for tests.
- `playwright` for Moorepay browser automation.

## Common Commands

```sh
uv sync --all-groups
uv run ruff check .
uv run ruff format --check .
uv run ty check src tests
uv run pytest
```

## Moorepay Automation

- The live Moorepay flow is intentionally interactive; do not automate or store
  user credentials.
- Use `.playwright/moorepay-profile` for local browser session state.
- Use saved HTML fixtures for selector tests where possible.
- Keep fixture HTML free of secrets, cookies, tokens, and personal data.

## Development Notes

- Keep source code under `src/playsipps`.
- Keep tests under `tests`.
- Prefer typed functions and small modules with focused tests.
- Use Hypothesis for behavior that can be expressed as general properties.
- Do not commit generated virtual environments, caches, or build artifacts.
- Use test-driven development: write tests and confirm that they fail before getting them to pass and, if necessary, refactoring.
- For comments, write WHY, not WHAT. Skip `// increment counter` above `i++`. 

## Logging

- Structured JSON when logging for debugging / observability.
- Plain text only for user-facing CLI output.
