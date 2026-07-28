"""Tests for product_url_search."""

from __future__ import annotations

import sys
from pathlib import Path

_RESEARCH_DIR = Path(__file__).resolve().parents[1]
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from product_url_search import (  # noqa: E402
    _pick_best,
    _score_candidate,
    is_weak_product_url,
)
from web_extract import robot_name_tokens


def test_is_weak_product_url_detects_catalog_and_tel():
    tokens = robot_name_tokens("iER8-720-MI-C", "iER8-720-MI-C")
    website = "https://www.estun.com"
    assert is_weak_product_url("https://www.estun.com/solute/", website, tokens)
    assert is_weak_product_url("https://www.estun.com/tel:400-025-3336", website, tokens)
    assert not is_weak_product_url("https://www.estun.com/gjjjqr/356.html", website, tokens)


def test_score_candidate_prefers_model_in_title():
    tokens = robot_name_tokens("iER8-720-MI-C", "iER8-720-MI-C")
    estun_page = _score_candidate(
        "https://www.estun.com/gjjjqr/356.html",
        tokens,
        title="iER8-720-MI-C collaborative robot",
        snippet="Estun industrial robot",
        company_netloc="estun.com",
    )
    catalog = _score_candidate(
        "https://www.estun.com/solute/",
        tokens,
        title="Robot catalog",
        snippet="All robots",
        company_netloc="estun.com",
    )
    assert estun_page > catalog


def test_pick_best_returns_estun_product_page():
    tokens = robot_name_tokens("iER8-720-MI-C", "iER8-720-MI-C")
    candidates = [
        ("https://www.estun.com/solute/", "Catalog", ""),
        ("https://www.estun.com/gjjjqr/356.html", "iER8-720-MI-C", "product page"),
    ]
    assert _pick_best(candidates, tokens, "estun.com") == "https://www.estun.com/gjjjqr/356.html"


def test_pick_best_opaque_url_with_model_in_page_markdown():
    tokens = robot_name_tokens("iER8-720-MI-C", "iER8-720-MI-C")
    markdown = "# iER8-720-MI-C\nCollaborative robot specifications for cleanroom use."
    candidates = [
        ("https://www.estun.com/gjjjqr/356.html", "Estun robot", markdown),
    ]
    assert _pick_best(candidates, tokens, "estun.com") == "https://www.estun.com/gjjjqr/356.html"
