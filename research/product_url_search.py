"""Find official manufacturer product page URLs via web search.

Crawl-only URL ranking fails when product paths are opaque (e.g. estun.com/gjjjqr/356.html)
and the model name never appears in the URL. Search tiers, fastest first:
1. Serper.dev (Google results as JSON, ~1-2s/query) — needs SERPER_API_KEY
2. Gemini + Google Search grounding
3. Apify rag-web-browser actor (slow, minutes/robot; skipped when RESEARCH_DISABLE_APIFY=1)
"""

from __future__ import annotations

import os
import re
from datetime import timedelta
from typing import Any
from urllib.parse import urlparse

import requests

from estun_english_catalog import preferred_estun_search_site
from load_env import load_research_env
from web_extract import robot_name_tokens, same_site, score_url_for_robot

load_research_env()

try:
    from apify_client import ApifyClient
except ImportError:  # pragma: no cover
    ApifyClient = None  # type: ignore

_WEAK_PATH_RE = re.compile(
    r"(?:^|/)(?:solute|products?|catalog|shop|tel:|mailto:|privacy|cookie|login|member)(?:/|$)",
    re.I,
)
_PDF_OR_ASSET_RE = re.compile(r"\.(?:pdf|zip|docx?|xlsx?|css|js|svg)$", re.I)
_URL_IN_TEXT_RE = re.compile(r"https?://[^\s\)\]\"'<>]+", re.I)
_LOW_CONFIDENCE_DOMAINS = {
    "facebook.com", "instagram.com", "x.com", "twitter.com",
    "tiktok.com", "linkedin.com", "medium.com", "youtube.com", "youtu.be",
}


def _normalize_netloc(website: str) -> str:
    return urlparse(website).netloc.lower().removeprefix("www.")


def is_weak_product_url(url: str, website: str, tokens: list[str]) -> bool:
    """True when crawl-derived URL is missing, off-domain, or clearly not a product page."""
    url = (url or "").strip()
    if not url or url.startswith(("tel:", "mailto:", "javascript:", "mail:")):
        return True
    if "mail:" in url.lower():
        return True
    if _PDF_OR_ASSET_RE.search(urlparse(url).path):
        return True
    if website and not same_site(url, urlparse(website).netloc):
        return True
    path = urlparse(url).path.rstrip("/").lower()
    home_path = urlparse(website).path.rstrip("/").lower() if website else ""
    if path in ("", home_path) or _WEAK_PATH_RE.search(path):
        return True
    # Opaque OEM paths like estun.com/gjjjqr/356.html have no model tokens in the URL —
    # that is fine once found via search; only reject token-less paths that aren't detail pages.
    if re.search(r"/\d+\.html?$", path, re.I):
        return False
    if score_url_for_robot(url, tokens) <= 0:
        return True
    return False


def _score_candidate(
    url: str,
    tokens: list[str],
    *,
    title: str = "",
    snippet: str = "",
    company_netloc: str = "",
) -> int:
    if not url:
        return -100
    parsed = urlparse(url)
    netloc = parsed.netloc.lower().removeprefix("www.")
    if company_netloc and netloc != company_netloc:
        return -100
    if _PDF_OR_ASSET_RE.search(parsed.path):
        return -50
    # Weak segments only disqualify when they END the path (catalog roots like /products).
    # Deep pages UNDER them (/products/robots/sp/sp210) are exactly what we're looking for.
    _last_seg = parsed.path.rstrip("/").rsplit("/", 1)[-1].lower()
    if _WEAK_PATH_RE.search("/" + _last_seg):
        return -20

    score = score_url_for_robot(url, tokens)
    if re.search(r"/(?:news|blog|press|market)/", parsed.path, re.I):
        score -= 15
    # Series/category pages that mention many models (e.g. scara/333.html) are not product pages.
    if re.search(r"/(?:scara|minixl|szpt|zijsjqr|xzjqr)/\d*\.html?$", parsed.path, re.I):
        if not any(tok in title.lower() for tok in tokens):
            score -= 25

    blob = f"{url} {title} {snippet}".lower()
    for tok in tokens:
        if tok in blob:
            score += 6
    # Estun-style /category/123.html product pages
    if re.search(r"/\d+\.html?$", parsed.path, re.I):
        score += 5
        if any(tok in title.lower() for tok in tokens):
            score += 25
    if any(d in netloc for d in _LOW_CONFIDENCE_DOMAINS):
        score -= 100
    return score


def _pick_best(candidates: list[tuple[str, str, str]], tokens: list[str], company_netloc: str) -> str:
    best_url = ""
    best_score = 0
    best_title = ""
    best_snippet = ""
    for rank, (url, title, snippet) in enumerate(candidates):
        s = _score_candidate(url, tokens, title=title, snippet=snippet, company_netloc=company_netloc)
        s += max(0, 8 - rank)
        blob = f"{title} {snippet}".lower()
        path = urlparse(url).path
        if any(tok in blob for tok in tokens) and re.search(r"/\d+\.html?$", path, re.I):
            s += 30
        if s > best_score:
            best_score = s
            best_url = url
            best_title = title
            best_snippet = snippet
    if not best_url:
        return ""
    path = urlparse(best_url).path
    blob = f"{best_title} {best_snippet}".lower()
    if re.search(r"/\d+\.html?$", path, re.I) and any(tok in blob for tok in tokens):
        return best_url
    return best_url if best_score >= 8 else ""


_SERPER_DOWN = False  # set when credits run out (4xx) — Exa takes over for the rest of the run


def _serper_google_search(query: str, *, max_results: int = 10) -> list[dict[str, Any]]:
    """Google results via serper.dev — returns `organic` result dicts (link/title/snippet)."""
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
            print(f"  [search] Serper unavailable (HTTP {resp.status_code}) — falling back to Exa", flush=True)
            return []
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError):
        return []
    return data.get("organic") or []


def _exa_search(query: str, *, include_domains: list[str] | None = None,
                num_results: int = 8) -> list[dict[str, Any]]:
    """Exa /search (auto type, URLs only — no contents; cheapest mode).
    Fallback tier when Serper credits run out."""
    api_key = os.environ.get("EXA_AI_API_KEY") or os.environ.get("EXA_API_KEY", "")
    if not api_key:
        return []
    body: dict[str, Any] = {"query": query, "type": "auto", "numResults": num_results}
    if include_domains:
        body["includeDomains"] = include_domains
    try:
        resp = requests.post(
            "https://api.exa.ai/search",
            headers={"x-api-key": api_key, "Content-Type": "application/json"},
            json=body,
            timeout=25,
        )
        resp.raise_for_status()
        return resp.json().get("results") or []
    except (requests.RequestException, ValueError):
        return []


def search_product_url_via_exa(
    robot_name: str,
    company_name: str,
    *,
    model_name: str = "",
    company_website: str = "",
) -> str:
    """Exa-backed product page search — same candidate scoring as the Serper tier."""
    company_website = preferred_estun_search_site(company_website)
    company_netloc = _normalize_netloc(company_website) if company_website else ""
    model = model_name or robot_name
    tokens = robot_name_tokens(robot_name, model_name)

    query = f'{model} {company_name} robot product page'
    items = _exa_search(query, include_domains=[company_netloc] if company_netloc else None)
    candidates: list[tuple[str, str, str]] = []
    for item in items:
        url = (item.get("url") or "").strip()
        if not url:
            continue
        netloc = urlparse(url).netloc.lower().removeprefix("www.")
        if company_netloc and netloc != company_netloc:
            continue
        candidates.append((url, item.get("title") or "", ""))
    return _pick_best(candidates, tokens, company_netloc)


def search_product_url_via_serper(
    robot_name: str,
    company_name: str,
    *,
    model_name: str = "",
    company_website: str = "",
) -> str:
    """Primary tier: Serper Google search with site: restriction."""
    company_website = preferred_estun_search_site(company_website)
    company_netloc = _normalize_netloc(company_website) if company_website else ""
    model = model_name or robot_name
    tokens = robot_name_tokens(robot_name, model_name)

    queries = [
        f'site:{company_netloc} "{model}"' if company_netloc else f'"{model}" {company_name} robot',
    ]
    if company_netloc:
        queries.append(f'"{model}" {company_name} product site:{company_netloc}')

    all_candidates: list[tuple[str, str, str]] = []
    for query in queries:
        for item in _serper_google_search(query):
            url = (item.get("link") or "").strip()
            if not url:
                continue
            netloc = urlparse(url).netloc.lower().removeprefix("www.")
            if company_netloc and netloc != company_netloc:
                continue
            all_candidates.append((url, item.get("title") or "", item.get("snippet") or ""))
        found = _pick_best(all_candidates, tokens, company_netloc)
        if found:
            return found
    return _pick_best(all_candidates, tokens, company_netloc)


def _apify_google_search(query: str, *, max_results: int = 10) -> list[dict[str, Any]]:
    if ApifyClient is None:
        return []
    # Bulk batch runs opt out: each Apify actor call adds minutes per robot and burns
    # credits. (Set to a non-empty value — empty env vars vanish across Windows spawns.)
    if os.environ.get("RESEARCH_DISABLE_APIFY", "").lower() in ("1", "true", "yes"):
        return []
    api_key = os.environ.get("APIFY_API_KEY", "")
    if not api_key:
        return []
    client = ApifyClient(api_key, max_retries=2)
    run = client.actor("apify/rag-web-browser").call(
        run_input={
            "query": query,
            "maxResults": max_results,
            "outputFormats": ["markdown"],
            "removeCookieWarnings": True,
        },
        wait_duration=timedelta(seconds=90),
    )
    return list(client.dataset(run.default_dataset_id).iterate_items())


def _candidates_from_apify_items(
    items: list[dict[str, Any]],
    *,
    company_netloc: str,
) -> list[tuple[str, str, str]]:
    """Collect URLs from Google result metadata and internal links mined from page markdown."""
    candidates: list[tuple[str, str, str]] = []
    seen: set[str] = set()

    def add(url: str, title: str = "", snippet: str = "") -> None:
        url = (url or "").strip().rstrip(".,;)")
        if not url or url in seen:
            return
        netloc = urlparse(url).netloc.lower().removeprefix("www.")
        if company_netloc and netloc != company_netloc:
            return
        seen.add(url)
        candidates.append((url, title, snippet))

    for item in items:
        sr = item.get("searchResult") or {}
        markdown = item.get("markdown") or ""
        snippet = " ".join(
            part for part in (
                sr.get("description") or "",
                sr.get("snippet") or "",
                markdown[:1200],
            ) if part
        )
        add(sr.get("url") or "", sr.get("title") or "", snippet)
        for match in _URL_IN_TEXT_RE.findall(markdown):
            add(match, "", markdown[:1200])
        for link_text, link in re.findall(r"\[([^\]]+)\]\((https?://[^)]+)\)", markdown):
            add(link, link_text, markdown[:1200])
    return candidates


def search_product_url_via_apify(
    robot_name: str,
    company_name: str,
    *,
    model_name: str = "",
    company_website: str = "",
) -> str:
    """Fallback: Apify Google search with site: restriction (used by company_research)."""
    company_website = preferred_estun_search_site(company_website)
    company_netloc = _normalize_netloc(company_website) if company_website else ""
    model = model_name or robot_name
    tokens = robot_name_tokens(robot_name, model_name)

    queries = [
        f'site:{company_netloc} "{model}"' if company_netloc else f'"{model}" {company_name} robot',
    ]
    if company_netloc:
        queries.append(f'"{model}" {company_name} product site:{company_netloc}')

    all_candidates: list[tuple[str, str, str]] = []
    for query in queries:
        try:
            items = _apify_google_search(query)
        except Exception:
            continue
        all_candidates.extend(_candidates_from_apify_items(items, company_netloc=company_netloc))
        found = _pick_best(all_candidates, tokens, company_netloc)
        if found:
            return found
    return _pick_best(all_candidates, tokens, company_netloc)


def search_product_url_for_robot(
    robot_name: str,
    company_name: str,
    *,
    model_name: str = "",
    company_website: str = "",
) -> str:
    """Return the best official product page URL, or \"\" if search finds nothing confident."""
    url = search_product_url_via_serper(
        robot_name, company_name, model_name=model_name, company_website=company_website,
    )
    if url:
        return url
    if _SERPER_DOWN:  # credits exhausted — Exa covers the search tier
        url = search_product_url_via_exa(
            robot_name, company_name, model_name=model_name, company_website=company_website,
        )
        if url:
            return url
    # No Gemini-grounding tier here (removed 2026-08-11). It read only the URLs out of
    # `grounding_chunks` — the same shape Serper returns — while billing $35/1,000 requests,
    # and because it sat BELOW Serper it fired exclusively on robots Serper could not find:
    # the obscure, the misnamed, and the ones that are not products at all. That concentrated
    # the most expensive call in the pipeline on its least valuable items. A robot neither
    # Serper nor Exa can locate is a human's problem, not one to spend 3.5c per retry on.
    return search_product_url_via_apify(
        robot_name, company_name, model_name=model_name, company_website=company_website,
    )
