"""verify_funding_source: one case per failure type the 2026-10-20 audit found.

    python -m unittest tests.test_verify_funding_source
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_RESEARCH_DIR = Path(__file__).resolve().parents[1]
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

import verify_funding_source as vfs  # noqa: E402

FILLER = " Robots are used in factories, warehouses and hospitals around the world." * 8


def ev(company, summary, amount=None, quote="", url="https://news.example/article", rnd="Series A"):
    nv = {"round": rnd, "amount": amount, "currency": "USD"} if amount is not None else {"round": rnd}
    note = f"funding_recheck t: new | quote: {quote}" if quote else ""
    return {"company": company, "summary": summary, "new_value": nv, "review_note": note,
            "source_url": url, "occurred_on": "2026-02-11", "event_type": "funding"}


class NumberTests(unittest.TestCase):
    def test_units(self):
        nums = [n for n, _ in vfs.page_numbers("US$520 million, CNY 1.5B, 1.5亿元, $2,500,000 and 3 bn")]
        for want in (520e6, 1.5e9, 1.5e8, 2.5e6, 3e9):
            self.assertTrue(any(abs(n - want) < 1 for n in nums), want)


class VerifyTests(unittest.TestCase):
    def test_real_round_passes(self):
        page = "Apptronik today announced it closed a US$520 million Series A extension led by B Capital." + FILLER
        v, r = vfs.verify_event(ev("Apptronik", "Raised a US$520M Series A+", 520e6,
                                   "Apptronik today announced it closed a US$520 million Series A extension"), page)
        self.assertEqual((v, r), (vfs.PASS, []))

    def test_raise_at_a_valuation_still_passes(self):
        page = "Anduril announced its Series H, a $5 billion raise which brings its valuation to $61 billion." + FILLER
        v, _ = vfs.verify_event(ev("Anduril Industries", "Raised a US$5B Series H", 5e9), page)
        self.assertEqual(v, vfs.PASS)

    def test_unreadable_page(self):
        self.assertEqual(vfs.verify_event(ev("Apptronik", "x", 1e6), "Access denied")[0], vfs.UNVERIFIABLE)

    def test_data_mill(self):
        v, r = vfs.verify_event(ev("Apptronik", "x", 1e6, url="https://bouncewatch.com/company/apptronik"), "text" * 200)
        self.assertEqual((v, r), (vfs.FAIL, ["data mill"]))

    def test_company_not_on_page(self):
        page = "Anyverse, the Madrid synthetic-data company, raised US$8 million." + FILLER
        v, r = vfs.verify_event(ev("Foxconn Robotics", "Raised a US$8M Seed", 8e6), page)
        self.assertEqual((v, r), (vfs.FAIL, ["company not on page"]))

    def test_amount_not_on_page(self):
        page = "Apptronik raised money from Google and B Capital this year." + FILLER
        v, r = vfs.verify_event(ev("Apptronik", "Raised a US$520M Series A", 520e6), page)
        self.assertEqual(v, vfs.FAIL)
        self.assertIn("amount not on page", r)

    def test_valuation(self):
        page = "Unitree Robotics is now valued at US$1.7 billion after its latest round." + FILLER
        v, r = vfs.verify_event(ev("Unitree Robotics", "Raised a US$1.7B Series C", 1.7e9), page)
        self.assertEqual(v, vfs.FAIL)
        self.assertIn("valuation", r[0])

    def test_fund(self):
        page = "Waseda University Ventures closed its second fund of JPY 5.66 billion to back campus startups." + FILLER
        v, r = vfs.verify_event(ev("Waseda University", "Raised a JPY 5.66B Series A", 5.66e9), page)
        self.assertEqual(v, vfs.FAIL)
        self.assertIn("fund", r[0])

    def test_joint_venture_pipeline(self):
        page = "EM&E Group signed a joint venture pipeline worth US$1.5 billion with partners in the Gulf." + FILLER
        v, r = vfs.verify_event(ev("EM&E Group", "Raised a US$1.5B strategic round", 1.5e9), page)
        self.assertEqual(v, vfs.FAIL)
        self.assertIn("joint venture / pipeline", r[0])

    def test_buyer(self):
        quote = "Thermo Fisher Scientific to acquire PPD for US$17.4 billion in cash."
        page = quote + FILLER
        v, r = vfs.verify_event(ev("Thermo Fisher Scientific", "Raised a US$17.4B strategic round", 17.4e9, quote), page)
        self.assertEqual(v, vfs.FAIL)
        self.assertIn("company is the buyer", r)

    def test_company_named_as_its_own_investor(self):
        quote = "VETA Secures JPY 200 Million from Waseda University Ventures"
        e = ev("Waseda University", "Raised a JPY 200M Seed led by Waseda University Ventures", 200e6, quote)
        e["new_value"]["lead_investors"] = ["Waseda University Ventures"]
        v, r = vfs.verify_event(e, quote + FILLER)
        self.assertEqual((v, r), (vfs.FAIL, ["company is the investor or buyer"]))

    def test_acquired_by_itself(self):
        quote = "BouMatic is pleased to announce the acquisition of SAC Group."
        v, r = vfs.verify_event(ev("BouMatic", "Acquired by BouMatic", None, quote, rnd="Acquisition"), quote + FILLER)
        self.assertIn("company is the investor or buyer", r)

    def test_quote_about_spending(self):
        quote = "Very active year of capital deployment, investing $24 billion in strategic acquisitions."
        v, r = vfs.verify_event(ev("Thermo Fisher Scientific", "Raised a US$24B strategic round", 24e9, quote),
                                "Thermo Fisher " + quote + FILLER)
        self.assertIn("quote is about money the company spent", r)

    def test_quote_about_a_unit_sale(self):
        quote = "Japanese government structures and Bain Group buy out Toshiba's semiconductor business for $18 billion."
        v, r = vfs.verify_event(ev("Toshiba", "Raised a US$18B strategic round led by Bain Capital", 18e9, quote),
                                quote + FILLER)
        self.assertIn("quote is about a business the company sold", r)

    def test_rights_issue_mentioning_a_joint_venture_passes(self):
        quote = "Electrolux plans a $980 million rights issue and partners with Midea for joint ventures."
        v, _ = vfs.verify_event(ev("Electrolux", "Raised a US$980M Rights Issue", 980e6, quote, rnd="Rights Issue"),
                                quote + FILLER)
        self.assertEqual(v, vfs.PASS)

    def test_acquisition_of_the_company_passes(self):
        quote = "Teradyne completed its acquisition of Mobile Industrial Robots for US$148 million."
        v, _ = vfs.verify_event(ev("Mobile Industrial Robots", "Acquired by Teradyne for US$148M", 148e6, quote,
                                   rnd="Acquisition"), quote + FILLER)
        self.assertEqual(v, vfs.PASS)

    def test_parent_buying_the_company_passes(self):
        quote = ("Amazon has steadily added to its fleet of warehouse robots since it acquired Kiva Systems for "
                 "$775 million in 2012, which has now become Amazon Robotics , the company's in-house incubator")
        e = ev("Amazon Robotics", "Acquired by Amazon for US$775M", 775e6, quote, rnd="Acquisition")
        e["new_value"]["lead_investors"] = ["Amazon"]
        v, _ = vfs.verify_event(e, quote + FILLER)
        self.assertEqual(v, vfs.PASS)

    def test_founders_and_own_raise_are_not_self_investment(self):
        quote = "Rekise Marine secures $9.7M seed funding led by Accel & NKSquared."
        e = ev("Rekise Marine", "Raised a US$9.7M Seed led by Accel", 9.7e6, quote, rnd="Seed")
        e["new_value"]["participating_investors"] = ["Rekise Marine founders"]
        self.assertEqual(vfs.verify_event(e, quote + FILLER)[0], vfs.PASS)
        quote = "Guangdong Nexwise Intelligent Technology announced that it has raised CNY 170 million."
        e = ev("Nexwise Intelligence", "Raised a CNY 170M strategic round", 170e6, quote, rnd="Strategic")
        e["new_value"]["participating_investors"] = ["Nexwise Intelligence China Limited"]
        self.assertEqual(vfs.verify_event(e, quote + FILLER)[0], vfs.PASS)

    def test_stake_bought_in_the_company_passes(self):
        quote = "Private-equity firm EQT has acquired a stake in BBS Automation GmbH, a German maker of automation."
        v, _ = vfs.verify_event(ev("BBS Automation", "Raised a strategic round from EQT", None, quote, rnd="Strategic"),
                                quote + FILLER)
        self.assertEqual(v, vfs.PASS)

    def test_rights_offering_and_backer_who_sold_products_pass(self):
        quote = "HL Holdings participated in a KRW 49 billion rights offering by HL Robotics to fund the acquisition."
        self.assertEqual(vfs.verify_event(ev("HL Robotics", "Raised a KRW 49B strategic round", 49e9, quote),
                                          quote + FILLER)[0], vfs.PASS)
        quote = ("Xiaomi invested a few months after the company was founded, and Roborock grew up as part of the "
                 "network of hardware makers that Xiaomi backed and sold through.")
        self.assertEqual(vfs.verify_event(ev("Roborock", "Raised a strategic round from Xiaomi", None, quote),
                                          quote + FILLER)[0], vfs.PASS)

    def test_money_into_the_company_passes_and_into_another_fails(self):
        quote = "LegaLogic Advises Tardid Technologies in relation to strategic investment in it by Samarthya Investment Advisors"
        self.assertEqual(vfs.verify_event(ev("Tardid Technologies", "Raised a strategic round", None, quote),
                                          quote + FILLER)[0], vfs.PASS)
        quote = ("The round also saw participation from existing investors, including MGF Kavachh and Pontaq Ventures, "
                 "who collectively invested over INR 17 crore in July 2025.")
        self.assertEqual(vfs.verify_event(ev("Coratia Technologies", "Raised a INR 170M Seed", 170e6, quote),
                                          "Coratia raised INR 170 million. " + quote + FILLER)[0], vfs.PASS)
        quote = ("To meet demand for AGVs, SSI SCHAEFER expanded its portfolio with an undisclosed investment in "
                 "Austrian AGV specialist DS AUTOMOTION.")
        self.assertIn("quote is about money the company spent",
                      vfs.verify_event(ev("SSI SCHAEFER", "Raised a strategic round from DS AUTOMOTION", None, quote),
                                       quote + FILLER)[1])

    def test_parent_buying_a_bracketed_subsidiary_passes(self):
        quote = "QinetiQ acquired Foster-Miller in 2004."
        e = ev("QinetiQ (Foster-Miller)", "Acquired by QinetiQ", None, quote, rnd="Acquisition")
        e["new_value"]["lead_investors"] = ["QinetiQ"]
        self.assertEqual(vfs.verify_event(e, quote + FILLER)[0], vfs.PASS)
        quote = "DoorDash acquired Chowbotics, the maker of the Sally salad robot."
        self.assertEqual(vfs.verify_event(ev("Chowbotics (DoorDash)", "Acquired by DoorDash", None, quote,
                                             rnd="Acquisition"), quote + FILLER)[0], vfs.PASS)

    def test_total_across_rounds_fails(self):
        for page, amount in [
            ("Xynova completed a series A round, bringing total capital raised to nearly 1 billion yuan (US$148 million).", 1e9),
            ("RoboParty closed back-to-back Angel++ and Pre-A rounds, raising nearly 500 million yuan in total.", 5e8),
            ("Hanson Robotics has raised around USD 21.7 million over four funding rounds.", 21.7e6),
            ("Cafe after two initial rounds of funding brought in $5.1 million from investors.", 5.1e6),
            ("YouiBot completed two rounds of Series B financing for a total of RMB 300 million.", 3e8),
        ]:
            company = page.split(" ")[0]
            v, r = vfs.verify_event(ev(company, "Raised a round", amount), page + FILLER)
            self.assertIn("amount is a total across rounds", r, page)

    def test_one_round_sized_with_total_wording_passes(self):
        for page, amount in [
            ("Spirit AI announced the completion of a Series A+ financing round totaling RMB 1.5 billion.", 1.5e9),
            ("BlueSword issued 18.17 million shares at 27.7 yuan, and a total of 503 million yuan raised.", 5.03e8),
            ("Spirit has raised about $420 million across two funding rounds in 30 days, including a $145 million round.",
             145e6),
            ("Niqo Robotics has raised $16 million to date including its $5 million in Series A round from FMC.", 5e6),
            ("Blue participated in two previous funding rounds of $7.4 million in 2016 and $14.8 million in 2018.", 7.4e6),
        ]:
            company = page.split(" ")[0]
            self.assertEqual(vfs.verify_event(ev(company, "Raised a round", amount), page + FILLER)[0], vfs.PASS, page)

    def test_round_with_a_running_total_passes(self):
        page = "Mind Robotics said it has raised $400 million, bringing its total investment to more than $1 billion." + FILLER
        self.assertEqual(vfs.verify_event(ev("Mind Robotics", "Raised US$400M", 400e6), page)[0], vfs.PASS)
        self.assertIn("amount is a total across rounds",
                      vfs.verify_event(ev("Mind Robotics", "Raised US$1B", 1e9), page)[1])

    def test_duplicates_in_audit(self):
        rows = [
            {"id": 172, "company_id": 37, "status": "published", "summary": "Raised a CNY 400M Series D",
             "new_value": {"round": "Series D", "amount": 400e6, "currency": "CNY"}, "occurred_on": "2022-01-26"},
            {"id": 173, "company_id": 37, "status": "published", "summary": "Raised a US$62M Series D",
             "new_value": {"round": "Series D", "amount": 62e6, "currency": "USD"}, "occurred_on": "2022-02-08"},
            {"id": 174, "company_id": 37, "status": "published", "summary": "Raised a CNY 800M Series E",
             "new_value": {"round": "Series E", "amount": 800e6, "currency": "CNY"}, "occurred_on": "2025-01-07"},
        ]
        verdicts = [{"id": r["id"], "verdict": vfs.PASS, "reasons": []} for r in rows]
        vfs.mark_duplicates(rows, verdicts)
        self.assertEqual([v["verdict"] for v in verdicts], [vfs.PASS, vfs.FAIL, vfs.PASS])
        self.assertEqual(verdicts[1]["reasons"], ["duplicate of #172"])

    def test_undisclosed_amount_needs_company_and_quote(self):
        quote = "PongBot completed its Series B financing led by Tencent."
        page = quote + FILLER
        self.assertEqual(vfs.verify_event(ev("PongBot", "Raised a Series B (amount undisclosed)", None, quote), page)[0], vfs.PASS)
        other = "Tennis is popular in China." + FILLER
        self.assertEqual(vfs.verify_event(ev("PongBot", "Raised a Series B", None, quote), "PongBot " + other)[1],
                         ["quote not on page"])

    def test_amount_from_summary_for_backfill_rows(self):
        page = "Kewazo raised a US$16 million Series A to scale its scaffolding robots." + FILLER
        e = {"company": "Kewazo", "summary": "Raised a US$16M Series A", "new_value": None, "review_note": "backfill:series_a",
             "source_url": "https://kewazo.example/news", "occurred_on": "2026-03-19"}
        self.assertEqual(vfs.verify_event(e, page)[0], vfs.PASS)


if __name__ == "__main__":
    unittest.main()
