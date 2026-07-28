"""Apify website-content-crawler integration — the bot-wall escape hatch.

Two jobs, both behind the same APIFY_API_KEY already used by rag-web-browser:

  wcc_fetch_html   — fetch ONE page through a headless Firefox + rotating Apify
                     proxy. Tier-4 of the fetch stack: only called after plain
                     requests, curl_cffi impersonation, and stealth Playwright
                     have all failed (see WebFetcher.apify_get). Slow (~30-90s
                     actor run) and ~$0.001-0.005/page, so callers budget it.

  wcc_crawl_site   — crawl a whole site when the bot-wall blocks URL discovery
                     itself (sitemap + homepage both unreachable), returning
                     page HTML/text for the discovery pipeline.

`saveHtml` is always on: markdown output loses <img> tags, and image URLs feed
both heuristic image selection and grounded image picking downstream.

Fail-open like every other enhancement in this pipeline: missing key, missing
client, RESEARCH_DISABLE_APIFY=1, or an actor error all return None/[] and the
caller proceeds with whatever the cheaper tiers produced.
"""

from __future__ import annotations

import os
from datetime import timedelta
from typing import Any

WCC_ACTOR = "apify/website-content-crawler"

# Single-page runs still pay actor startup (~30-60s); site crawls render every
# page in a real browser. Wait caps keep a hung run from stalling a batch.
SINGLE_PAGE_WAIT_SECS = 300
SITE_CRAWL_WAIT_SECS = 1200


def apify_enabled() -> bool:
    """True when Apify calls are possible AND allowed for this run."""
    if os.environ.get("RESEARCH_DISABLE_APIFY", "").lower() in ("1", "true", "yes"):
        return False
    if not os.environ.get("APIFY_API_KEY", ""):
        return False
    try:
        from apify_client import ApifyClient  # noqa: F401
    except ImportError:
        return False
    return True


def _run_wcc(run_input: dict[str, Any], wait_secs: int) -> list[dict[str, Any]]:
    from apify_client import ApifyClient

    client = ApifyClient(os.environ["APIFY_API_KEY"], max_retries=2)
    run = client.actor(WCC_ACTOR).call(
        run_input=run_input, wait_duration=timedelta(seconds=wait_secs)
    )
    # apify-client returns an attribute object in 3.x (see product_url_search) but a
    # plain run dict in older versions — accept both.
    dataset_id = getattr(run, "default_dataset_id", None) or (
        run.get("defaultDatasetId") if isinstance(run, dict) else None
    )
    if not dataset_id:
        return []
    # If the wait cap expired mid-crawl, the dataset still holds finished pages.
    return list(client.dataset(dataset_id).iterate_items())


def wcc_fetch_html(url: str, *, wait_secs: int = SINGLE_PAGE_WAIT_SECS) -> str | None:
    """Fetch one page's HTML through WCC. None on any failure.

    crawlerType is pinned to headless Firefox (not "adaptive"): this only runs
    after plain HTTP already failed, so paying the adaptive HTTP probe first
    would waste the run. htmlTransformer "none" keeps the full document so our
    own extractors see meta tags and image URLs.
    """
    if not apify_enabled() or not url:
        return None
    try:
        items = _run_wcc(
            {
                "startUrls": [{"url": url}],
                "crawlerType": "playwright:firefox",
                "maxCrawlPages": 1,
                "maxCrawlDepth": 0,
                "saveHtml": True,
                "htmlTransformer": "none",
                "removeCookieWarnings": True,
                "proxyConfiguration": {"useApifyProxy": True},
            },
            wait_secs,
        )
    except Exception as exc:
        print(f"    [apify] WCC fetch failed for {url}: {exc}", flush=True)
        return None
    for item in items:
        html = item.get("html") or ""
        if html.strip():
            return html
    return None


def wcc_crawl_site(
    start_url: str,
    *,
    max_pages: int = 60,
    max_depth: int = 3,
    include_globs: list[str] | None = None,
    wait_secs: int = SITE_CRAWL_WAIT_SECS,
) -> list[dict[str, Any]]:
    """Crawl a site through WCC and return its dataset items
    (each: url, html, text, markdown, metadata{title, description, ...}).

    Used by discovery when the normal sitemap/homepage crawl is bot-walled and
    yields (almost) nothing. Empty list on any failure.
    """
    if not apify_enabled() or not start_url:
        return []
    run_input: dict[str, Any] = {
        "startUrls": [{"url": start_url}],
        "crawlerType": "playwright:firefox",
        "maxCrawlPages": max_pages,
        "maxCrawlDepth": max_depth,
        "saveHtml": True,
        "htmlTransformer": "none",
        "removeCookieWarnings": True,
        "proxyConfiguration": {"useApifyProxy": True},
    }
    if include_globs:
        run_input["includeUrlGlobs"] = [{"glob": g} for g in include_globs]
    try:
        items = _run_wcc(run_input, wait_secs)
    except Exception as exc:
        print(f"    [apify] WCC site crawl failed for {start_url}: {exc}", flush=True)
        return []
    return [i for i in items if (i.get("url") or "").strip()]
