"""Re-check published robots (and their makers) that were approved a while ago.

Martti (2026-11-11): "start a new discovery process to validate existing
published company and robot data — those approved 3 months and older. We need
to make sure we have relevant data, up to date."

The AI verification score (verify_content) only says our data matches the
source page; it cannot say the page still exists or the product is still
sold. This script answers the freshness question, per robot:

  1. source page health — probed politely (browser headers, one request at a
     time, a delay per domain) and classified by its BODY, not only its status:
       ok | dead (404/410/DNS) | soft404 (200 with "not found" copy) |
       empty (SPA shell, no text) | redirected_home | blocked (403/406/418/429:
       a bot wall or rate limit — the page may well exist; never called dead) |
       unreachable (SSL/timeout) | no_url
  2. is the model still named on that page?
  3. headline specs read off the page (regex, free) against ours — a LEAD for
     a reviewer, never a correction (family pages carry several models).
  4. one metered Gemini call per robot with a live page: still current,
     discontinued or replaced (successor), plus page price/availability and
     spec conflicts, each with the quote it came from.
  5. dead / soft404 / model-gone rows get one search on the maker's domain
     for a candidate replacement page.

and once per maker in the run: website alive? redirected to another domain
(rebrand or acquisition signal)?

It WRITES NOTHING to the site. Live robots go back through review by a
person (feedback: no auto-fix on live robots). Output is a JSON snapshot and
a review CSV in output/. Funding is not checked here: recheck_company_funding
covers it.

Cost guards (every paid call capped and counted, printed at the end):
  --max-robots (300 hard cap on --limit)   robots per run
  --max-gemini (150)                        Gemini calls per run, and spend_guard's
                                            daily USD/call budgets on top
                                            (SpendBudgetExceeded stops the run)
  --max-searches (60)                       serper searches per run
  scrape.serper.dev fallback for walled pages is capped by the fetcher budget.

Run from scripts/research:
  export PYTHONIOENCODING=utf-8
  python recheck_published.py --company-id 807                 # one maker, dry run
  python recheck_published.py --limit 50 --no-gemini           # free checks only
  python recheck_published.py --limit 100 --older-than-days 90
Env: IMPORT_SYNC_API_BASE_URL, IMPORT_SYNC_API_KEY (admin key), SERPER_API_KEY,
GEMINI_API_KEY. Missing ones are read from ../../robotaigeek-server/.env.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from collections import Counter, OrderedDict
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import urlparse

import requests

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from recheck_company_funding import domain_of, load_env_file, serper_search  # noqa: E402

# ---------------------------------------------------------------------------
# Page probing
# ---------------------------------------------------------------------------

BROWSER_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/124.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
BLOCKED_CODES = {401, 403, 406, 418, 429, 503}
DEAD_CODES = {404, 410}
MIN_TEXT_CHARS = 400  # web_extract._BOT_WALL_TEXT_CHARS: below this the page is a shell or a wall

_NOT_FOUND_RE = re.compile(
    r"page (?:was )?not found|page (?:you|you're|you are) looking for|(?:doesn't|does not|no longer) exists?|"
    r"\b404\b.{0,40}(?:error|not found|page)|error 404|product (?:is )?(?:no longer|not) available|"
    r"页面不存在|找不到|您访问的页面|ページが見つかりません|페이지를 찾을 수 없습니다",
    re.I)


@dataclass
class Probe:
    url: str
    status: str            # ok | dead | soft404 | empty | redirected_home | blocked | unreachable | no_url
    http: int | None = None
    final_url: str = ""
    title: str = ""
    text: str = ""         # main text (product copy) when the page is usable
    full_text: str = ""    # whole-page text, for model-name matching
    detail: str = ""


def _page_parts(url: str, html: str) -> tuple[str, str, str]:
    """(title, main_text, full_text) through web_extract's own parser."""
    try:
        import web_extract
        page = web_extract.page_from_html(url, html or "")
    except Exception:  # noqa: BLE001
        page = None
    if page is None:
        return "", "", ""
    return page.title or "", (page.main_text or page.text or ""), (page.text or "")


def _is_deep(path: str) -> bool:
    return len([p for p in (path or "").split("/") if p]) >= 1


def classify(url: str, http: int | None, final_url: str, title: str, full_text: str, error: str = "") -> tuple[str, str]:
    """Pure classification of one fetch. Returns (status, detail)."""
    if not url:
        return "no_url", ""
    if http is None:
        return "unreachable", error[:120]
    if http in DEAD_CODES:
        return "dead", f"HTTP {http}"
    if http in BLOCKED_CODES:
        return "blocked", f"HTTP {http}"
    if http >= 400:
        return "unreachable", f"HTTP {http}"
    orig, final = urlparse(url), urlparse(final_url or url)
    if _is_deep(orig.path) and not _is_deep(final.path) and not final.query:
        return "redirected_home", f"-> {final_url}"[:200]
    head = f"{title} {full_text[:1500]}"
    if _NOT_FOUND_RE.search(title or "") or (len(full_text) < 3000 and _NOT_FOUND_RE.search(head)):
        return "soft404", (title or full_text[:80]).strip()[:120]
    if len(full_text.strip()) < MIN_TEXT_CHARS:
        return "empty", f"{len(full_text.strip())} chars of text"
    return "ok", ""


class PoliteFetcher:
    """One request at a time, at least `per_domain_delay` seconds between hits
    on the same host. Walled/empty pages get one scrape.serper.dev retry through
    web_extract's ladder (capped there)."""

    def __init__(self, *, per_domain_delay: float = 2.0, timeout: int = 20, rescue: bool = True,
                 serper_scrape_budget: int = 40):
        self.session = requests.Session()
        self.session.headers.update(BROWSER_HEADERS)
        self.delay = per_domain_delay
        self.timeout = timeout
        self.rescue = rescue
        self._last: dict[str, float] = {}
        self._ladder = None
        self.serper_scrape_budget = serper_scrape_budget
        self.requests = 0
        self.rescues = 0

    def _wait(self, url: str) -> None:
        host = domain_of(url)
        gap = time.monotonic() - self._last.get(host, 0.0)
        if gap < self.delay:
            time.sleep(self.delay - gap)
        self._last[host] = time.monotonic()

    def _rescue_html(self, url: str) -> str:
        if not self.rescue:
            return ""
        try:
            import web_extract
            if self._ladder is None:
                self._ladder = web_extract.WebFetcher(serper_budget=self.serper_scrape_budget)
            self.rescues += 1
            return self._ladder.serper_get(url) or ""
        except Exception:  # noqa: BLE001
            return ""

    def probe(self, url: str) -> Probe:
        if not url:
            return Probe(url="", status="no_url")
        self._wait(url)
        self.requests += 1
        http, final, html, err = None, url, "", ""
        for attempt in range(2):
            try:
                resp = self.session.get(url, timeout=self.timeout, allow_redirects=True)
                http, final = resp.status_code, resp.url
                html = resp.text if resp.status_code < 400 else ""
                break
            except requests.RequestException as exc:
                err = f"{type(exc).__name__}: {exc}"
                if attempt == 0:
                    time.sleep(3)
        title, main, full = _page_parts(final, html)
        status, detail = classify(url, http, final, title, full, err)
        if status in ("blocked", "empty", "unreachable"):
            # A wall or an SPA shell to plain requests is often a normal page to a
            # real browser; only call it broken if the rescue tier agrees.
            rescued = self._rescue_html(url)
            if rescued:
                t2, m2, f2 = _page_parts(url, rescued)
                s2, d2 = classify(url, 200, url, t2, f2)
                if s2 in ("ok", "soft404"):
                    return Probe(url=url, status=s2, http=http, final_url=final, title=t2, text=m2, full_text=f2,
                                 detail=(d2 or f"rescued after {status}"))
        return Probe(url=url, status=status, http=http, final_url=final, title=title, text=main, full_text=full,
                     detail=detail)


# ---------------------------------------------------------------------------
# Comparisons
# ---------------------------------------------------------------------------

# (field, tolerance as a fraction; 0 = must match exactly)
SPEC_FIELDS = (("payload_kg", 0.05), ("reach_mm", 0.03), ("repeatability_mm", 0.0), ("dof", 0.0),
               ("weight_kg", 0.08), ("runtime_minutes", 0.10))


def _num(v: Any) -> float | None:
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def spec_diffs(ours: dict[str, Any], page_specs: dict[str, Any]) -> list[dict[str, Any]]:
    """Fields set on both sides whose values disagree beyond tolerance."""
    out = []
    for f, tol in SPEC_FIELDS:
        a, b = _num(ours.get(f)), _num(page_specs.get(f))
        if a is None or b is None:
            continue
        if tol == 0:
            differs = abs(a - b) > 1e-9
        else:
            differs = abs(a - b) > tol * max(abs(a), abs(b))
        if differs:
            out.append({"field": f, "ours": a, "page": b})
    return out


def model_on_page(robot: dict[str, Any], probe: Probe) -> bool | None:
    if probe.status not in ("ok",):
        return None
    try:
        import web_extract
        page = web_extract.PageContent(url=probe.final_url or probe.url, html="", text=probe.full_text,
                                       main_text=probe.text, title=probe.title)
        return web_extract.confirm_target_on_page(robot.get("name") or "", robot.get("model_name") or "", page)
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Gemini freshness check (metered)
# ---------------------------------------------------------------------------

_FRESHNESS_SYSTEM = """You check whether OUR catalogue record for ONE robot is still current, using
the maker's product page (and any search snippets) as evidence. Return JSON only:
{
  "product_status": "current" | "discontinued" | "replaced" | "not_on_page" | "unclear",
  "successor": "name of the model that replaces it, only if the evidence says so, else ''",
  "page_availability": "what the page says about availability/ordering, else ''",
  "page_price": "price exactly as written on the page, else ''",
  "spec_conflicts": [ {"field": "payload_kg|reach_mm|repeatability_mm|dof|weight_kg|runtime_minutes|speed|other",
                       "ours": "...", "page": "...", "quote": "the sentence or table cell"} ],
  "confidence": "high" | "medium" | "low",
  "quote": "the one sentence that best supports product_status"
}
Rules:
- "discontinued"/"replaced" ONLY when the evidence says so (end of life, discontinued, no longer
  available, succeeded by, replaced by). A missing price or a sparse page is NOT discontinued.
- "not_on_page" when the page does not describe this model at all (wrong product, category list).
- "current" when the page presents the model as a product on sale/offer today.
- spec_conflicts only for values the page states for THIS model (not a sibling variant on the same
  page) that differ from ours. Ignore unit-rounding differences under 5%.
- Our record's units: payload_kg kg, reach_mm mm, repeatability_mm mm, weight_kg kg, speed km/h,
  runtime_minutes minutes. A page value that is the SAME quantity in another unit (3000 kg vs
  6614 lb, 7.92 km/h vs 2.2 m/s) is NOT a conflict. Copy the page value with its unit as written.
- Never infer numbers. No conflicts -> []."""

# Units of our record's numeric fields, for real_conflict().
OUR_UNITS = {"payload_kg": "kg", "weight_kg": "kg", "reach_mm": "mm", "repeatability_mm": "mm",
             "speed": "km/h", "runtime_minutes": "min", "dof": ""}
# Factor to our unit, per unit as written on pages.
_TO_BASE = {
    "kg": ("kg", 1.0), "kgs": ("kg", 1.0), "t": ("kg", 1000.0), "ton": ("kg", 1000.0), "tons": ("kg", 1000.0),
    "lb": ("kg", 0.45359237), "lbs": ("kg", 0.45359237), "g": ("kg", 0.001),
    "mm": ("mm", 1.0), "cm": ("mm", 10.0), "m": ("mm", 1000.0), "in": ("mm", 25.4), "inch": ("mm", 25.4),
    "km/h": ("km/h", 1.0), "kmh": ("km/h", 1.0), "kph": ("km/h", 1.0), "m/s": ("km/h", 3.6),
    "mph": ("km/h", 1.609344), "mm/s": ("km/h", 0.0036),
    "min": ("min", 1.0), "mins": ("min", 1.0), "minutes": ("min", 1.0), "h": ("min", 60.0), "hr": ("min", 60.0),
    "hrs": ("min", 60.0), "hours": ("min", 60.0), "hour": ("min", 60.0),
}
_UNIT_WORDS = {"meters per second": "m/s", "metres per second": "m/s", "kilometers per hour": "km/h",
               "kilometres per hour": "km/h", "miles per hour": "mph", "kilograms": "kg", "kilogram": "kg",
               "pounds": "lb", "pound": "lb", "grams": "g", "gram": "g", "millimeters": "mm", "millimetres": "mm",
               "centimeters": "cm", "centimetres": "cm", "meters": "m", "metres": "m", "inches": "in"}
_QTY_RE = re.compile(r"(-?\d+(?:[.,]\d+)?)\s*(" + "|".join(sorted(map(re.escape, _UNIT_WORDS), key=len, reverse=True))
                     + r"|km/h|kmh|kph|m/s|mm/s|mph|kgs?|lbs?|tons?|t|g|mm|cm|m|inch|in|"
                     r"minutes|mins?|hours?|hrs?|hr|h)?(?![a-z])", re.I)


_RANGE_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:[a-z/]+\s*)?(?:to|-|–|—|~)\s*(\d+(?:[.,]\d+)?)\s*([a-z/]+)?", re.I)


def _page_quantity(text: str, our_unit: str) -> float | None:
    """First number in `text` converted to our unit; None when its unit is foreign or unknown."""
    matches = list(_QTY_RE.finditer(str(text or "").replace("±", "")))
    if not matches:
        return None
    # "Mavic 2 Pro: 907 g": the quantity is the number WITH a unit, not the model number.
    m = next((x for x in matches if x.group(2)), None) or (matches[0] if len(matches) == 1 else None)
    if m is None:
        return None
    value = float(m.group(1).replace(",", "."))
    unit = (m.group(2) or "").lower()
    unit = _UNIT_WORDS.get(unit, unit)
    if not unit:
        return value if our_unit in ("", "kg", "mm", "km/h", "min") else None
    base, factor = _TO_BASE.get(unit, (None, None))
    if base != our_unit:
        return None
    return value * factor


def ground_conflicts(robot: dict[str, Any], freshness: dict[str, Any] | None) -> None:
    """Replace Gemini's "ours" with the value actually on our record, and drop the
    conflict when we hold no value. Gemini invented "ours" for ABB repeatability
    (0.013, 0.35, 0.12) on robots whose repeatability is empty (2026-11-11 batch)."""
    if not freshness:
        return
    kept = []
    for c in freshness.get("spec_conflicts") or []:
        field_ = str(c.get("field") or "")
        if field_ in OUR_UNITS:
            value = robot.get(field_)
            if value in (None, ""):
                continue
            c = {**c, "ours": value}
            if not real_conflict(c):
                continue
        kept.append(c)
    freshness["spec_conflicts"] = kept


def real_conflict(c: dict[str, Any], tol: float = 0.05) -> bool:
    """False when Gemini's 'conflict' is the same quantity in another unit or rounding."""
    field_ = str(c.get("field") or "")
    if field_ not in OUR_UNITS:
        return True
    ours = _num(re.sub(r"[^\d.\-]", "", str(c.get("ours") or "")) or None)
    page_text = str(c.get("page") or "")
    rng = _RANGE_RE.search(page_text)
    if rng and ours is not None:
        # "available in four variants, 20 to 60 kg": a family range, not this model's value.
        unit = rng.group(3) or ""
        lo = _page_quantity(f"{rng.group(1)} {unit}", OUR_UNITS[field_])
        hi = _page_quantity(f"{rng.group(2)} {unit}", OUR_UNITS[field_])
        if lo is not None and hi is not None:
            return not (min(lo, hi) * (1 - tol) <= ours <= max(lo, hi) * (1 + tol))
    page = _page_quantity(page_text, OUR_UNITS[field_])
    if ours is None or page is None:
        return ours is not None  # nothing on our side = missing data, not a conflict
    if field_ == "dof":
        return abs(ours - page) > 1e-9
    return abs(ours - page) > tol * max(abs(ours), abs(page))


def gemini_freshness(robot: dict[str, Any], company: str, probe: Probe, snippets: list[dict[str, str]],
                     *, model: str = "models/gemini-2.5-flash") -> dict[str, Any] | None:
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return None
    from google.genai import types

    import spend_guard
    client = spend_guard.client(api_key=api_key, http_options={"api_version": "v1beta"})
    ours = {k: robot.get(k) for k in ("name", "model_name", "release_year", "price_min", "price_max", "price_currency",
                                      "payload_kg", "reach_mm", "repeatability_mm", "dof", "weight_kg", "speed",
                                      "runtime_minutes") if robot.get(k) not in (None, "")}
    avail = robot.get("availability_status")
    if isinstance(avail, dict):
        ours["availability"] = avail.get("label") or avail.get("key")
    blocks = [f"[PAGE] {probe.final_url or probe.url}\nTitle: {probe.title}\n{probe.text[:9000]}"]
    for s in snippets[:6]:
        blocks.append(f"[SEARCH] {s.get('link', '')} ({s.get('date', '')})\n{s.get('title', '')}\n{s.get('snippet', '')}")
    prompt = (f"{_FRESHNESS_SYSTEM}\n\nMaker: {company}\nOur record: {json.dumps(ours, ensure_ascii=False, default=str)}"
              f"\n\n--- Evidence ---\n" + "\n\n".join(blocks))
    resp = client.models.generate_content(
        model=model, contents=prompt[:40000],
        config=types.GenerateContentConfig(temperature=0.0, response_mime_type="application/json",
                                           max_output_tokens=1024,
                                           thinking_config=types.ThinkingConfig(thinking_budget=0)))
    return parse_freshness(resp.text or "")


_STATUSES = {"current", "discontinued", "replaced", "not_on_page", "unclear"}


def parse_freshness(text: str) -> dict[str, Any] | None:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", (text or "").strip())
    try:
        data = json.loads(text)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    status = str(data.get("product_status") or "unclear").strip().lower()
    conflicts = [c for c in (data.get("spec_conflicts") or []) if isinstance(c, dict) and c.get("field")]
    conflicts = [c for c in conflicts if real_conflict(c)]
    return {
        "product_status": status if status in _STATUSES else "unclear",
        "successor": str(data.get("successor") or "")[:120],
        "page_availability": str(data.get("page_availability") or "")[:200],
        "page_price": str(data.get("page_price") or "")[:120],
        "spec_conflicts": conflicts[:8],
        "confidence": str(data.get("confidence") or "low").lower(),
        "quote": str(data.get("quote") or "")[:300],
    }


# ---------------------------------------------------------------------------
# Verdict
# ---------------------------------------------------------------------------

BROKEN_PAGE = {"dead", "soft404", "redirected_home", "empty"}


def reasons_for(rec: dict[str, Any]) -> list[str]:
    """Why a person should look at this robot. Empty list = nothing found."""
    out: list[str] = []
    page = rec.get("page_status")
    if page in BROKEN_PAGE:
        out.append(f"source page {page}")
    elif page == "no_url":
        out.append("no source URL")
    if rec.get("model_on_page") is False:
        out.append("model not named on source page")
    # Makers move retired products to support/download pages (all four old DJI
    # models in the 2026-11-11 pilot); free, and Gemini cannot see it on the page.
    path = (urlparse(rec.get("page_final") or rec.get("url") or "").path or "").lower()
    if page == "ok" and re.search(r"/(support|downloads?|service|eol|legacy|archive)(/|$)", path):
        out.append("source is a support/archive page (product may be retired)")
    fr = rec.get("freshness") or {}
    st = fr.get("product_status")
    if st in ("discontinued", "replaced") and fr.get("confidence") in ("high", "medium"):
        if st == "replaced" and is_the_successor(rec.get("name") or "", fr.get("successor") or ""):
            # ABB "IRB 1200-9/0.7 Gen2" linked to the old IRB 1200 page, which says
            # "replaced by IRB 1200 Next Gen (Gen 2)": the robot IS the successor,
            # only its link is stale (2026-11-11 batch).
            out.append("source page is the predecessor's page")
        else:
            out.append(st + (f" -> {fr['successor']}" if fr.get("successor") else ""))
    # The deterministic name match wins: Gemini said "not on page" for DJI Air 3S
    # and Mavic 4 Pro, both named in the page title (2026-11-11 pilot).
    if st == "not_on_page" and rec.get("model_on_page") is None:
        out.append("page does not describe this model")
    if rec.get("spec_diffs"):
        out.append("spec differs: " + ", ".join(d["field"] for d in rec["spec_diffs"]))
    if fr.get("spec_conflicts"):
        fields = sorted({str(c.get("field")) for c in fr["spec_conflicts"]} - {d["field"] for d in rec.get("spec_diffs", [])})
        if fields:
            out.append("page states different: " + ", ".join(fields))
    return out


_GEN_RE = re.compile(r"gen\s*\.?\s*(\d+)|next\s*gen|mk\s*(ii+|\d)|(?<![a-z0-9])v(\d)(?![a-z0-9])", re.I)


def is_the_successor(name: str, successor: str) -> bool:
    """True when our robot's name already carries the successor's generation marker."""
    a, b = _GEN_RE.findall(name or ""), _GEN_RE.findall(successor or "")
    if not a or not b:
        return False
    norm = lambda xs: {"".join(x).lower() or "next" for x in xs}  # noqa: E731
    return bool(norm(a) & norm(b)) or ("next" in norm(b) and bool(a))


# Family pages (KUKA lists variants in a script-rendered table, or as
# "KR 8 R1440-2 arc HW" for our "KR 8 R1440 arc HW-2"): the model not being in the
# static text is a weak signal when Gemini reads the page as current.
LOW_ONLY = ("model not named on source page",)


def priority_of(reasons: list[str], freshness: dict[str, Any] | None = None) -> str:
    if any(r.startswith(("discontinued", "replaced", "source page dead", "source page soft404")) for r in reasons):
        return "high"
    if reasons and all(r in LOW_ONLY for r in reasons) and (freshness or {}).get("product_status") == "current":
        return "low"
    if reasons:
        return "medium"
    return ""


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

@dataclass
class Stats:
    robots: int = 0
    companies: int = 0
    page_requests: int = 0
    scrape_rescues: int = 0
    searches: int = 0
    gemini_calls: int = 0
    gemini_skipped_cap: int = 0
    flagged: int = 0
    high: int = 0
    errors: int = 0


def _get_with_backoff(api: Any, path: str, params: dict[str, Any] | None = None, tries: int = 6) -> Any:
    for a in range(tries):
        try:
            return api._get(path, params)
        except Exception:  # noqa: BLE001 — prod 429s/resets under agent load
            if a == tries - 1:
                raise
            time.sleep(4 * (a + 1))


def stale_robots(api: Any, cutoff: str, *, company_ids: list[int] | None = None) -> list[dict[str, Any]]:
    """Published robots with published_at on or before `cutoff` (YYYY-MM-DD),
    oldest first. Robots with no published_at are left out (40 on 2026-11-11)."""
    out: list[dict[str, Any]] = []
    page = 1
    params: dict[str, Any] = {"lite": 1, "status": "published", "ordering": "published_at", "page_size": 100}
    while True:
        data = _get_with_backoff(api, "robots/robots/", {**params, "page": page})
        rows = data.get("results", []) if isinstance(data, dict) else (data or [])
        stop = False
        for r in rows:
            p = (r.get("published_at") or "")[:10]
            if not p:
                continue
            if p > cutoff:
                stop = True
                break
            c = r.get("company_ref")
            cid = c.get("id") if isinstance(c, dict) else None
            if company_ids and cid not in company_ids:
                continue
            out.append({"id": r["id"], "name": r.get("name"), "company_id": cid,
                        "company": (c.get("name") if isinstance(c, dict) else r.get("company")) or "",
                        "published_at": p})
        if stop or not rows or (isinstance(data, dict) and not data.get("next")):
            break
        page += 1
    return out


def order_by_company(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Makers with the most stale robots first, so a run finishes whole makers."""
    counts = Counter(r["company_id"] for r in rows)
    return sorted(rows, key=lambda r: (-counts[r["company_id"]], r["company_id"] or 0, r["published_at"], r["id"]))


class PublishedRecheck:
    def __init__(self, api: Any, *, fetcher: Any = None, search: Callable[..., list[dict[str, Any]]] = serper_search,
                 freshness: Callable[..., dict[str, Any] | None] = gemini_freshness, use_gemini: bool = True,
                 max_gemini: int = 150, max_searches: int = 60, run_id: str = ""):
        self.api = api
        self.fetcher = fetcher or PoliteFetcher()
        self.search = search
        self.freshness = freshness
        self.use_gemini = use_gemini
        self.max_gemini = max(0, max_gemini)
        self.max_searches = max(0, max_searches)
        self.run_id = run_id or datetime.now().strftime("%Y%m%d-%H%M")
        self.stats = Stats()
        self.records: list[dict[str, Any]] = []
        self.companies: "OrderedDict[int, dict[str, Any]]" = OrderedDict()
        self.checkpoint: Callable[[], None] | None = None

    # -- maker --------------------------------------------------------------

    def check_company(self, cid: int | None, name: str) -> dict[str, Any]:
        if cid is None or cid in self.companies:
            return self.companies.get(cid, {}) if cid is not None else {}
        rec: dict[str, Any] = {"company_id": cid, "name": name, "reasons": []}
        try:
            company = _get_with_backoff(self.api, f"companies/{cid}/")
        except Exception as exc:  # noqa: BLE001
            rec["error"] = f"{type(exc).__name__}: {exc}"[:200]
            self.companies[cid] = rec
            return rec
        self.stats.companies += 1
        website = (company.get("website") or "").strip()
        rec.update({"website": website, "publication_status": company.get("publication_status"),
                    "company_status": company.get("company_status") or ""})
        if not website:
            rec["website_status"] = "no_url"
            rec["reasons"].append("no website")
        else:
            p = self.fetcher.probe(website)
            rec["website_status"] = p.status if p.status != "redirected_home" else "ok"
            rec["website_final"] = p.final_url
            if p.status in ("dead", "unreachable"):
                rec["reasons"].append(f"website {p.status} ({p.detail})")
            a, b = domain_of(website), domain_of(p.final_url or website)
            if a and b and a != b and not (b.endswith("." + a) or a.endswith("." + b)):
                rec["reasons"].append(f"website now redirects to {b}")
        self.companies[cid] = rec
        return rec

    # -- robot --------------------------------------------------------------

    def candidate_pages(self, robot: dict[str, Any], website: str) -> list[dict[str, str]]:
        if self.stats.searches >= self.max_searches:
            return []
        host = domain_of(website)
        name = robot.get("model_name") or robot.get("name") or ""
        q = f'"{name}"' + (f" site:{host}" if host else f" {robot.get('company') or ''}")
        self.stats.searches += 1
        results = self.search(q, num=6) or []
        return [{"link": r.get("link", ""), "title": r.get("title", ""), "snippet": r.get("snippet", ""),
                 "date": r.get("date", "")} for r in results if r.get("link")][:5]

    def process(self, brief: dict[str, Any]) -> dict[str, Any]:
        robot = _get_with_backoff(self.api, f"robots/robots/{brief['id']}/")
        rec: dict[str, Any] = {"robot_id": brief["id"], "name": robot.get("name"), "company_id": brief.get("company_id"),
                               "company": brief.get("company"), "published_at": brief.get("published_at"),
                               "url": robot.get("url") or ""}
        if robot.get("status") != "published":
            rec["skipped"] = f"status now {robot.get('status')}"
            return rec
        self.stats.robots += 1
        company = self.check_company(brief.get("company_id"), brief.get("company") or "")
        probe = self.fetcher.probe(rec["url"])
        rec.update({"page_status": probe.status, "page_http": probe.http, "page_final": probe.final_url,
                    "page_detail": probe.detail})
        rec["model_on_page"] = model_on_page(robot, probe)
        if probe.status == "ok":
            try:
                import web_extract
                page_specs = web_extract.extract_specs_from_text(probe.text)
            except Exception:  # noqa: BLE001
                page_specs = {}
            # Only trust page numbers when the page is about this model, and only
            # without Gemini: the regex reader takes any number near a label
            # (runtime "360 min" off a DJI support page), Gemini reads the table.
            use_regex = rec["model_on_page"] and not self.use_gemini
            rec["spec_diffs"] = spec_diffs(robot, page_specs) if use_regex else []
        snippets: list[dict[str, str]] = []
        if probe.status in BROKEN_PAGE or probe.status == "no_url" or rec["model_on_page"] is False:
            snippets = self.candidate_pages(robot, company.get("website") or "")
            rec["candidate_pages"] = [s["link"] for s in snippets]
        if self.use_gemini and probe.status == "ok":
            if self.stats.gemini_calls >= self.max_gemini:
                self.stats.gemini_skipped_cap += 1
                rec["freshness_skipped"] = "gemini cap reached"
            else:
                self.stats.gemini_calls += 1
                rec["freshness"] = self.freshness(robot, brief.get("company") or "", probe, snippets)
                ground_conflicts(robot, rec["freshness"])
        rec["reasons"] = reasons_for(rec)
        rec["priority"] = priority_of(rec["reasons"], rec.get("freshness"))
        if rec["priority"] in ("high", "medium"):
            self.stats.flagged += 1
        if rec["priority"] == "high":
            self.stats.high += 1
        return rec

    def run(self, rows: Iterable[dict[str, Any]], *, limit: int) -> None:
        for i, brief in enumerate(rows):
            if i >= limit:
                break
            try:
                rec = self.process(brief)
            except Exception as exc:  # noqa: BLE001
                if type(exc).__name__ == "SpendBudgetExceeded":
                    print(f"STOP: {exc}", flush=True)
                    break
                self.stats.errors += 1
                rec = {"robot_id": brief.get("id"), "name": brief.get("name"), "company": brief.get("company"),
                       "error": f"{type(exc).__name__}: {exc}"[:300]}
            self.records.append(rec)
            self.print_record(rec)
            if self.checkpoint:
                self.checkpoint()
        self.stats.page_requests = getattr(self.fetcher, "requests", 0)
        self.stats.scrape_rescues = getattr(self.fetcher, "rescues", 0)

    @staticmethod
    def print_record(rec: dict[str, Any]) -> None:
        head = f"[{rec.get('robot_id')}] {rec.get('company')} / {rec.get('name')}"
        if rec.get("error"):
            print(f"{head}: ERROR {rec['error']}", flush=True)
        elif rec.get("skipped"):
            print(f"{head}: skipped ({rec['skipped']})", flush=True)
        elif rec.get("reasons"):
            print(f"{head}: {rec['priority'].upper()} — {'; '.join(rec['reasons'])}", flush=True)
        else:
            fr = (rec.get("freshness") or {}).get("product_status", "-")
            print(f"{head}: ok (page {rec.get('page_status')}, {fr})", flush=True)

    def summary(self) -> str:
        s = self.stats
        spend = ""
        try:
            import spend_guard
            spend = f"\nGEMINI SPEND: {json.dumps(spend_guard.status(), default=str)}"
        except Exception:  # noqa: BLE001
            pass
        pages = Counter(r.get("page_status") for r in self.records if r.get("page_status"))
        fresh = Counter((r.get("freshness") or {}).get("product_status") for r in self.records if r.get("freshness"))
        makers = sum(1 for c in self.companies.values() if c.get("reasons"))
        return (f"\nREPORT-ONLY run {self.run_id}: robots={s.robots} makers={s.companies} flagged={s.flagged} "
                f"(high={s.high}) makers_flagged={makers} errors={s.errors}\n"
                f"pages: {dict(pages)}\nfreshness: {dict(fresh)}\n"
                f"paid calls: gemini={s.gemini_calls} (skipped at cap {s.gemini_skipped_cap}) searches={s.searches} "
                f"scrape_rescues={s.scrape_rescues} page_requests={s.page_requests}{spend}")


def write_csv(path: Path, records: list[dict[str, Any]], companies: dict[int, dict[str, Any]]) -> None:
    cols = ["priority", "robot_id", "company", "name", "published_at", "reasons", "page_status", "page_detail",
            "url", "page_final", "product_status", "successor", "page_price", "page_availability", "quote",
            "candidate_pages", "maker_reasons"]
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        order = {"high": 0, "medium": 1, "low": 2, "": 3}
        for r in sorted(records, key=lambda x: (order.get(x.get("priority", ""), 3), str(x.get("company")), x.get("robot_id") or 0)):
            if r.get("error") or r.get("skipped"):
                continue
            fr = r.get("freshness") or {}
            maker = companies.get(r.get("company_id")) or {}
            w.writerow({
                "priority": r.get("priority", ""), "robot_id": r.get("robot_id"), "company": r.get("company"),
                "name": r.get("name"), "published_at": r.get("published_at"), "reasons": "; ".join(r.get("reasons", [])),
                "page_status": r.get("page_status"), "page_detail": r.get("page_detail"), "url": r.get("url"),
                "page_final": r.get("page_final") if r.get("page_final") != r.get("url") else "",
                "product_status": fr.get("product_status", ""), "successor": fr.get("successor", ""),
                "page_price": fr.get("page_price", ""), "page_availability": fr.get("page_availability", ""),
                "quote": fr.get("quote", ""), "candidate_pages": " ".join(r.get("candidate_pages", [])),
                "maker_reasons": "; ".join(maker.get("reasons", [])),
            })


def done_robot_ids(patterns: list[str]) -> set[int]:
    import glob
    done: set[int] = set()
    for pattern in patterns or []:
        for path in glob.glob(pattern):
            try:
                data = json.loads(Path(path).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            for rec in data.get("records", []):
                if rec.get("robot_id") and not rec.get("error"):
                    done.add(int(rec["robot_id"]))
    return done


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--older-than-days", type=int, default=90, help="published at least this many days ago (default 90)")
    ap.add_argument("--company-id", type=int, action="append", help="only this maker's robots (repeatable)")
    ap.add_argument("--limit", type=int, default=50, help="robots this run (default 50)")
    ap.add_argument("--max-robots", type=int, default=300, help="hard cap on --limit (default 300)")
    ap.add_argument("--max-gemini", type=int, default=150, help="Gemini calls this run (default 150)")
    ap.add_argument("--max-searches", type=int, default=60, help="serper searches this run (default 60)")
    ap.add_argument("--no-gemini", action="store_true", help="free checks only (page health, model name, regex specs)")
    ap.add_argument("--no-rescue", action="store_true", help="never use the scrape.serper.dev tier for walled pages")
    ap.add_argument("--per-domain-delay", type=float, default=2.0, help="seconds between hits on one host (default 2)")
    ap.add_argument("--exclude-snapshots", action="append", default=[],
                    help="glob of earlier snapshots; robots in them are skipped (rotation)")
    ap.add_argument("--out", default="", help="snapshot path (default output/published_recheck_<run>.json)")
    args = ap.parse_args(argv)

    filled = load_env_file()
    if filled:
        print(f"env from server .env: {', '.join(filled)}", flush=True)
    for key in ("IMPORT_SYNC_API_BASE_URL", "IMPORT_SYNC_API_KEY"):
        if not os.environ.get(key):
            print(f"missing env {key}", file=sys.stderr)
            return 2
    if not args.no_gemini and not os.environ.get("GEMINI_API_KEY"):
        print("missing env GEMINI_API_KEY (or pass --no-gemini)", file=sys.stderr)
        return 2

    from api_client import ResearchApiClient
    api = ResearchApiClient()
    cutoff = (date.today() - timedelta(days=args.older_than_days)).isoformat()
    rows = stale_robots(api, cutoff, company_ids=args.company_id)
    total = len(rows)
    exclude = done_robot_ids(args.exclude_snapshots)
    rows = order_by_company([r for r in rows if r["id"] not in exclude])
    limit = min(args.limit, args.max_robots)
    job = PublishedRecheck(api, fetcher=PoliteFetcher(per_domain_delay=args.per_domain_delay, rescue=not args.no_rescue),
                           use_gemini=not args.no_gemini, max_gemini=args.max_gemini, max_searches=args.max_searches)
    print(f"REPORT-ONLY published re-check {job.run_id}: {total} published robots on or before {cutoff}"
          f"{f' ({len(exclude)} done in earlier runs)' if exclude else ''}; checking up to {limit} "
          f"(gemini cap {0 if args.no_gemini else args.max_gemini}, search cap {args.max_searches})", flush=True)
    out = Path(args.out) if args.out else _HERE / "output" / f"published_recheck_{job.run_id}.json"

    def write_snapshot() -> bool:
        try:
            out.parent.mkdir(parents=True, exist_ok=True)
            tmp = out.with_suffix(out.suffix + ".tmp")
            tmp.write_text(json.dumps({"run_id": job.run_id, "cutoff": cutoff, "eligible": total,
                                       "stats": asdict(job.stats), "companies": list(job.companies.values()),
                                       "records": job.records}, indent=1, ensure_ascii=False, default=str),
                           encoding="utf-8")
            tmp.replace(out)
            return True
        except OSError as exc:
            print(f"snapshot not written: {exc}", flush=True)
            return False

    job.checkpoint = write_snapshot
    try:
        job.run(rows, limit=limit)
    finally:
        if write_snapshot():
            csv_path = out.with_suffix(".csv")
            write_csv(csv_path, job.records, job.companies)
            print(f"snapshot: {out}\nreview sheet: {csv_path}", flush=True)
        for c in job.companies.values():
            if c.get("reasons"):
                print(f"MAKER [{c['company_id']}] {c.get('name')}: {'; '.join(c['reasons'])}", flush=True)
        print(job.summary(), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
