"""Tests for `company_country_resolve` — the offline tiers.

Only the deterministic tiers are covered here (ccTLD + address-text parsing);
the serper and Gemini tiers need network and are exercised by the batch driver.
The bar for every case is the module's contract: a MISS must return "", because
a wrong country mislabels the manufacturer on every robot page and country facet
while a blank one just leaves the existing flag up.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_RESEARCH_DIR = Path(__file__).resolve().parents[1]
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from company_country_resolve import (  # noqa: E402
    _COUNTRY_NAME_TO_CODE,
    _country_from_text,
    country_from_domain,
)


class CcTldTests(unittest.TestCase):
    def test_known_cctlds(self):
        for url, expected in (
            ("https://www.fanuc.co.jp/", "JP"),
            ("kuka.de", "DE"),
            ("https://siasun.com.cn", "CN"),
            ("https://example.co.uk", "GB"),
            ("http://firm.com.au/path?q=1", "AU"),
        ):
            with self.subTest(url=url):
                self.assertEqual(country_from_domain(url), expected)

    def test_generic_tlds_are_not_countries(self):
        for url in ("https://unitree.com", "https://x.org", "https://foo.net"):
            with self.subTest(url=url):
                self.assertEqual(country_from_domain(url), "")

    def test_vanity_tlds_are_deliberately_excluded(self):
        # A robotics startup on .ai is not headquartered in Anguilla, and one on
        # .io is not in the British Indian Ocean Territory.
        for url in ("https://robotics.ai", "https://build.io", "https://x.co",
                    "https://a.me", "https://b.tv"):
            with self.subTest(url=url):
                self.assertEqual(country_from_domain(url), "")

    def test_blank(self):
        self.assertEqual(country_from_domain(""), "")


class AddressTextTests(unittest.TestCase):
    def test_explicit_country_name(self):
        self.assertEqual(_country_from_text("Rue de Paris 12, 75001 Paris, France"), "FR")

    def test_region_hints_when_no_country_named(self):
        self.assertEqual(_country_from_text("Pittsburgh, PA 15201"), "US")
        self.assertEqual(_country_from_text("Shenzhen Nanshan District"), "CN")
        self.assertEqual(_country_from_text("Impressum | Musterstrasse 1"), "DE")

    def test_hq_marker_beats_an_earlier_mention(self):
        # The failure this guards: a sales-office sentence appearing before the
        # real HQ line would otherwise relocate the manufacturer.
        self.assertEqual(_country_from_text("Our USA office opened; HQ in Germany"), "DE")
        self.assertEqual(
            _country_from_text("Sales in USA, Canada and Japan. Headquartered in Shenzhen, China."),
            "CN",
        )
        self.assertEqual(
            _country_from_text("Founded in 2015 and based in Seoul, South Korea; US subsidiary in Texas"),
            "KR",
        )

    def test_word_boundaries(self):
        # "usa" inside "usability"/"causal" must not read as United States.
        self.assertEqual(_country_from_text("usability testing and causal analysis"), "")
        self.assertEqual(_country_from_text("a walk through chinatown"), "")

    def test_no_signal(self):
        self.assertEqual(_country_from_text(""), "")
        self.assertEqual(_country_from_text("Contact us for a quote."), "")


class VocabularyTests(unittest.TestCase):
    def test_all_codes_are_iso_alpha2(self):
        for phrase, code in _COUNTRY_NAME_TO_CODE.items():
            with self.subTest(phrase=phrase):
                self.assertRegex(code, r"^[A-Z]{2}$")


if __name__ == "__main__":
    unittest.main()
