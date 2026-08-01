"""The extraction ladder: try structured sources before prose.

Order is best-evidence-first, and each rung declines (rather than fails) when
it does not apply so the next one gets a turn:

    manufacturer_api -> json_ld -> spec_table -> (caller's existing prose path)

This package intentionally does NOT replace the Gemini/prose discovery in
`discover_robots.py`. It runs in front of it. Prose extraction remains the
right tool for a hand-built site with no structure to read; it is simply the
wrong FIRST choice, because it discards structure the server already published.

`declined_reason` is threaded through deliberately. A run that finds nothing
should be able to say why — "no ld+json, no tables, endpoint 403" is
actionable, an empty list is not. That distinction has bitten this pipeline
before: a broken run and a genuinely empty one look identical unless the
difference is recorded.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import requests

# Mirrors web_extract._JS_SHELL_TEXT_CHARS. A page whose visible text is this
# short is almost certainly an unrendered app shell rather than a real page.
_JS_SHELL_TEXT_CHARS = 5000
_TAG_RE = re.compile(r"<script.*?</script>|<style.*?</style>", re.S | re.I)


def _looks_like_shell(html: str) -> bool:
    text = _TAG_RE.sub("", html or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return len(re.sub(r"\s+", " ", text).strip()) < _JS_SHELL_TEXT_CHARS

from .base import ExtractionResult, registry
from .manufacturer_api import BROWSER_HEADERS, ManufacturerAPIExtractor
from .structured_html import JsonLdExtractor, SpecTableExtractor


@dataclass
class LadderReport:
    url: str
    winner: str = ""
    products: int = 0
    attempts: list[tuple[str, str]] = field(default_factory=list)  # (strategy, why-not)

    def summary(self) -> str:
        if self.winner:
            return f"{self.url}: {self.products} products via {self.winner}"
        tried = "; ".join(f"{s}: {why}" for s, why in self.attempts) or "no strategy applied"
        return f"{self.url}: nothing structured found ({tried})"


class ExtractionLadder:
    """
    `escalate` controls what happens when a plain fetch is refused or returns a
    JS shell. Measured on four unconfigured OEM sites (DENSO, Doosan, Techman,
    Stäubli): two returned 403 to a plain client and two returned a shell with
    ~6-7k visible characters and no structured markup. So on real manufacturer
    sites a plain GET is refused or useless about half the time, and without
    escalation the structured rungs never even get markup to read.

    Escalation reuses `web_extract.WebFetcher` rather than reimplementing it —
    that class already owns the stealth/curl-impersonation and Playwright
    render tiers, and its render calls serialise on `_PLAYWRIGHT_LOCK`, which
    matters because the nightly runs multiple workers.
    """

    def __init__(self, session: requests.Session | None = None,
                 escalate: bool = True) -> None:
        self.session = session or requests.Session()
        self.escalate = escalate
        self._fetcher = None
        self.strategies = [
            ManufacturerAPIExtractor(self.session),
            JsonLdExtractor(),
            SpecTableExtractor(),
        ]

    def _web_fetcher(self):
        if self._fetcher is None:
            from web_extract import WebFetcher  # local import: optional dependency chain
            # stealth=True turns on the escalation ladder inside WebFetcher
            # (curl impersonation, then render when blocked or when visible
            # text looks like a shell).
            self._fetcher = WebFetcher(stealth=True)
        return self._fetcher

    def fetch_html(self, url: str, timeout: int = 25) -> str | None:
        try:
            r = self.session.get(url, headers=BROWSER_HEADERS, timeout=timeout)
            if r.status_code == 200:
                r.encoding = r.apparent_encoding or r.encoding
                html = r.text
                # A 200 that is really a JS shell is not a success for our
                # purposes — the markup we need was never in it.
                if not self.escalate or not _looks_like_shell(html):
                    return html
            elif not self.escalate:
                return None
        except requests.RequestException:
            if not self.escalate:
                return None

        try:
            return self._web_fetcher().get(url)
        except Exception:
            return None

    def run(self, url: str, html: str | None = None) -> tuple[ExtractionResult, LadderReport]:
        report = LadderReport(url=url)
        # The API rung can work without HTML when the domain is registered;
        # only pay for a fetch if some rung actually needs the markup.
        if html is None and not registry.site_config(url):
            html = self.fetch_html(url)

        for strat in self.strategies:
            try:
                if not strat.can_handle(url, html):
                    report.attempts.append((strat.name, "not applicable"))
                    continue
                result = strat.extract(url, html)
            except Exception as exc:  # a fault is not "no products"
                report.attempts.append((strat.name, f"error: {str(exc)[:120]}"))
                continue
            if result:
                report.winner = strat.name
                report.products = len(result.products)
                return result, report
            report.attempts.append((strat.name, result.declined_reason or "no products"))

        return ExtractionResult(declined_reason="all structured strategies declined"), report
