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
- After login, navigate directly to
  `https://app-spa.moorepay.co.uk/me/details/pay-details/payslips`.
- Avoid `networkidle` waits for Moorepay pages; background requests can keep the
  page from ever becoming idle.
- Wait for `View` buttons by polling with a timeout rather than using a short
  fixed sleep.
- Count `button:has-text('View')` on the SPA page. If Moorepay redirects to the
  wrapper app, fall back to `iframe#serviceProvider`.
- Use saved HTML fixtures for selector tests where possible.
- If the live count is zero, inspect `.playwright/debug/payslips-zero-view-buttons.html`.
- Keep fixture HTML free of secrets, cookies, tokens, and personal data.

## Development Notes

- Keep source code under `src/playsipps`.
- Keep tests under `tests`.
- Prefer typed functions and small modules with focused tests.
- Use Hypothesis for behavior that can be expressed as general properties.
- Do not commit generated virtual environments, caches, or build artifacts.
- Use test-driven development: write tests and confirm that they fail before getting them to pass and, if necessary, refactoring.
- For comments, write WHY, not WHAT. Skip `// increment counter` above `i++`.
- Never import annotations from __future__, there is no need.
- Type constants as Final.

## Logging

- Structured JSON when logging for debugging / observability.
- Plain text only for user-facing CLI output.
