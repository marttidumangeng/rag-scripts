#!/usr/bin/env python3
"""Competitor-gap greenfield discovery workflow.

Identifies robot companies that exist on competitor platforms (Robolist.ai,
Aparobot) but are NOT yet in the RobotAIGeek database, then produces a
prioritised seed list ready for the greenfield import pipeline.

Sources scraped (in priority order):
  1. Robolist.ai company directory + sitemap  (1,300+ companies, robot counts)
  2. Aparobot company listing                 (~200 humanoid-focused companies)

Output files:
  staging/reports/competitor_gap_companies.json   — full ranked gap list
  staging/reports/competitor_gap_summary.md       — human-readable summary
  seeds/competitor_gap_seeds.txt                  — top-N seeds for greenfield

Usage:
  python competitor_gap_discover.py
  python competitor_gap_discover.py --max-seeds 50
  python competitor_gap_discover.py --source robolist          # robolist only
  python competitor_gap_discover.py --source aparobot          # aparobot only
  python competitor_gap_discover.py --dry-run                  # no file writes
  python competitor_gap_discover.py --local                    # use local API
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree as ET

import requests
from bs4 import BeautifulSoup

_HERE = Path(__file__).resolve().parent
_SCRIPTS = _HERE.parent
for _p in (_HERE, _SCRIPTS):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from load_env import load_research_env  # noqa: E402

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient  # noqa: E402
from company_website_resolve import resolve_company_website  # noqa: E402

# ── Constants ────────────────────────────────────────────────────────────────

ROBOLIST_BASE = "https://robolist.ai"
APAROBOT_BASE = "https://aparobot.com"

REPORTS_DIR = _HERE / "staging" / "reports"
SEEDS_DIR = _HERE / "seeds"

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Robolist categories to scrape for manufacturer data
ROBOLIST_CATEGORIES = [
    "agricultural",
    "agv",
    "amr-warehouse",
    "autonomous-vehicle",
    "cleaning",
    "cobot",
    "delivery",
    "education",
    "exoskeleton",
    "hospitality-service",
    "humanoid",
    "industrial-arm",
    "mobile-manipulator",
    "quadruped",
    "research",
    "surgical-medical",
]

# ── Utilities ────────────────────────────────────────────────────────────────


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def norm_name(value: str) -> str:
    """Normalise a company/robot name for fuzzy matching."""
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.casefold()
    text = text.replace("&", " and ")
    text = re.sub(r"[®™©]", "", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def company_aliases(name: str) -> set[str]:
    """Generate normalised name variants for fuzzy matching."""
    n = norm_name(name)
    aliases = {n}
    for suffix in (
        " robotics", " robot", " robots", " automation", " intelligent",
        " technology", " technologies", " systems", " corporation", " corp",
        " co ltd", " co", " ltd", " limited", " inc", " gmbh", " ag",
        " sa", " plc", " group", " ai",
    ):
        if n.endswith(suffix) and len(n) > len(suffix) + 2:
            aliases.add(n[: -len(suffix)].strip())
    return {a for a in aliases if a}


def fetch_html(url: str, sess: requests.Session | None = None, retries: int = 2) -> str:
    """Fetch URL with retries; return empty string on failure."""
    s = sess or requests.Session()
    for attempt in range(retries + 1):
        try:
            r = s.get(url, headers=UA, timeout=30, allow_redirects=True)
            if r.status_code == 200:
                return r.text
            if r.status_code in (403, 429, 503) and attempt < retries:
                time.sleep(3 * (attempt + 1))
                continue
            return ""
        except requests.RequestException:
            if attempt < retries:
                time.sleep(2)
    return ""


# ── Robolist scraping ────────────────────────────────────────────────────────


def robolist_sitemap_companies(sess: requests.Session) -> list[dict[str, Any]]:
    """Extract company slugs from Robolist sitemap."""
    print("  [robolist] Fetching sitemap...")
    xml_text = fetch_html(f"{ROBOLIST_BASE}/sitemap.xml", sess)
    if not xml_text:
        print("  [robolist] Sitemap fetch failed — trying robots.txt fallback")
        return []
    xml_text = re.sub(r'\sxmlns="[^"]+"', "", xml_text, count=1)
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        print("  [robolist] Sitemap XML parse error")
        return []

    companies: list[dict[str, Any]] = []
    seen: set[str] = set()
    for loc in root.findall(".//loc"):
        url = (loc.text or "").strip()
        if "/companies/" in url and url.rstrip("/").count("/") >= 4:
            slug = urlparse(url).path.rstrip("/").split("/")[-1]
            if slug and slug not in seen:
                seen.add(slug)
                companies.append({"slug": slug, "url": url, "source": "robolist_sitemap"})
    print(f"  [robolist] Sitemap: {len(companies)} company URLs")
    return companies


def robolist_category_manufacturers(sess: requests.Session) -> dict[str, dict[str, Any]]:
    """Scrape category pages to get company names + robot counts."""
    print("  [robolist] Scraping category pages for manufacturer data...")
    by_slug: dict[str, dict[str, Any]] = {}

    for cat in ROBOLIST_CATEGORIES:
        url = f"{ROBOLIST_BASE}/categories/{cat}"
        html = fetch_html(url, sess)
        if not html:
            print(f"    Category {cat}: fetch failed")
            time.sleep(1)
            continue

        soup = BeautifulSoup(html, "html.parser")
        # Extract company links from robot cards
        for a in soup.select('a[href^="/companies/"]'):
            href = a.get("href", "").rstrip("/")
            slug = href.rsplit("/", 1)[-1]
            if not slug or slug == "companies":
                continue
            raw_name = a.get_text(" ", strip=True)
            # Strip country suffix like "Comau · IT"
            name = re.split(r"\s*[·•|]\s*", raw_name, maxsplit=1)[0].strip()
            if not name:
                name = slug.replace("-", " ").title()
            if slug not in by_slug:
                by_slug[slug] = {
                    "slug": slug,
                    "name": name,
                    "url": f"{ROBOLIST_BASE}/companies/{slug}",
                    "categories": [],
                    "robot_count": None,
                    "source": "robolist_category",
                }
            if cat not in by_slug[slug]["categories"]:
                by_slug[slug]["categories"].append(cat)

        # Also try to extract robot counts from company directory section
        for card in soup.select('[class*="card"], [class*="Card"], article, li'):
            text = card.get_text(" ", strip=True)
            m = re.search(r"([\d,]+)\s+robots?", text, re.I)
            if not m:
                continue
            count = int(m.group(1).replace(",", ""))
            for a in card.select('a[href^="/companies/"]'):
                slug = a.get("href", "").rstrip("/").rsplit("/", 1)[-1]
                if slug in by_slug and not by_slug[slug]["robot_count"]:
                    by_slug[slug]["robot_count"] = count

        print(f"    Category {cat}: {len(by_slug)} companies so far")
        time.sleep(0.8)

    return by_slug


def robolist_company_directory(sess: requests.Session) -> list[dict[str, Any]]:
    """Scrape the /companies directory page for names + robot counts."""
    print("  [robolist] Scraping company directory page...")
    html = fetch_html(f"{ROBOLIST_BASE}/companies", sess)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    results: dict[str, dict[str, Any]] = {}

    for a in soup.select('a[href^="/companies/"]'):
        href = a.get("href", "").split("?", 1)[0].rstrip("/")
        if href.count("/") < 2:
            continue
        slug = href.rsplit("/", 1)[-1]
        raw = a.get_text(" ", strip=True)
        name = re.split(r"\s*[·•|]\s*", raw, maxsplit=1)[0].strip()
        if not name:
            name = slug.replace("-", " ").title()

        robot_count = None
        country = None
        node = a
        for _ in range(7):
            node = node.parent
            if node is None:
                break
            text = node.get_text(" ", strip=True)
            m = re.search(r"([\d,]+)\s+robots?", text, re.I)
            if m:
                robot_count = int(m.group(1).replace(",", ""))
            cm = re.search(
                r"\b(United States|China|Germany|Japan|South Korea|France|"
                r"United Kingdom|Italy|Spain|Sweden|Switzerland|Canada|"
                r"Taiwan|Denmark|Austria|Netherlands|Belgium|Finland|"
                r"Norway|Australia|India|Singapore|Israel|Poland|"
                r"Czech Republic|Hungary|Turkey|Brazil|Mexico)\b",
                text,
            )
            if cm:
                country = cm.group(1)
            if robot_count is not None:
                break

        prev = results.get(slug)
        if prev and prev.get("robot_count") and not robot_count:
            continue
        results[slug] = {
            "slug": slug,
            "name": name,
            "url": f"{ROBOLIST_BASE}/companies/{slug}",
            "robot_count": robot_count,
            "country": country,
            "source": "robolist_directory",
        }

    print(f"  [robolist] Directory: {len(results)} companies")
    return list(results.values())


def scrape_robolist(sess: requests.Session) -> list[dict[str, Any]]:
    """Aggregate all Robolist company data from sitemap + categories + directory."""
    sitemap_cos = robolist_sitemap_companies(sess)
    cat_cos = robolist_category_manufacturers(sess)
    dir_cos = robolist_company_directory(sess)

    # Merge: sitemap provides full slug coverage; directory + categories provide names/counts
    merged: dict[str, dict[str, Any]] = {}

    for c in sitemap_cos:
        slug = c["slug"]
        merged[slug] = {
            "slug": slug,
            "name": slug.replace("-", " ").title(),
            "url": c["url"],
            "robot_count": None,
            "country": None,
            "categories": [],
            "source": "robolist",
        }

    for slug, c in cat_cos.items():
        if slug in merged:
            merged[slug].update({k: v for k, v in c.items() if v})
        else:
            merged[slug] = {**c, "source": "robolist"}

    for c in dir_cos:
        slug = c["slug"]
        if slug in merged:
            for k, v in c.items():
                if v and not merged[slug].get(k):
                    merged[slug][k] = v
        else:
            merged[slug] = {**c, "source": "robolist"}

    result = list(merged.values())
    print(f"  [robolist] Total merged: {len(result)} companies")
    return result


# ── Aparobot scraping ────────────────────────────────────────────────────────


def scrape_aparobot(sess: requests.Session) -> list[dict[str, Any]]:
    """Scrape Aparobot company/manufacturer listing."""
    print("  [aparobot] Scraping company listing...")
    html = fetch_html(f"{APAROBOT_BASE}/companies", sess)
    if not html:
        html = fetch_html(f"{APAROBOT_BASE}/manufacturers", sess)
    if not html:
        print("  [aparobot] Company listing fetch failed")
        return []

    soup = BeautifulSoup(html, "html.parser")
    results: dict[str, dict[str, Any]] = {}

    for a in soup.find_all("a", href=True):
        href = a["href"]
        # Aparobot company URLs: /companies/{slug} or /manufacturers/{slug}
        m = re.match(r"^(?:https?://aparobot\.com)?/(companies|manufacturers)/([^/?#]+)", href)
        if not m:
            continue
        slug = m.group(2)
        name = a.get_text(" ", strip=True)
        name = re.split(r"\s*[·•|]\s*", name, maxsplit=1)[0].strip()
        if not name or len(name) < 2:
            name = slug.replace("-", " ").title()
        if slug not in results:
            results[slug] = {
                "slug": slug,
                "name": name,
                "url": f"{APAROBOT_BASE}/companies/{slug}",
                "robot_count": None,
                "country": None,
                "categories": ["humanoid"],
                "source": "aparobot",
            }

    # Also try robots listing to extract manufacturers
    if not results:
        html2 = fetch_html(f"{APAROBOT_BASE}/robots", sess)
        if html2:
            soup2 = BeautifulSoup(html2, "html.parser")
            for a in soup2.find_all("a", href=True):
                href = a["href"]
                m = re.match(r"^(?:https?://aparobot\.com)?/(companies|manufacturers)/([^/?#]+)", href)
                if not m:
                    continue
                slug = m.group(2)
                name = a.get_text(" ", strip=True).strip()
                if not name or len(name) < 2:
                    name = slug.replace("-", " ").title()
                if slug not in results:
                    results[slug] = {
                        "slug": slug,
                        "name": name,
                        "url": f"{APAROBOT_BASE}/companies/{slug}",
                        "robot_count": None,
                        "country": None,
                        "categories": ["humanoid"],
                        "source": "aparobot",
                    }

    print(f"  [aparobot] Found {len(results)} companies")
    return list(results.values())


# ── Known false-positive blocklist ──────────────────────────────────────────
# Companies that ARE in our DB but whose Robolist slug/name doesn't fuzzy-match.
# Add entries here when the gap analysis incorrectly flags them as missing.
# Format: normalised name token (lowercase, no punctuation)
KNOWN_IN_DB: set[str] = {
    "irobot",
    "yaskawa",
    "borunte",
    "realman",
    "geekplus",
    "kawada",
    "meka",
    "star automation",  # industrial distributor, not a robot OEM
}


# ── RobotAIGeek inventory ────────────────────────────────────────────────────


def fetch_rag_inventory(client: ResearchApiClient) -> tuple[list[dict[str, Any]], set[str]]:
    """Fetch all companies from RobotAIGeek and build a normalised name index."""
    print("  [rag] Fetching company inventory...")
    companies: list[dict[str, Any]] = []
    page = 1
    while True:
        try:
            data = client._get("companies/", params={"page": page, "page_size": 200})
        except Exception as e:
            print(f"  [rag] API error page {page}: {e}")
            break
        batch = data.get("results", data if isinstance(data, list) else [])
        if not batch:
            break
        companies.extend(batch)
        if not (isinstance(data, dict) and data.get("next")):
            break
        page += 1
        if page > 100:
            break
        if page % 5 == 0:
            print(f"    ...page {page}, {len(companies)} companies so far")

    # Build normalised name index for fast lookup
    name_index: set[str] = set()
    for c in companies:
        name = c.get("name") or ""
        slug = c.get("slug") or ""
        for alias in company_aliases(name):
            name_index.add(alias)
        if slug:
            name_index.add(norm_name(slug.replace("-", " ")))
            name_index.add(norm_name(slug))

    print(f"  [rag] {len(companies)} companies in DB ({len(name_index)} name keys)")
    return companies, name_index


def is_in_rag(
    company_name: str,
    company_slug: str,
    rag_index: set[str],
    client: ResearchApiClient | None = None,
) -> bool:
    """Return True if the company already exists in RobotAIGeek."""
    # 1. Check known-in-DB blocklist first (fast)
    name_norm = norm_name(company_name)
    for blocked in KNOWN_IN_DB:
        if blocked in name_norm or name_norm in blocked:
            return True

    # 2. Fuzzy alias matching against pre-built index
    for alias in company_aliases(company_name):
        if alias in rag_index:
            return True
    slug_key = norm_name(company_slug.replace("-", " "))
    if slug_key in rag_index:
        return True
    if norm_name(company_slug) in rag_index:
        return True

    # 3. API search fallback for short/ambiguous names (only when client provided)
    if client is not None and len(company_name) >= 4:
        try:
            results = client.search_companies(company_name)
            for hit in results[:3]:
                hit_norm = norm_name(hit.get("name") or "")
                if hit_norm and (hit_norm == name_norm or name_norm in hit_norm or hit_norm in name_norm):
                    # Add to index so future lookups are fast
                    for alias in company_aliases(hit.get("name") or ""):
                        rag_index.add(alias)
                    return True
        except Exception:
            pass

    return False


# ── Gap analysis ─────────────────────────────────────────────────────────────


def score_company(c: dict[str, Any]) -> int:
    """Score a missing company by priority (higher = more urgent to add)."""
    score = 0
    robot_count = c.get("robot_count") or 0
    score += min(robot_count * 3, 150)  # up to 150 pts for robot count

    # Bonus for high-value categories
    cats = c.get("categories") or []
    priority_cats = {"humanoid", "cobot", "surgical-medical", "exoskeleton", "industrial-arm"}
    score += len(priority_cats & set(cats)) * 20

    # Bonus for known countries with large robot industries
    country = (c.get("country") or "").lower()
    if country in ("china", "united states", "germany", "japan", "south korea"):
        score += 15

    # Bonus for aparobot (humanoid-focused, high quality)
    if c.get("source") == "aparobot":
        score += 25

    # Bonus if found on multiple sources
    if c.get("found_on_sources") and len(c["found_on_sources"]) > 1:
        score += 30

    return score


def run_gap_analysis(
    competitor_companies: list[dict[str, Any]],
    rag_index: set[str],
    client: ResearchApiClient | None = None,
) -> list[dict[str, Any]]:
    """Cross-reference competitor companies against RAG inventory."""
    gaps: list[dict[str, Any]] = []
    already_in_rag: list[dict[str, Any]] = []

    # Deduplicate competitor companies by slug (merge sources)
    merged: dict[str, dict[str, Any]] = {}
    for c in competitor_companies:
        slug = c["slug"]
        if slug in merged:
            existing = merged[slug]
            # Merge categories
            cats = set(existing.get("categories") or []) | set(c.get("categories") or [])
            existing["categories"] = sorted(cats)
            # Track all sources
            sources = set(existing.get("found_on_sources") or [existing.get("source", "")])
            sources.add(c.get("source", ""))
            existing["found_on_sources"] = sorted(s for s in sources if s)
            # Take best robot count
            if c.get("robot_count") and not existing.get("robot_count"):
                existing["robot_count"] = c["robot_count"]
            # Take best country
            if c.get("country") and not existing.get("country"):
                existing["country"] = c["country"]
        else:
            merged[slug] = {
                **c,
                "found_on_sources": [c.get("source", "")],
            }

    for slug, c in merged.items():
        name = c.get("name") or slug.replace("-", " ").title()
        if is_in_rag(name, slug, rag_index, client):
            already_in_rag.append(c)
        else:
            c["priority_score"] = score_company(c)
            gaps.append(c)

    # Sort by priority score descending
    gaps.sort(key=lambda x: x.get("priority_score", 0), reverse=True)

    print(f"\n  Gap analysis: {len(gaps)} missing | {len(already_in_rag)} already in RAG")
    return gaps


# ── Website resolution ───────────────────────────────────────────────────────


def resolve_gap_websites(
    gaps: list[dict[str, Any]],
    *,
    limit: int,
    sess: requests.Session,
    delay: float = 0.5,
) -> int:
    """Resolve + validate an official `website` for the top `limit` gap entries.

    Storing the website at discovery time means the greenfield importer never
    has to re-fetch a Robolist page that may since have 404'd. Mutates entries
    in place; returns the number newly resolved.
    """
    subset = gaps[:limit] if limit and limit > 0 else gaps
    resolved = 0
    for i, c in enumerate(subset, 1):
        if (c.get("website") or "").strip():
            continue
        name = c.get("name") or c["slug"].replace("-", " ").title()
        website, method = resolve_company_website(
            name, c.get("slug", ""), country=c.get("country"), session=sess,
        )
        if website:
            c["website"] = website
            c["website_source"] = method
            resolved += 1
            print(f"    [{i}/{len(subset)}] {name}: {website} ({method})")
        else:
            print(f"    [{i}/{len(subset)}] {name}: no website resolved")
        time.sleep(delay)
    print(f"  Websites resolved: {resolved}/{len(subset)}")
    return resolved


# ── Output ───────────────────────────────────────────────────────────────────


def write_outputs(
    gaps: list[dict[str, Any]],
    rag_company_count: int,
    competitor_total: int,
    max_seeds: int,
    dry_run: bool,
) -> None:
    """Write gap report JSON, markdown summary, and seeds file."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    SEEDS_DIR.mkdir(parents=True, exist_ok=True)

    report = {
        "generated_at": _now(),
        "rag_companies_in_db": rag_company_count,
        "competitor_companies_scraped": competitor_total,
        "gaps_found": len(gaps),
        "top_gaps": gaps[:max_seeds],
        "all_gaps": gaps,
    }

    # JSON report
    json_path = REPORTS_DIR / "competitor_gap_companies.json"
    if not dry_run:
        json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"\n  Wrote: {json_path}")

    # Markdown summary
    md_lines = [
        "# Competitor Gap Discovery Report",
        "",
        f"Generated: {_now()[:19]}Z",
        "",
        "## Summary",
        "",
        f"| Metric | Value |",
        f"| --- | --- |",
        f"| RobotAIGeek companies in DB | {rag_company_count} |",
        f"| Competitor companies scraped | {competitor_total} |",
        f"| Missing from RAG (gap) | {len(gaps)} |",
        f"| Top seeds selected | {min(max_seeds, len(gaps))} |",
        "",
        "## Top Missing Companies (Priority Order)",
        "",
        "| Rank | Company | Robot Count | Categories | Country | Sources | Score |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for i, c in enumerate(gaps[:50], 1):
        cats = ", ".join((c.get("categories") or [])[:3])
        sources = ", ".join(c.get("found_on_sources") or [c.get("source", "")])
        md_lines.append(
            f"| {i} | [{c['name']}]({c['url']}) | "
            f"{c.get('robot_count') or '?'} | {cats} | "
            f"{c.get('country') or '?'} | {sources} | {c.get('priority_score', 0)} |"
        )

    md_lines += [
        "",
        "## Next Steps",
        "",
        "1. Review the top companies above and verify they are genuine robot manufacturers.",
        "2. For each confirmed company, run:",
        "   ```",
        "   python cli.py auto discover --company-name \"<Company Name>\" --product-pages-only",
        "   ```",
        "3. Or add them to `seeds/competitor_gap_seeds.txt` and run the batch greenfield workflow.",
        "",
        "## Seed File",
        "",
        f"Top {min(max_seeds, len(gaps))} companies written to `seeds/competitor_gap_seeds.txt`.",
    ]

    md_path = REPORTS_DIR / "competitor_gap_summary.md"
    if not dry_run:
        md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
        print(f"  Wrote: {md_path}")

    # Seeds file
    seed_lines = [
        "# Auto-generated by competitor_gap_discover.py",
        f"# Generated: {_now()[:19]}Z",
        f"# Top {min(max_seeds, len(gaps))} companies missing from RobotAIGeek",
        "# Format: Company Name  # source=<source> robots=<count> score=<score>",
        "",
    ]
    for c in gaps[:max_seeds]:
        name = c.get("name") or c["slug"].replace("-", " ").title()
        meta = (
            f"source={','.join(c.get('found_on_sources') or [c.get('source','?')])} "
            f"robots={c.get('robot_count') or '?'} "
            f"score={c.get('priority_score', 0)}"
        )
        seed_lines.append(f"{name}  # {meta}")

    seeds_path = SEEDS_DIR / "competitor_gap_seeds.txt"
    if not dry_run:
        seeds_path.write_text("\n".join(seed_lines) + "\n", encoding="utf-8")
        print(f"  Wrote: {seeds_path}")

    # Console preview
    print(f"\n{'='*60}")
    print(f"TOP 20 MISSING COMPANIES (of {len(gaps)} total gaps)")
    print(f"{'='*60}")
    for i, c in enumerate(gaps[:20], 1):
        cats = ",".join((c.get("categories") or [])[:2])
        print(
            f"  #{i:2d} score={c.get('priority_score',0):3d} "
            f"robots={str(c.get('robot_count') or '?'):>4s} "
            f"[{cats}] {c['name']}"
        )


# ── Main ─────────────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--max-seeds", type=int, default=100, help="Max companies to write to seeds file (default: 100)")
    p.add_argument("--source", choices=["robolist", "aparobot", "all"], default="all", help="Which competitor to scrape (default: all)")
    p.add_argument("--dry-run", action="store_true", help="Do not write any output files")
    p.add_argument("--local", action="store_true", help="Use local API (http://127.0.0.1:8000)")
    p.add_argument(
        "--no-resolve-websites",
        action="store_true",
        help="Skip resolving/validating each gap company's official website",
    )
    p.add_argument(
        "--website-limit",
        type=int,
        default=0,
        help="Resolve websites for the top N gaps (0 = use --max-seeds)",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()

    print("=" * 60)
    print("Competitor Gap Discovery Workflow")
    print(f"Started: {_now()}")
    print(f"Sources: {args.source}  |  Max seeds: {args.max_seeds}  |  Dry run: {args.dry_run}")
    print("=" * 60)

    sess = requests.Session()
    client = ResearchApiClient()

    # 1. Fetch RobotAIGeek inventory
    print("\n[1/3] Fetching RobotAIGeek inventory...")
    rag_companies, rag_index = fetch_rag_inventory(client)

    # 2. Scrape competitor platforms
    competitor_companies: list[dict[str, Any]] = []

    if args.source in ("robolist", "all"):
        print("\n[2/3] Scraping Robolist.ai...")
        robolist_cos = scrape_robolist(sess)
        competitor_companies.extend(robolist_cos)
        time.sleep(1)

    if args.source in ("aparobot", "all"):
        print("\n[2/3] Scraping Aparobot...")
        aparobot_cos = scrape_aparobot(sess)
        competitor_companies.extend(aparobot_cos)

    print(f"\n  Total competitor companies collected: {len(competitor_companies)}")

    # 3. Gap analysis
    print("\n[3/3] Running gap analysis...")
    gaps = run_gap_analysis(competitor_companies, rag_index, client)

    # 3b. Resolve + validate official websites for the top gaps so the importer
    #     never has to re-fetch a (now-often-404) Robolist page.
    if not args.no_resolve_websites:
        website_limit = args.website_limit or args.max_seeds
        print(f"\n[3b] Resolving websites for top {website_limit} gaps...")
        resolve_gap_websites(gaps, limit=website_limit, sess=sess)

    # 4. Write outputs
    write_outputs(
        gaps=gaps,
        rag_company_count=len(rag_companies),
        competitor_total=len(set(c["slug"] for c in competitor_companies)),
        max_seeds=args.max_seeds,
        dry_run=args.dry_run,
    )

    print(f"\n{'='*60}")
    print(f"DONE — {len(gaps)} companies missing from RobotAIGeek")
    print(f"Finished: {_now()}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
