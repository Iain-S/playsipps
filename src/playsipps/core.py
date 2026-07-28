"""Core project functionality."""


def normalize_name(name: str) -> str:
    """Normalize display names by trimming and collapsing whitespace."""
    return " ".join(name.split())
