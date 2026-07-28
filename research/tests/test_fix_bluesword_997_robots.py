"""Regression tests for BlueSword company 997 catalog curation."""

from __future__ import annotations

import sys
from pathlib import Path

RESEARCH_DIR = Path(__file__).resolve().parents[1]
if str(RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(RESEARCH_DIR))

import fix_bluesword_997_robots as bluesword


def test_identity_plan_keeps_only_named_robot_products() -> None:
    assert set(bluesword.PRODUCTS) == {
        5051,
        5050,
        5048,
        5047,
        5046,
        2807,
        2806,
        1233,
        1231,
    }
    assert set(bluesword.REJECTS) == {
        5052,
        5049,
        5045,
        3609,
        1234,
        1232,
        1230,
        1229,
    }


def test_four_way_shuttle_omits_conflicting_payload() -> None:
    typed = bluesword.PRODUCTS[5050]["typed"]

    assert "payload_kg" not in typed
    assert typed["weight_kg"] == 350
    assert typed["speed"] == 5.4
    assert (
        typed["length_mm"],
        typed["width_mm"],
        typed["height_mm"],
    ) == (1150, 980, 135)


def test_official_heroes_are_unique_and_transfer_names_are_current() -> None:
    heroes = [product["image"] for product in bluesword.PRODUCTS.values()]

    assert len(set(heroes)) == len(heroes)
    assert bluesword.PRODUCTS[1233]["name"] == "Transfer FMR"
    assert bluesword.PRODUCTS[1231]["name"] == "Latent Mobile Robot (LMR)"
    assert bluesword.PRODUCTS[1233]["typed"]["payload_kg"] == 3000
    assert bluesword.PRODUCTS[1231]["typed"]["payload_kg"] == 2000
