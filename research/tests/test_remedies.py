"""Tests for the Tier-1 remedy library.

Focus on the two guarantees the loop depends on:
  1. the no-op detector (never write / never retry when nothing changed)
  2. the ledger-aware planner (never repeat a fix that already failed to help)

Plus a drift check: every flag the server can raise must be either remediable
or explicitly listed as unfixable.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_RESEARCH_DIR = Path(__file__).resolve().parents[1]
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from remedies import (  # noqa: E402
    FAILED,
    NO_OP,
    REMEDY_ORDER,
    REMEDY_REGISTRY,
    UNFIXABLE_FLAGS,
    blocked_actions,
    diff_fields,
    flags_from_categories,
    is_terminal,
    plan_remedies,
    snapshot,
)


class TestNoOpDetector(unittest.TestCase):
    def test_identical_payload_reports_no_change(self):
        fields = frozenset({"description", "url"})
        before = snapshot({"description": "A robot.", "url": "https://x.com/a"}, fields)
        after = snapshot({"description": "A robot.", "url": "https://x.com/a"}, fields)
        self.assertEqual(diff_fields(before, after), [])

    def test_whitespace_only_change_is_not_a_change(self):
        fields = frozenset({"description"})
        before = snapshot({"description": "A robot."}, fields)
        after = snapshot({"description": "  A robot.  "}, fields)
        self.assertEqual(diff_fields(before, after), [])

    def test_real_change_is_detected(self):
        fields = frozenset({"description"})
        before = snapshot({"description": ""}, fields)
        after = snapshot({"description": "A welding cobot."}, fields)
        self.assertEqual(diff_fields(before, after), ["description"])

    def test_media_compared_by_url_not_order(self):
        fields = frozenset({"video_urls"})
        before = snapshot({"video_urls": [{"url": "b"}, {"url": "a"}]}, fields)
        after = snapshot({"video_urls": [{"url": "a"}, {"url": "b"}]}, fields)
        self.assertEqual(diff_fields(before, after), [], "reordering is not a change")

    def test_media_addition_is_detected(self):
        fields = frozenset({"images"})
        before = snapshot({"images": ["a"]}, fields)
        after = snapshot({"images": ["a", "b"]}, fields)
        self.assertEqual(diff_fields(before, after), ["images"])


class TestLedgerBlocking(unittest.TestCase):
    def test_no_op_blocks_that_action_forever(self):
        attempts = [{"action": "refresh_media", "outcome": NO_OP}]
        self.assertIn("refresh_media", blocked_actions(attempts))

    def test_single_failure_still_retryable(self):
        attempts = [{"action": "refresh_url", "outcome": FAILED}]
        self.assertNotIn("refresh_url", blocked_actions(attempts))

    def test_two_failures_exhaust_budget(self):
        attempts = [
            {"action": "refresh_url", "outcome": FAILED},
            {"action": "refresh_url", "outcome": FAILED},
        ]
        self.assertIn("refresh_url", blocked_actions(attempts))

    def test_success_does_not_block(self):
        attempts = [{"action": "refresh_media", "outcome": "fixed"}]
        self.assertEqual(blocked_actions(attempts), set())


class TestPlanner(unittest.TestCase):
    def test_terminal_categories_short_circuit(self):
        for cat in ("not_real", "duplicate"):
            self.assertTrue(is_terminal([cat]))
            self.assertEqual(
                plan_remedies(quality_flags=["missing_image"], rejection_categories=[cat]),
                [],
                f"{cat} must never be enriched",
            )

    def test_terminal_wins_even_mixed_with_fixable(self):
        self.assertEqual(
            plan_remedies(
                quality_flags=["missing_image"],
                rejection_categories=["wrong_image", "not_real"],
            ),
            [],
        )

    def test_plans_remedy_for_flag(self):
        plan = plan_remedies(quality_flags=["missing_image"])
        self.assertEqual([f for f, _ in plan], ["missing_image"])

    def test_accepts_quality_flag_dicts(self):
        plan = plan_remedies(quality_flags=[{"flag": "missing_video", "severity": "warn"}])
        self.assertEqual([f for f, _ in plan], ["missing_video"])

    def test_errors_only_filters_warnings(self):
        flags = [
            {"flag": "missing_image", "severity": "error"},
            {"flag": "missing_video", "severity": "warn"},
        ]
        plan = plan_remedies(quality_flags=flags, errors_only=True)
        self.assertEqual([f for f, _ in plan], ["missing_image"])

    def test_url_repaired_before_content_drawn_from_it(self):
        plan = plan_remedies(quality_flags=["missing_description", "url_dead"])
        self.assertEqual([f for f, _ in plan], ["url_dead", "missing_description"])

    def test_no_op_on_shared_action_blocks_sibling_flag(self):
        # refresh_url was already useless -> a sibling URL flag must not retry it
        attempts = [{"action": "refresh_url", "outcome": NO_OP}]
        plan = plan_remedies(quality_flags=["url_content_mismatch"], attempts=attempts)
        self.assertEqual(plan, [], "sibling flag must not resurrect a no-op action")

    def test_blocked_action_still_allows_other_flags(self):
        attempts = [{"action": "refresh_url", "outcome": NO_OP}]
        plan = plan_remedies(quality_flags=["url_dead", "missing_image"], attempts=attempts)
        self.assertEqual([f for f, _ in plan], ["missing_image"])

    def test_rejection_categories_map_onto_flags(self):
        self.assertEqual(flags_from_categories(["wrong_image"]), ["image_mismatch"])
        self.assertIn("short_description", flags_from_categories(["thin_content"]))

    def test_rejection_category_alone_produces_a_plan(self):
        plan = plan_remedies(rejection_categories=["wrong_image"])
        self.assertEqual([f for f, _ in plan], ["image_mismatch"])

    def test_unknown_flag_is_ignored(self):
        self.assertEqual(plan_remedies(quality_flags=["totally_unknown_flag"]), [])


class TestRegistryIntegrity(unittest.TestCase):
    def test_every_registered_flag_is_ordered(self):
        missing = set(REMEDY_REGISTRY) - set(REMEDY_ORDER)
        self.assertEqual(missing, set(), "registered remedies missing from REMEDY_ORDER are unreachable")

    def test_order_has_no_unknown_flags(self):
        self.assertEqual(set(REMEDY_ORDER) - set(REMEDY_REGISTRY), set())

    def test_covers_server_flag_registry(self):
        """Drift guard: every robot flag the server raises is handled or waived."""
        server_dir = _RESEARCH_DIR.parents[1] / "robotaigeek-server"
        if not server_dir.is_dir():
            self.skipTest("server package not available")
        sys.path.insert(0, str(server_dir))
        try:
            from robots.quality import FLAG_REGISTRY
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"cannot import FLAG_REGISTRY: {exc}")

        company_flags = {
            "missing_website", "malformed_website", "website_dead", "website_shared",
            "missing_logo", "missing_country", "missing_company_description",
        }
        robot_flags = set(FLAG_REGISTRY) - company_flags
        unhandled = robot_flags - set(REMEDY_REGISTRY) - UNFIXABLE_FLAGS
        self.assertEqual(
            unhandled, set(),
            f"new server flags with no remedy and no waiver: {sorted(unhandled)}",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
