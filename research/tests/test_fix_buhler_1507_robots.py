"""Focused tests for Bühler Group company 1507 curated enrichment."""

from __future__ import annotations

import sys
from pathlib import Path

RESEARCH_DIR = Path(__file__).resolve().parents[1]
if str(RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(RESEARCH_DIR))

import fix_buhler_1507_robots as buhler


def test_pending_ids_match_stakeholder_list() -> None:
    assert set(buhler.PRODUCTS) == {
        5068,
        5069,
        5070,
        5071,
        5072,
        5073,
        5074,
        5075,
        5076,
        5077,
    }


def test_family_keys_and_scopes() -> None:
    assert buhler.PRODUCTS[5068]["family_key"] == "buhler:sortex-r500"
    assert buhler.PRODUCTS[5069]["family_key"] == "buhler:sortex-r500"
    assert buhler.PRODUCTS[5070]["family_key"] == "buhler:sortex-ai700"
    assert buhler.PRODUCTS[5071]["family_key"] == "buhler:sortex-h"
    assert buhler.PRODUCTS[5073]["family_key"] == "buhler:sortex-j"
    assert buhler.PRODUCTS[5074]["family_key"] == "buhler:sortex-s"
    assert buhler.PRODUCTS[5075]["family_key"] == "buhler:sortex-s"
    assert buhler.PRODUCTS[5076]["family_key"] == "buhler:sortex-a"
    assert buhler.PRODUCTS[5077]["family_key"] == "buhler:sortex-a"
    assert buhler.PRODUCTS[5072]["family_key"] == "buhler:spark"
    assert buhler.PRODUCTS[5068]["product_url_scope"] == "family"
    assert buhler.PRODUCTS[5070]["product_url_scope"] == "exact_variant"
    assert buhler.PRODUCTS[5072]["family_name"] == "SPARK Pro"


def test_r500_exact_brochure_specs() -> None:
    five = buhler.payload(5068)
    six = buhler.payload(5069)
    assert five["weight_kg"] == 1230.0
    assert six["weight_kg"] == 1270.0
    assert five["width_mm"] == six["width_mm"] == 2771.0
    assert five["length_mm"] == six["length_mm"] == 1342.0
    assert five["height_mm"] == six["height_mm"] == 2069.0
    # Public OEM render shows six chutes → keep on R500 6 only.
    assert five["image"] is None
    assert six["image"]
    assert "IMAGE TO-DO" in five["notes"]


def test_shared_module_dims_only_when_columns_agree() -> None:
    ai = buhler.payload(5070)
    assert ai["length_mm"] == 1776.0
    assert "weight_kg" not in ai
    assert "width_mm" not in ai

    crystal = buhler.payload(5074)
    ultra = buhler.payload(5075)
    assert crystal["height_mm"] == ultra["height_mm"] == 2060.0
    assert crystal["length_mm"] == ultra["length_mm"] == 1372.0
    assert "weight_kg" not in crystal

    glow = buhler.payload(5076)
    lumo = buhler.payload(5077)
    assert glow["width_mm"] == lumo["width_mm"] == 2387.0
    assert glow["height_mm"] == lumo["height_mm"] == 2088.0
    assert "weight_kg" not in glow


def test_h_and_j_and_spark_document_dead_spec_searches() -> None:
    for rid in (5071, 5072, 5073):
        body = buhler.payload(rid)
        assert body.get("weight_kg") is None or "weight_kg" not in body
        assert "Dead searches" in body["notes"] or "dead" in buhler.PRODUCTS[rid]


def test_tags_are_catalog_names_and_status_pending() -> None:
    allowed = {
        "Sorting",
        "Agriculture",
        "Food Handling",
        "Computer Vision",
        "Industrial",
        "Automation",
        "Inspection",
        "Industrial Inspection",
        "AI",
        "Recycling",
        "Manufacturing",
    }
    for rid in buhler.PRODUCTS:
        body = buhler.payload(rid)
        assert body["status"] == "pending_review"
        assert body["availability_status"] == 11
        assert body["manufacturer_country_ref"] == 17
        assert set(body["tags"]) <= allowed
        assert len(body["features"]) >= 40
        assert "\n" in body["purpose"]
        assert "http" not in body["description"].lower()
        assert "http" not in body["features"].lower()
        assert "http" not in body["purpose"].lower()


def test_purpose_not_description_slice() -> None:
    for rid in buhler.PRODUCTS:
        body = buhler.payload(rid)
        assert body["purpose"].strip() != body["description"].strip()
        assert not body["description"].startswith(body["purpose"].split("\n")[0][:40])
