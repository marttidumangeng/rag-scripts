"""Hikrobot (hikrobotics.com) category-page tab extractor.

Hikrobot's mobile-robot site is a Vue.js SPA where each product family
(LMR / FMR / CMR / CTU) lives on a single category page that renders all
models as tabs.  A plain HTTP fetch returns a near-empty JS shell; even a
Playwright render of the category URL does not surface individual model specs
because the spec panel only becomes visible after the matching tab is clicked.

This module:
  1. Detects hikrobotics.com URLs.
  2. Maps every known robot model to its category page URL.
  3. Uses Playwright to open the category page, click the model's tab, wait
     for the spec panel to appear, then extracts the rendered HTML of that
     panel as a ``PageContent`` object that the normal enrichment pipeline can
     consume (spec extraction, image selection, confirmation gate).

The confirmation gate in ``web_extract.confirm_target_on_page`` will pass
because the extracted text contains the model name from the tab heading.

Robot-name normalisation
------------------------
DB names sometimes carry a company suffix or Chinese text:
  "Q3-600D (Hikrobot)"  →  base model "Q3-600D"
  "Q3S 潜行式清扫机器人"  →  base model "Q3S"
``normalize_hikrobot_model`` strips these so the tab-ID lookup works.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from urllib.parse import urlparse

from web_extract import PageContent

# ---------------------------------------------------------------------------
# Site detection
# ---------------------------------------------------------------------------

HIKROBOT_SITE = "https://www.hikrobotics.com"

# Category page URLs for each product family
HIKROBOT_CATEGORY_URLS: dict[str, str] = {
    "LMR": f"{HIKROBOT_SITE}/en/mobilerobot/LMR/",
    "FMR": f"{HIKROBOT_SITE}/en/mobilerobot/FMR/",
    "CMR": f"{HIKROBOT_SITE}/en/mobilerobot/CMR/",
    "CTU": f"{HIKROBOT_SITE}/en/mobilerobot/CTU/",
}

# Model-prefix → family key mapping (longest prefix first to avoid ambiguity)
_MODEL_FAMILY_PREFIXES: list[tuple[str, str]] = [
    ("TP0",  "LMR"),   # TP0-T50 is an LMR despite the TP prefix
    ("TP5",  "CTU"),
    ("TP6",  "CTU"),
    ("TP",   "CTU"),   # generic TP fallback
    ("Q",    "LMR"),   # Q2-400D, Q3-600D, Q3S, Q7-1000E, Q7-1500D, Q8-2000A
    ("F",    "FMR"),   # F3-1500, F5-1600, F7-1500, F8-2000
    ("C",    "CMR"),   # C3-200LB2, C3-400B4
]

# Playwright wait timeout (ms) for tab panel to become visible
_TAB_WAIT_MS = 8_000
# Extra settle time after click (seconds) for lazy-loaded images
_SETTLE_S = 2.5


def is_hikrobot_website(website: str) -> bool:
    """Return True when *website* is hikrobotics.com (any sub-domain)."""
    netloc = urlparse(website or "").netloc.lower().removeprefix("www.")
    return netloc in ("hikrobotics.com", "www.hikrobotics.com")


def normalize_hikrobot_model(name: str, model_name: str = "") -> str:
    """Return the bare model code, stripping company suffix and CJK text.

    Examples
    --------
    "Q3-600D (Hikrobot)"  →  "Q3-600D"
    "Q3S 潜行式清扫机器人"  →  "Q3S"
    "TP0-T50"             →  "TP0-T50"
    """
    raw = (model_name or name or "").strip()
    # Strip known variant suffixes that appear as parentheticals but are NOT
    # company names — these are hardware variant codes that differ between the
    # DB name and the tab label on hikrobotics.com.
    # e.g. "TP5-50DCP(T)" → "TP5-50DCP"  (T = Traction variant)
    _VARIANT_SUFFIXES = re.compile(
        r"\s*\((T|H|W|P|C|S|DC|DCH|DCW|DCP|SCP|SCW|SCH|SGH|SGP)\)\s*$",
        re.IGNORECASE,
    )
    raw = _VARIANT_SUFFIXES.sub("", raw).strip()
    # Strip parenthetical company suffix: "Q3-600D (Hikrobot)" → "Q3-600D"
    raw = re.sub(r"\s*\([^)]*\)\s*$", "", raw).strip()
    # Strip CJK characters and everything after the first CJK run
    raw = re.sub(r"[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef].*$", "", raw).strip()
    # Strip trailing whitespace left by the above
    return raw.strip()


def hikrobot_family_for_model(model: str) -> str | None:
    """Return the product-family key (LMR/FMR/CMR/CTU) for a model code."""
    upper = model.upper()
    for prefix, family in _MODEL_FAMILY_PREFIXES:
        if upper.startswith(prefix):
            return family
    return None


def hikrobot_category_url_for_model(model: str) -> str | None:
    """Return the category page URL for a model, or None if unknown."""
    family = hikrobot_family_for_model(model)
    return HIKROBOT_CATEGORY_URLS.get(family) if family else None


# ---------------------------------------------------------------------------
# Tab-aware Playwright extractor
# ---------------------------------------------------------------------------

@dataclass
class HikrobotTabResult:
    """Result of extracting a single model tab from a Hikrobot category page."""
    model: str
    family: str
    category_url: str
    tab_id: str          # e.g. "tab-15"  (the element id on the page)
    html: str            # rendered HTML of the *entire* page after tab click
    text: str            # visible text of the active tab panel
    images: list[str] = field(default_factory=list)
    success: bool = True
    error: str = ""


def _extract_images_from_html(html: str, base_url: str) -> list[str]:
    """Pull absolute image URLs from rendered HTML (no BeautifulSoup dependency)."""
    from web_extract import extract_image_urls
    return extract_image_urls(html, base_url)


def extract_hikrobot_tab(
    model: str,
    *,
    timeout_ms: int = _TAB_WAIT_MS,
    settle_s: float = _SETTLE_S,
    stealth: bool = False,
) -> HikrobotTabResult | None:
    """Open the category page for *model* in Playwright, click its tab, and
    return the rendered content as a ``HikrobotTabResult``.

    Returns ``None`` when Playwright is not installed or the model is unknown.
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        return None

    bare_model = normalize_hikrobot_model(model)
    family = hikrobot_family_for_model(bare_model)
    if not family:
        return None
    category_url = HIKROBOT_CATEGORY_URLS[family]

    result = HikrobotTabResult(
        model=bare_model,
        family=family,
        category_url=category_url,
        tab_id="",
        html="",
        text="",
    )

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
                locale="en-US",
                extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
            )
            if stealth:
                try:
                    from playwright_stealth import Stealth
                    page = ctx.new_page()
                    Stealth().apply_stealth_sync(page)
                except ImportError:
                    page = ctx.new_page()
            else:
                page = ctx.new_page()

            page.goto(category_url, wait_until="networkidle", timeout=timeout_ms * 3)
            time.sleep(1.0)  # let Vue finish hydrating

            # --- Find the tab whose title matches the bare model code ---
            # Hikrobot renders tabs as: <div id="tab-NN" role="tab">MODEL_NAME</div>
            tab_el = None
            tab_id = ""

            # Strategy 1: exact text match on role=tab elements
            tabs = page.query_selector_all('[role="tab"]')
            for tab in tabs:
                label = (tab.inner_text() or "").strip()
                if label.upper() == bare_model.upper():
                    tab_el = tab
                    tab_id = tab.get_attribute("id") or ""
                    break

            # Strategy 2: partial match (model code appears inside tab label)
            if tab_el is None:
                for tab in tabs:
                    label = (tab.inner_text() or "").strip().upper()
                    if bare_model.upper() in label:
                        tab_el = tab
                        tab_id = tab.get_attribute("id") or ""
                        break

            # Strategy 3: id-based match — tab IDs are "tab-NN"; the aria-controls
            # attribute on each tab points to "pane-NN". We can also search pane
            # content for the model name to find the right tab.
            if tab_el is None:
                for tab in tabs:
                    pane_id = tab.get_attribute("aria-controls") or ""
                    if pane_id:
                        pane = page.query_selector(f"#{pane_id}")
                        if pane:
                            pane_text = (pane.inner_text() or "").strip()
                            if bare_model.upper() in pane_text.upper():
                                tab_el = tab
                                tab_id = tab.get_attribute("id") or ""
                                break

            if tab_el is None:
                result.success = False
                result.error = f"Tab for model '{bare_model}' not found on {category_url}"
                browser.close()
                return result

            result.tab_id = tab_id

            # --- Click the tab and wait for the spec panel to appear ---
            tab_el.click()
            pane_id = tab_id.replace("tab-", "pane-")
            try:
                page.wait_for_selector(
                    f"#{pane_id}",
                    state="visible",
                    timeout=timeout_ms,
                )
            except PWTimeout:
                pass  # panel may already be visible; proceed anyway

            time.sleep(settle_s)  # lazy images / transitions

            # --- Extract content ---
            html = page.content()
            # Extract only the active tab panel text to avoid contaminating
            # the spec extractor with sibling model data
            pane_el = page.query_selector(f"#{pane_id}")
            if pane_el:
                panel_text = pane_el.inner_text() or ""
            else:
                panel_text = page.inner_text("body") or ""

            # Also grab the page title and meta description for confirmation gate
            title = page.title() or ""
            meta_desc = page.evaluate(
                "() => (document.querySelector('meta[name=\"description\"]') || {}).content || ''"
            ) or ""

            result.html = html
            # Prepend model name + title to text so confirm_target_on_page passes
            result.text = f"{bare_model}\n{title}\n{meta_desc}\n{panel_text}"
            result.images = _extract_images_from_html(html, category_url)

            browser.close()
            return result

    except Exception as exc:
        result.success = False
        result.error = str(exc)
        return result


def hikrobot_tab_to_page_content(result: HikrobotTabResult) -> PageContent:
    """Convert a ``HikrobotTabResult`` into a ``PageContent`` for the enrichment pipeline."""
    from web_extract import extract_main_text
    from bs4 import BeautifulSoup

    # Build a minimal main_text from the panel text (already stripped of sibling data)
    main_text = result.text

    # If we have full HTML, extract a cleaner main_text from it
    if result.html:
        try:
            soup = BeautifulSoup(result.html, "html.parser")
            # Remove sibling tab panels — keep only the active one
            pane_id = result.tab_id.replace("tab-", "pane-")
            for pane in soup.find_all(id=lambda x: x and x.startswith("pane-") and x != pane_id):
                pane.decompose()
            main_text = soup.get_text(" ", strip=True)
        except Exception:
            pass

    return PageContent(
        url=result.category_url,
        html=result.html,
        text=result.text,
        main_text=main_text,
        title=f"Hikrobot {result.model} - {result.family}",
        meta_description=f"Hikrobot {result.model} mobile robot specifications",
        images=result.images,
        video_urls=[],
        # DELIBERATELY False — do not flip this to True.
        # The tab panel scopes TEXT to one model, but Hikrobot serves FAMILY-LEVEL
        # images: measured 2026-07-26, C3-400B4 (tab-5) and sibling C3-200LB2 (tab-2)
        # return byte-identical 4-image sets, and TP6-30SGH (tab-20) / TP6-30SGP
        # (tab-21) return identical 22-image sets, while their text differs. Trusting
        # these as model-specific pins one photo onto every robot in the family — the
        # shared-hero defect. Hikrobot simply does not publish per-model photos, so
        # `missing_image` here is correctly unfixable and should escalate to a human.
        model_scoped=False,
    )


# ---------------------------------------------------------------------------
# Convenience: fetch all models for a family in one Playwright session
# ---------------------------------------------------------------------------

def extract_all_hikrobot_tabs(
    family: str,
    *,
    timeout_ms: int = _TAB_WAIT_MS,
    settle_s: float = _SETTLE_S,
    stealth: bool = False,
) -> dict[str, HikrobotTabResult]:
    """Extract all model tabs for a product family in a single Playwright session.

    Returns a dict mapping bare model name → HikrobotTabResult.
    More efficient than calling ``extract_hikrobot_tab`` per model because the
    category page is only loaded once.
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        return {}

    family = family.upper()
    category_url = HIKROBOT_CATEGORY_URLS.get(family)
    if not category_url:
        return {}

    results: dict[str, HikrobotTabResult] = {}

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
                locale="en-US",
                extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
            )
            if stealth:
                try:
                    from playwright_stealth import Stealth
                    page = ctx.new_page()
                    Stealth().apply_stealth_sync(page)
                except ImportError:
                    page = ctx.new_page()
            else:
                page = ctx.new_page()

            page.goto(category_url, wait_until="networkidle", timeout=timeout_ms * 3)
            time.sleep(1.5)

            tabs = page.query_selector_all('[role="tab"]')
            print(f"  [hikrobot] {family}: found {len(tabs)} tabs on {category_url}", flush=True)

            for tab in tabs:
                label = (tab.inner_text() or "").strip()
                tab_id = tab.get_attribute("id") or ""
                if not label or not tab_id:
                    continue

                print(f"    clicking tab: {label!r} ({tab_id})", flush=True)
                tab.click()
                pane_id = tab_id.replace("tab-", "pane-")
                try:
                    page.wait_for_selector(
                        f"#{pane_id}",
                        state="visible",
                        timeout=timeout_ms,
                    )
                except PWTimeout:
                    pass
                time.sleep(settle_s)

                html = page.content()
                pane_el = page.query_selector(f"#{pane_id}")
                panel_text = (pane_el.inner_text() if pane_el else page.inner_text("body")) or ""
                title = page.title() or ""

                images = _extract_images_from_html(html, category_url)

                results[label] = HikrobotTabResult(
                    model=label,
                    family=family,
                    category_url=category_url,
                    tab_id=tab_id,
                    html=html,
                    text=f"{label}\n{title}\n{panel_text}",
                    images=images,
                    success=True,
                )

            browser.close()

    except Exception as exc:
        print(f"  [hikrobot] extract_all_tabs error: {exc}", flush=True)

    return results
