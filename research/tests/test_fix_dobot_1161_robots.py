"""Regression tests for the curated Dobot CR30H repair."""

from __future__ import annotations

import io
import sys
from pathlib import Path

from PIL import Image

RESEARCH_DIR = Path(__file__).resolve().parents[1]
if str(RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(RESEARCH_DIR))

import fix_dobot_1161_robots as dobot


def test_prepare_hero_removes_blank_footer_and_builds_card_size() -> None:
    source = Image.new("RGB", (200, 300), "white")
    for x in range(30, 171):
        for y in range(20, 151):
            source.putpixel((x, y), (100, 120, 140))
    buffer = io.BytesIO()
    source.save(buffer, format="PNG")

    output = dobot.prepare_hero(buffer.getvalue())
    hero = Image.open(io.BytesIO(output))

    assert hero.format == "PNG"
    assert max(hero.size) == 1_200
    assert hero.height / hero.width < 1.2


def test_patch_payload_uses_exact_cr30h_specs_and_family() -> None:
    payload = dobot.patch_payload("https://cdn.example/cr30h.png")

    assert payload["payload_kg"] == 30.0
    assert payload["reach_mm"] == 1_800.0
    assert payload["weight_kg"] == 98.5
    assert payload["repeatability_mm"] == 0.05
    assert payload["dof"] == 6
    assert payload["family_key"] == "dobot:cr-30h"
    assert payload["status"] == "pending_review"
