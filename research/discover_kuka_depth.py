#!/usr/bin/env python3
"""KUKA depth discovery: OEM family-table variants not yet in our DB.

Prefer unitree-style discover checkpoint:
  1. Refresh / extend kuka-recon from family pages (plain HTTP)
  2. Fuzzy-match against company 1396 (+ optional 57 duplicate shell)
  3. Stage recommend_import candidates under staging/robots/kuka/
  4. Write triage report — NO import until approved

Usage:
  python -u discover_kuka_depth.py              # dry plan + triage
  python -u discover_kuka_depth.py --refresh-recon
  python -u discover_kuka_depth.py --stage      # write staging JSON
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from load_env import load_research_env

load_research_env()

from api_client import ResearchApiClient
from kuka_recon import parse_family
from web_extract import WebFetcher

COMPANY_ID = 1396
COMPANY_SLUG = "kuka"
COMPANY_NAME = "KUKA"
INDEX_URL = (
    "https://www.kuka.com/en-us/products/robotics-systems/industrial-robots"
)
RECON_PATH = _RESEARCH_DIR / "staging" / "reports" / "kuka-recon.json"
TRIAGE_PATH = _RESEARCH_DIR / "staging" / "reports" / "kuka_discovery_triage.json"
STAGING_DIR = _RESEARCH_DIR / "staging" / "robots" / COMPANY_SLUG

# Suffixes KUKA DB rows often append that family tables omit
_STRIP_SUFFIXES = (
    " IONTEC",
    " ultra",
    " nano",
    " Delta",
    " FORTEC",
    " QUANTEC",
    " CYBERTECH",
    " titan",
    " PA",
)


def norm_name(s: str) -> str:
    s = (s or "").strip().lower()
    s = s.replace("–", "-").replace("—", "-")
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s


def soft_norm(s: str) -> str:
    """Normalize for fuzzy match: drop common family marketing suffixes."""
    t = (s or "").strip()
    for suf in _STRIP_SUFFIXES:
        if t.endswith(suf):
            t = t[: -len(suf)].strip()
    return norm_name(t)


def discover_family_urls(fetcher: WebFetcher) -> list[str]:
    html = fetcher.get(INDEX_URL) or ""
    urls: list[str] = []
    for m in re.finditer(
        r'href="(/en-us/products/robotics-systems/industrial-robots/[^"?#]+)"',
        html,
        re.I,
    ):
        path = m.group(1).rstrip("/")
        # skip the index itself and non-family crumbs
        if path.count("/") < 5:
            continue
        full = urljoin("https://www.kuka.com", path)
        if full.rstrip("/") == INDEX_URL.rstrip("/"):
            continue
        urls.append(full)
    # dedupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def refresh_recon(extra_urls: list[str] | None = None) -> dict[str, dict[str, Any]]:
    client = ResearchApiClient()
    robots = client.list_robots_for_company(COMPANY_ID)
    db_urls = sorted(
        {
            (r.get("website_url") or r.get("url") or "").strip()
            for r in robots
            if (r.get("website_url") or r.get("url") or "").strip()
            and "industrial-robots/" in (r.get("website_url") or r.get("url") or "")
            and (r.get("website_url") or r.get("url") or "").rstrip("/").count("/") >= 6
        }
    )
    fetcher = WebFetcher(stealth=False)
    index_urls = discover_family_urls(fetcher)
    print(f"index family urls: {len(index_urls)}")
    print(f"db family urls: {len(db_urls)}")
    urls = sorted(set(db_urls) | set(index_urls) | set(extra_urls or []))
    # Prefer family pages only (last segment not 'industrial-robots')
    urls = [u for u in urls if u.rstrip("/").split("/")[-1] != "industrial-robots"]
    print(f"scraping {len(urls)} family pages")

    catalog: dict[str, dict[str, Any]] = {}
    for u in urls:
        family = u.rstrip("/").split("/")[-1]
        html = fetcher.get(u)
        if not html:
            print(f"  FAIL {family}")
            continue
        got = parse_family(html, family, u)
        for k, v in got.items():
            catalog.setdefault(k, v)
        print(f"  {family:<40} variants={len(got)}")
        time.sleep(0.25)

    RECON_PATH.parent.mkdir(parents=True, exist_ok=True)
    RECON_PATH.write_text(
        json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"wrote {len(catalog)} variants → {RECON_PATH}")
    return catalog


def load_db_names(client: ResearchApiClient) -> tuple[list[dict[str, Any]], set[str], set[str]]:
    robots = client.list_robots_for_company(COMPANY_ID)
    # also pull sibling shell company 57 to avoid staging dups
    try:
        robots57 = client.list_robots_for_company(57)
        robots = robots + robots57
    except Exception as exc:  # noqa: BLE001
        print(f"warn: company 57 list failed: {exc}")

    exact: set[str] = set()
    soft: set[str] = set()
    for r in robots:
        name = (r.get("name") or "").strip()
        if not name:
            continue
        exact.add(norm_name(name))
        soft.add(soft_norm(name))
        # also index model_name
        mn = (r.get("model_name") or "").strip()
        if mn:
            exact.add(norm_name(mn))
            soft.add(soft_norm(mn))
    return robots, exact, soft


def classify_variant(
    name: str,
    exact: set[str],
    soft: set[str],
) -> str:
    n = norm_name(name)
    s = soft_norm(name)
    if n in exact or s in exact:
        return "already_in_db"
    if s in soft:
        return "already_in_db_fuzzy"
    # Environment/specialized suffixes that are real distinct SKUs → recommend
    # Very short / incomplete names → review
    if len(name) < 6 or name.upper() in {"KR", "LBR", "KMP", "KMR"}:
        return "review"
    return "recommend_import"


def features_from_rec(name: str, rec: dict[str, Any]) -> str:
    bits = [f"KUKA industrial robot variant: {name}"]
    if rec.get("total_load"):
        bits.append(f"Total load: {rec['total_load']}")
    if rec.get("max_reach") or rec.get("maximum_reach"):
        bits.append(f"Reach: {rec.get('max_reach') or rec.get('maximum_reach')}")
    if rec.get("version_environment"):
        bits.append(f"Version / environment: {rec['version_environment']}")
    if rec.get("construction_type"):
        bits.append(f"Construction: {rec['construction_type']}")
    if rec.get("protection_class"):
        bits.append(f"Protection: {rec['protection_class']}")
    if rec.get("controller"):
        bits.append(f"Controller: {rec['controller']}")
    if rec.get("mounting_positions"):
        bits.append(f"Mounting: {rec['mounting_positions']}")
    return "\n".join(bits)


def stage_robot(name: str, rec: dict[str, Any]) -> Path:
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    path = STAGING_DIR / f"{slug}.json"
    # avoid overwrite collisions
    if path.exists():
        path = STAGING_DIR / f"{slug}-discovered.json"
    payload = {
        "name": name,
        "model_name": name,
        "company": COMPANY_NAME,
        "company_slug": COMPANY_SLUG,
        "company_ref": COMPANY_ID,
        "source_locale": "en",
        "url": rec.get("url") or INDEX_URL,
        "website_url": rec.get("url") or INDEX_URL,
        "description": (
            f"{name} is a KUKA industrial robot variant listed on the "
            f"{rec.get('family') or 'product'} family page."
        ),
        "purpose": "Industrial robot arm for manufacturing and automation applications.",
        "features": features_from_rec(name, rec),
        "status": "pending_review",
        "sources": [{"url": rec.get("url") or INDEX_URL, "note": "KUKA OEM family page"}],
        "research_notes": (
            f"[AI Research — KUKA depth discover 2026-07-18] "
            f"family={rec.get('family')} total_load={rec.get('total_load')} "
            f"reach={rec.get('max_reach') or rec.get('maximum_reach')}"
        ),
        "tags": "Industrial|Industrial Robot|6-Axis|Manufacturing",
    }
    # typed specs when parseable
    load = rec.get("total_load") or ""
    m = re.search(r"([\d.]+)\s*kg", load, re.I)
    if m:
        payload["payload_kg"] = float(m.group(1))
    reach = rec.get("max_reach") or rec.get("maximum_reach") or ""
    m = re.search(r"([\d.]+)\s*mm", reach, re.I)
    if m:
        payload["reach_mm"] = float(m.group(1))

    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh-recon", action="store_true")
    ap.add_argument("--stage", action="store_true", help="Write staging JSON for recommend_import")
    args = ap.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if args.refresh_recon or not RECON_PATH.exists():
        catalog = refresh_recon()
    else:
        catalog = json.loads(RECON_PATH.read_text(encoding="utf-8"))
        print(f"loaded existing recon: {len(catalog)} variants")

    client = ResearchApiClient()
    robots, exact, soft = load_db_names(client)
    print(f"DB robots (1396+57): {len(robots)}")

    buckets: dict[str, list[dict[str, Any]]] = {
        "recommend_import": [],
        "already_in_db": [],
        "already_in_db_fuzzy": [],
        "review": [],
    }
    for name, rec in sorted(catalog.items()):
        bucket = classify_variant(name, exact, soft)
        row = {
            "name": name,
            "family": rec.get("family"),
            "url": rec.get("url"),
            "total_load": rec.get("total_load"),
            "max_reach": rec.get("max_reach") or rec.get("maximum_reach"),
            "bucket": bucket,
        }
        buckets[bucket].append(row)

    if args.stage:
        for row in buckets["recommend_import"]:
            path = stage_robot(row["name"], catalog[row["name"]])
            row["file"] = path.name
            print(f"staged {path.name}")

    triage = {
        "company_id": COMPANY_ID,
        "company": COMPANY_NAME,
        "recon_variants": len(catalog),
        "db_robots": len(robots),
        "counts": {k: len(v) for k, v in buckets.items()},
        **buckets,
    }
    TRIAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    TRIAGE_PATH.write_text(json.dumps(triage, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print("\n=== KUKA depth discovery triage ===")
    print(json.dumps(triage["counts"], indent=2))
    print(f"wrote {TRIAGE_PATH}")
    print("\nRecommend import (first 25):")
    for row in buckets["recommend_import"][:25]:
        print(
            f"  {row['name']:<32} {row.get('total_load') or '-':<10} "
            f"{row.get('max_reach') or '-':<10} {row.get('family')}"
        )
    if len(buckets["recommend_import"]) > 25:
        print(f"  ... +{len(buckets['recommend_import']) - 25} more")
    print("\nNo import yet — approve recommend_import to proceed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
