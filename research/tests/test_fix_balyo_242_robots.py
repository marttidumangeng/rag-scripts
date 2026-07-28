"""Regression tests for BALYO company 242 curation."""

from __future__ import annotations

import sys
from pathlib import Path

RESEARCH_DIR = Path(__file__).resolve().parents[1]
if str(RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(RESEARCH_DIR))

import fix_balyo_242_robots as balyo


def test_identity_plan_keeps_one_current_record_per_model() -> None:
    assert set(balyo.PRODUCTS) == {2680, 2681, 2682, 2683, 2684, 2685}
    assert balyo.REJECTS == {
        4129: 2680,
        3850: 2681,
        4130: 2681,
        4131: 2682,
        3849: 2683,
        4132: 2683,
        4133: 2684,
        3851: 2685,
        4134: 2685,
    }


def test_safe_typed_fields_do_not_invent_configuration_values() -> None:
    tuggy = balyo.PRODUCTS[2685]["typed"]
    lowy = balyo.PRODUCTS[2683]["typed"]
    reachy = balyo.PRODUCTS[2681]["typed"]

    assert "payload_kg" not in tuggy
    assert "payload_kg" not in lowy
    assert tuggy["speed"] == 7.2
    assert (tuggy["length_mm"], tuggy["width_mm"], tuggy["height_mm"]) == (
        1706,
        709,
        2351,
    )
    assert reachy["payload_kg"] == 1600


def test_lowy_hd_uses_exact_current_cover_and_prunes_wrong_gallery() -> None:
    lowy_hd = balyo.PRODUCTS[2684]

    assert "Lowy-HD_Cover-photo.jpg" in lowy_hd["image"]
    assert set(balyo.STALE_PHOTOS) == {12277, 12278, 12280}


def test_video_plan_does_not_keep_sibling_or_generic_clips() -> None:
    assert balyo.PRODUCTS[2680]["videos"] == [
        "https://www.youtube.com/watch?v=2dm_Q_oCvCg"
    ]
    assert balyo.PRODUCTS[2681]["videos"] == [
        "https://www.youtube.com/watch?v=swXkiIincqs"
    ]
    assert len(balyo.PRODUCTS[2682]["videos"]) == 1
    assert len(balyo.PRODUCTS[2683]["videos"]) == 1
    assert len(balyo.PRODUCTS[2684]["videos"]) == 1
    assert balyo.PRODUCTS[2685]["videos"] == [
        "https://www.youtube.com/watch?v=8zl3C5NRKfQ"
    ]
