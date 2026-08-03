"""Spend-guard tests: budget mechanics + a drift guard so no pipeline module
can construct an unmetered Gemini client.

Context (2026-08-02): Gemini spend nearly doubled in a day ($42.75 -> $76) and
nothing noticed until the human read the bill, because nothing counted calls.
The meter (spend_guard.py) only works if every call site goes through it —
the drift test makes bypassing it a test failure instead of a billing incident.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

_RESEARCH_DIR = Path(__file__).resolve().parents[1]
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

import spend_guard


# Modules the NIGHTLY PIPELINE imports (directly or transitively). One-off
# manual fix scripts (fix_*.py, *_enrich.py etc.) are excluded on purpose:
# they're human-run, low-volume, and forcing the refactor there adds risk
# without touching the runaway-spend problem.
PIPELINE_MODULES = [
    "verify_lib.py",
    "discover_robots.py",
    "product_url_search.py",
    "release_year_lookup.py",
    "company_country_resolve.py",
    "robot_auto_research.py",
    "company_research.py",
    "grounded_select.py",
    "overnight_queue_enrich.py",
    "overnight_greenfield_import.py",
    "remedy_dryrun.py",
    "rejection_feedback_loop.py",
    "resolve_pending_company_gaps.py",
    "smoke_test.py",
]

_RAW_CLIENT_RE = re.compile(r"genai\.Client\(")


class TestNoUnmeteredClients(unittest.TestCase):
    def test_pipeline_modules_use_spend_guard(self):
        """Raw genai.Client( in a pipeline module bypasses the daily budget."""
        offenders: list[str] = []
        for name in PIPELINE_MODULES:
            path = _RESEARCH_DIR / name
            if not path.exists():
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for i, line in enumerate(text.splitlines(), 1):
                if _RAW_CLIENT_RE.search(line) and "spend_guard" not in line:
                    offenders.append(f"{name}:{i}: {line.strip()}")
        self.assertEqual(
            offenders, [],
            "unmetered genai.Client( construction in pipeline modules — route "
            "through spend_guard.client() so the call counts against the daily "
            "budget:\n" + "\n".join(offenders),
        )


class TestBudgetMechanics(unittest.TestCase):
    def setUp(self):
        # Redirect the ledger to a temp file so tests never touch real state.
        import tempfile
        self._tmp = Path(tempfile.mkdtemp())
        self._orig_path = spend_guard.STATE_PATH
        spend_guard.STATE_PATH = self._tmp / "gemini_spend.json"

    def tearDown(self):
        spend_guard.STATE_PATH = self._orig_path

    def test_charges_accumulate_and_cap(self):
        import os
        os.environ["GEMINI_DAILY_CALL_BUDGET"] = "3"
        try:
            spend_guard.charge("t")
            spend_guard.charge("t")
            spend_guard.charge("t")
            with self.assertRaises(spend_guard.SpendBudgetExceeded):
                spend_guard.charge("t")
            st = spend_guard.status()
            self.assertEqual(st["calls"], 3)
            self.assertEqual(st["budget"], 3)
        finally:
            del os.environ["GEMINI_DAILY_CALL_BUDGET"]

    def test_day_rollover_resets(self):
        spend_guard.charge("t")
        data = spend_guard._load()
        data["date"] = "2000-01-01"  # simulate yesterday's ledger
        spend_guard._save(data)
        st = spend_guard.status()
        self.assertEqual(st["calls"], 0, "a stale date must reset the counter")

    def test_metered_client_charges_before_call(self):
        import os
        os.environ["GEMINI_DAILY_CALL_BUDGET"] = "1"
        try:
            calls = []

            class FakeModels:
                def generate_content(self, *a, **k):
                    calls.append(k.get("model"))
                    return "ok"

            class FakeClient:
                models = FakeModels()

            metered = spend_guard._MeteredClient(FakeClient())
            self.assertEqual(metered.models.generate_content(model="m1"), "ok")
            with self.assertRaises(spend_guard.SpendBudgetExceeded):
                metered.models.generate_content(model="m2")
            self.assertEqual(calls, ["m1"], "the over-budget call must never reach the API")
        finally:
            del os.environ["GEMINI_DAILY_CALL_BUDGET"]


if __name__ == "__main__":
    unittest.main()
