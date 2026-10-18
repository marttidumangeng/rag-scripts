"""recheck_company_funding: parsing, comparison with milestones, and the runner
with search, fetch, extraction and the API all faked. From scripts/research:

    python -m unittest tests.test_recheck_company_funding
"""
from __future__ import annotations

import sys
import unittest
import unittest.mock
from datetime import date
from pathlib import Path
from typing import Any

import requests

_RESEARCH_DIR = Path(__file__).resolve().parents[1]
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

import recheck_company_funding as rcf  # noqa: E402
from recheck_company_funding import (  # noqa: E402
    FundingRecheck, Round, amounts_in_text, change_payload, format_amount, match_existing, normalise_round,
    parse_round_date, rounds_from_json, select_links, summary_for_round,
)


class ParsingTests(unittest.TestCase):
    def test_round_dates_and_precision(self):
        self.assertEqual(parse_round_date("2026-02-11"), (date(2026, 2, 11), "day"))
        self.assertEqual(parse_round_date("2026-02"), (date(2026, 2, 1), "month"))
        self.assertEqual(parse_round_date("2026"), (date(2026, 1, 1), "year"))
        self.assertIsNone(parse_round_date("Feb 2026"))
        self.assertIsNone(parse_round_date("2026-13"))

    def test_round_labels(self):
        self.assertEqual(normalise_round("Series A extension"), "Series A")
        self.assertEqual(normalise_round("series-a+"), "Series A+")
        self.assertEqual(normalise_round("Pre-A"), "Pre-A")
        self.assertEqual(normalise_round("acquired by Hyundai"), "Acquisition")
        self.assertEqual(normalise_round(""), "Funding round")
        self.assertEqual(normalise_round("Bridge"), "Bridge")

    def test_amount_formatting(self):
        self.assertEqual(format_amount(520_000_000, "USD"), "US$520M")
        self.assertEqual(format_amount(22_600_000, "GBP"), "GBP 22.6M")
        self.assertEqual(format_amount(1_500_000_000, "CNY"), "CNY 1.5B")
        self.assertEqual(format_amount(None, None, "hundreds of millions of yuan"), "hundreds of millions of yuan")
        self.assertEqual(format_amount(None, None), "amount undisclosed")

    def test_summaries(self):
        self.assertEqual(summary_for_round(Round("2026-02-11", "Series A", 520e6, "USD", lead_investors=["B Capital"])),
                         "Raised a US$520M Series A led by B Capital")
        self.assertEqual(summary_for_round(Round("2026", "Acquisition", 1.1e9, "USD", lead_investors=["Hyundai"])),
                         "Acquired by Hyundai for US$1.1B")
        self.assertEqual(summary_for_round(Round("2026-04", "Series A", None, None, amount_text="hundreds of millions of yuan")),
                         "Raised a Series A (hundreds of millions of yuan)")
        self.assertEqual(summary_for_round(Round("2026-04", "Angel", None, None)), "Raised an Angel (amount undisclosed)")
        self.assertEqual(summary_for_round(Round("2026-06-10", "Funding round", 1.5e9, "CNY")), "Raised a CNY 1.5B funding round")
        self.assertEqual(summary_for_round(Round("2026-08-11", "Strategic", None, None, amount_text="several hundred million yuan",
                                                 lead_investors=["Ant Group"])),
                         "Raised a strategic round (several hundred million yuan) led by Ant Group")
        self.assertEqual(normalise_round("Other"), "Funding round")
        self.assertEqual(summary_for_round(Round("2023-11", "Acquisition", None, None, amount_text="undisclosed",
                                                 lead_investors=["Agile Robots"])), "Acquired by Agile Robots")
        self.assertEqual(summary_for_round(Round("2022", "Seed", None, None, amount_text="Undisclosed")),
                         "Raised a Seed (amount undisclosed)")
        self.assertEqual(summary_for_round(Round("2026-02-11", "Series A", 520e6, "USD", lead_investors=["B Capital"],
                                                 participating_investors=["AT&T Ventures", "John Deere", "B Capital"])),
                         "Raised a US$520M Series A led by B Capital with AT&T Ventures, John Deere")
        self.assertEqual(summary_for_round(Round("2025", "Seed", 5e6, "USD", participating_investors=["Y Combinator"])),
                         "Raised a US$5M Seed from Y Combinator")

    def test_stage_mapping(self):
        self.assertEqual(rcf.stage_from_rounds([Round("2024", "Seed", None, None), Round("2026", "Series B", 1, "USD"),
                                                Round("2026", "Acquisition", None, None)]), "series_b")
        self.assertIsNone(rcf.stage_from_rounds([Round("2026", "Grant", None, None)]))
        self.assertTrue(rcf.stage_is_later("series_b", "series_a"))
        self.assertTrue(rcf.stage_is_later("seed", ""))
        self.assertFalse(rcf.stage_is_later("series_a", "series_a"))
        self.assertFalse(rcf.stage_is_later("series_a", "public_company"))
        self.assertFalse(rcf.stage_is_later(None, ""))

    def test_unopened_results_become_their_own_evidence_blocks(self):
        job = FundingRecheck(FakeApi({}), search=lambda q: [
            {"link": "https://press.example/a", "title": "A raises", "snippet": "US$5M seed", "date": "Jan 1, 2026"},
            {"link": "https://press.example/b", "title": "B", "snippet": "later round", "date": ""},
            {"link": "https://www.crunchbase.com/organization/a", "title": "A", "snippet": "x"},
        ], fetch=lambda url: "page text", extract=lambda c, e: [], searches_per_company=1, pages_per_company=1, run_id="t")
        evidence = job.evidence_for({"name": "A", "website": "https://a.example"})
        self.assertEqual([e["url"] for e in evidence], ["https://press.example/a", "https://press.example/b"])
        self.assertTrue(evidence[1]["text"].startswith("Search result"))

    def test_amounts_in_milestone_text(self):
        self.assertIn(520_000_000, amounts_in_text("Closed a US$520 million Series A extension"))
        self.assertIn(415_000_000, amounts_in_text("Raised an oversubscribed US$415M initial Series A"))
        self.assertIn(1_000_000_000, amounts_in_text("CNY 1B (~US$140M) Series A"))
        self.assertEqual(amounts_in_text("Founded in Austin"), set())

    def test_rounds_from_json_maps_sources_and_drops_junk(self):
        evidence = [{"url": "https://maker.example/news", "text": ""}, {"url": "https://press.example/a", "text": ""}]
        rounds = rounds_from_json({"rounds": [
            {"date": "2026-02-11", "round": "series a extension", "amount": "520000000", "currency": "usd",
             "source_index": 1, "source_kind": "company", "confidence": "high", "lead_investors": ["B Capital", ""]},
            {"date": "sometime", "round": "Seed", "amount": 1},
            {"date": "2025", "round": "Seed", "amount": -5, "source_index": 9},
        ]}, evidence)
        self.assertEqual(len(rounds), 2)
        self.assertEqual((rounds[0].round, rounds[0].amount, rounds[0].currency, rounds[0].source_url),
                         ("Series A", 520e6, "USD", "https://maker.example/news"))
        self.assertEqual(rounds[0].lead_investors, ["B Capital"])
        self.assertEqual((rounds[1].amount, rounds[1].source_url), (None, ""))
        self.assertEqual(rounds_from_json("nonsense", evidence), [])


class CollapseTests(unittest.TestCase):
    def test_same_event_from_press_and_company_keeps_the_company_source(self):
        press = Round("2026-02-25", "Seed", 280e6, "USD", source_url="https://press.example", source_kind="press",
                      confidence="high", lead_investors=["Yunfeng Capital"])
        own = Round("2026-02", "Seed", 280e6, "USD", source_url="https://spirit.example/news/30", source_kind="company",
                    confidence="high", lead_investors=["Chaos Investment"])
        other = Round("2026-03-31", "Pre-A", 528e6, "CNY", source_kind="company")
        press.participating_investors = ["Synstellation", "Chaos Investment"]
        kept = rcf.collapse_rounds([press, own, other])
        self.assertEqual([r.source_url for r in kept], ["https://spirit.example/news/30", ""])
        self.assertEqual(kept[0].lead_investors, ["Chaos Investment", "Yunfeng Capital"])
        self.assertEqual(kept[0].participating_investors, ["Synstellation"])  # a lead is not also a participant

    def test_different_amounts_stay_separate(self):
        a = Round("2026", "Seed", 280e6, "USD")
        b = Round("2026", "Seed", 1.5e9, "CNY")
        self.assertEqual(len(rcf.collapse_rounds([a, b])), 2)


class DealMadeTests(unittest.TestCase):
    def test_deals_the_company_made_are_dropped(self):
        drop = [
            ("Thermo Fisher Scientific", "Thermo Fisher Scientific to acquire PPD for US$17.4 billion in cash."),
            ("Brooks Automation", "Brooks Automation sold its semiconductor business to Thomas H. Lee Partners for US$3 billion."),
            ("Hydrex", "Hydrex acquired VertiDrive B.V., maker of magnetic blasting crawlers."),
            ("PongBot", "The Pace series raised more than US$2.7 million on Kickstarter."),
            ("Anduril Industries", "Anduril Industries invested in a drone maker last year."),
        ]
        for name, quote in drop:
            with self.subTest(name=name):
                self.assertTrue(rcf.is_deal_made_by(name, Round("2021", "Acquisition", 1, "USD", quote=quote)))

    def test_money_the_company_received_is_kept(self):
        keep = [
            ("Anduril Industries", "Anduril Industries raised US$2.5 billion in a Series G led by Founders Fund."),
            ("Universal Robots", "Universal Robots was acquired by Teradyne for US$285 million."),
            ("Boston Dynamics", "Hyundai acquired Boston Dynamics for about US$1.1 billion."),
            ("Mecka AI", "Mecka AI announced a US$60M Series B led by Sequoia."),
            ("Cleveron", "Cleveron raises EUR 2.2 million, sells package machines in the US."),
            ("Franka Robotics", "Franka Robotics (force-sensitive robotic arms, acquired by Agile Robots for about EUR 33 million)."),
            ("Acme Robotics", "Acme Robotics secured US$5M and acquired a small software team."),
            ("Kinova", ""),
        ]
        for name, quote in keep:
            with self.subTest(name=name):
                self.assertFalse(rcf.is_deal_made_by(name, Round("2021", "Series A", 1, "USD", quote=quote)))


class MatchingTests(unittest.TestCase):
    milestones = [
        {"year": 2026, "description": "Closed a US$520 million Series A extension (Series A-X) on 11 February 2026",
         "source_url": "https://apptronik.com/news"},
        {"year": 2025, "description": "Raised an oversubscribed US$415 million initial Series A", "source_url": ""},
        {"year": 2016, "description": "Founded in Austin, Texas", "source_url": ""},
    ]

    def test_same_round_same_amount_is_known(self):
        rel, m = match_existing(Round("2026-02-11", "Series A", 520e6, "USD"), self.milestones)
        self.assertEqual(rel, "known")
        self.assertEqual(m["year"], 2026)

    def test_same_round_other_amount_is_mismatch(self):
        rel, m = match_existing(Round("2025-02", "Series A", 350e6, "USD"), self.milestones)
        self.assertEqual((rel, m["year"]), ("mismatch", 2025))

    def test_unknown_round_label_matches_on_amount(self):
        rel, _ = match_existing(Round("2025", "Funding round", 415e6, "USD"), self.milestones)
        self.assertEqual(rel, "known")

    def test_other_year_is_new(self):
        rel, m = match_existing(Round("2024-06", "Seed", 5e6, "USD"), self.milestones)
        self.assertEqual((rel, m), ("new", None))

    def test_undisclosed_amount_same_round_is_known(self):
        rel, _ = match_existing(Round("2026", "Series A", None, None, amount_text="undisclosed"), self.milestones)
        self.assertEqual(rel, "known")

    def test_two_percent_tolerance(self):
        rel, _ = match_existing(Round("2026", "Series A", 525e6, "USD"), self.milestones)
        self.assertEqual(rel, "known")


class LinkSelectionTests(unittest.TestCase):
    def test_skips_paid_databases_and_ranks_company_and_filings_first(self):
        results = [
            {"link": "https://www.crunchbase.com/organization/x", "title": "X funding", "snippet": "raised"},
            {"link": "https://techcrunch.com/2026/02/11/x-raises", "title": "X raises $520M", "snippet": "Series A"},
            {"link": "https://www.linkedin.com/company/x", "title": "X", "snippet": ""},
            {"link": "https://x.example/news/series-a", "title": "X closes Series A", "snippet": "raised"},
            {"link": "https://www.sec.gov/Archives/edgar/x", "title": "Form D", "snippet": "offering"},
            {"link": "https://techcrunch.com/2026/02/11/x-raises", "title": "dupe", "snippet": ""},
            {"link": "https://blog.example/x-is-cool", "title": "X is cool", "snippet": "robots"},
        ]
        picked = [i["link"] for i in select_links(results, "https://x.example", 3)]
        self.assertEqual(picked, ["https://x.example/news/series-a", "https://www.sec.gov/Archives/edgar/x",
                                  "https://techcrunch.com/2026/02/11/x-raises"])

    def test_payload_shape(self):
        r = Round("2026-02", "Series B", 60e6, "USD", source_url="https://maker.example/news", source_kind="company",
                  quote="Maker today announced a $60M Series B.")
        p = change_payload(14, r, "new", None, "run1")
        self.assertEqual((p["company"], p["event_type"], p["occurred_on"], p["date_precision"], p["confidence"], p["status"]),
                         (14, "funding", "2026-02-01", "month", "verified", "draft"))
        self.assertEqual(p["summary"], "Raised a US$60M Series B")
        self.assertIn("quote:", p["review_note"])
        press = change_payload(14, Round("2026", "Seed", None, None, source_kind="press"), "mismatch",
                               {"year": 2026, "description": "Raised a US$5M seed"}, "run1")
        self.assertEqual(press["confidence"], "reported")
        self.assertIn("milestone on record", press["review_note"])


class _Resp:
    def __init__(self, status_code, text=""):
        self.status_code, self.text = status_code, text


class FakeApi:
    def __init__(self, companies: dict[int, dict[str, Any]], listing: list[dict[str, Any]] | None = None):
        self.companies = companies
        self.listing = listing or [{"id": cid, "name": c["name"], "publication_status": c.get("publication_status", "published")}
                                   for cid, c in companies.items()]
        self.posts: list[dict[str, Any]] = []
        self.patches: list[tuple[int, dict[str, Any]]] = []
        self.conflict_on: set[str] = set()

    def _get(self, path, params=None):
        assert path == "companies/" and params["lite"] == 1
        return {"results": self.listing, "next": None}

    def get_company(self, cid):
        return {"id": cid, **self.companies[int(cid)]}

    def _post(self, path, data):
        assert path == "changes/"
        self.posts.append(data)
        if data["summary"] in self.conflict_on:
            err = requests.HTTPError("409")
            err.response = _Resp(409, '{"stage": "duplicate"}')
            raise err
        return {"id": len(self.posts)}

    def patch_company(self, cid, payload):
        self.patches.append((cid, payload))
        return {}


def _search(query):
    return [{"link": "https://maker.example/news/series-b", "title": "Maker raises $60M Series B", "snippet": "led by Sequoia",
             "date": "Oct 7, 2026"},
            {"link": "https://www.crunchbase.com/organization/maker", "title": "Maker", "snippet": "funding"}]


def _fetch(url):
    return "Maker today announced a US$60 million Series B led by Sequoia. It previously raised a $20M Series A in 2025."


def _extract(company, evidence):
    return [
        Round("2026-10-07", "Series B", 60e6, "USD", lead_investors=["Sequoia"], source_url=evidence[0]["url"],
              source_kind="company", confidence="high", quote="announced a US$60 million Series B"),
        Round("2025", "Series A", 20e6, "USD", source_url=evidence[0]["url"], source_kind="company", confidence="high"),
        Round("2023", "Seed", 2e6, "USD", source_url="", source_kind="press", confidence="low"),
    ]


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.api = FakeApi({
            7: {"name": "Maker", "website": "https://maker.example", "publication_status": "published",
                "company_maturity": "series_a",
                "milestones": [{"year": 2025, "description": "Raised a US$25M Series A", "source_url": ""},
                               {"year": 2016, "description": "Founded", "source_url": ""}]},
            8: {"name": "Hidden Co", "publication_status": "hidden", "milestones": []},
        })

    def _job(self, **kw):
        return FundingRecheck(self.api, search=_search, fetch=_fetch, extract=_extract, run_id="t", **kw)

    def test_dry_run_classifies_and_writes_nothing(self):
        job = self._job()
        job.run(limit=10, company_ids=None, since_year=None, start_page=1, pause=0)
        self.assertEqual(self.api.posts, [])
        self.assertEqual(self.api.patches, [])
        s = job.stats
        self.assertEqual((s.companies, s.searches, s.pages, s.gemini_calls), (1, 2, 1, 1))
        self.assertEqual((s.new, s.mismatch, s.known, s.low_confidence, s.filed), (1, 1, 0, 1, 0))
        rels = {r["summary"]: r["relation"] for r in job.records[0]["rounds"]}
        self.assertEqual(rels["Raised a US$60M Series B led by Sequoia"], "new")
        self.assertEqual(rels["Raised a US$20M Series A"], "mismatch")
        # the hidden company never left the listing filter
        self.assertEqual([r["company_id"] for r in job.records], [7])
        self.assertIn("DRY RUN", job.summary())
        # where the company is now: the Series B proves a later stage than the profile's series_a
        self.assertEqual(job.records[0]["stage"], {"on_record": "series_a", "suggested": "series_b"})
        notes = {r["summary"]: r.get("payload", {}).get("review_note", "") for r in job.records[0]["rounds"]}
        self.assertIn("evidence suggests series_b", notes["Raised a US$60M Series B led by Sequoia"])
        self.assertNotIn("evidence suggests", notes["Raised a US$20M Series A"])
        self.assertEqual(job.stats.stage_suggestions, 1)

    def test_listed_company_is_suggested_public_not_an_early_round(self):
        self.api.companies[7]["company_status"] = "public"
        self.api.companies[7]["company_maturity"] = ""
        job = self._job()
        job.run(limit=10, company_ids=[7], since_year=None, start_page=1, pause=0)
        self.assertEqual(job.records[0]["stage"], {"on_record": None, "suggested": "public_company"})

    def test_connection_reset_is_retried_once(self):
        calls = {"n": 0}
        real = self.api.get_company

        def flaky(cid):
            calls["n"] += 1
            if calls["n"] == 1:
                raise requests.ConnectionError("reset")
            return real(cid)

        self.api.get_company = flaky
        job = self._job()
        with unittest.mock.patch.object(rcf.time, "sleep"):
            job.run(limit=10, company_ids=[7], since_year=None, start_page=1, pause=0)
        self.assertEqual(job.stats.errors, 0)
        self.assertEqual(job.records[0]["company_id"], 7)
        self.assertTrue(job.records[0]["rounds"])

    def test_gateway_error_is_retried_once(self):
        calls = {"n": 0}
        real = self.api._post

        def flaky(path, data):
            calls["n"] += 1
            if calls["n"] == 1:
                err = requests.HTTPError("502")
                err.response = _Resp(502, "Bad gateway")
                raise err
            return real(path, data)

        self.api._post = flaky
        job = self._job(apply=True)
        with unittest.mock.patch.object(rcf.time, "sleep"):
            job.run(limit=10, company_ids=[7], since_year=None, start_page=1, pause=0)
        self.assertEqual((job.stats.filed, job.stats.errors), (2, 0))

    def test_excluded_companies_are_skipped_without_using_the_limit(self):
        listing = [{"id": 7, "name": "Maker"}, {"id": 9, "name": "Other"}]
        companies = dict(self.api.companies)
        companies[9] = {"name": "Other", "website": "https://other.example", "publication_status": "published",
                        "milestones": []}
        api = FakeApi(companies, listing)
        job = FundingRecheck(api, search=_search, fetch=_fetch, extract=lambda c, e: [], run_id="t")
        job.run(limit=1, company_ids=None, since_year=None, start_page=1, pause=0, exclude={7})
        self.assertEqual([r["company_id"] for r in job.records], [9])

    def test_done_company_ids_reads_snapshots(self):
        import json as _json
        import tempfile
        d = Path(tempfile.mkdtemp())
        (d / "a.json").write_text(_json.dumps({"records": [{"company_id": 1}, {"company_id": 2, "error": "x"}]}), encoding="utf-8")
        (d / "b.json").write_text(_json.dumps({"records": [{"company_id": 3}]}), encoding="utf-8")
        self.assertEqual(rcf.done_company_ids([str(d / "*.json")]), {1, 3})

    def test_aggregators_are_never_sources(self):
        self.assertTrue(rcf.is_skipped_domain("https://bouncewatch.com/company/cyberdyne-inc"))
        self.assertTrue(rcf.is_skipped_domain("https://www.crustdata.com/x"))
        self.assertTrue(rcf.is_skipped_domain("https://forgeglobal.com/vecna-robotics_funding/"))

    def test_unpublished_company_named_explicitly_is_skipped(self):
        job = self._job()
        job.run(limit=10, company_ids=[8], since_year=None, start_page=1, pause=0)
        self.assertEqual(job.records[0]["skipped"], "not published")
        self.assertEqual(job.stats.gemini_calls, 0)

    def test_apply_files_drafts_and_keeps_milestones_unless_asked(self):
        job = self._job(apply=True)
        job.run(limit=10, company_ids=[7], since_year=None, start_page=1, pause=0)
        self.assertEqual([p["summary"] for p in self.api.posts],
                         ["Raised a US$60M Series B led by Sequoia", "Raised a US$20M Series A"])
        self.assertTrue(all(p["status"] == "draft" for p in self.api.posts))
        self.assertEqual(self.api.posts[0]["confidence"], "verified")
        self.assertEqual(self.api.patches, [])
        self.assertEqual(job.stats.filed, 2)

    def test_write_milestones_appends_only_new_rounds(self):
        job = self._job(apply=True, write_milestones=True)
        job.run(limit=10, company_ids=[7], since_year=None, start_page=1, pause=0)
        self.assertEqual(len(self.api.patches), 1)
        cid, payload = self.api.patches[0]
        years = [m["year"] for m in payload["milestones"]]
        self.assertEqual(years, [2025, 2016, 2026])  # existing kept, the new Series B appended
        self.assertEqual(payload["milestones"][2]["description"], "Raised a US$60M Series B led by Sequoia")
        self.assertEqual(job.stats.milestones_written, 1)

    def test_duplicate_is_counted_not_fatal(self):
        self.api.conflict_on.add("Raised a US$60M Series B led by Sequoia")
        job = self._job(apply=True, write_milestones=True)
        job.run(limit=10, company_ids=[7], since_year=None, start_page=1, pause=0)
        self.assertEqual((job.stats.filed, job.stats.duplicates, job.stats.errors), (1, 1, 0))
        self.assertEqual(self.api.patches, [])  # the duplicate round is not re-appended

    def test_since_year_skips_stale_companies(self):
        job = self._job()
        job.run(limit=10, company_ids=[7], since_year=2026, start_page=1, pause=0)
        self.assertEqual(job.records[0]["skipped"], "no funding milestone since 2026")
        self.assertEqual(job.stats.gemini_calls, 0)

    def test_budget_exceeded_stops_the_run(self):
        class SpendBudgetExceeded(RuntimeError):
            pass

        def boom(company, evidence):
            raise SpendBudgetExceeded("daily budget spent")

        listing = [{"id": 7, "name": "Maker"}, {"id": 7, "name": "Maker again"}]
        api = FakeApi(self.api.companies, listing)
        job = FundingRecheck(api, search=_search, fetch=_fetch, extract=boom, run_id="t")
        job.run(limit=10, company_ids=None, since_year=None, start_page=1, pause=0)
        self.assertEqual(len(job.records), 0)
        self.assertEqual(job.stats.errors, 0)

    def test_module_builds_gemini_through_spend_guard(self):
        src = (_RESEARCH_DIR / "recheck_company_funding.py").read_text(encoding="utf-8")
        self.assertNotIn("genai.Client(", src)
        self.assertIn("spend_guard.client(", src)


if __name__ == "__main__":
    unittest.main()
