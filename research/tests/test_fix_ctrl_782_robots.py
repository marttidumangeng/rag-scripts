"""Regression tests for CTRL Robotics company 782 ownership cleanup."""

from __future__ import annotations

import sys
from pathlib import Path

RESEARCH_DIR = Path(__file__).resolve().parents[1]
if str(RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(RESEARCH_DIR))

import fix_ctrl_782_robots as ctrl


def test_ownership_plan_keeps_only_ctrl_box_under_ctrl() -> None:
    assert set(ctrl.PRODUCTS) == {5086}
    assert ctrl.REPARENT == {
        5085: ("Pudu Robotics", 148),
        5083: ("REEMAN", 1421),
        5082: ("REEMAN", 1421),
    }
    assert set(ctrl.REJECTS) == {5087, 5084, 5081, 5080, 2815}


def test_box_uses_ctrl_specs_without_inventing_hardware_oem() -> None:
    box = ctrl.PRODUCTS[5086]

    assert box["typed"]["payload_kg"] == 40
    assert box["typed"]["speed"] == 3.6
    assert box["typed"]["charging_time_minutes"] == 90
    assert box["family_key"] == "ctrl:box"
    assert "undisclosed" in box["notes"].lower()


def test_reparented_rows_get_current_oem_identities() -> None:
    assert ctrl.REPARENT_DATA[5085]["name"] == "PuduBot"
    assert ctrl.REPARENT_DATA[5083]["model_name"] == "WBOT11B"
    assert ctrl.REPARENT_DATA[5082]["model_name"] == "FBOT13B"
