"""Smoke tests for the research-side image_confidence shim."""

from __future__ import annotations

import sys
from pathlib import Path

_RESEARCH_DIR = Path(__file__).resolve().parents[1]
_SERVER_DIR = _RESEARCH_DIR.parents[1] / "robotaigeek-server"
for path in (_RESEARCH_DIR, _SERVER_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from image_confidence import (  # noqa: E402
    CLASSIFIER_VERSION,
    build_candidate,
    confidence_level,
    score_source_authority,
)


def test_shim_reexports_core_helpers():
    assert score_source_authority("official_exact") == 25
    assert confidence_level(40) == "reject"
    assert CLASSIFIER_VERSION == "image-confidence-v1"


def test_shim_build_candidate_reject_for_search_host():
    candidate = build_candidate(
        url="https://www.google.com/images/branding/product/1x/googlelogo.png",
        source_page_url="",
    )
    assert candidate["confidence_level"] == "reject"
