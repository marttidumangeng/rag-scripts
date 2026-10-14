"""Tier-3 Serper rescue: wall detection, markdown conversion, budget, retry.

Regression cover for two defects found on akarobotics.com (2026-08-27):

1. A bot wall is a PAGE, not an error. "Robot Challenge Screen" arrives as 80KB
   of valid HTML with ~200 characters of text, so `if not html` was False and the
   escape-hatch tiers never ran. Ten challenge screens went to Gemini, which
   correctly judged each "not a robot product page" — the crawler concluded the
   company had no products.

2. Serper's flat `text` field drops every link and image. Wrapping it as HTML
   made pages readable but linkless, which broke URL discovery WORSE than the
   wall did: a site with 12 product pages yielded 1 candidate (a mangled
   `data:` URI). The markdown field keeps both, so we convert that instead.
"""
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from web_extract import (  # noqa: E402
    WebFetcher,
    _looks_like_a_wall,
    _markdown_to_html,
    parse_page,
)

CHALLENGE = (
    "<html><head><title>Robot Challenge Screen</title></head><body>"
    "<div id=px-captcha></div><p>Please verify you are a human.</p>"
    + "<script>var a=1;</script>" * 400
    + "</body></html>"
)
REAL_PAGE = "<html><body><p>" + ("The WallHiker CH-02 is a magnetic crawler. " * 40) + "</p></body></html>"


class TestWallDetection:
    def test_challenge_screen_is_a_wall_despite_being_large(self):
        assert len(CHALLENGE) > 5000, "fixture should be big, like the real one"
        assert _looks_like_a_wall(CHALLENGE) is True

    def test_none_is_a_wall(self):
        assert _looks_like_a_wall(None) is True

    def test_empty_is_a_wall(self):
        assert _looks_like_a_wall("") is True

    def test_403_page_is_a_wall(self):
        assert _looks_like_a_wall("<html><body><h1>403 - Forbidden</h1></body></html>") is True

    def test_real_page_is_not_a_wall(self):
        assert _looks_like_a_wall(REAL_PAGE) is False

    def test_thin_but_real_page_is_not_treated_as_a_wall(self):
        # A short product page must not trigger a paid fetch. 400+ chars of prose
        # sits well under the JS-shell threshold but above the wall threshold.
        page = "<html><body><p>" + ("Compact delta robot for pick and place. " * 12) + "</p></body></html>"
        assert _looks_like_a_wall(page) is False


class TestMarkdownToHtml:
    def test_links_survive(self):
        html = _markdown_to_html("see [CH-02](https://x.com/products/ch-02/) now")
        assert '<a href="https://x.com/products/ch-02/">CH-02</a>' in html

    def test_images_survive(self):
        html = _markdown_to_html("![hero](https://x.com/img/hero.jpg)")
        assert '<img src="https://x.com/img/hero.jpg"' in html

    def test_image_is_not_parsed_as_a_link(self):
        html = _markdown_to_html("![hero](https://x.com/a.jpg)")
        assert "<a href" not in html

    def test_headings_are_siblings_not_nested_in_p(self):
        html = _markdown_to_html("## Specifications\n\nPayload 5 kg")
        assert "<h2>Specifications</h2>" in html
        assert "<p><h2>" not in html

    def test_heading_depth_is_capped(self):
        assert "<h6>" in _markdown_to_html("###### deep")

    def test_page_markup_cannot_inject_tags(self):
        html = _markdown_to_html("evil <script>alert(1)</script> text")
        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_ampersand_in_url_is_escaped_but_href_intact(self):
        html = _markdown_to_html("[p](https://x.com/a?b=1&c=2)")
        assert 'href="https://x.com/a?b=1&amp;c=2"' in html

    def test_blank_input_gives_blank_output(self):
        assert _markdown_to_html("") == ""


def _fetcher():
    f = WebFetcher(timeout=5, stealth=False)
    f._serper_budget = 3
    return f


def _resp(status, payload=None):
    r = mock.Mock()
    r.status_code = status
    r.json.return_value = payload or {}
    return r


MD_PAYLOAD = {
    "markdown": "# WallHiker\n\n" + ("A magnetic crawler cleaning robot. " * 20)
    + "\n\n[spec sheet](https://x.com/spec/)",
    "text": "WallHiker " * 40,
    "credits": 6,
    "metadata": {"title": "WallHiker CH-02"},
}


class TestSerperGet:
    def test_no_key_returns_none_without_spending(self, monkeypatch):
        monkeypatch.delenv("SERPER_API_KEY", raising=False)
        f = _fetcher()
        assert f.serper_get("https://x.com/p/") is None

    def test_xml_is_never_scraped(self, monkeypatch):
        monkeypatch.setenv("SERPER_API_KEY", "k")
        f = _fetcher()
        with mock.patch("web_extract.requests.post") as post:
            assert f.serper_get("https://x.com/sitemap.xml") is None
            post.assert_not_called()

    def test_success_returns_html_with_links(self, monkeypatch):
        monkeypatch.setenv("SERPER_API_KEY", "k")
        f = _fetcher()
        with mock.patch("web_extract.requests.post", return_value=_resp(200, MD_PAYLOAD)):
            html = f.serper_get("https://x.com/p/")
        assert html is not None
        assert 'href="https://x.com/spec/"' in html
        assert "<title>WallHiker CH-02</title>" in html

    def test_credits_are_accumulated_for_spend_logging(self, monkeypatch):
        monkeypatch.setenv("SERPER_API_KEY", "k")
        f = _fetcher()
        with mock.patch("web_extract.requests.post", return_value=_resp(200, MD_PAYLOAD)):
            f.serper_get("https://x.com/a/")
            f.serper_get("https://x.com/b/")
        assert f._serper_credits == 12

    def test_budget_is_a_hard_cap(self, monkeypatch):
        monkeypatch.setenv("SERPER_API_KEY", "k")
        f = _fetcher()
        f._serper_budget = 2
        with mock.patch("web_extract.requests.post", return_value=_resp(200, MD_PAYLOAD)) as post:
            for i in range(5):
                f.serper_get(f"https://x.com/{i}/")
        assert post.call_count == 2, "budget must stop paid calls, not merely warn"

    def test_transient_500_is_retried(self, monkeypatch):
        monkeypatch.setenv("SERPER_API_KEY", "k")
        monkeypatch.setattr("web_extract.time.sleep", lambda *_: None)
        f = _fetcher()
        seq = [_resp(500), _resp(500), _resp(200, MD_PAYLOAD)]
        with mock.patch("web_extract.requests.post", side_effect=seq) as post:
            html = f.serper_get("https://x.com/p/")
        assert post.call_count == 3
        assert html is not None

    def test_one_url_costs_one_unit_of_budget_regardless_of_retries(self, monkeypatch):
        monkeypatch.setenv("SERPER_API_KEY", "k")
        monkeypatch.setattr("web_extract.time.sleep", lambda *_: None)
        f = _fetcher()
        f._serper_budget = 3
        with mock.patch("web_extract.requests.post", side_effect=[_resp(500)] * 3):
            f.serper_get("https://x.com/p/")
        assert f._serper_budget == 2

    @pytest.mark.parametrize("status", [401, 403, 429])
    def test_auth_and_quota_errors_disable_the_tier(self, monkeypatch, status):
        monkeypatch.setenv("SERPER_API_KEY", "k")
        f = _fetcher()
        with mock.patch("web_extract.requests.post", return_value=_resp(status)) as post:
            assert f.serper_get("https://x.com/p/") is None
        assert post.call_count == 1, "retrying a refusal just burns the plan"
        assert f._serper_budget == 0

    def test_network_exception_is_swallowed(self, monkeypatch):
        monkeypatch.setenv("SERPER_API_KEY", "k")
        monkeypatch.setattr("web_extract.time.sleep", lambda *_: None)
        f = _fetcher()
        with mock.patch("web_extract.requests.post", side_effect=OSError("boom")):
            assert f.serper_get("https://x.com/p/") is None


class TestParsePageTierOrder:
    def test_wall_triggers_serper_before_apify(self, monkeypatch):
        f = _fetcher()
        monkeypatch.setattr(f, "get", lambda u: CHALLENGE)
        monkeypatch.setattr(f, "serper_get", lambda u: REAL_PAGE)
        apify = mock.Mock(return_value=None)
        monkeypatch.setattr(f, "apify_get", apify)
        page = parse_page(f, "https://x.com/p/")
        assert "magnetic crawler" in page.text
        apify.assert_not_called()

    def test_apify_runs_only_when_serper_also_fails(self, monkeypatch):
        f = _fetcher()
        monkeypatch.setattr(f, "get", lambda u: CHALLENGE)
        monkeypatch.setattr(f, "serper_get", lambda u: None)
        monkeypatch.setattr(f, "apify_get", lambda u: REAL_PAGE)
        assert "magnetic crawler" in parse_page(f, "https://x.com/p/").text

    def test_good_page_costs_nothing(self, monkeypatch):
        f = _fetcher()
        monkeypatch.setattr(f, "get", lambda u: REAL_PAGE)
        serper, apify = mock.Mock(), mock.Mock()
        monkeypatch.setattr(f, "serper_get", serper)
        monkeypatch.setattr(f, "apify_get", apify)
        parse_page(f, "https://x.com/p/")
        serper.assert_not_called()
        apify.assert_not_called()

    def test_wall_is_kept_when_every_tier_fails(self, monkeypatch):
        # Falling back to the wall text beats returning nothing: downstream still
        # gets a PageContent and logs a real reason instead of a null.
        f = _fetcher()
        monkeypatch.setattr(f, "get", lambda u: CHALLENGE)
        monkeypatch.setattr(f, "serper_get", lambda u: None)
        monkeypatch.setattr(f, "apify_get", lambda u: None)
        assert parse_page(f, "https://x.com/p/") is not None
