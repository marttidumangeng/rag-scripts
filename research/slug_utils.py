"""Company slug helpers aligned with Django's slugify behavior."""

from __future__ import annotations

import re
import unicodedata

GENERIC_COMPANY_SLUG_RE = re.compile(r"^company-\d+$", re.IGNORECASE)


def slugify_company_name(name: str, *, max_length: int = 220) -> str:
    """ASCII slug from company name (same idea as django.utils.text.slugify)."""
    if not name or not str(name).strip():
        return ""
    value = str(name).strip()
    value = (
        unicodedata.normalize("NFKD", value)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    value = re.sub(r"[^\w\s-]", "", value, flags=re.UNICODE).strip().lower()
    value = re.sub(r"[-\s]+", "-", value)
    return value[:max_length].strip("-")


def is_generic_company_slug(slug: str | None) -> bool:
    """True for auto placeholders like company-14 (not derived from the name)."""
    if not slug:
        return True
    return bool(GENERIC_COMPANY_SLUG_RE.match(slug.strip()))


def resolve_company_slug(name: str, current_slug: str | None = None) -> str:
    """
    Slug to use for staging filenames and PATCH updates.
    Regenerates from name when current slug is missing or generic.
    """
    from_name = slugify_company_name(name)
    if from_name and is_generic_company_slug(current_slug):
        return from_name
    if current_slug and not is_generic_company_slug(current_slug):
        return slugify_company_name(current_slug) or from_name
    return from_name
