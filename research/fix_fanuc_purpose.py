#!/usr/bin/env python3
"""Rewrite FANUC (189) purpose from OEM application lists (one line per use).

Stakeholder rule: purpose must NOT mirror description. Derive real applications
from FANUC EU "Perfect Fit for Your Application" (or series/product prose),
one application per newline.

Usage:
  python fix_fanuc_purpose.py
  python fix_fanuc_purpose.py --apply
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from html import unescape
from pathlib import Path
from typing import Any

import requests

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env
from api_client import ResearchApiClient

load_research_env(local="--local" in sys.argv)

COMPANY_ID = 189
UA = {"User-Agent": "Mozilla/5.0 (compatible; RobotAIGeekResearch/1.0)"}

# Family → OEM series/product page that lists applications
FAMILY_APP_URL: dict[str, str] = {
    "fanuc:m-710": "https://www.fanuc.eu/eu-en/m-710-series",
    "fanuc:lr-mate": "https://www.fanuc.eu/eu-en/lr-mate-series",
    "fanuc:lr-10ia": "https://www.fanuc.eu/eu-en/lr-mate-series",
    "fanuc:crx": "https://www.fanuc.eu/eu-en/crx-series",
    "fanuc:m-2000": "https://www.fanuc.eu/eu-en/m-2000-series",
    "fanuc:r-2000": "https://www.fanuc.eu/eu-en/r-2000-series",
    "fanuc:m-410": "https://www.fanuc.eu/eu-en/m-410-series",
    "fanuc:m-10": "https://www.fanuc.eu/eu-en/m-10-series",
    "fanuc:m-20": "https://www.fanuc.eu/eu-en/m-20-series",
    "fanuc:m-900": "https://www.fanuc.eu/eu-en/m-900-series",
    "fanuc:m-950": "https://www.fanuc.eu/eu-en/m-900-series",
    "fanuc:m-1ia": "https://www.fanuc.eu/eu-en/m-1-series",
    "fanuc:m-2ia": "https://www.fanuc.eu/eu-en/m-2-series",
    "fanuc:m-3ia": "https://www.fanuc.eu/eu-en/product/robot/m-3ia12h",
    "fanuc:scara": "https://www.fanuc.eu/eu-en/scara-series",
    "fanuc:arc-mate": "https://www.fanuc.eu/eu-en/arc-mate-series",
    "fanuc:paint": "https://www.fanuc.eu/eu-en/paint-series",
    "fanuc:r-1000": "https://www.fanuc.eu/eu-en/r-1000-series",
    # m-800 / m-810 / ER / DR: no stable Perfect-Fit page — FAMILY_FALLBACK only
    "fanuc:m-1000": "https://www.fanuc.eu/eu-en/product/robot/m-1000ia",
}

# When Perfect-Fit scrape is empty/thin, OEM-cited applications from series prose
FAMILY_FALLBACK: dict[str, list[str]] = {
    "fanuc:m-800": [
        "Heavy material handling",
        "Large-part transfer",
        "Press tending",
    ],
    "fanuc:m-810": [
        "Heavy material handling",
        "Large-part transfer",
    ],
    "fanuc:m-2000": [
        "Ultra-heavy material handling",
        "Vehicle / large-component lifting",
    ],
    "fanuc:m-1000": [
        "Heavy material handling",
        "Large-part transfer",
    ],
    "fanuc:er": [
        "Robotics education and training",
        "Classroom and lab instruction",
    ],
    "fanuc:dr-3ib": [
        "High-speed picking and packing",
        "Food handling",
        "Washdown packaging",
    ],
    "fanuc:paint": [
        "Painting",
        "Coating and dispensing",
    ],
    "fanuc:arc-mate": [
        "Arc welding",
    ],
}

# Name-token overrides / prepends (OEM variant intent)
VARIANT_PREPEND: list[tuple[re.Pattern[str], list[str]]] = [
    (
        re.compile(r"Food\s*/\s*Clean|Food|Clean\s*Room|Cleanroom", re.I),
        [
            "Food and beverage handling",
            "Cleanroom / hygiene-sensitive processing",
        ],
    ),
    (
        re.compile(r"\bWash\b|Washproof|WP\b", re.I),
        [
            "Washdown / wet-environment handling",
            "Machine tending in hose-down cells",
        ],
    ),
    (
        re.compile(r"Paint", re.I),
        [
            "Painting",
            "Coating and dispensing",
        ],
    ),
]

SPELLING = {
    "Palletising": "Palletizing",
    "Assembling": "Assembly",
    "Warehousing": "Warehousing / logistics",
}


def normalize_app(label: str) -> str:
    t = re.sub(r"\s+", " ", (label or "").strip())
    t = SPELLING.get(t, t)
    # Title-case short OEM chips; keep multi-word as-is if already mixed
    if t.islower() or t.isupper():
        t = t.title()
    return t


def extract_perfect_fit_apps(html: str) -> list[str]:
    m = re.search(
        r"Perfect Fit for Your Application(.*?)(?:Tailored Solutions|Get in Touch|"
        r"Discover the Product|Get Inspired|Case Studies|## )",
        html,
        re.I | re.S,
    )
    chunk = m.group(1) if m else ""
    apps: list[str] = []
    for h in re.finditer(r"<h3[^>]*>(.*?)</h3>", chunk, re.I | re.S):
        t = unescape(re.sub(r"<[^>]+>", "", h.group(1))).strip()
        t = normalize_app(t)
        if not t or len(t) > 60:
            continue
        if t.lower() in {a.lower() for a in apps}:
            continue
        # skip nav junk
        if t.lower() in {"applications", "industries", "case studies", "overview"}:
            continue
        apps.append(t)
    return apps


def extract_us_prose_apps(html: str) -> list[str]:
    """Conservative fallback: only accept well-known OEM application chips."""
    allow = {
        "arc welding",
        "spot welding",
        "material handling",
        "machine tending",
        "palletizing",
        "palletising",
        "assembly",
        "assembling",
        "painting",
        "vision inspection",
        "polishing",
        "deburring",
        "packaging",
        "picking",
        "packing",
    }
    plain = unescape(re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I))
    plain = re.sub(r"<[^>]+>", " ", plain)
    plain = re.sub(r"\s+", " ", plain).lower()
    apps: list[str] = []
    for label in sorted(allow, key=len, reverse=True):
        if label in plain:
            apps.append(normalize_app(label))
    # dedupe
    out: list[str] = []
    for a in apps:
        if a.lower() not in {x.lower() for x in out}:
            out.append(a)
    return out[:6]


def fetch_apps(url: str, cache: dict[str, list[str]]) -> list[str]:
    if url in cache:
        return cache[url]
    try:
        r = requests.get(url, timeout=45, headers=UA)
    except requests.RequestException as e:
        print(f"  fetch fail {url}: {e}")
        cache[url] = []
        return []
    if r.status_code != 200:
        print(f"  HTTP {r.status_code} {url}")
        cache[url] = []
        return []
    apps = extract_perfect_fit_apps(r.text)
    if not apps and "fanucamerica.com" in url:
        apps = extract_us_prose_apps(r.text)
    cache[url] = apps
    return apps


def purpose_for_robot(
    name: str,
    family_key: str,
    product_url: str,
    family_apps: dict[str, list[str]],
    url_cache: dict[str, list[str]],
) -> tuple[list[str], str]:
    apps: list[str] = []
    source = "family"

    # Prefer exact EU product page when we have one; merge family apps if thin
    if product_url and "fanuc.eu" in product_url and "/product/robot/" in product_url:
        prod_apps = fetch_apps(product_url, url_cache)
        if prod_apps:
            apps = list(prod_apps)
            source = "product"
            for a in family_apps.get(family_key) or []:
                if a.lower() not in {x.lower() for x in apps}:
                    apps.append(a)
            if len(apps) > len(prod_apps):
                source = "product+family"

    if not apps:
        apps = list(family_apps.get(family_key) or [])
        source = "family"

    if len(apps) < 2:
        for extra in FAMILY_FALLBACK.get(family_key, []):
            if extra.lower() not in {a.lower() for a in apps}:
                apps.append(extra)
        if FAMILY_FALLBACK.get(family_key):
            source = source + "+fallback"

    # Variant prepends (Food/Clean, Wash, Paint)
    prepend: list[str] = []
    for pat, lines in VARIANT_PREPEND:
        if pat.search(name or ""):
            for line in lines:
                if line.lower() not in {a.lower() for a in prepend + apps}:
                    prepend.append(line)
    apps = prepend + apps

    # Dedupe preserve order
    out: list[str] = []
    for a in apps:
        a = normalize_app(a)
        if a and a.lower() not in {x.lower() for x in out}:
            out.append(a)

    return out, source


def list_company_robots(client: ResearchApiClient) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    page = 1
    while True:
        data = client._get(
            "robots/robots/",
            params={"company_ref": COMPANY_ID, "page": page, "page_size": 50},
        )
        batch = data.get("results") or []
        rows.extend(batch)
        if not data.get("next") or not batch:
            break
        page += 1
        time.sleep(0.05)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--ids", type=int, nargs="*")
    args = ap.parse_args()

    client = ResearchApiClient()
    robots = list_company_robots(client)
    if args.ids:
        want = set(args.ids)
        robots = [r for r in robots if int(r["id"]) in want]
    print(f"robots={len(robots)}")

    url_cache: dict[str, list[str]] = {}
    family_apps: dict[str, list[str]] = {}
    for fk, url in FAMILY_APP_URL.items():
        apps = fetch_apps(url, url_cache)
        if len(apps) < 2 and fk in FAMILY_FALLBACK:
            for extra in FAMILY_FALLBACK[fk]:
                if extra.lower() not in {a.lower() for a in apps}:
                    apps.append(extra)
        family_apps[fk] = apps
        print(f"  family {fk}: {apps}")
        time.sleep(0.15)

    plan = []
    for r in robots:
        rid = int(r["id"])
        full = client._get(f"robots/robots/{rid}/")
        name = full.get("name") or r.get("name") or ""
        fk = (full.get("family_key") or "").strip()
        url = (full.get("url") or "").strip()
        old = (full.get("purpose") or "").strip()
        desc = (full.get("description") or "").strip()
        apps, source = purpose_for_robot(name, fk, url, family_apps, url_cache)
        purpose = "\n".join(apps)
        plan.append(
            {
                "id": rid,
                "name": name,
                "family_key": fk,
                "source": source,
                "old_purpose": old,
                "new_purpose": purpose,
                "same_as_desc": bool(purpose and desc and purpose == desc),
                "lines": len(apps),
            }
        )
        time.sleep(0.05)

    empty = [p for p in plan if not p["new_purpose"]]
    print(f"plan={len(plan)} empty={len(empty)}")
    if empty:
        for p in empty[:10]:
            print("  EMPTY", p["id"], p["name"], p["family_key"])

    out = _HERE / "staging" / "reports" / "fanuc-purpose-fix.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"apply": args.apply, "plan": plan}, indent=2), encoding="utf-8")
    print("wrote", out)
    for p in plan[:8]:
        print(f"--- {p['id']} {p['name']} ({p['source']})")
        print(p["new_purpose"])
        print(f"  was: {p['old_purpose']!r}")

    if not args.apply:
        print("dry-run only; pass --apply to PATCH")
        return 1 if empty else 0

    ok = 0
    errors = []
    for p in plan:
        if not p["new_purpose"]:
            errors.append(f"{p['id']}: empty purpose")
            continue
        try:
            client._patch(f"robots/robots/{p['id']}/", {"purpose": p["new_purpose"]})
            ok += 1
            print(f"  patched {p['id']} lines={p['lines']}")
        except Exception as e:
            errors.append(f"{p['id']}: {e}")
            print(f"  ERROR {p['id']}: {e}")
        time.sleep(0.08)
    print(f"done {ok}/{len(plan)} errors={len(errors)}")
    return 0 if ok == len(plan) and not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
