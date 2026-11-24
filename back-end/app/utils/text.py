"""Shared checks for user-visible Vietnamese learning content."""

import unicodedata


def has_visible_text(value: str) -> bool:
    """Whitespace, formatting characters and combining marks alone are empty."""
    return any(
        not char.isspace() and unicodedata.category(char)[0] not in {"C", "M", "Z"}
        for char in value
    )
