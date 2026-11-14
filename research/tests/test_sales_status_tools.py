"""Unit tests for assess_sales_status and apply_sales_status helpers.

From scripts/research:

    python -m unittest tests.test_sales_status_tools
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

_RESEARCH_DIR = Path(__file__).resolve().parents[1]
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

import apply_sales_status as apply_mod  # noqa: E402
import assess_sales_status as assess_mod  # noqa: E402
from schema import StagedRobot  # noqa: E402
from validate_staging import validate_robot  # noqa: E402


class ParseAssessmentTests(unittest.TestCase):
    def test_assessable_with_quote_and_url(self):
        raw = '{"sales_status":"general_sale","confidence":"high","quote":"Buy now","source_url":"https://m.example/p","reason":"shop"}'
        r = assess_mod.parse_sales_assessment(raw)
        self.assertEqual(r["sales_status"], "general_sale")
        self.assertEqual(r["quote"], "Buy now")

    def test_missing_quote_becomes_unclear(self):
        raw = '{"sales_status":"general_sale","confidence":"high","quote":"","source_url":"https://m.example/p"}'
        r = assess_mod.parse_sales_assessment(raw)
        self.assertEqual(r["sales_status"], "unclear")

    def test_missing_url_becomes_unclear(self):
        raw = '{"sales_status":"pre_order","confidence":"medium","quote":"Reserve today","source_url":""}'
        r = assess_mod.parse_sales_assessment(raw)
        self.assertEqual(r["sales_status"], "unclear")

    def test_unknown_status_becomes_unclear(self):
        raw = '{"sales_status":"shipping_soon","quote":"x","source_url":"https://m.example/p"}'
        r = assess_mod.parse_sales_assessment(raw)
        self.assertEqual(r["sales_status"], "unclear")


class ApplySheetTests(unittest.TestCase):
    def test_accept_and_corrected_rows(self):
        sheet = [
            {
                "id": "1",
                "name": "Bot A",
                "current_status": "not_assessed",
                "proposed_sales_status": "general_sale",
                "source_url": "https://m.example/a",
                "decision": "accept",
            },
            {
                "id": "2",
                "name": "Bot B",
                "current_status": "not_assessed",
                "proposed_sales_status": "unclear",
                "source_url": "https://m.example/b",
                "decision": "made_to_order",
            },
            {
                "id": "3",
                "name": "Bot C",
                "current_status": "not_assessed",
                "proposed_sales_status": "pre_order",
                "source_url": "https://m.example/c",
                "decision": "",
            },
        ]
        batch, skips = apply_mod.build_batch_rows(sheet)
        self.assertEqual(len(batch), 2)
        self.assertEqual(batch[0]["sales_status"], "general_sale")
        self.assertEqual(batch[1]["sales_status"], "made_to_order")
        self.assertTrue(any("blank decision" in s for s in skips))

    def test_rejects_accept_of_unclear(self):
        sheet = [{
            "id": "9",
            "name": "Bot Z",
            "current_status": "not_assessed",
            "proposed_sales_status": "unclear",
            "source_url": "https://m.example/z",
            "decision": "accept",
        }]
        batch, skips = apply_mod.build_batch_rows(sheet)
        self.assertEqual(batch, [])
        self.assertTrue(skips)


class StagingValidationTests(unittest.TestCase):
    def test_assessed_without_quote_errors(self):
        robot = StagedRobot(
            name="X",
            company_slug="acme",
            description="A robot.",
            purpose="Inspection",
            features="Lidar",
            tags="mobile",
            industry_keys="logistics",
            use_keys="inspection",
            sources=[],
            sales_status_key="general_sale",
            sales_status_source_url="https://m.example/x",
            sales_status_quote="",
        )
        # sources required separately; focus on sales fields
        result = validate_robot(robot)
        fields = {i.field for i in result.issues if i.level == "error"}
        self.assertIn("sales_status_quote", fields)

    def test_not_assessed_needs_no_source(self):
        robot = StagedRobot(
            name="Y",
            company_slug="acme",
            description="A robot.",
            purpose="Inspection",
            features="Lidar",
            tags="mobile",
            industry_keys="logistics",
            use_keys="inspection",
            sources=[{"url": "https://m.example/y", "type": "website"}],
            sales_status_key="",
        )
        # from_dict-like sources via SourceRef happens in from_dict; construct carefully
        from schema import SourceRef
        robot.sources = [SourceRef(url="https://m.example/y", type="website")]
        result = validate_robot(robot)
        sales_errors = [i for i in result.issues if i.field.startswith("sales_status") and i.level == "error"]
        self.assertEqual(sales_errors, [])


class ExcludeSnapshotTests(unittest.TestCase):
    def test_loads_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "snap.json"
            path.write_text(
                '{"rows":[{"id":11},{"robot_id":22}]}',
                encoding="utf-8",
            )
            ids = assess_mod.load_excluded_ids([path])
            self.assertEqual(ids, {11, 22})


if __name__ == "__main__":
    unittest.main()
