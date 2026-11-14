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

    def _row(self, rid, **extra):
        row = {
            "id": str(rid), "name": f"Bot {rid}", "current_status": "not_assessed",
            "proposed_sales_status": "general_sale", "source_url": f"https://m.example/{rid}",
            "decision": "accept", "checked_on": "2026-11-14",
        }
        row.update(extra)
        return row

    def test_sends_assess_date_not_today(self):
        batch, _ = apply_mod.build_batch_rows([self._row(1)])
        self.assertEqual(batch[0]["checked_on"], "2026-11-14")

    def test_missing_checked_on_falls_back_with_note(self):
        batch, skips = apply_mod.build_batch_rows([self._row(1, checked_on="")])
        self.assertEqual(len(batch), 1)
        self.assertTrue(any("checked_on" in s for s in skips))

    def test_repeated_id_sent_once(self):
        batch, skips = apply_mod.build_batch_rows([self._row(1), self._row(1, decision="pre_order")])
        self.assertEqual([r["sales_status"] for r in batch], ["general_sale"])
        self.assertTrue(any("repeated id" in s for s in skips))

    def test_non_numeric_id_skipped(self):
        batch, skips = apply_mod.build_batch_rows([self._row("abc")])
        self.assertEqual(batch, [])
        self.assertTrue(any("not a number" in s for s in skips))

    def test_chunks_at_200(self):
        rows = [{"id": i} for i in range(450)]
        self.assertEqual([len(c) for c in apply_mod.chunked(rows)], [200, 200, 50])


class EvidenceCheckTests(unittest.TestCase):
    PAGE = "https://maker.example/robot-x"
    TEXT = "Robot X. Orders are open now — “Reserve yours today”. Deliveries start in 2027."

    def test_real_quote_on_page_passes(self):
        from sales_evidence import verify_sales_evidence
        ok, why = verify_sales_evidence(
            "pre_order", "Orders are open now", self.PAGE + "/", [(self.PAGE, self.TEXT)],
        )
        self.assertTrue(ok, why)

    def test_curly_quotes_and_case_normalized(self):
        from sales_evidence import quote_in_text
        self.assertTrue(quote_in_text('"reserve yours today"', self.TEXT))

    def test_invented_quote_fails(self):
        from sales_evidence import verify_sales_evidence
        ok, why = verify_sales_evidence(
            "general_sale", "Available to order now from our shop", self.PAGE, [(self.PAGE, self.TEXT)],
        )
        self.assertFalse(ok)
        self.assertIn("not found", why)

    def test_url_must_be_the_page_with_the_quote(self):
        from sales_evidence import verify_sales_evidence
        ok, why = verify_sales_evidence(
            "pre_order", "Orders are open now", "https://other.example/x", [(self.PAGE, self.TEXT)],
        )
        self.assertFalse(ok)

    def test_too_short_quote_fails(self):
        from sales_evidence import quote_in_text
        self.assertFalse(quote_in_text("Robot X", self.TEXT))

    def test_assess_downgrades_unverified(self):
        probe = assess_mod.Probe(url=self.PAGE, status="ok", final_url=self.PAGE, text=self.TEXT, full_text=self.TEXT)
        out = assess_mod.apply_evidence_check({
            "sales_status": "general_sale", "confidence": "high",
            "quote": "Buy it now in our online store", "source_url": self.PAGE, "reason": "shop",
        }, probe)
        self.assertEqual(out["sales_status"], "unclear")
        self.assertEqual(out["confidence"], "low")

    def test_assess_keeps_verified(self):
        probe = assess_mod.Probe(url=self.PAGE, status="ok", final_url=self.PAGE, text=self.TEXT, full_text=self.TEXT)
        out = assess_mod.apply_evidence_check({
            "sales_status": "pre_order", "confidence": "high",
            "quote": "Orders are open now", "source_url": self.PAGE, "reason": "deposit",
        }, probe)
        self.assertEqual(out["sales_status"], "pre_order")


class BulkImportMappingTests(unittest.TestCase):
    def test_checked_on_passed_only_with_status(self):
        from map_to_bulk_import import staging_robot_to_bulk_import_row
        robot = StagedRobot(
            name="Bot", sales_status_key="pre_order", sales_status_source_url="https://m.example/p",
            sales_status_quote="Orders are open now", sales_status_checked_on="2026-11-14",
        )
        row = staging_robot_to_bulk_import_row(robot)
        self.assertEqual(row["sales_status_checked_on"], "2026-11-14")
        bare = staging_robot_to_bulk_import_row(StagedRobot(name="Bot"))
        self.assertEqual(bare.get("sales_status_checked_on", ""), "")


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
