from hypothesis import given
from hypothesis import strategies as st

from playsipps import normalize_name


@given(st.text())
def test_normalize_name_is_idempotent(name: str) -> None:
    normalized = normalize_name(name)

    assert normalize_name(normalized) == normalized


@given(st.lists(st.text(min_size=1), min_size=1))
def test_normalize_name_preserves_non_whitespace_tokens(parts: list[str]) -> None:
    raw = " \t\n ".join(parts)

    assert normalize_name(raw).split() == raw.split()
