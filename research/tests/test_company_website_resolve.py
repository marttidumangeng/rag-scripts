"""Hardening tests for company_website_resolve (QA classes qa7/qa8).

Covers: skip-domain FAMILY matching (linkedin.cn evading a .com-only list),
token-match tightening (2-letter stopword tokens matching att.com /
animenewsnetwork.com), and the robotics-content sniff that kills merch-shop /
wrong-entity domains (FEDOR pool merch, MABEL T-shirt shop).
"""

from __future__ import annotations

import requests

import company_website_resolve as cwr
from company_website_resolve import (
    domain_matches_company,
    is_skippable_domain,
    name_too_generic_to_resolve,
    page_looks_like_robot_company,
)


# ── skip-domain family matching ──────────────────────────────────────────────

def test_skip_domains_cover_tld_families():
    # qa8: linkedin.cn evaded a list that only had linkedin.com
    assert is_skippable_domain("https://www.linkedin.cn/company/foo")
    assert is_skippable_domain("https://linkedin.com/company/foo")
    assert is_skippable_domain("https://www.facebook.de/somepage")
    assert is_skippable_domain("https://www.amazon.co.jp/dp/B000")
    assert is_skippable_domain("https://youtu.be/abc123")


def test_skip_domains_subdomains_still_skipped():
    assert is_skippable_domain("https://flexlink.pissedconsumer.com/review")
    assert is_skippable_domain("https://cable.made-in-china.com/factory")


def test_skip_domains_no_substring_false_positives():
    # "x.com" must not catch xerox.com; "wp.com" must not catch mywp.com
    assert not is_skippable_domain("https://www.xerox.com")
    assert not is_skippable_domain("https://www.mywp.com")
    assert not is_skippable_domain("https://www.yaskawa.co.jp")


# ── token matching ───────────────────────────────────────────────────────────

def test_stopword_tokens_never_match_domains():
    # qa7: "an" matched animenewsnetwork.com; "At" matched att.com
    assert not domain_matches_company(
        "https://www.animenewsnetwork.com",
        "Does It Count If You Lose Your Virginity to an Android?",
    )
    assert not domain_matches_company("https://www.att.com", "At")
    assert not domain_matches_company("https://www.att.com", "AT Robotics")


def test_short_tokens_require_exact_label_equality():
    # 3-char tokens only count when they ARE the domain label
    assert domain_matches_company("https://global.abb", "ABB") or \
        domain_matches_company("https://www.abb.com", "ABB")
    assert not domain_matches_company(
        "https://www.attractive-machines.com", "ATT Co"
    )


def test_substantive_tokens_and_full_name_containment():
    assert domain_matches_company("https://www.yaskawa.co.jp", "YASKAWA Electric")
    # full-name containment covers compact brands whose only token is short
    assert domain_matches_company("https://www.ti5robot.com", "Ti5 Robot")
    assert not domain_matches_company("https://www.usa.gov", "Us")


# ── robotics-content sniff ───────────────────────────────────────────────────

class _Resp:
    def __init__(self, text: str):
        self.text = text


class _Sess:
    def __init__(self, text: str):
        self._text = text

    def get(self, url, **kwargs):
        return _Resp(self._text)


class _ErrSess:
    def get(self, url, **kwargs):
        raise requests.ConnectionError("boom")


def test_sniff_rejects_merch_shop():
    # qa8: FEDOR resolved to a pool player's merch shop
    merch = ("Add to cart — Ghost Mystery Bundle. Shop hoodies, t-shirts and "
             "apparel. Checkout now. More merch drops soon.")
    assert not page_looks_like_robot_company(
        "https://fedorgorst.example", session=_Sess(merch))


def test_sniff_accepts_robot_company_page():
    page = ("We build industrial robots and collaborative cobot arms for "
            "welding automation and palletizing.")
    assert page_looks_like_robot_company(
        "https://maker.example", session=_Sess(page))


def test_sniff_rejects_anti_signal_dominated_page():
    page = "Robot t-shirts! Add to cart. Hoodies, apparel and merch."
    assert not page_looks_like_robot_company(
        "https://tshirts.example", session=_Sess(page))


def test_sniff_fails_open_on_network_error():
    assert page_looks_like_robot_company(
        "https://unreachable.example", session=_ErrSess())


def test_website_from_search_gated_on_content_sniff(monkeypatch):
    hits = [{"link": "https://shop.mabelofficial.com/collections/robots"}]
    monkeypatch.setattr(cwr, "_serper_search", lambda q, **kw: hits)
    monkeypatch.setattr(cwr, "domain_matches_company", lambda url, name: True)
    monkeypatch.setattr(cwr, "validate_website", lambda url, **kw: True)

    monkeypatch.setattr(
        cwr, "page_looks_like_robot_company", lambda url, **kw: False)
    assert cwr.website_from_search("MABEL Robotics") is None

    monkeypatch.setattr(
        cwr, "page_looks_like_robot_company", lambda url, **kw: True)
    assert cwr.website_from_search("MABEL Robotics") == "https://shop.mabelofficial.com"


# ── generic-name guard (FEDOR/MABEL/Ee/Fi/Us class) ──────────────────────────

def test_generic_single_word_names_not_search_resolved():
    for name in ("FEDOR", "MABEL", "Ee", "Fi", "Us", "Soundwave"):
        assert name_too_generic_to_resolve(name), name
    for name in ("Agility Robotics", "Symbotic", "Volocopter", "Flexiv Inc"):
        assert not name_too_generic_to_resolve(name), name
