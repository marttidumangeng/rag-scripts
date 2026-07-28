"""Unit tests for REEMAN 1421 curated keep/reject sets."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parent / "fix_reeman_1421_robots.py"
_SPEC = importlib.util.spec_from_file_location("fix_reeman_1421_robots", _SCRIPT)
assert _SPEC and _SPEC.loader
_MOD = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MOD)


def test_inventory_partitions_all_34():
    keepers = set(_MOD.PRODUCTS)
    rejects = set(_MOD.REJECTS)
    assert len(keepers) == 22
    assert len(rejects) == 12
    assert keepers.isdisjoint(rejects)
    assert keepers | rejects == {
        2305, 2306, 2308, 2310, 2311, 2313, 2314, 2315, 2316, 2318, 2319,
        2320, 2322, 2324, 2326, 2327, 2329, 2330, 2332, 2334,
        4654, 4655, 4656, 4657, 4658, 4659, 4660, 4661, 4662, 4663, 4664, 4665,
        5082, 5083,
    }


def test_family_keys_use_reeman_prefix():
    for rid, data in _MOD.PRODUCTS.items():
        assert data["family_key"].startswith("reeman:"), rid
        assert data["family_name"]
        assert data["family_url"]
        assert "\n" in data["purpose"] or data["purpose"].count("\n") >= 1


def test_no_source_urls_in_prose():
    for rid, data in _MOD.PRODUCTS.items():
        for field in ("description", "features", "purpose"):
            text = data[field]
            assert "http://" not in text and "https://" not in text, (rid, field)


def test_approve_allowlist_requires_image():
    allow = set(_MOD.approve_allowlist())
    for rid in allow:
        assert _MOD.PRODUCTS[rid].get("image")
    for rid, data in _MOD.PRODUCTS.items():
        if not data.get("image"):
            assert rid not in allow
            assert data.get("image_todo")


def test_company_website_prefers_reemanbot():
    assert _MOD.COMPANY_WEBSITE == "https://reemanbot.com/"
