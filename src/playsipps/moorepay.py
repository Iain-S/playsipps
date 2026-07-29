"""Playwright automation for retrieving Moorepay payslips."""

import argparse
from collections.abc import Iterable
from multiprocessing import Pool
from pathlib import Path
from typing import Final, Protocol, cast

from tqdm import tqdm

LOGIN_URL: Final = "https://app.moorepay.co.uk/Account/Login?Idp=THEALANTURINGINSTITUTE"
PAYSLIPS_URL: Final = "https://app-spa.moorepay.co.uk/me/details/pay-details/payslips"
DEFAULT_TIMEOUT_MS: Final = 60_000
POLL_INTERVAL_MS: Final = 500
DOWNLOADS_DIR: Final = Path("downloads")
STORAGE_STATE_PATH: Final = Path(".playwright/moorepay-storage-state.json")
ZERO_COUNT_DEBUG_HTML: Final = Path(".playwright/debug/payslips-zero-view-buttons.html")


class LocatorLike(Protocol):
    def get_by_role(self, role: str, *, name: str) -> LocatorLike:
        """Return a child locator by accessible role and name."""
        ...

    def click(self) -> None:
        """Click the located element."""
        ...

    def count(self) -> int:
        """Return the number of matched elements."""
        ...

    def nth(self, index: int) -> LocatorLike:
        """Return the matched element at the given index."""
        ...

    def evaluate_all(self, expression: str) -> list[str]:
        """Evaluate JavaScript over all matched elements."""
        ...

    def text_content(self, **kwargs: object) -> str | None:
        """Return the matched element text content."""
        ...


class DownloadLike(Protocol):
    @property
    def suggested_filename(self) -> str:
        """Return the browser-suggested filename for the download."""
        ...

    def save_as(self, path: str | Path) -> None:
        """Save the download to the given path."""
        ...


class DownloadInfoLike(Protocol):
    @property
    def value(self) -> DownloadLike:
        """Return the completed download."""
        ...

    def __enter__(self) -> DownloadInfoLike:
        """Enter the download expectation context."""
        ...

    def __exit__(
        self,
        exc_type: object,
        exc_value: object,
        traceback: object,
    ) -> None:
        """Exit the download expectation context."""
        ...


class FrameLocatorLike(Protocol):
    def locator(self, selector: str) -> LocatorLike:
        """Return a locator inside the matched frame."""
        ...


class PageLike(Protocol):
    def goto(self, url: str, **kwargs: object) -> object:
        """Navigate the page to a URL."""
        ...

    def wait_for_load_state(self, state: str = "load") -> None:
        """Wait for the page to reach a load state."""
        ...

    def wait_for_timeout(self, timeout: float) -> None:
        """Wait for a fixed number of milliseconds."""
        ...

    def locator(self, selector: str) -> LocatorLike:
        """Return a locator for a CSS or Playwright selector."""
        ...

    def frame_locator(self, selector: str) -> FrameLocatorLike:
        """Return a locator for an iframe."""
        ...

    def get_by_role(self, role: str, *, name: str | None = None) -> LocatorLike:
        """Return a locator by accessible role and optional name."""
        ...

    def expect_download(self) -> DownloadInfoLike:
        """Return a context manager that waits for the next download."""
        ...

    def go_back(self) -> object:
        """Navigate back in browser history."""
        ...

    def content(self) -> str:
        """Return the current page HTML."""
        ...


class DownloadProgress(Protocol):
    def __call__(self, periods: Iterable[str], *, total: int) -> Iterable[str]:
        """Show progress while payslip download periods are produced."""
        ...


def open_login(page: PageLike, login_url: str = LOGIN_URL) -> None:
    """Open the Moorepay login URL and allow Playwright to follow redirects."""
    page.goto(login_url, wait_until="domcontentloaded")


def navigate_to_payslips(
    page: PageLike,
    payslips_url: str = PAYSLIPS_URL,
) -> None:
    """Navigate from an authenticated browser session to payslips."""
    page.goto(payslips_url, wait_until="domcontentloaded")


def payslip_view_buttons(page: PageLike) -> LocatorLike:
    """Return Moorepay payslip View buttons."""
    return page.locator("button:has-text('View')")


def iframe_payslip_view_buttons(page: PageLike) -> LocatorLike:
    """Return Moorepay payslip View buttons from the wrapper iframe."""
    return page.frame_locator("iframe#serviceProvider").locator(
        "button:has-text('View')"
    )


def count_payslip_view_buttons(page: PageLike) -> int:
    """Count payslip View buttons in the main content area."""
    direct_count = payslip_view_buttons(page).count()
    if direct_count:
        return direct_count
    return iframe_payslip_view_buttons(page).count()


def payslip_period_cell(page: PageLike) -> LocatorLike:
    """Return the payslip detail table cell containing the Period value."""
    return page.locator("tbody tr:nth-child(2) td:nth-child(5)")


def payslip_download_button(page: PageLike) -> LocatorLike:
    """Return the payslip detail table button in the Download column."""
    return page.locator("tbody tr:nth-child(2) td:nth-child(6) button")


def extract_payslip_period(page: PageLike, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> str:
    """Extract the Period value from the currently open payslip detail view."""
    period = payslip_period_cell(page).text_content(timeout=timeout_ms)
    if period is None:
        raise RuntimeError("Could not find payslip period cell.")
    return " ".join(period.split())


def period_download_path(period: str, downloads_dir: Path | None = None) -> Path:
    """Return the local PDF path for a payslip period."""
    target_dir = DOWNLOADS_DIR if downloads_dir is None else downloads_dir
    safe_period = "-".join(period.split())
    return target_dir / f"{safe_period}.pdf"


def download_payslip_pdf(
    page: PageLike,
    period: str,
    downloads_dir: Path | None = None,
) -> Path:
    """Download the currently open payslip PDF and return its local path."""
    target_dir = DOWNLOADS_DIR if downloads_dir is None else downloads_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    destination = period_download_path(period, downloads_dir=target_dir)
    with page.expect_download() as download_info:
        payslip_download_button(page).click()
    download_info.value.save_as(destination)
    return destination


def wait_for_payslip_view_buttons(
    page: PageLike,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
    poll_interval_ms: int = POLL_INTERVAL_MS,
) -> int:
    """Wait for payslip View buttons to render and return their count."""
    elapsed_ms = 0
    while True:
        count = count_payslip_view_buttons(page)
        if count:
            return count
        if elapsed_ms >= timeout_ms:
            return 0
        page.wait_for_timeout(poll_interval_ms)
        elapsed_ms += poll_interval_ms


def view_indices(total: int, limit: int | None) -> list[int]:
    """Return the payslip View indices to process."""
    if limit is None:
        return list(range(total))
    return list(range(min(total, limit)))


def payslip_period_for_view_index(index: int) -> str:
    """Open the nth payslip, download its PDF, and return its Period."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(STORAGE_STATE_PATH))
        page = cast(PageLike, context.new_page())

        navigate_to_payslips(page)
        wait_for_payslip_view_buttons(page)
        payslip_view_buttons(page).nth(index).click()
        period = extract_payslip_period(page)
        download_payslip_pdf(page, period)

        context.close()
        browser.close()
        return period


def sorted_payslip_periods(
    indices: list[int],
    *,
    progress: DownloadProgress | None = None,
) -> list[str]:
    """Fetch payslip periods in parallel and return them sorted."""
    progress_reporter = tqdm_downloads if progress is None else progress
    with Pool() as pool:
        periods = pool.imap_unordered(payslip_period_for_view_index, indices)
        return sorted(progress_reporter(periods, total=len(indices)))


def tqdm_downloads(periods: Iterable[str], *, total: int) -> Iterable[str]:
    """Show payslip download progress on stderr."""
    return tqdm(periods, total=total, desc="Downloading payslips", unit="pdf")


def view_each_payslip(page: PageLike) -> int:
    """Open every payslip view button."""
    total = count_payslip_view_buttons(page)
    for index in range(total):
        payslip_view_buttons(page).nth(index).click()
        page.wait_for_load_state("domcontentloaded")
        page.go_back()
        page.wait_for_load_state("domcontentloaded")
    return total


def save_html(page: PageLike, path: Path) -> None:
    """Save the current page HTML for fixture-backed tests."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page.content(), encoding="utf-8")


def run(
    *,
    headless: bool,
    profile_dir: Path,
    save_html_path: Path | None,
    skip_login_prompt: bool,
    timeout_ms: int,
    limit: int | None,
) -> list[str]:
    """Run the Moorepay browser flow and return sorted payslip periods."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=profile_dir,
            headless=headless,
        )
        page = cast(PageLike, context.pages[0] if context.pages else context.new_page())

        open_login(page)
        if not effective_skip_login_prompt(
            headless=headless,
            skip_login_prompt=skip_login_prompt,
        ):
            input("Complete login in the browser, then press Enter here: ")

        navigate_to_payslips(page)
        if save_html_path is not None:
            save_html(page, save_html_path)

        viewed = wait_for_payslip_view_buttons(page, timeout_ms=timeout_ms)
        if viewed == 0:
            save_html(page, ZERO_COUNT_DEBUG_HTML)
            print(f"Saved debug HTML to {ZERO_COUNT_DEBUG_HTML}")
            context.close()
            return []
        STORAGE_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        context.storage_state(path=str(STORAGE_STATE_PATH))
        context.close()

    return sorted_payslip_periods(view_indices(viewed, limit))


def effective_skip_login_prompt(*, headless: bool, skip_login_prompt: bool) -> bool:
    """Return whether the login prompt should be skipped."""
    return headless or skip_login_prompt


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments for the Moorepay automation CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    add_download_arguments(parser)
    return parser.parse_args(argv)


def add_download_arguments(parser: argparse.ArgumentParser) -> None:
    """Add Moorepay download arguments to an argparse parser."""
    parser.add_argument(
        "-H",
        "--headless",
        action="store_true",
        help="Run without showing a browser window.",
    )
    parser.add_argument(
        "-p",
        "--profile-dir",
        type=Path,
        default=Path(".playwright/moorepay-profile"),
        help="Persistent Playwright profile directory for Moorepay login state.",
    )
    parser.add_argument(
        "-s",
        "--save-html",
        type=Path,
        help="Save the payslips page HTML after navigation.",
    )
    parser.add_argument(
        "-k",
        "--skip-login-prompt",
        action="store_true",
        help="Do not pause for manual login before navigating.",
    )
    parser.add_argument(
        "-t",
        "--timeout-ms",
        type=int,
        default=DEFAULT_TIMEOUT_MS,
        help="Milliseconds to wait for payslip View buttons.",
    )
    parser.add_argument(
        "-l",
        "--limit",
        type=int,
        help="Maximum number of payslips to submit to worker processes.",
    )


def main(argv: list[str] | None = None) -> None:
    """Run the CLI using provided arguments or the process arguments."""
    args = parse_args(argv)
    periods = run(
        headless=args.headless,
        profile_dir=args.profile_dir,
        save_html_path=args.save_html,
        skip_login_prompt=effective_skip_login_prompt(
            headless=args.headless,
            skip_login_prompt=args.skip_login_prompt,
        ),
        timeout_ms=args.timeout_ms,
        limit=args.limit,
    )
    for period in periods:
        print(period)


if __name__ == "__main__":
    main()  # pragma: no cover
