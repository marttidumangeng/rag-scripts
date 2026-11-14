"""Evidence checks for sales_status findings.

A sales status is only kept when the model's "verbatim" quote really appears
in text we fetched, and its source URL is one of the pages that text came
from. LLM extractors paraphrase and invent; the prompt rule alone is not a
guarantee (discover_robots already documents invented release years).
"""
from __future__ import annotations

import re
from typing import Iterable
from urllib.parse import urlsplit

ASSESSABLE_SALES_STATUSES = frozenset({
    "not_for_sale",
    "pre_order",
    "limited_availability",
    "general_sale",
    "made_to_order",
})

# Quotes shorter than this match too much by accident ("Buy", "Order now").
MIN_QUOTE_CHARS = 12

_QUOTE_CHARS = str.maketrans({
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", " ": " ",
})


def _norm_text(text: str) -> str:
    text = (text or "").translate(_QUOTE_CHARS).lower()
    return re.sub(r"\s+", " ", text).strip()


def _norm_quote(quote: str) -> str:
    # Models wrap quotes in quote marks and trailing ellipses; drop those.
    return _norm_text(quote).strip(" \"'.…")


def _norm_url(url: str) -> str:
    parts = urlsplit((url or "").strip())
    host = parts.netloc.lower().removeprefix("www.")
    return f"{host}{parts.path.rstrip('/')}"


def quote_in_text(quote: str, text: str) -> bool:
    """True when the normalized quote is a substring of the normalized text."""
    q = _norm_quote(quote)
    return len(q) >= MIN_QUOTE_CHARS and q in _norm_text(text)


def verify_sales_evidence(
    key: str,
    quote: str,
    source_url: str,
    pages: Iterable[tuple[str, str]],
) -> tuple[bool, str]:
    """Check one finding against fetched ``(url, text)`` pages.

    Returns ``(ok, reason)``. ok means: key is assessable, the quote appears
    in a fetched page, and source_url is the page it appears in.
    """
    if key not in ASSESSABLE_SALES_STATUSES:
        return False, "status not in allowed set"
    if not (quote or "").strip():
        return False, "missing verbatim quote"
    if not (source_url or "").strip():
        return False, "missing source URL"
    pages = [(u, t) for u, t in pages if u or t]
    containing = [u for u, t in pages if quote_in_text(quote, t)]
    if not containing:
        return False, "quote not found in fetched page text"
    if _norm_url(source_url) not in {_norm_url(u) for u in containing}:
        return False, "source URL is not the page that contains the quote"
    return True, ""
