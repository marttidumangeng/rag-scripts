"""Regression tests for the "No country" / "No category" pipeline holes.

Each test below pins one link in the chain that was broken on 2026-07-31, when
351 of 1596 pending robots had no country and 317 had no category:

  1. `robot_gaps` did not report either, and `overnight_queue_enrich` filters its
     work queue on `robot_gaps(r)` — so a robot whose ONLY problems were these
     two was dropped from every remediation pass (295 robots were in exactly
     that state).
  2. `missing_manufacturer_country` sat in UNFIXABLE_FLAGS despite being
     error-severity and deterministically derivable from the company.
  3. `missing_category` and `missing_taxonomy` shared the `refresh_taxonomy`
     action, so a NO_OP recorded under one blocked the other.
  4. The researcher never wrote `category_slugs` at all, and
     `_robot_api_to_staged` did not carry the robot's existing categories or
     movement types — so the merge base was blank on both sides.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_RESEARCH_DIR = Path(__file__).resolve().parents[1]
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from remedies import (  # noqa: E402
    NO_OP,
    REMEDY_ORDER,
    REMEDY_REGISTRY,
    UNFIXABLE_FLAGS,
    plan_remedies,
)
from remedies.registry import GAP_TO_FLAG, _action_for_flag, flags_from_gaps  # noqa: E402
from triage_content_queue import gap_score, robot_gaps  # noqa: E402


def _robot(**over):
    """A robot with everything filled EXCEPT what the test blanks out."""
    base = {
        "id": 1,
        "name": "Test Bot",
        "image": "https://x.test/a.jpg",
        "features": "Elevator integration\nLiDAR navigation\nGuest notification",
        "videos": [{"url": "https://y.test/v"}],
        "tags": ["arm"],
        "url": "https://x.test/bot",
        "weight_kg": 12.0,
        "company_ref": {"id": 7, "name": "Test Co"},
        "manufacturer_country_ref": {"id": 3, "code": "JP"},
        "categories": ["Industrial-Robot"],
    }
    base.update(over)
    return base


class GapDetectionTests(unittest.TestCase):
    def test_a_complete_robot_has_no_gaps(self):
        self.assertEqual(robot_gaps(_robot()), [])

    def test_missing_country_is_a_gap(self):
        self.assertIn("no_country", robot_gaps(_robot(manufacturer_country_ref=None)))

    def test_missing_category_is_a_gap(self):
        self.assertIn("no_category", robot_gaps(_robot(categories=[])))

    def test_legacy_country_string_counts(self):
        # Older rows carry the free-text `manufacturer_country` and no FK.
        gaps = robot_gaps(_robot(manufacturer_country_ref=None, manufacturer_country="Japan"))
        self.assertNotIn("no_country", gaps)

    def test_country_and_category_only_robot_is_no_longer_invisible(self):
        """`overnight_queue_enrich` keeps robots where `robot_gaps(r)` is truthy."""
        gaps = robot_gaps(_robot(manufacturer_country_ref=None, categories=[]))
        self.assertTrue(gaps, "such a robot would be filtered out of every enrichment pass")
        self.assertEqual(set(gaps), {"no_country", "no_category"})

    def test_country_outranks_the_warning_level_gaps(self):
        # It is the only error-severity flag in the list and the cheapest to fix.
        self.assertGreater(
            gap_score(["no_country"]),
            gap_score(["no_category"]),
        )


class GapToFlagTests(unittest.TestCase):
    def test_new_gaps_map_to_real_flags(self):
        self.assertEqual(GAP_TO_FLAG["no_country"], "missing_manufacturer_country")
        self.assertEqual(GAP_TO_FLAG["no_category"], "missing_category")

    def test_gaps_translate_into_a_runnable_plan(self):
        flags = flags_from_gaps(["no_country", "no_category"])
        plan = [flag for flag, _fn in plan_remedies(quality_flags=flags)]
        self.assertEqual(plan, ["missing_manufacturer_country", "missing_category"])


class RegistryWiringTests(unittest.TestCase):
    def test_country_is_remediable(self):
        self.assertIn("missing_manufacturer_country", REMEDY_REGISTRY)
        self.assertNotIn("missing_manufacturer_country", UNFIXABLE_FLAGS)
        self.assertIn("missing_manufacturer_country", REMEDY_ORDER)

    def test_country_runs_first(self):
        # Cheapest fix, only error-severity flag with a remedy, and resolving it
        # writes the Company — which makes every sibling robot free.
        self.assertEqual(REMEDY_ORDER[0], "missing_manufacturer_country")

    def test_category_and_taxonomy_no_longer_share_an_action(self):
        self.assertNotEqual(
            _action_for_flag("missing_category"),
            _action_for_flag("missing_taxonomy"),
            "sharing an action means a NO_OP on one silently blocks the other",
        )

    def test_a_taxonomy_no_op_does_not_block_the_category_remedy(self):
        plan = [
            flag for flag, _fn in plan_remedies(
                quality_flags=["missing_category", "missing_taxonomy"],
                attempts=[{"action": _action_for_flag("missing_taxonomy"), "outcome": NO_OP}],
            )
        ]
        self.assertIn("missing_category", plan)
        self.assertNotIn("missing_taxonomy", plan)

    def test_wrong_category_rejection_reaches_the_category_remedy(self):
        plan = [flag for flag, _fn in plan_remedies(rejection_categories=["wrong_category"])]
        self.assertIn("missing_category", plan)


class WebsiteFreeFlagTests(unittest.TestCase):
    """A company with no resolvable website must still get these two fixed."""

    def test_the_website_free_set_is_exactly_the_two_offline_remedies(self):
        from remedies import WEBSITE_FREE_FLAGS

        self.assertEqual(
            WEBSITE_FREE_FLAGS,
            frozenset({"missing_category", "missing_manufacturer_country"}),
        )

    def test_every_website_free_flag_has_a_remedy(self):
        from remedies import WEBSITE_FREE_FLAGS

        self.assertEqual(WEBSITE_FREE_FLAGS - set(REMEDY_REGISTRY), set())

    def test_filtering_a_plan_to_website_free_leaves_work_to_do(self):
        from remedies import WEBSITE_FREE_FLAGS

        plan = plan_remedies(quality_flags=[
            "missing_image", "missing_features", "missing_category",
            "missing_manufacturer_country",
        ])
        offline = [flag for flag, _fn in plan if flag in WEBSITE_FREE_FLAGS]
        self.assertEqual(offline, ["missing_manufacturer_country", "missing_category"])


class StagedFieldTests(unittest.TestCase):
    """The staged payload must actually carry the fields the fixes depend on."""

    def test_api_robot_round_trips_categories_and_movement_types(self):
        from robot_auto_research import _robot_api_to_staged

        staged = _robot_api_to_staged(
            _robot(
                categories=["Industrial-Robot", "Collaborative-Robot"],
                movement_types=[{"key": "stationary", "label": "Stationary"}],
            ),
            "test-co", "Test Co",
        )
        self.assertEqual(staged.category_slugs, "Industrial-Robot|Collaborative-Robot")
        self.assertEqual(staged.movement_type_keys, "stationary")
        self.assertEqual(staged.manufacturer_country_code, "JP")

    def test_bulk_import_payload_carries_both_fields(self):
        from map_to_bulk_import import staging_robot_to_bulk_import_row
        from schema import StagedRobot

        row = staging_robot_to_bulk_import_row(StagedRobot(
            name="Test Bot",
            category_slugs="industrial-robot|collaborative-robot",
            manufacturer_country_code="JP",
        ))
        self.assertEqual(row["category_slugs"], "industrial-robot|collaborative-robot")
        self.assertEqual(row["manufacturer_country_code"], "JP")


if __name__ == "__main__":
    unittest.main()
