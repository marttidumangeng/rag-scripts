"""Resolve + validate a company's official website.

The greenfield pipeline used to derive a company's website by re-fetching its
Robolist page at import time (``robolist.ai/companies/<slug>``). Robolist has
since delisted/renamed most of those pages, so ~90% now 404 and the importer
skipped the company entirely. The fix is to resolve the website **once, at
discovery time**, validate it, and store it on the gap entry so Stage 0 never
has to re-fetch a page that may be dead.

Resolution tiers (first validated hit wins):
  1. Robolist company page — scrape the first external (non-aggregator) link.
  2. serper.dev search — "<name> official website", best manufacturer domain.

Every candidate is screened against a social/aggregator skip-list and
HEAD/GET-validated (status < 400) before being returned.
"""

from __future__ import annotations

import os
import re
from typing import Any

import requests

from load_env import load_research_env

load_research_env()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Social / aggregator / CDN domains that are never a manufacturer's own site.
# Superset of the lists previously inlined in overnight_greenfield_import.py
# (Robolist link skip) and product_url_search.py (_LOW_CONFIDENCE_DOMAINS).
_SKIP_DOMAINS: tuple[str, ...] = (
    # competitor directories / aggregators
    "robolist.ai", "aparobot.com", "robotsguide.com", "therobotreport.com",
    "wikipedia.org", "crunchbase.com", "pitchbook.com", "bloomberg.com",
    "tracxn.com", "dnb.com", "zoominfo.com", "glassdoor.com", "indeed.com",
    # social
    "twitter.com", "x.com", "linkedin.com", "facebook.com", "instagram.com",
    "youtube.com", "youtu.be", "tiktok.com", "medium.com", "pinterest.com",
    "reddit.com", "weibo.com", "bilibili.com",
    # search / app stores / code hosts
    "google.com", "bing.com", "baidu.com", "apps.apple.com", "play.google.com",
    "github.com", "gitlab.com",
    # B2B marketplaces / trade directories (list a product, aren't the maker)
    "alibaba.com", "aliexpress.com", "made-in-china.com", "globalsources.com",
    "tradewheel.com", "tradeindia.com", "indiamart.com", "thomasnet.com",
    "ec21.com", "dhgate.com", "amazon.com", "ebay.com", "go4worldbusiness.com",
    "exporthub.com", "europages.com", "kompass.com", "yellowpages.com",
    # review / complaint / business-listing aggregators
    "pissedconsumer.com", "trustpilot.com", "yelp.com", "manta.com",
    "buzzfile.com", "mapquest.com", "bbb.org", "opencorporates.com",
    # CDN / infra
    "cloudfront.net", "amazonaws.com", "googleapis.com", "gstatic.com",
    "googleusercontent.com", "fbcdn.net", "wp.com",
)

# Generic tokens dropped before comparing a domain to a company name.
_STOP_TOKENS: set[str] = {
    "co", "com", "ltd", "inc", "corp", "group", "robot", "robots", "robotics",
    "ai", "tech", "technology", "technologies", "systems", "the", "china",
    "industries", "industry", "global", "international", "intelligent",
    "automation", "laser", "company", "limited", "gmbh",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _domain(url: str) -> str:
    """Return the lowercased host of ``url`` without a leading ``www.``."""
    m = re.match(r"https?://([^/]+)", url or "")
    if not m:
        return ""
    return m.group(1).lower().removeprefix("www.")


def is_skippable_domain(url: str) -> bool:
    """True when the URL's host is a social/aggregator/CDN domain (never a maker site)."""
    host = _domain(url)
    if not host:
        return True
    return any(skip in host for skip in _SKIP_DOMAINS)


def _name_tokens(company_name: str) -> set[str]:
    tokens = set(re.sub(r"[^a-z0-9]+", " ", (company_name or "").lower()).split())
    return {t for t in (tokens - _STOP_TOKENS) if len(t) >= 2}


def _registrable_label(host: str) -> str:
    """Return the second-level (registrable) label of a host.

    Strips subdomains AND the public suffix so only the brand label remains:
      www.ti5robot.com        -> ti5robot
      en.directdrive.com      -> directdrive
      alpha-robot.com.cn      -> alpha-robot
      flexlink.pissedconsumer.com -> pissedconsumer   (NOT flexlink)

    Matching on this label prevents a company name that appears only as a
    *subdomain* of an aggregator from counting as a domain match.
    """
    base = re.sub(r"\.[a-z]{2,6}$", "", host)   # strip TLD (.com / .cn)
    base = re.sub(r"\.[a-z]{2,6}$", "", base)    # strip a second-level ccTLD (.com.cn)
    return base.rsplit(".", 1)[-1] if base else ""


def domain_matches_company(url: str, company_name: str) -> bool:
    """Heuristic: does the URL's domain plausibly belong to ``company_name``?

    Used to prefer manufacturer domains over unrelated hits in search results.
    Compares only the registrable label so aggregator subdomains
    (``flexlink.pissedconsumer.com``) don't spoof a match. Permissive: returns
    True when there is nothing meaningful to compare.
    """
    host = _domain(url)
    if not host:
        return False
    label = _registrable_label(host)
    label_flat = re.sub(r"[^a-z0-9]", "", label)

    name_tokens = _name_tokens(company_name)
    if not name_tokens:
        return True

    for tok in name_tokens:
        if tok in label_flat:
            return True
    # Reverse: a meaningful chunk of the domain label appears in the company name
    for tok in re.split(r"[^a-z0-9]+", label):
        if len(tok) >= 4 and tok in (company_name or "").lower():
            return True
    return False


def validate_website(
    url: str,
    *,
    session: requests.Session | None = None,
    timeout: int = 12,
) -> bool:
    """HEAD (then GET) the URL; True when it resolves with status < 400."""
    if not url or is_skippable_domain(url):
        return False
    s = session or requests
    try:
        resp = s.head(url, headers=_HEADERS, timeout=timeout, allow_redirects=True)
        if resp.status_code >= 400 or resp.status_code == 405:
            # Some hosts reject HEAD — retry with a light GET.
            resp = s.get(
                url, headers=_HEADERS, timeout=timeout,
                allow_redirects=True, stream=True,
            )
            resp.close()
        return resp.status_code < 400
    except requests.RequestException:
        return False


# ---------------------------------------------------------------------------
# Tier 1: Robolist company page
# ---------------------------------------------------------------------------

def website_from_robolist(
    slug: str,
    *,
    session: requests.Session | None = None,
    timeout: int = 12,
) -> str | None:
    """Scrape a Robolist company page for the first external (maker) link.

    Returns ``None`` when the page 404s / errors or has no clean external link.
    """
    if not slug:
        return None
    s = session or requests
    url = f"https://robolist.ai/companies/{slug}"
    try:
        resp = s.get(url, headers=_HEADERS, timeout=timeout)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
    except requests.RequestException:
        return None

    ext_links = re.findall(r'href=["\']((https?://)[^"\']+)["\']', resp.text)
    seen: set[str] = set()
    for (href, _) in ext_links:
        href = href.strip()
        if is_skippable_domain(href):
            continue
        host_match = re.match(r"(https?://[^/]+)", href)
        if not host_match:
            continue
        root = host_match.group(1)
        if root in seen:
            continue
        seen.add(root)
        return root
    return None


# ---------------------------------------------------------------------------
# Tier 2: serper.dev search
# ---------------------------------------------------------------------------

_SERPER_DOWN = False  # set once credits run out (4xx) so we stop hammering it


def _serper_search(query: str, *, max_results: int = 10) -> list[dict[str, Any]]:
    """Google organic results via serper.dev (link/title/snippet)."""
    global _SERPER_DOWN
    api_key = os.environ.get("SERPER_API_KEY", "")
    if not api_key or _SERPER_DOWN:
        return []
    try:
        resp = requests.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            json={"q": query, "num": max_results},
            timeout=15,
        )
        if resp.status_code in (400, 401, 402, 403, 429):
            _SERPER_DOWN = True
            return []
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError):
        return []
    return data.get("organic") or []


def website_from_search(
    company_name: str,
    *,
    country: str | None = None,
    session: requests.Session | None = None,
    validate: bool = True,
) -> str | None:
    """serper.dev search for the company's official website.

    Returns the first manufacturer-domain hit whose domain plausibly matches the
    company name (skipping social/aggregator/marketplace domains). A hit that
    matches no name token is NOT returned — the importer would reject a
    mismatched domain anyway, and storing an unrelated site helps no one.
    Validated by default.
    """
    if not company_name:
        return None
    country_hint = f" {country}" if country else ""
    queries = [
        f'"{company_name}"{country_hint} official website',
        f"{company_name} robot manufacturer",
    ]
    for query in queries:
        for item in _serper_search(query):
            url = (item.get("link") or "").strip()
            if not url or is_skippable_domain(url):
                continue
            # Normalise to the domain root (search hits often land on deep pages).
            root_match = re.match(r"(https?://[^/]+)", url)
            root = root_match.group(1) if root_match else url
            if not domain_matches_company(root, company_name):
                continue
            if validate and not validate_website(root, session=session):
                continue
            return root
    return None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def resolve_company_website(
    name: str,
    slug: str = "",
    *,
    country: str | None = None,
    session: requests.Session | None = None,
    use_robolist: bool = True,
    use_search: bool = True,
    validate: bool = True,
) -> tuple[str | None, str]:
    """Resolve a company's official website.

    Returns ``(website_or_None, method)`` where method is one of
    ``"robolist"``, ``"search"`` or ``"none"``.
    """
    if use_robolist and slug:
        site = website_from_robolist(slug, session=session)
        if site and (not validate or validate_website(site, session=session)):
            return site, "robolist"

    if use_search:
        site = website_from_search(
            name, country=country, session=session, validate=validate,
        )
        if site:
            return site, "search"

    return None, "none"
