from __future__ import annotations

import builtins
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import cast

import pytest
from hypothesis import given
from hypothesis import strategies as st

import playsipps.moorepay as moorepay
from playsipps.moorepay import (
    DEFAULT_TIMEOUT_MS,
    count_payslip_view_buttons,
    iframe_payslip_view_buttons,
    main,
    navigate_to_payslips,
    open_login,
    parse_args,
    payslip_view_buttons,
    run,
    save_html,
    view_each_payslip,
    wait_for_payslip_view_buttons,
)

MOOREPAY_VIEW_BUTTON_HTML = """
<button type="button"
        class="button is-secondary is-fullwidth button v-button is-raised
               is-secondary is-fullwidth"
        aria-hidden="false"><span> View </span></button>
"""


@dataclass
class ParsedButton:
    attrs: dict[str, str]
    text: str


class ButtonParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.buttons: list[ParsedButton] = []
        self._active_attrs: dict[str, str] | None = None
        self._active_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "button":
            self._active_attrs = {key: value or "" for key, value in attrs}
            self._active_text = []

    def handle_data(self, data: str) -> None:
        if self._active_attrs is not None:
            self._active_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "button" and self._active_attrs is not None:
            self.buttons.append(
                ParsedButton(
                    attrs=self._active_attrs,
                    text=" ".join("".join(self._active_text).split()),
                )
            )
            self._active_attrs = None
            self._active_text = []


@dataclass
class FakePage:
    view_count: int = 0
    iframe_view_count: int = 0
    count_after_timeouts: int | None = None
    clicks: list[tuple[str, str | None, int | None]] = field(default_factory=list)
    gotos: list[str] = field(default_factory=list)
    backs: int = 0
    load_states: list[str] = field(default_factory=list)
    selectors: list[str] = field(default_factory=list)
    frame_selectors: list[str] = field(default_factory=list)
    timeouts: list[float] = field(default_factory=list)

    def goto(self, url: str, **kwargs: object) -> None:
        self.gotos.append(url)

    def wait_for_load_state(self, state: str = "load") -> None:
        self.load_states.append(state)

    def wait_for_timeout(self, timeout: float) -> None:
        self.timeouts.append(timeout)
        if (
            self.count_after_timeouts is not None
            and len(self.timeouts) >= self.count_after_timeouts
        ):
            self.view_count = 3

    def locator(self, selector: str) -> FakeLocator:
        self.selectors.append(selector)
        return FakeLocator(
            page=self,
            role="css",
            name=selector,
            count_value=self.view_count,
        )

    def frame_locator(self, selector: str) -> FakeFrameLocator:
        self.frame_selectors.append(selector)
        return FakeFrameLocator(page=self, selector=selector)

    def get_by_role(self, role: str, *, name: str | None = None) -> FakeLocator:
        return FakeLocator(page=self, role=role, name=name)

    def go_back(self) -> None:
        self.backs += 1

    def content(self) -> str:
        return "<html></html>"


@dataclass
class FakeLocator:
    page: FakePage
    role: str
    name: str | None
    count_value: int = 0
    index: int | None = None

    def get_by_role(self, role: str, *, name: str) -> FakeLocator:
        return FakeLocator(page=self.page, role=role, name=name)

    def click(self) -> None:
        self.page.clicks.append((self.role, self.name, self.index))

    def count(self) -> int:
        return self.count_value

    def nth(self, index: int) -> FakeLocator:
        return FakeLocator(
            page=self.page,
            role=self.role,
            name=self.name,
            count_value=self.count_value,
            index=index,
        )

    def evaluate_all(self, expression: str) -> list[str]:
        return []


@dataclass
class FakeFrameLocator:
    page: FakePage
    selector: str

    def locator(self, selector: str) -> FakeLocator:
        self.page.selectors.append(selector)
        return FakeLocator(
            page=self.page,
            role="frame-css",
            name=selector,
            count_value=self.page.iframe_view_count,
        )


def test_navigate_to_payslips_opens_direct_spa_url() -> None:
    page = FakePage()

    navigate_to_payslips(page)

    assert page.gotos == [
        "https://app-spa.moorepay.co.uk/me/details/pay-details/payslips"
    ]
    assert page.clicks == []
    assert page.load_states == []
    assert page.timeouts == []


def test_open_login_opens_idp_login_url() -> None:
    page = FakePage()

    open_login(page)

    assert page.gotos == [
        "https://app.moorepay.co.uk/Account/Login?Idp=THEALANTURINGINSTITUTE"
    ]


@given(st.integers(min_value=1, max_value=20))
def test_count_payslip_view_buttons_returns_view_button_count(view_count: int) -> None:
    page = FakePage(view_count=view_count)

    assert count_payslip_view_buttons(page) == view_count
    assert page.selectors == ["button:has-text('View')"]
    assert page.clicks == []
    assert page.backs == 0


def test_count_payslip_view_buttons_returns_zero_when_no_buttons_exist() -> None:
    page = FakePage()

    assert count_payslip_view_buttons(page) == 0
    assert page.frame_selectors == ["iframe#serviceProvider"]
    assert page.selectors == [
        "button:has-text('View')",
        "button:has-text('View')",
    ]


def test_wait_for_payslip_view_buttons_returns_immediately_when_loaded() -> None:
    page = FakePage(view_count=4)

    assert wait_for_payslip_view_buttons(page, timeout_ms=5_000) == 4
    assert page.timeouts == []


def test_wait_for_payslip_view_buttons_polls_until_buttons_render() -> None:
    page = FakePage(count_after_timeouts=2)

    assert (
        wait_for_payslip_view_buttons(
            page,
            timeout_ms=5_000,
            poll_interval_ms=250,
        )
        == 3
    )
    assert page.timeouts == [250, 250]


def test_wait_for_payslip_view_buttons_returns_zero_after_timeout() -> None:
    page = FakePage()

    assert (
        wait_for_payslip_view_buttons(
            page,
            timeout_ms=1_000,
            poll_interval_ms=500,
        )
        == 0
    )
    assert page.timeouts == [500, 500]


@given(st.integers(min_value=1, max_value=20))
def test_count_payslip_view_buttons_falls_back_to_wrapper_iframe(
    iframe_view_count: int,
) -> None:
    page = FakePage(iframe_view_count=iframe_view_count)

    assert count_payslip_view_buttons(page) == iframe_view_count
    assert page.frame_selectors == ["iframe#serviceProvider"]
    assert page.selectors == [
        "button:has-text('View')",
        "button:has-text('View')",
    ]


def test_payslip_view_buttons_match_direct_spa_button_markup() -> None:
    page = FakePage(view_count=1)

    locator = cast(FakeLocator, payslip_view_buttons(page))

    assert locator.role == "css"
    assert locator.name == "button:has-text('View')"


def test_iframe_payslip_view_buttons_match_wrapper_page_markup() -> None:
    page = FakePage(view_count=1)

    locator = cast(FakeLocator, iframe_payslip_view_buttons(page))

    assert locator.role == "frame-css"
    assert locator.name == "button:has-text('View')"


def test_moorepay_view_button_html_matches_expected_accessible_control() -> None:
    parser = ButtonParser()

    parser.feed(MOOREPAY_VIEW_BUTTON_HTML)

    assert len(parser.buttons) == 1
    assert parser.buttons[0].attrs["type"] == "button"
    assert parser.buttons[0].attrs["aria-hidden"] == "false"
    assert parser.buttons[0].text == "View"


def test_save_html_writes_current_page_content(tmp_path: Path) -> None:
    page = FakePage()
    path = tmp_path / "nested" / "page.html"

    save_html(page, path)

    assert path.read_text(encoding="utf-8") == "<html></html>"


@given(st.integers(min_value=0, max_value=5))
def test_view_each_payslip_clicks_each_view_when_hrefs_are_unavailable(
    view_count: int,
) -> None:
    page = FakePage(view_count=view_count)

    viewed = view_each_payslip(page)

    assert viewed == view_count
    assert page.backs == view_count
    assert page.clicks == [
        ("css", "button:has-text('View')", index) for index in range(view_count)
    ]


def test_parse_args_uses_cli_defaults() -> None:
    args = parse_args([])

    assert args.headless is False
    assert args.profile_dir == Path(".playwright/moorepay-profile")
    assert args.save_html is None
    assert args.skip_login_prompt is False
    assert args.timeout_ms == DEFAULT_TIMEOUT_MS


def test_parse_args_accepts_all_options(tmp_path: Path) -> None:
    profile_dir = tmp_path / "profile"
    save_html_path = tmp_path / "page.html"

    args = parse_args(
        [
            "--headless",
            "--profile-dir",
            str(profile_dir),
            "--save-html",
            str(save_html_path),
            "--skip-login-prompt",
            "--timeout-ms",
            "1234",
        ]
    )

    assert args.headless is True
    assert args.profile_dir == profile_dir
    assert args.save_html == save_html_path
    assert args.skip_login_prompt is True
    assert args.timeout_ms == 1234


@dataclass
class FakeContext:
    page: FakePage
    pages: list[FakePage]
    closed: bool = False
    new_page_called: bool = False

    def new_page(self) -> FakePage:
        self.new_page_called = True
        return self.page

    def close(self) -> None:
        self.closed = True


@dataclass
class FakeChromium:
    context: FakeContext
    launch_args: dict[str, object] = field(default_factory=dict)

    def launch_persistent_context(
        self,
        *,
        user_data_dir: Path,
        headless: bool,
    ) -> FakeContext:
        self.launch_args = {
            "user_data_dir": user_data_dir,
            "headless": headless,
        }
        return self.context


@dataclass
class FakePlaywright:
    chromium: FakeChromium


@dataclass
class FakeSyncPlaywright:
    playwright: FakePlaywright

    def __enter__(self) -> FakePlaywright:
        return self.playwright

    def __exit__(
        self,
        exc_type: object,
        exc_value: object,
        traceback: object,
    ) -> None:
        return None


def install_fake_playwright(
    monkeypatch: pytest.MonkeyPatch,
    context: FakeContext,
) -> FakeChromium:
    chromium = FakeChromium(context=context)
    fake_sync_playwright = FakeSyncPlaywright(
        playwright=FakePlaywright(chromium=chromium)
    )

    monkeypatch.setattr(
        "playwright.sync_api.sync_playwright",
        lambda: fake_sync_playwright,
    )
    return chromium


def test_run_counts_buttons_with_existing_browser_page(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    page = FakePage(view_count=2)
    context = FakeContext(page=page, pages=[page])
    chromium = install_fake_playwright(monkeypatch, context)
    save_html_path = tmp_path / "payslips.html"
    profile_dir = tmp_path / "profile"

    viewed = run(
        headless=True,
        profile_dir=profile_dir,
        save_html_path=save_html_path,
        skip_login_prompt=True,
        timeout_ms=5_000,
    )

    assert viewed == 2
    assert page.gotos == [
        "https://app.moorepay.co.uk/Account/Login?Idp=THEALANTURINGINSTITUTE",
        "https://app-spa.moorepay.co.uk/me/details/pay-details/payslips",
    ]
    assert save_html_path.read_text(encoding="utf-8") == "<html></html>"
    assert context.closed is True
    assert context.new_page_called is False
    assert chromium.launch_args == {
        "user_data_dir": profile_dir,
        "headless": True,
    }


def test_run_prompts_creates_page_and_saves_debug_html_on_zero_count(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    page = FakePage()
    context = FakeContext(page=page, pages=[])
    install_fake_playwright(monkeypatch, context)
    prompts: list[str] = []
    debug_html_path = tmp_path / "debug.html"

    def fake_input(prompt: str) -> str:
        prompts.append(prompt)
        return ""

    monkeypatch.setattr(builtins, "input", fake_input)
    monkeypatch.setattr(moorepay, "ZERO_COUNT_DEBUG_HTML", debug_html_path)

    viewed = run(
        headless=False,
        profile_dir=tmp_path / "profile",
        save_html_path=None,
        skip_login_prompt=False,
        timeout_ms=0,
    )

    assert viewed == 0
    assert prompts == ["Complete login in the browser, then press Enter here: "]
    assert context.closed is True
    assert context.new_page_called is True
    assert debug_html_path.read_text(encoding="utf-8") == "<html></html>"
    assert f"Saved debug HTML to {debug_html_path}" in capsys.readouterr().out


def test_main_prints_view_button_count(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_calls: list[dict[str, object]] = []

    def fake_run(**kwargs: object) -> int:
        run_calls.append(kwargs)
        return 7

    monkeypatch.setattr(moorepay, "run", fake_run)

    main(
        [
            "--headless",
            "--profile-dir",
            str(tmp_path / "profile"),
            "--save-html",
            str(tmp_path / "page.html"),
            "--skip-login-prompt",
            "--timeout-ms",
            "999",
        ]
    )

    assert run_calls == [
        {
            "headless": True,
            "profile_dir": tmp_path / "profile",
            "save_html_path": tmp_path / "page.html",
            "skip_login_prompt": True,
            "timeout_ms": 999,
        }
    ]
    assert capsys.readouterr().out == "Found 7 View button(s).\n"
