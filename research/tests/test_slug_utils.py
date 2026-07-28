"""Unit tests for slug_utils."""

from __future__ import annotations

import sys
from pathlib import Path

_RESEARCH_DIR = Path(__file__).resolve().parents[1]
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from slug_utils import (  # noqa: E402
    is_generic_company_slug,
    resolve_company_slug,
    slugify_company_name,
)


def test_slugify_company_name():
    assert slugify_company_name("Boston Dynamics") == "boston-dynamics"
    assert slugify_company_name("Figure AI, Inc.") == "figure-ai-inc"


def test_is_generic_company_slug():
    assert is_generic_company_slug("company-14")
    assert is_generic_company_slug("COMPANY-99")
    assert not is_generic_company_slug("boston-dynamics")
    assert is_generic_company_slug(None)
    assert is_generic_company_slug("")


def test_resolve_company_slug_from_generic():
    assert resolve_company_slug("Boston Dynamics", "company-14") == "boston-dynamics"


def test_resolve_company_slug_keeps_good_slug():
    assert resolve_company_slug("Boston Dynamics", "boston-dynamics") == "boston-dynamics"
