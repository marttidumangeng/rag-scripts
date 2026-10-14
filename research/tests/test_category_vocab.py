"""CANONICAL_CATEGORY_SLUGS must stay in step with the prod Category table.

The failure this guards against is silent. bulk_import resolves category_slugs
against EXISTING rows only — it will not create a facet — so a slug this module
emits but prod lacks is dropped into import_warnings and the robot lands with no
category at all. views.py's own comment leans on this file being right:

    "The research pipeline sends a fixed vocabulary
     (scripts/research/robot_categories.py) whose slugs all exist, so a miss
     here is a hand-authored XLSX or junk."

It has been wrong twice. `industrial-robots` and `autonomous-mobile-robots` left
18 rows uncategorised, and `logistics-robots` silently dropped the category on
every robot the classifier put in the logistics industry — caught only when an
assert happened to fire during the Nomagic import.

These tests cannot reach prod, so they pin the expected set instead: changing the
vocabulary now requires editing this file too, which is the prompt to go and
check the slug actually exists.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from robot_categories import (  # noqa: E402
    CANONICAL_CATEGORY_SLUGS,
    _BY_INDUSTRY,
    _BY_MOVEMENT,
    _BY_SUB_CATEGORY,
    _BY_USE,
    _IMPLIES,
    _KEYWORD_RULES,
    _RANK,
    derive_category_slugs,
)

# Verified present in the prod Category table on 2026-08-30, with robot counts.
# Re-run scratchpad/category_reconcile.py against prod before editing this.
PROD_VERIFIED = {
    "aerial", "agricultural-robots", "cleaning-robots", "collaborative-robot",
    "computing-platform", "consumer-robot", "delivery-robots", "delta-robot",
    "educational-robots", "end-effectors", "exosuit", "food-service-robots",
    "humanoid", "industrial-robot", "legged-robots", "marine", "medical-robots",
    "military", "mobile-robots", "other", "quadruped", "research-robots",
    "robotic-arms", "scara-robot", "security", "service-robots",
    "warehouse-robots",
}

# Slugs that were emitted but do NOT exist in prod. Regression guards.
PHANTOMS = {
    "logistics-robots",          # dropped every logistics robot's category
    "home-robots",
    "industrial-robots",         # the 18-row incident
    "autonomous-mobile-robots",  # ditto
}


def test_canonical_set_matches_prod_verified():
    assert CANONICAL_CATEGORY_SLUGS == PROD_VERIFIED, (
        "CANONICAL_CATEGORY_SLUGS drifted. Every slug must exist in the prod "
        "Category table — bulk_import silently drops the ones that do not."
    )


@pytest.mark.parametrize("slug", sorted(PHANTOMS))
def test_known_phantom_slugs_are_not_emittable(slug):
    assert slug not in CANONICAL_CATEGORY_SLUGS


class TestEverySignalMapsIntoTheCanonicalSet:
    """A mapping table pointing at a non-canonical slug is the actual bug: the
    slug gets proposed, passes the mapping, then dies at the importer."""

    @pytest.mark.parametrize("table,name", [
        (_BY_MOVEMENT, "_BY_MOVEMENT"),
        (_BY_SUB_CATEGORY, "_BY_SUB_CATEGORY"),
        (_BY_INDUSTRY, "_BY_INDUSTRY"),
        (_BY_USE, "_BY_USE"),
    ])
    def test_mapping_targets_are_canonical(self, table, name):
        bad = {k: v for k, v in table.items() if v not in CANONICAL_CATEGORY_SLUGS}
        assert not bad, f"{name} maps to non-canonical slugs: {bad}"

    def test_keyword_rule_targets_are_canonical(self):
        bad = [(p.pattern, s) for p, s in _KEYWORD_RULES
               if s not in CANONICAL_CATEGORY_SLUGS]
        assert not bad, f"_KEYWORD_RULES map to non-canonical slugs: {bad}"

    def test_implies_both_sides_are_canonical(self):
        bad = {k: v for k, v in _IMPLIES.items()
               if k not in CANONICAL_CATEGORY_SLUGS or v not in CANONICAL_CATEGORY_SLUGS}
        assert not bad, f"_IMPLIES references non-canonical slugs: {bad}"

    def test_rank_keys_are_canonical(self):
        bad = sorted(set(_RANK) - CANONICAL_CATEGORY_SLUGS)
        assert not bad, f"_RANK ranks non-canonical slugs: {bad}"

    def test_every_canonical_slug_is_rankable(self):
        """An unranked slug sorts unpredictably against the MAX_CATEGORIES cap."""
        assert not sorted(CANONICAL_CATEGORY_SLUGS - set(_RANK))


def _slugs(**kw):
    """derive_category_slugs returns a PIPE-JOINED STRING, not a list — set() on
    it iterates characters. Split before comparing."""
    return [s for s in (derive_category_slugs(**kw) or "").split("|") if s]


class TestLogisticsNowResolves:
    """The concrete regression: a logistics robot used to end up with nothing."""

    def test_logistics_industry_yields_a_real_category(self):
        got = _slugs(industry_keys="logistics")
        assert got, "logistics industry produced no category at all"
        assert set(got) <= CANONICAL_CATEGORY_SLUGS
        assert "warehouse-robots" in got

    def test_homes_industry_yields_a_real_category(self):
        got = _slugs(industry_keys="homes")
        assert got
        assert set(got) <= CANONICAL_CATEGORY_SLUGS


def test_derive_never_emits_outside_the_canonical_set():
    """Belt and braces across a spread of realistic inputs."""
    cases = [
        dict(industry_keys="logistics", movement_type_keys="wheeled"),
        dict(industry_keys="homes", use_keys="cleaning"),
        dict(name="6-axis welding robot", industry_keys="manufacturing"),
        dict(name="quadruped inspection robot", movement_type_keys="legged"),
        dict(name="subsea hull cleaning crawler", use_keys="cleaning"),
        dict(name="SCARA pick and place", industry_keys="manufacturing"),
        dict(industry_keys="logistics,retail", use_keys="picking"),
        dict(name="", industry_keys="", use_keys=""),
    ]
    for kw in cases:
        got = set(_slugs(**kw))
        assert got <= CANONICAL_CATEGORY_SLUGS, f"{kw} -> {got - CANONICAL_CATEGORY_SLUGS}"
