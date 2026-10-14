"""Regression tests for TagCatalog.suggest — the tag-flood bug.

Published robots carried junk form-factor tags: OMRON/FANUC/Kassow cobots tagged
"Drone + Humanoid + Stationary", AGVs tagged "Care Robot", a robot vacuum tagged "Stationary".
Three defects produced it (2026-09-13):

1. a keyword-hint condition that did not depend on the tag, so one matching word added +6 to
   EVERY catalog tag and alphabetical tie-breaking handed out "Autonomous, Collaborative, Drone,
   Humanoid...";
2. a popularity bonus applied to every tag, so popular tags filled empty slots with no textual
   match at all;
3. substring matching (tag parts like "robot"; short tags like "ai" inside "maintain"), plus the
   movement key being read, so a wrong `stationary` movement became a wrong tag.
"""

from __future__ import annotations

import sys
from pathlib import Path

_RESEARCH_DIR = Path(__file__).resolve().parents[1]
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from tag_suggest import TagCatalog, suggest_robot_tags  # noqa: E402


def _catalog() -> TagCatalog:
    rows = [
        ("Drone", "drone", 300),
        ("Humanoid", "humanoid", 300),
        ("Autonomous", "autonomous", 200),
        ("Stationary", "stationary", 150),
        ("AI", "ai", 150),
        ("AMR", "amr", 120),
        ("Manufacturing", "manufacturing", 90),
        ("Collaborative Robot", "collaborative-robot", 80),
        ("Logistics", "logistics", 70),
        ("Assembly", "assembly", 60),
        ("Care Robot", "care-robot", 40),
        ("Arm", "arm", 30),
        ("Robot Vacuum", "robot-vacuum", 20),
    ]
    return TagCatalog(tags=[{"name": n, "slug": s, "robots_count": c} for n, s, c in rows])


def test_cobot_never_gets_drone_or_humanoid():
    tags = _catalog().suggest(
        name="OMRON TM7S",
        description="Collaborative robot for manufacturing assembly in industrial factories.",
        movement_type_keys="stationary",
    )
    assert "Drone" not in tags
    assert "Humanoid" not in tags
    assert "Collaborative Robot" in tags
    assert "Manufacturing" in tags


def test_hint_does_not_boost_unrelated_tags():
    # "industrial" / "factory" fire the manufacturing hint. The boost must reach only tags
    # NAMED after the hint, never the whole catalog.
    tags = _catalog().suggest(name="Unit X", description="Industrial factory equipment.")
    assert "Manufacturing" in tags
    for junk in ("Drone", "Humanoid", "Care Robot", "Stationary", "Autonomous"):
        assert junk not in tags


def test_popularity_alone_never_suggests_a_tag():
    assert _catalog().suggest(name="Xyz", description="Nothing relevant is described here.") == []


def test_movement_key_is_ignored():
    tags = _catalog().suggest(
        name="Saros 10",
        description="Robot vacuum that mops floors.",
        movement_type_keys="stationary",
    )
    assert "Stationary" not in tags
    assert "Robot Vacuum" in tags


def test_matching_is_whole_word():
    tags = _catalog().suggest(name="Farm chain", description="It can maintain a farm chain.")
    assert "AI" not in tags   # "ai" inside "maintain" / "chain"
    assert "Arm" not in tags  # "arm" inside "farm"


def test_generic_word_robot_does_not_attach_care_robot():
    tags = _catalog().suggest(
        name="VMR-FR4800P",
        description="Autonomous mobile robot for warehouse logistics.",
    )
    assert "Care Robot" not in tags
    assert "AMR" in tags        # boosted by the amr hint ("autonomous mobile")
    assert "Logistics" in tags


def test_suggest_robot_tags_returns_pipe_string_without_flood():
    out = suggest_robot_tags(
        {"name": "FANUC CRX-30iA/L", "description": "Collaborative robot for assembly.",
         "movement_type_keys": "stationary"},
        catalog=_catalog(),
    )
    parts = out.split("|")
    assert "Collaborative Robot" in parts
    assert not {"Drone", "Humanoid", "Stationary"} & set(parts)
