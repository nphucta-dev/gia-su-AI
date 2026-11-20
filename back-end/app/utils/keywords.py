"""Shared keyword rules for deterministic Vietnamese text retrieval."""

from collections import Counter
import re
import unicodedata


MAX_QUERY_LENGTH = 400
MAX_QUERY_TERMS = 20
WORD = re.compile(r"[^\W_]+", re.UNICODE)


def fold_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold().replace("đ", "d")
    return "".join(char for char in unicodedata.normalize("NFD", normalized) if unicodedata.category(char) != "Mn")


def text_terms(value: str) -> list[str]:
    return WORD.findall(fold_text(value))


def parse_query(value: str) -> tuple[str, tuple[str, ...]]:
    if not isinstance(value, str) or len(value) > MAX_QUERY_LENGTH:
        raise ValueError("Invalid search query")
    if any(unicodedata.category(char) in {"Cc", "Cs"} and char not in "\n\r\t" for char in value):
        raise ValueError("Invalid search query")
    cleaned = unicodedata.normalize("NFC", " ".join(value.split()))
    terms = tuple(dict.fromkeys(text_terms(cleaned)))
    if not terms or len(terms) > MAX_QUERY_TERMS:
        raise ValueError("Search requires between one and twenty keywords")
    return cleaned, terms


def keyword_score(content: str, terms: tuple[str, ...]) -> tuple[int, int]:
    counts = Counter(text_terms(content))
    return sum(term in counts for term in terms), sum(counts[term] for term in terms)


def literal_contains_pattern(term: str) -> str:
    # Bound SQL parameters still require escaping LIKE's pattern metacharacters.
    return "%" + term.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"
