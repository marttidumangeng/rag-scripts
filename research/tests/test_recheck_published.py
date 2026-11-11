"""recheck_published: page classification, spec comparison, Gemini parsing,
verdicts, selection and the runner with fetch, search, Gemini and the API faked.
From scripts/research:

    python -m unittest tests.test_recheck_published
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any

_RESEARCH_DIR = Path(__file__).resolve().parents[1]
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

import recheck_published as rp  # noqa: E402
from recheck_published import Probe, PublishedRecheck, classify, parse_freshness, reasons_for, spec_diffs  # noqa: E402

LONG = "Industrial robot arm product page. " * 40


class ClassifyTests(unittest.TestCase):
    def test_ok_page(self):
        self.assertEqual(classify("https://x.com/p/a1", 200, "https://x.com/p/a1", "A1", LONG)[0], "ok")

    def test_dead_codes(self):
        self.assertEqual(classify("https://x.com/p", 404, "https://x.com/p", "", "")[0], "dead")
        self.assertEqual(classify("https://x.com/p", 410, "https://x.com/p", "", "")[0], "dead")

    def test_rate_limit_and_walls_are_blocked_not_dead(self):
        for code in (403, 406, 418, 429):
            self.assertEqual(classify("https://x.com/p", code, "https://x.com/p", "", "")[0], "blocked")

    def test_connection_error_is_unreachable(self):
        self.assertEqual(classify("https://x.com/p", None, "", "", "", "SSLError")[0], "unreachable")

    def test_soft404_by_title(self):
        self.assertEqual(classify("https://x.com/p", 200, "https://x.com/p", "Page Not Found", LONG)[0], "soft404")

    def test_soft404_chinese_body(self):
        body = "抱歉，您访问的页面不存在 " + "导航 " * 200
        self.assertEqual(classify("https://x.cn/p", 200, "https://x.cn/p", "", body)[0], "soft404")

    def test_long_page_mentioning_404_elsewhere_is_ok(self):
        body = LONG * 3 + " error 404 troubleshooting guide"
        self.assertEqual(classify("https://x.com/p", 200, "https://x.com/p", "A1", body)[0], "ok")

    def test_spa_shell_is_empty(self):
        self.assertEqual(classify("https://x.com/p", 200, "https://x.com/p", "Fourier", "Loading")[0], "empty")

    def test_deep_link_redirected_to_home(self):
        self.assertEqual(classify("https://x.com/products/a1", 200, "https://x.com/", "Home", LONG)[0], "redirected_home")

    def test_homepage_url_staying_home_is_ok(self):
        self.assertEqual(classify("https://x.com/", 200, "https://x.com/", "Home", LONG)[0], "ok")

    def test_no_url(self):
        self.assertEqual(classify("", None, "", "", "")[0], "no_url")


class SpecDiffTests(unittest.TestCase):
    def test_within_tolerance_is_not_a_diff(self):
        self.assertEqual(spec_diffs({"payload_kg": 10, "reach_mm": 1000}, {"payload_kg": 10.2, "reach_mm": 1010}), [])

    def test_real_diff_reported(self):
        d = spec_diffs({"payload_kg": 10, "dof": 6}, {"payload_kg": 12, "dof": 7})
        self.assertEqual({x["field"] for x in d}, {"payload_kg", "dof"})

    def test_missing_side_ignored(self):
        self.assertEqual(spec_diffs({"payload_kg": None}, {"payload_kg": 5}), [])
        self.assertEqual(spec_diffs({"payload_kg": 5}, {}), [])


class FreshnessParseTests(unittest.TestCase):
    def test_parses_fenced_json(self):
        r = parse_freshness('```json\n{"product_status": "Replaced", "successor": "A2", "confidence": "high"}\n```')
        self.assertEqual(r["product_status"], "replaced")
        self.assertEqual(r["successor"], "A2")

    def test_unknown_status_becomes_unclear(self):
        self.assertEqual(parse_freshness('{"product_status": "maybe"}')["product_status"], "unclear")

    def test_garbage_is_none(self):
        self.assertIsNone(parse_freshness("not json"))
        self.assertIsNone(parse_freshness("[1,2]"))


class RealConflictTests(unittest.TestCase):
    """Cases from the 2026-11-11 VisionNav pilot, where Gemini flagged unit changes."""

    def test_same_quantity_other_unit_is_not_a_conflict(self):
        for c in ({"field": "payload_kg", "ours": "3000.0", "page": "3000kg"},
                  {"field": "payload_kg", "ours": "2800.0", "page": "6180 lb"},
                  {"field": "speed", "ours": "7.92", "page": "2.2m/s"},
                  {"field": "speed", "ours": "9.0", "page": "5.59 mph"},
                  {"field": "speed", "ours": "7.2", "page": "4.47mph"},
                  {"field": "reach_mm", "ours": "1500", "page": "1.5 m"},
                  {"field": "runtime_minutes", "ours": "480", "page": "8 hours"},
                  {"field": "runtime_minutes", "ours": "90", "page": "90 min"},
                  {"field": "weight_kg", "ours": "0.907", "page": "Mavic 2 Pro: 907 g"},
                  {"field": "speed", "ours": "72.0 km/h", "page": "20 meters per second"}):
            self.assertFalse(rp.real_conflict(c), c)

    def test_real_difference_kept(self):
        self.assertTrue(rp.real_conflict({"field": "payload_kg", "ours": "1500", "page": "2000 kg"}))
        self.assertTrue(rp.real_conflict({"field": "dof", "ours": "6", "page": "7"}))
        self.assertTrue(rp.real_conflict({"field": "other", "ours": "", "page": "IP54"}))

    def test_ours_inside_family_range_is_not_a_conflict(self):
        self.assertFalse(rp.real_conflict({"field": "payload_kg", "ours": "20.0", "page": "20 to 60 kg"}))
        self.assertFalse(rp.real_conflict({"field": "payload_kg", "ours": "110", "page": "90–180 kg"}))
        self.assertFalse(rp.real_conflict({"field": "reach_mm", "ours": "900", "page": "0.9 to 1.4 m"}))
        self.assertTrue(rp.real_conflict({"field": "payload_kg", "ours": "180", "page": "220–310 kg"}))

    def test_empty_ours_is_missing_data_not_conflict(self):
        self.assertFalse(rp.real_conflict({"field": "payload_kg", "ours": "", "page": "1500 kg"}))

    def test_parse_freshness_drops_unit_only_conflicts(self):
        r = parse_freshness('{"product_status": "current", "spec_conflicts": ['
                            '{"field": "speed", "ours": "7.92", "page": "2.2m/s"},'
                            '{"field": "payload_kg", "ours": "1500", "page": "2000kg"}]}')
        self.assertEqual([c["field"] for c in r["spec_conflicts"]], ["payload_kg"])


class GroundConflictTests(unittest.TestCase):
    def test_invented_ours_dropped_and_real_ours_used(self):
        robot = {"repeatability_mm": None, "weight_kg": 14.0, "payload_kg": 9.0}
        fr = {"spec_conflicts": [
            {"field": "repeatability_mm", "ours": "0.35", "page": "0.05"},   # we hold none: invented
            {"field": "weight_kg", "ours": "99", "page": "21 kg"},           # real, ours replaced by 14
            {"field": "payload_kg", "ours": "7", "page": "9 kg"},            # our 9 agrees with the page
            {"field": "other", "ours": "", "page": "IP67"}]}
        rp.ground_conflicts(robot, fr)
        self.assertEqual([(c["field"], c["ours"]) for c in fr["spec_conflicts"]], [("weight_kg", 14.0), ("other", "")])


class VerdictTests(unittest.TestCase):
    def test_clean_record_has_no_reasons(self):
        rec = {"page_status": "ok", "model_on_page": True, "spec_diffs": [],
               "freshness": {"product_status": "current", "confidence": "high"}}
        self.assertEqual(reasons_for(rec), [])
        self.assertEqual(rp.priority_of([]), "")

    def test_discontinued_needs_confidence(self):
        low = {"page_status": "ok", "model_on_page": True, "freshness": {"product_status": "discontinued", "confidence": "low"}}
        self.assertEqual(reasons_for(low), [])
        high = {"page_status": "ok", "model_on_page": True,
                "freshness": {"product_status": "replaced", "confidence": "high", "successor": "A2"}}
        r = reasons_for(high)
        self.assertEqual(r, ["replaced -> A2"])
        self.assertEqual(rp.priority_of(r), "high")

    def test_dead_page_is_high(self):
        r = reasons_for({"page_status": "dead", "model_on_page": None})
        self.assertEqual(rp.priority_of(r), "high")

    def test_name_match_overrules_gemini_not_on_page(self):
        rec = {"page_status": "ok", "model_on_page": True, "freshness": {"product_status": "not_on_page", "confidence": "high"}}
        self.assertEqual(reasons_for(rec), [])

    def test_support_page_flagged(self):
        rec = {"page_status": "ok", "model_on_page": True, "url": "https://www.dji.com/global/support/product/mavic-2",
               "freshness": {"product_status": "unclear", "confidence": "medium"}}
        r = reasons_for(rec)
        self.assertEqual(r, ["source is a support/archive page (product may be retired)"])
        self.assertEqual(rp.priority_of(r), "medium")
        rec["url"] = "https://www.dji.com/global/mavic-4-pro"
        self.assertEqual(reasons_for(rec), [])

    def test_successor_named_robot_on_old_page(self):
        rec = {"page_status": "ok", "model_on_page": True, "name": "IRB 1200-9/0.7 Gen2",
               "freshness": {"product_status": "replaced", "confidence": "high",
                             "successor": "IRB 1200 Next Gen (Gen 2) Family"}}
        r = reasons_for(rec)
        self.assertEqual(r, ["source page is the predecessor's page"])
        self.assertEqual(rp.priority_of(r), "medium")
        rec["name"] = "IRB 1200"
        self.assertEqual(rp.priority_of(reasons_for(rec)), "high")

    def test_family_page_not_named_but_current_is_low(self):
        self.assertEqual(rp.priority_of(["model not named on source page"], {"product_status": "current"}), "low")
        self.assertEqual(rp.priority_of(["model not named on source page"], {"product_status": "not_on_page"}), "medium")

    def test_blocked_page_is_not_flagged(self):
        self.assertEqual(reasons_for({"page_status": "blocked", "model_on_page": None}), [])

    def test_gemini_conflicts_not_double_counted(self):
        rec = {"page_status": "ok", "model_on_page": True, "spec_diffs": [{"field": "payload_kg", "ours": 1, "page": 2}],
               "freshness": {"product_status": "current", "confidence": "high",
                             "spec_conflicts": [{"field": "payload_kg"}, {"field": "speed"}]}}
        self.assertEqual(reasons_for(rec), ["spec differs: payload_kg", "page states different: speed"])


class SelectionTests(unittest.TestCase):
    class Api:
        def __init__(self, pages):
            self.pages = pages

        def _get(self, path, params=None):
            return self.pages[params["page"] - 1]

    def test_stops_at_cutoff_and_filters_company(self):
        def row(i, d, cid):
            return {"id": i, "name": f"R{i}", "published_at": (d + "T00:00:00Z") if d else None, "company_ref": {"id": cid, "name": f"C{cid}"}}
        api = self.Api([{"results": [row(1, "2026-02-01", 5), row(2, "", 5), row(3, "2026-07-01", 6)], "next": "p2"},
                        {"results": [row(4, "2026-08-01", 5), row(5, "2026-09-01", 5)], "next": "p3"},
                        {"results": [row(6, "2026-10-01", 5)], "next": None}])
        rows = rp.stale_robots(api, "2026-08-13")
        self.assertEqual([r["id"] for r in rows], [1, 3, 4])
        self.assertEqual([r["id"] for r in rp.stale_robots(api, "2026-08-13", company_ids=[5])], [1, 4])

    def test_order_by_company_groups_biggest_first(self):
        rows = [{"id": 1, "company_id": 9, "published_at": "a"}, {"id": 2, "company_id": 7, "published_at": "a"},
                {"id": 3, "company_id": 7, "published_at": "b"}]
        self.assertEqual([r["id"] for r in rp.order_by_company(rows)], [2, 3, 1])


class FakeFetcher:
    def __init__(self, probes: dict[str, Probe]):
        self.probes = probes
        self.requests = 0
        self.rescues = 0

    def probe(self, url):
        self.requests += 1
        return self.probes.get(url) or Probe(url=url, status="no_url" if not url else "dead", http=404)


class FakeApi:
    def __init__(self, robots: dict[int, dict[str, Any]], companies: dict[int, dict[str, Any]]):
        self.robots, self.companies = robots, companies
        self.writes = 0

    def _get(self, path, params=None):
        kind, _, rest = path.partition("/")
        if kind == "robots":
            return self.robots[int(rest.strip("/").split("/")[-1])]
        return self.companies[int(rest.strip("/"))]

    def _patch(self, *a, **k):  # pragma: no cover - must never be called
        self.writes += 1

    _post = _patch


class RunnerTests(unittest.TestCase):
    def make(self, **kw):
        robots = {
            1: {"id": 1, "name": "A1", "model_name": "A1", "status": "published", "url": "https://maker.com/a1", "payload_kg": 10},
            2: {"id": 2, "name": "B2", "model_name": "B2", "status": "published", "url": "https://maker.com/b2"},
            3: {"id": 3, "name": "C3", "status": "draft", "url": "https://maker.com/c3"},
        }
        companies = {5: {"id": 5, "website": "https://maker.com", "publication_status": "published"}}
        page_a1 = Probe(url="https://maker.com/a1", status="ok", http=200, final_url="https://maker.com/a1", title="A1",
                        text="A1 robot. Payload: 12 kg. " + LONG, full_text="A1 robot. Payload: 12 kg. " + LONG)
        home = Probe(url="https://maker.com", status="ok", http=200, final_url="https://maker.com/", text=LONG, full_text=LONG)
        fetcher = FakeFetcher({"https://maker.com/a1": page_a1, "https://maker.com": home})
        searches: list[str] = []
        calls: list[int] = []

        def search(q, num=8):
            searches.append(q)
            return [{"link": "https://maker.com/b2-new", "title": "B2", "snippet": "B2 Pro"}]

        def fresh(robot, company, probe, snippets):
            calls.append(robot["id"])
            return {"product_status": "current", "confidence": "high", "spec_conflicts": []}

        api = FakeApi(robots, companies)
        job = PublishedRecheck(api, fetcher=fetcher, search=search, freshness=fresh, **kw)
        rows = [{"id": i, "name": robots[i]["name"], "company_id": 5, "company": "Maker", "published_at": "2026-07-01"}
                for i in (1, 2, 3)]
        return job, rows, api, searches, calls

    def test_run_flags_and_never_writes(self):
        job, rows, api, searches, calls = self.make()
        job.run(rows, limit=10)
        by_id = {r["robot_id"]: r for r in job.records}
        self.assertEqual(by_id[1]["page_status"], "ok")
        self.assertEqual(by_id[1]["reasons"], [])  # regex specs are off when Gemini runs
        self.assertEqual(by_id[2]["page_status"], "dead")
        self.assertEqual(by_id[2]["priority"], "high")
        self.assertEqual(by_id[2]["candidate_pages"], ["https://maker.com/b2-new"])
        self.assertTrue(searches[0].endswith("site:maker.com"))
        self.assertEqual(by_id[3]["skipped"], "status now draft")
        self.assertEqual(calls, [1])            # Gemini only for the live page
        self.assertEqual(job.stats.companies, 1)  # maker probed once
        self.assertEqual(api.writes, 0)

    def test_gemini_cap(self):
        job, rows, _, _, calls = self.make(max_gemini=0)
        job.run(rows, limit=10)
        self.assertEqual(calls, [])
        self.assertEqual(job.stats.gemini_skipped_cap, 1)

    def test_search_cap(self):
        job, rows, _, searches, _ = self.make(max_searches=0)
        job.run(rows, limit=10)
        self.assertEqual(searches, [])

    def test_no_gemini(self):
        job, rows, _, _, calls = self.make(use_gemini=False)
        job.run(rows, limit=10)
        self.assertEqual(calls, [])
        self.assertIn("spec differs: payload_kg", job.records[0]["reasons"])

    def test_budget_exceeded_stops_run(self):
        class SpendBudgetExceeded(RuntimeError):
            pass
        job, rows, _, _, _ = self.make()

        def boom(*a, **k):
            raise SpendBudgetExceeded("daily cap")
        job.freshness = boom
        job.run(rows, limit=10)
        self.assertEqual(len(job.records), 0)

    def test_maker_redirect_flagged(self):
        job, rows, _, _, _ = self.make()
        job.fetcher.probes["https://maker.com"] = Probe(url="https://maker.com", status="ok", http=200,
                                                        final_url="https://newowner.com/", text=LONG, full_text=LONG)
        job.run(rows[:1], limit=1)
        self.assertEqual(job.companies[5]["reasons"], ["website now redirects to newowner.com"])


if __name__ == "__main__":
    unittest.main()
