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


class WeakSourceTests(unittest.TestCase):
    """A homepage is marketing. It names deployments, partners and press.

    Regression: Shark Robotics (company 1806) is a French firm in La Rochelle
    whose homepage carries a Ukraine delivery story and never spells "France".
    It resolved to UA until the homepage was demoted below the legal-notice page
    AND required to look like an address.
    """

    HOMEPAGE = ("Shark Robotics designs firefighting robots. "
                "Our Colossus units were delivered to Ukraine in 2022.")

    def test_bare_mention_on_a_weak_source_is_not_an_address(self):
        self.assertEqual(_country_from_text(self.HOMEPAGE, require_address_context=True), "")

    def test_the_same_text_is_accepted_from_a_legal_page(self):
        self.assertEqual(_country_from_text(self.HOMEPAGE), "UA")

    def test_a_real_address_passes_the_weak_source_gate(self):
        self.assertEqual(
            _country_from_text(
                "Rue Fleming 17, 17000 La Rochelle, France", require_address_context=True),
            "FR",
        )

    def test_an_hq_marker_also_passes_the_gate(self):
        self.assertEqual(
            _country_from_text("Siege social: La Rochelle, France", require_address_context=True),
            "FR",
        )

    def test_region_hints_do_not_bypass_the_gate(self):
        # A bare "Pittsburgh, PA 15201" is fine on a contact page but must not
        # let a homepage guess.
        self.assertEqual(_country_from_text("Pittsburgh, PA", require_address_context=True), "")

    def test_legal_pages_are_tried_before_the_homepage(self):
        from company_country_resolve import _CONTACT_PATHS

        self.assertEqual(_CONTACT_PATHS[-1], "", "the homepage must be the LAST resort")
        self.assertLess(_CONTACT_PATHS.index("/mentions-legales"), _CONTACT_PATHS.index("/about"))


class FalsePrefixTests(unittest.TestCase):
    """A country name inside a longer place name is a different place.

    Regression: Dane Technologies (company 1637, Minnesota) resolved to MX
    because its contact page carries a US state dropdown containing
    "New Mexico".
    """

    STATE_DROPDOWN = ("minnesota mississippi missouri montana nebraska nevada "
                      "new hampshire new jersey new mexico new york north carolina")

    def test_new_mexico_is_not_mexico(self):
        self.assertNotEqual(_country_from_text(self.STATE_DROPDOWN), "MX")

    def test_a_real_mexico_address_still_resolves(self):
        self.assertEqual(_country_from_text("Av. Reforma 100, 06600 Mexico"), "MX")


class AmbiguousPageTests(unittest.TestCase):
    """A page listing several countries and no HQ is offices, not a headquarters."""

    def test_multiple_countries_with_no_hq_marker_is_ambiguous(self):
        self.assertEqual(
            _country_from_text("Offices in Germany, Japan and Singapore."), "",
        )

    def test_an_hq_marker_resolves_the_ambiguity(self):
        self.assertEqual(
            _country_from_text("Offices in Germany and Japan. Headquartered in Singapore."),
            "SG",
        )

    def test_a_single_country_is_still_accepted(self):
        self.assertEqual(_country_from_text("Contact our office in Japan."), "JP")

    def test_postal_hint_survives_when_no_country_is_named(self):
        # Address blocks routinely omit the country: "Brooklyn Park, MN 55428".
        self.assertEqual(
            _country_from_text("Brooklyn Park, MN 55428", require_address_context=True), "US",
        )

    def test_soft_city_hints_are_gated_on_weak_sources(self):
        self.assertEqual(_country_from_text("our Tokyo partner", require_address_context=True), "")
        self.assertEqual(_country_from_text("our Tokyo partner"), "JP")


class DomesticAddressTests(unittest.TestCase):
    """A company does not write its own country into its own address.

    The only country spelled out on a contact page is usually the FOREIGN
    satellite, which biases every non-US manufacturer toward "US". Regression:
    Bluepath Robotics (company 1677) lists its head office in Istanbul, its
    factory in Kocaeli and a US office in Detroit — and resolved to US because
    Detroit's was the only line naming a country.
    """

    BLUEPATH = ("Head Office Sanayi Mahallesi, Teknopark Bulvari 9C Blok No: 327, "
                "34906 Pendik - Istanbul  Factory Deniz Evler, Mazhar Ozen Cd. "
                "No:110, 41650 Golcuk/Kocaeli  US office Newlab, 2050 15th St, "
                "Detroit, MI 48216, United States")

    def test_hq_marker_anchors_a_city_hint_over_a_named_foreign_country(self):
        self.assertEqual(_country_from_text(self.BLUEPATH), "TR")

    def test_it_holds_under_the_weak_source_gate_too(self):
        self.assertEqual(_country_from_text(self.BLUEPATH, require_address_context=True), "TR")

    def test_turkish_dotted_capital_i_folds_to_ascii(self):
        # "Istanbul" with a Turkish dotted capital I lowercases to "i" plus a
        # combining dot, which never matches the literal hint without folding.
        self.assertEqual(_country_from_text("Headquarters: Pendik İstanbul"), "TR")

    def test_satellite_label_between_marker_and_hit_is_not_anchored(self):
        text = "Headquarters Munich, Germany. US office Detroit, MI 48216, United States"
        self.assertEqual(_country_from_text(text), "DE")

    def test_a_lone_satellite_address_is_still_read_when_nothing_else_is(self):
        self.assertEqual(_country_from_text("Detroit, MI 48216, United States"), "US")


class CodeBlobTests(unittest.TestCase):
    def test_js_i18n_dictionaries_are_stripped(self):
        # Shark Robotics ships a MediaElement.js language table; scanning it for
        # an address is noise at best.
        blob = ('{"mejs.chinese":"Chinois","mejs.danish":"Danois",'
                '"mejs.dutch":"Neerlandais","mejs.english":"Anglais",'
                '"mejs.finnish":"Finnois","mejs.greek":"Grec"}')
        self.assertEqual(_country_from_text(blob + " Contact us."), "")


class VocabularyTests(unittest.TestCase):
    def test_all_codes_are_iso_alpha2(self):
        for phrase, code in _COUNTRY_NAME_TO_CODE.items():
            with self.subTest(phrase=phrase):
                self.assertRegex(code, r"^[A-Z]{2}$")


if __name__ == "__main__":
    unittest.main()
