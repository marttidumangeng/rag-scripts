#!/usr/bin/env python3
"""Scan Robolist.ai and compare against RobotAIGeek inventory (gap analysis).

Uses public sitemap + category JSON-LD/HTML catalogs. Does NOT import Robolist
as primary research data — staging is for discovery / coverage comparison only.
"""

from __future__ import annotations

import csv
import json
import re
import sys
import time
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

import requests
from bs4 import BeautifulSoup

_HERE = Path(__file__).resolve().parent
_SCRIPTS = _HERE.parent
for _p in (_HERE, _SCRIPTS):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from api_client import ResearchApiClient  # noqa: E402
from scrape_robolist import BASE_URL, USER_AGENT, fetch, read_category  # noqa: E402

CATEGORIES = [
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

STAGING_ROOT = Path(__file__).resolve().parent / "staging" / "robolist_gap"
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "output" / "robolist_gap"


def norm_name(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.casefold()
    text = text.replace("&", " and ")
    text = re.sub(r"[®™©]", "", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def slug_from_url(url: str) -> str:
    return urlparse(url).path.rstrip("/").split("/")[-1]


def session() -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml",
            "Accept-Encoding": "identity",
            "Connection": "close",
        }
    )
    return s


def parse_sitemap(sess: requests.Session) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    xml_text = fetch(sess, f"{BASE_URL}/sitemap.xml")
    # Strip default namespace for easier parsing
    xml_text = re.sub(r'\sxmlns="[^"]+"', "", xml_text, count=1)
    root = ET.fromstring(xml_text)
    companies: list[dict[str, str]] = []
    robots: list[dict[str, str]] = []
    for loc in root.findall(".//loc"):
        url = (loc.text or "").strip()
        if "/companies/" in url and url.rstrip("/").count("/") >= 4:
            companies.append({"slug": slug_from_url(url), "url": url})
        elif "/robots/" in url and url.rstrip("/").count("/") >= 4:
            robots.append({"slug": slug_from_url(url), "url": url})
    # Dedupe
    companies = list({c["slug"]: c for c in companies}.values())
    robots = list({r["slug"]: r for r in robots}.values())
    return companies, robots


def scrape_companies_directory(sess: requests.Session) -> list[dict[str, Any]]:
    """Parse the companies directory page for name + robot count (first page + HTML).

    Full catalog may be JS-paginated; we still extract whatever is server-rendered
    and rely on sitemap for complete slug coverage.
    """
    html = fetch(sess, f"{BASE_URL}/companies")
    soup = BeautifulSoup(html, "html.parser")
    results: dict[str, dict[str, Any]] = {}

    for a in soup.select('a[href^="/companies/"]'):
        href = a.get("href", "").split("?", 1)[0].rstrip("/")
        if href.count("/") < 2:
            continue
        slug = href.rsplit("/", 1)[-1]
        # Walk up to find a card-like container with robot count
        node = a
        robot_count = None
        country = None
        name = a.get_text(" ", strip=True)
        for _ in range(6):
            node = node.parent
            if node is None:
                break
            text = node.get_text(" ", strip=True)
            m = re.search(r"([\d,]+)\s+robots?", text, re.I)
            if m:
                robot_count = int(m.group(1).replace(",", ""))
            # Country often appears near robot count
            cm = re.search(
                r"\b(United States|China|Germany|Japan|South Korea|France|"
                r"United Kingdom|Italy|Spain|Sweden|Switzerland|Canada|"
                r"Taiwan|Denmark|Austria|Netherlands|Belgium|Finland|"
                r"Norway|Australia|India|Singapore|Israel|Poland)\b",
                text,
            )
            if cm:
                country = cm.group(1)
            if robot_count is not None:
                break

        if not name:
            name = slug.replace("-", " ").title()
        prev = results.get(slug)
        if prev and prev.get("robot_count") and not robot_count:
            continue
        results[slug] = {
            "slug": slug,
            "name": name,
            "url": f"{BASE_URL}/companies/{slug}",
            "robot_count": robot_count,
            "country": country,
        }

    return list(results.values())


def enrich_category_manufacturers(
    sess: requests.Session, category: str, robots: list[dict[str, Any]]
) -> None:
    """Attach manufacturer name/slug from the company link inside each catalog card."""
    html = fetch(sess, f"{BASE_URL}/categories/{category}")
    soup = BeautifulSoup(html, "html.parser")
    by_slug = {r["slug"]: r for r in robots}

    section = None
    largest_total = 0
    for marker in soup.find_all(["p", "div", "span"]):
        marker_text = marker.get_text(" ", strip=True)
        match = re.search(r"([\d,]+)\s+of\s+([\d,]+)\s+shown", marker_text, re.I)
        candidate = marker.find_parent("section")
        if not match or not candidate:
            continue
        total = int(match.group(2).replace(",", ""))
        if total > largest_total:
            largest_total = total
            section = candidate
    root = section or soup

    for a in root.select('a[href^="/robots/"]'):
        href = a.get("href", "").split("?", 1)[0].rstrip("/")
        if href.count("/") != 2:
            continue
        slug = href.rsplit("/", 1)[-1]
        robot = by_slug.get(slug)
        if not robot:
            continue

        company_name = None
        company_slug = None
        node = a
        for _ in range(8):
            node = node.parent
            if node is None or not hasattr(node, "select"):
                break
            links = node.select('a[href^="/companies/"]')
            if not links:
                continue
            company_slug = links[0].get("href", "").rstrip("/").split("/")[-1]
            raw = links[0].get_text(" ", strip=True)
            # "Comau · IT" → "Comau"
            company_name = re.split(r"\s*[·•]\s*", raw, maxsplit=1)[0].strip()
            break

        if company_name:
            robot["manufacturer"] = company_name
        if company_slug:
            robot["manufacturer_slug"] = company_slug
        # Prefer visible robot title from the card if structured name is weak
        title = a.get_text(" ", strip=True)
        if title and len(title) > 1:
            robot["name"] = title


def scrape_all_categories(sess: requests.Session) -> list[dict[str, Any]]:
    all_robots: dict[str, dict[str, Any]] = {}
    for cat in CATEGORIES:
        print(f"Category {cat}...")
        try:
            robots = read_category(sess, cat)
        except Exception as exc:
            print(f"  FAILED: {exc}")
            continue
        print(f"  {len(robots)} robots")
        try:
            enrich_category_manufacturers(sess, cat, robots)
        except Exception as exc:
            print(f"  manufacturer enrich failed: {exc}")
        for r in robots:
            slug = r["slug"]
            if slug in all_robots:
                prev = all_robots[slug]
                cats = set(prev.get("categories") or [prev.get("category")])
                cats.add(cat)
                prev["categories"] = sorted(c for c in cats if c)
                if r.get("manufacturer") and not prev.get("manufacturer"):
                    prev["manufacturer"] = r["manufacturer"]
            else:
                r["categories"] = [cat]
                all_robots[slug] = r
        time.sleep(1.0)
    return list(all_robots.values())


def fetch_our_inventory(client: ResearchApiClient) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Pull company + robot inventory via lightweight API endpoints."""
    names = client.get_company_names()
    companies: list[dict[str, Any]] = []
    page = 1
    while True:
        data = client._get("companies/", params={"page": page, "page_size": 100})
        batch = data.get("results", data if isinstance(data, list) else [])
        if not batch:
            break
        # Keep matching fields only
        for row in batch:
            companies.append(
                {
                    "id": row.get("id"),
                    "name": row.get("name"),
                    "slug": row.get("slug"),
                    "country": row.get("country") or row.get("country_code"),
                }
            )
        if not (isinstance(data, dict) and data.get("next")):
            break
        page += 1
        if page > 200:
            break
        print(f"  companies page {page}, total {len(companies)}")

    if not companies and names:
        companies = [{"name": n} for n in names]

    robots: list[dict[str, Any]] = []
    page = 1
    while True:
        data = client._get(
            "robots/robots/",
            params={"page": page, "page_size": 100, "lite": "1"},
        )
        batch = data.get("results", [])
        if not batch:
            break
        for row in batch:
            company = row.get("company") or {}
            if isinstance(company, str):
                company_name = company
            else:
                company_name = (company or {}).get("name")
            robots.append(
                {
                    "id": row.get("id"),
                    "name": row.get("name"),
                    "slug": row.get("slug"),  # may be absent on lite
                    "model_name": row.get("model_name"),
                    "status": row.get("status"),
                    "company_name": company_name,
                    "company_ref": row.get("company_ref"),
                }
            )
        if not data.get("next"):
            break
        page += 1
        if page > 500:
            break
        if page % 5 == 0:
            print(f"  robots lite page {page}, total {len(robots)}")

    return companies, robots


def company_aliases(name: str) -> set[str]:
    n = norm_name(name)
    aliases = {n}
    for suffix in (
        " robotics",
        " robot",
        " robots",
        " automation",
        " intelligent",
        " technology",
        " technologies",
        " systems",
        " corporation",
        " corp",
        " co ltd",
        " co",
        " ltd",
        " limited",
        " inc",
        " gmbh",
        " ag",
        " sa",
        " plc",
        " group",
    ):
        if n.endswith(suffix) and len(n) > len(suffix) + 2:
            aliases.add(n[: -len(suffix)].strip())
    return {a for a in aliases if a}


def build_company_index(our_companies: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for c in our_companies:
        name = c.get("name") or ""
        slug = c.get("slug") or ""
        for key in company_aliases(name):
            index.setdefault(key, c)
        if slug:
            index.setdefault(norm_name(slug.replace("-", " ")), c)
            index.setdefault(norm_name(slug), c)
    return index


def match_company(
    name: str, slug: str, index: dict[str, dict[str, Any]]
) -> dict[str, Any] | None:
    for key in company_aliases(name):
        if key in index:
            return index[key]
    slug_key = norm_name(slug.replace("-", " "))
    if slug_key in index:
        return index[slug_key]
    if slug and norm_name(slug) in index:
        return index[norm_name(slug)]
    if len(slug_key) >= 8:
        for key, company in index.items():
            if slug_key == key:
                return company
            if abs(len(slug_key) - len(key)) <= 12 and (
                slug_key in key or key in slug_key
            ):
                return company
    elif len(slug_key) >= 5 and slug_key in index:
        return index[slug_key]
    return None


def robot_keys(robot: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for field in ("name", "model_name", "slug"):
        val = robot.get(field)
        if not val:
            continue
        n = norm_name(str(val))
        if not n:
            continue
        keys.add(n)
        compact = re.sub(
            r"\b(robot|robotic|collaborative|industrial|series|model)\b",
            " ",
            n,
        )
        compact = re.sub(r"\s+", " ", compact).strip()
        if compact:
            keys.add(compact)
    return keys


def build_robot_index(our_robots: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for r in our_robots:
        for key in robot_keys(r):
            index.setdefault(key, r)
        company = norm_name(str(r.get("company_name") or ""))
        name = norm_name(str(r.get("name") or ""))
        if company and name:
            index.setdefault(f"{company}::{name}", r)
    return index


def match_robot(
    name: str,
    slug: str,
    index: dict[str, dict[str, Any]],
    manufacturer: str | None = None,
) -> dict[str, Any] | None:
    candidates = [
        norm_name(name),
        norm_name(slug.replace("-", " ")),
    ]
    if manufacturer:
        mfr = norm_name(manufacturer)
        stripped = norm_name(re.sub(re.escape(manufacturer), "", name, flags=re.I))
        if stripped:
            candidates.append(stripped)
        if mfr and stripped:
            candidates.append(f"{mfr}::{stripped}")
        if mfr and norm_name(name):
            candidates.append(f"{mfr}::{norm_name(name)}")

    for key in candidates:
        if key and key in index:
            return index[key]

    slug_tokens = [t for t in slug.split("-") if t]
    for token in reversed(slug_tokens[-3:]):
        key = norm_name(token)
        if len(key) >= 4 and key in index:
            return index[key]
    return None


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def scrape_robolist_bundle(sess: requests.Session) -> dict[str, Any]:
    print("=== 1) Sitemap ===")
    sm_companies, sm_robots = parse_sitemap(sess)
    print(f"Sitemap companies: {len(sm_companies)}")
    print(f"Sitemap robots: {len(sm_robots)}")

    print("=== 2) Companies directory (partial SSR) ===")
    dir_companies = scrape_companies_directory(sess)
    print(f"Directory cards parsed: {len(dir_companies)}")
    dir_by_slug = {c["slug"]: c for c in dir_companies}

    robolist_companies: list[dict[str, Any]] = []
    for c in sm_companies:
        meta = dir_by_slug.get(c["slug"], {})
        robolist_companies.append(
            {
                "slug": c["slug"],
                "url": c["url"],
                "name": meta.get("name") or c["slug"].replace("-", " ").title(),
                "robot_count": meta.get("robot_count"),
                "country": meta.get("country"),
            }
        )

    print("=== 3) Category robot catalogs ===")
    category_robots = scrape_all_categories(sess)
    print(f"Unique robots from categories: {len(category_robots)}")
    cat_by_slug = {r["slug"]: r for r in category_robots}

    robolist_robots: list[dict[str, Any]] = []
    for r in sm_robots:
        cat = cat_by_slug.get(r["slug"], {})
        robolist_robots.append(
            {
                "slug": r["slug"],
                "url": r["url"],
                "name": cat.get("name") or r["slug"].replace("-", " ").title(),
                "manufacturer": cat.get("manufacturer"),
                "manufacturer_slug": cat.get("manufacturer_slug"),
                "categories": cat.get("categories")
                or ([cat["category"]] if cat.get("category") else []),
            }
        )
    seen = {r["slug"] for r in robolist_robots}
    for slug, cat in cat_by_slug.items():
        if slug in seen:
            continue
        robolist_robots.append(
            {
                "slug": slug,
                "url": cat.get("url") or f"{BASE_URL}/robots/{slug}",
                "name": cat.get("name") or slug,
                "manufacturer": cat.get("manufacturer"),
                "manufacturer_slug": cat.get("manufacturer_slug"),
                "categories": cat.get("categories") or [cat.get("category")],
            }
        )

    # Backfill company display names from manufacturer strings when directory was truncated
    mfr_names = {
        norm_name(r["manufacturer"]): r["manufacturer"]
        for r in robolist_robots
        if r.get("manufacturer")
    }
    for c in robolist_companies:
        if c["name"] == c["slug"].replace("-", " ").title():
            guess = mfr_names.get(norm_name(c["slug"].replace("-", " ")))
            if guess:
                c["name"] = guess

    return {
        "scraped_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sitemap_companies": len(sm_companies),
        "sitemap_robots": len(sm_robots),
        "category_robots_unique": len(category_robots),
        "companies": robolist_companies,
        "robots": robolist_robots,
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    skip_scrape = "--skip-scrape" in sys.argv
    STAGING_ROOT.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    sess = session()
    client = ResearchApiClient()
    cache_path = STAGING_ROOT / "robolist_bundle.json"

    if skip_scrape and cache_path.exists():
        print(f"=== Loading cached Robolist scrape: {cache_path} ===")
        bundle = json.loads(cache_path.read_text(encoding="utf-8"))
    else:
        bundle = scrape_robolist_bundle(sess)
        _write_json(cache_path, bundle)
        print(f"Cached Robolist bundle → {cache_path}")

    robolist_companies = bundle["companies"]
    robolist_robots = bundle["robots"]
    sm_companies_n = bundle.get("sitemap_companies", len(robolist_companies))
    sm_robots_n = bundle.get("sitemap_robots", len(robolist_robots))
    category_robots_n = bundle.get("category_robots_unique", 0)

    print("=== 4) Our inventory ===")
    our_companies, our_robots = fetch_our_inventory(client)
    _write_json(
        STAGING_ROOT / "our_inventory.json",
        {"companies": our_companies, "robots": our_robots},
    )
    print(f"Our companies: {len(our_companies)}")
    print(f"Our robots: {len(our_robots)}")

    company_index = build_company_index(our_companies)
    robot_index = build_robot_index(our_robots)

    print("=== 5) Matching ===")
    company_matches: list[dict[str, Any]] = []
    missing_companies: list[dict[str, Any]] = []
    matched_companies: list[dict[str, Any]] = []

    for c in sorted(robolist_companies, key=lambda x: x["slug"]):
        hit = match_company(c["name"], c["slug"], company_index)
        row = {
            **c,
            "match_status": "matched" if hit else "missing",
            "our_company_id": hit.get("id") if hit else None,
            "our_company_name": hit.get("name") if hit else None,
            "our_company_slug": hit.get("slug") if hit else None,
        }
        company_matches.append(row)
        if hit:
            matched_companies.append(row)
        else:
            missing_companies.append(row)

    robot_matches: list[dict[str, Any]] = []
    missing_robots: list[dict[str, Any]] = []
    matched_robots: list[dict[str, Any]] = []

    for r in sorted(robolist_robots, key=lambda x: x["slug"]):
        hit = match_robot(
            r["name"],
            r["slug"],
            robot_index,
            manufacturer=r.get("manufacturer"),
        )
        mfr_hit = None
        mfr_slug = r.get("manufacturer_slug") or ""
        if r.get("manufacturer") or mfr_slug:
            mfr_hit = match_company(r.get("manufacturer") or "", mfr_slug, company_index)
        row = {
            **r,
            "match_status": "matched" if hit else "missing",
            "our_robot_id": hit.get("id") if hit else None,
            "our_robot_name": hit.get("name") if hit else None,
            "our_robot_slug": hit.get("slug") if hit else None,
            "manufacturer_in_db": bool(mfr_hit),
            "our_manufacturer_id": mfr_hit.get("id") if mfr_hit else None,
            "our_manufacturer_name": mfr_hit.get("name") if mfr_hit else None,
        }
        robot_matches.append(row)
        if hit:
            matched_robots.append(row)
        else:
            missing_robots.append(row)

    # Category breakdown
    cat_stats: list[dict[str, Any]] = []
    for cat in CATEGORIES:
        in_cat = [r for r in robot_matches if cat in (r.get("categories") or [])]
        miss = [r for r in in_cat if r["match_status"] == "missing"]
        cat_stats.append(
            {
                "category": cat,
                "robolist_count": len(in_cat),
                "matched": len(in_cat) - len(miss),
                "missing": len(miss),
                "coverage_pct": round(
                    100.0 * (len(in_cat) - len(miss)) / len(in_cat), 1
                )
                if in_cat
                else 0.0,
            }
        )

    # Missing robots grouped by manufacturer (priority backlog)
    miss_by_mfr: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in missing_robots:
        key = r.get("manufacturer") or "(unknown manufacturer)"
        miss_by_mfr[key].append(r)
    mfr_gap = sorted(
        (
            {
                "manufacturer": mfr,
                "missing_robots": len(robots),
                "manufacturer_in_db": any(r.get("manufacturer_in_db") for r in robots),
                "sample_robots": [x["name"] for x in robots[:8]],
            }
            for mfr, robots in miss_by_mfr.items()
        ),
        key=lambda x: -x["missing_robots"],
    )

    summary = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "https://www.robolist.ai/",
        "note": (
            "Robolist used as competitive coverage reference only — "
            "not as primary research/import source."
        ),
        "robolist": {
            "companies_sitemap": sm_companies_n,
            "robots_sitemap": sm_robots_n,
            "robots_categories_unique": category_robots_n,
            "robots_merged": len(robolist_robots),
            "companies_merged": len(robolist_companies),
            "scraped_at": bundle.get("scraped_at"),
        },
        "ours": {
            "companies": len(our_companies),
            "robots": len(our_robots),
        },
        "gap": {
            "companies_matched": len(matched_companies),
            "companies_missing": len(missing_companies),
            "company_coverage_pct": round(
                100.0 * len(matched_companies) / max(len(robolist_companies), 1), 1
            ),
            "robots_matched": len(matched_robots),
            "robots_missing": len(missing_robots),
            "robot_coverage_pct": round(
                100.0 * len(matched_robots) / max(len(robolist_robots), 1), 1
            ),
        },
        "by_category": cat_stats,
        "top_manufacturer_gaps": mfr_gap[:40],
    }

    # Write staging artifacts
    (STAGING_ROOT / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (STAGING_ROOT / "robolist_companies.json").write_text(
        json.dumps(robolist_companies, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (STAGING_ROOT / "robolist_robots.json").write_text(
        json.dumps(robolist_robots, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (STAGING_ROOT / "company_matches.json").write_text(
        json.dumps(company_matches, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (STAGING_ROOT / "robot_matches.json").write_text(
        json.dumps(robot_matches, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (STAGING_ROOT / "missing_companies.json").write_text(
        json.dumps(missing_companies, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (STAGING_ROOT / "missing_robots.json").write_text(
        json.dumps(missing_robots, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (STAGING_ROOT / "manufacturer_gaps.json").write_text(
        json.dumps(mfr_gap, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Also mirror under scripts/output for the existing scrape convention
    for name in (
        "summary.json",
        "missing_companies.json",
        "missing_robots.json",
        "manufacturer_gaps.json",
        "by_category.json",
    ):
        src = STAGING_ROOT / name if name != "by_category.json" else None
        if name == "by_category.json":
            (OUTPUT_DIR / name).write_text(
                json.dumps(cat_stats, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        elif src and src.exists():
            (OUTPUT_DIR / name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    # CSV for quick triage
    with (STAGING_ROOT / "missing_companies.csv").open(
        "w", newline="", encoding="utf-8-sig"
    ) as fh:
        w = csv.DictWriter(
            fh, fieldnames=["slug", "name", "url", "robot_count", "country"]
        )
        w.writeheader()
        for row in missing_companies:
            w.writerow({k: row.get(k) for k in w.fieldnames})

    with (STAGING_ROOT / "missing_robots.csv").open(
        "w", newline="", encoding="utf-8-sig"
    ) as fh:
        w = csv.DictWriter(
            fh,
            fieldnames=[
                "slug",
                "name",
                "manufacturer",
                "categories",
                "url",
                "manufacturer_in_db",
            ],
        )
        w.writeheader()
        for row in missing_robots:
            w.writerow(
                {
                    "slug": row.get("slug"),
                    "name": row.get("name"),
                    "manufacturer": row.get("manufacturer"),
                    "categories": ",".join(row.get("categories") or []),
                    "url": row.get("url"),
                    "manufacturer_in_db": row.get("manufacturer_in_db"),
                }
            )

    print("=== SUMMARY ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\nStaged under: {STAGING_ROOT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
