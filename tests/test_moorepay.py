from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import cast

from hypothesis import given
from hypothesis import strategies as st

from playsipps.moorepay import (
    count_payslip_view_buttons,
    iframe_payslip_view_buttons,
    navigate_to_payslips,
    payslip_view_buttons,
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
