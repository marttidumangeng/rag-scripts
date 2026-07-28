"""Tests for the curated Huayan Robotics company 1490 catalog."""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

RESEARCH_DIR = Path(__file__).resolve().parents[1]
if str(RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(RESEARCH_DIR))

from huayan_1490_catalog import (
    CATALOG,
    CURRENT_MODEL_CODES,
    RETIREMENT_CANDIDATES,
    normalize_model_code,
)
import huayan_1490_catalog as catalog


def test_catalog_has_exactly_42_unique_current_models() -> None:
    assert len(CATALOG) == 42
    assert len(CURRENT_MODEL_CODES) == 42
    assert {normalize_model_code(row["model"]) for row in CATALOG} == CURRENT_MODEL_CODES


def test_catalog_family_counts() -> None:
    assert Counter(row["family"] for row in CATALOG) == {
        "Elfin": 7,
        "Elfin-Pro": 7,
        "Elfin-Ex": 5,
        "S": 5,
        "Echo": 3,
        "HY": 3,
        "STAR": 4,
        "Elfin-Li": 6,
        "S-Li": 2,
    }


def test_catalog_contains_current_authoritative_specs() -> None:
    by_model = {row["model"]: row for row in CATALOG}
    assert by_model["E15"]["typed"]["payload_kg"] == 18
    assert by_model["E12F"]["typed"]["weight_kg"] == 72
    assert by_model["S20"]["typed"]["repeatability_mm"] == 0.03
    assert by_model["S40"]["typed"]["reach_mm"] == 2000
    assert by_model["S50"]["typed"]["weight_kg"] == 156
    assert by_model["Echo 3"]["typed"]["dof"] == 7
    assert by_model["STAR-M"]["typed"] == {"speed": 3.96, "runtime_minutes": 720}
    assert by_model["E03Li"]["typed"] == {}


def test_catalog_has_no_media_fields_and_purposes_are_distinct() -> None:
    for row in CATALOG:
        assert "image" not in row
        assert "images" not in row
        assert row["description"].strip()
        assert row["purpose"].strip()
        assert row["purpose"].strip() != row["description"].strip()
        assert row["sources"]


def test_catalog_owns_the_known_existing_model_id_contract() -> None:
    assert catalog.EXISTING_ID_BY_MODEL == {
        "E03": 5295,
        "E05-L": 5296,
        "E05": 5297,
        "E10-L": 5298,
        "E10": 5299,
        "E12": 5300,
        "E15": 5301,
        "E03-Pro": 3670,
        "E05-Pro": 3671,
        "E05L-Pro": 3672,
        "E10-Pro": 3673,
        "E10L-Pro": 3674,
        "E12-Pro": 3675,
        "E15-Pro": 3676,
        "E05F": 3683,
        "E10F": 3684,
        "E10F-L": 3685,
        "E12F": 3686,
        "E15F": 3687,
        "S20": 3677,
        "S30": 5205,
        "S40": 3680,
        "S50": 3681,
        "S60": 3682,
    }


def test_all_li_models_have_no_model_specific_typed_specs() -> None:
    li_models = {
        row["model"]: row
        for row in CATALOG
        if row["family"] in {"Elfin-Li", "S-Li"}
    }
    assert set(li_models) == {
        "E03Li",
        "E05Li",
        "E05Li-L",
        "E10Li",
        "E12Li",
        "E15Li",
        "S20Li",
        "S30Li",
    }
    assert all(row["typed"] == {} for row in li_models.values())


def test_normalization_preserves_variant_identity() -> None:
    assert normalize_model_code("S-30 Heavy Payload Robot") == "s30"
    assert normalize_model_code("Elfin E05-L") == "e05l"
    assert normalize_model_code("E10L-Pro") != normalize_model_code("E10-Pro")
    assert normalize_model_code("E10F-L") != normalize_model_code("E10F")
    assert normalize_model_code("E10Li") != normalize_model_code("E10")


def test_retirement_candidates_are_exact_existing_records() -> None:
    assert RETIREMENT_CANDIDATES == {
        3679: "Legacy S35; absent from current model tables",
        5302: "Published Echo family shell superseded by six model records",
        5303: "Published STAR family shell superseded by four model records",
    }
