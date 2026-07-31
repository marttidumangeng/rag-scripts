"""Tests for `robot_categories` — the derivation that clears `missing_category`.

The invariant that matters most is the LAST one: every slug this module can emit
must already exist on prod, because the bulk importer resolves `category_slugs`
by slug and only creates a row as a last resort. A typo here would silently mint
a new Category and deepen the duplication problem this vocabulary exists to stop.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_RESEARCH_DIR = Path(__file__).resolve().parents[1]
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from robot_categories import (  # noqa: E402
    CANONICAL_CATEGORY_SLUGS,
    MAX_CATEGORIES,
    categories_from_discovery_hints,
    derive_category_slugs,
)


class DeriveFromTaxonomyTests(unittest.TestCase):
    def test_stationary_industrial_arm(self):
        got = derive_category_slugs(
            name="M-20iD/25",
            movement_type_keys="stationary",
            sub_category_slug="manufacturing-industrial",
        )
        self.assertIn("industrial-robot", got.split("|"))

    def test_cobot_keyword_beats_generic_industrial(self):
        got = derive_category_slugs(
            name="UR10e",
            text="collaborative robot arm for machine tending",
            movement_type_keys="stationary",
            sub_category_slug="manufacturing-industrial",
        ).split("|")
        self.assertEqual(got[0], "collaborative-robot")

    def test_form_factor_keywords_the_classifier_cannot_express(self):
        # A SCARA and a delta are both "stationary / manufacturing-industrial"
        # to Gemini — only the name distinguishes them.
        for name, expected in (
            ("TM5-900 SCARA", "scara-robot"),
            ("IRB 360 FlexPicker delta robot", "delta-robot"),
            ("2F-85 adaptive gripper", "end-effectors"),
        ):
            with self.subTest(name=name):
                self.assertEqual(
                    derive_category_slugs(name=name, movement_type_keys="stationary").split("|")[0],
                    expected,
                )

    def test_specific_form_factor_drops_the_broader_sibling(self):
        self.assertEqual(derive_category_slugs(name="Atlas humanoid", movement_type_keys="legged"), "humanoid")
        self.assertEqual(derive_category_slugs(name="Go2 quadruped", movement_type_keys="legged"), "quadruped")

    def test_locomotion_alone_still_categorises(self):
        for keys, expected in (
            ("wheeled", "mobile-robots"),
            ("tracked", "mobile-robots"),
            ("aerial", "aerial"),
            ("swimming", "marine"),
            ("legged", "legged-robots"),
        ):
            with self.subTest(keys=keys):
                self.assertEqual(derive_category_slugs(name="X", movement_type_keys=keys), expected)

    def test_capped_and_rank_ordered(self):
        got = derive_category_slugs(
            name="HotelBot W",
            text="hotel delivery robot for room service",
            movement_type_keys="wheeled",
            sub_category_slug="service-hospitality",
            use_keys="delivery|guiding",
            industry_keys="hotels|restaurants",
        ).split("|")
        self.assertLessEqual(len(got), MAX_CATEGORIES)
        # Domain before locomotion: "delivery robot" is more useful than "mobile",
        # and the cap drops the locomotion tier rather than the specific one.
        self.assertEqual(got[0], "delivery-robots")
        self.assertNotIn("mobile-robots", got)


class KeywordScopeTests(unittest.TestCase):
    """Keyword rules must not read a whole site's product nav as this model's spec."""

    def test_the_name_wins_over_the_body_text(self):
        got = derive_category_slugs(
            name="TM5-900 SCARA",
            text="We also build delta robots, cobots and exoskeletons.",
        ).split("|")
        self.assertEqual(got, ["scara-robot"])

    def test_body_text_is_only_consulted_when_the_name_is_silent(self):
        self.assertEqual(
            derive_category_slugs(name="Model 7", text="A collaborative robot arm."),
            "collaborative-robot",
        )

    def test_footer_beyond_the_window_is_ignored(self):
        from robot_categories import TEXT_MATCH_WINDOW

        blurb = "A general purpose machine. " * 5
        footer = "Products: SCARA robot | delta robot | exoskeleton"
        text = blurb + ("x" * TEXT_MATCH_WINDOW) + footer
        self.assertEqual(derive_category_slugs(name="Model 7", text=text), "")


class NoSignalTests(unittest.TestCase):
    def test_no_signal_returns_blank_without_a_fallback(self):
        # Discovery must NOT stamp "Other" on an unresearched robot: the chip
        # would clear while the reviewer still has nothing to act on.
        self.assertEqual(derive_category_slugs(name="Model 7"), "")

    def test_fallback_is_opt_in(self):
        self.assertEqual(derive_category_slugs(name="Model 7", fallback="other"), "other")

    def test_unknown_fallback_is_rejected_not_created(self):
        self.assertEqual(derive_category_slugs(name="Model 7", fallback="brand-new-thing"), "")


class ExistingAssignmentTests(unittest.TestCase):
    def test_display_names_from_the_api_round_trip(self):
        # The API serializes `categories` as NAMES ("Industrial-Robot"), not slugs.
        got = derive_category_slugs(name="X", existing="Industrial-Robot")
        self.assertIn("industrial-robot", got.split("|"))

    def test_existing_assignment_is_never_dropped(self):
        got = derive_category_slugs(
            name="X", existing="Industrial-Robot", movement_type_keys="wheeled",
        ).split("|")
        self.assertIn("industrial-robot", got)
        self.assertIn("mobile-robots", got)

    def test_junk_existing_value_is_not_propagated(self):
        self.assertEqual(derive_category_slugs(name="X", existing="and grasp quality."), "")


class DiscoveryHintTests(unittest.TestCase):
    def test_directory_labels_map_to_canonical_slugs(self):
        got = categories_from_discovery_hints(["humanoid", "amr", "drone"]).split("|")
        self.assertEqual(got[0], "humanoid")
        self.assertIn("mobile-robots", got)   # amr is a duplicate row on prod
        self.assertIn("aerial", got)          # so are drone/uav

    def test_junk_hint_is_ignored(self):
        self.assertEqual(categories_from_discovery_hints(["and grasp quality."]), "")

    def test_empty(self):
        self.assertEqual(categories_from_discovery_hints(None), "")


class VocabularyTests(unittest.TestCase):
    def test_every_emitted_slug_is_in_the_vocabulary(self):
        """No mapping table may name a slug the vocabulary does not declare."""
        from robot_categories import (
            _BY_INDUSTRY, _BY_MOVEMENT, _BY_SUB_CATEGORY, _BY_USE,
            _IMPLIES, _KEYWORD_RULES, _RANK,
        )
        emitted = set()
        for table in (_BY_MOVEMENT, _BY_SUB_CATEGORY, _BY_INDUSTRY, _BY_USE):
            emitted |= set(table.values())
        emitted |= {slug for _, slug in _KEYWORD_RULES}
        emitted |= set(_IMPLIES) | set(_IMPLIES.values()) | set(_RANK)
        self.assertEqual(emitted - CANONICAL_CATEGORY_SLUGS, set())

    def test_every_vocabulary_slug_is_ranked(self):
        """An unranked slug sorts to the middle by accident, not by decision."""
        self.assertEqual(CANONICAL_CATEGORY_SLUGS - set(_rank_keys()), set())

    def test_ground_is_not_emittable(self):
        # `ground` is the 224-robot locomotion catch-all; adding to it buys a
        # chip and tells a browsing user nothing.
        self.assertNotIn("ground", CANONICAL_CATEGORY_SLUGS)


def _rank_keys():
    from robot_categories import _RANK
    return _RANK.keys()


if __name__ == "__main__":
    unittest.main()
