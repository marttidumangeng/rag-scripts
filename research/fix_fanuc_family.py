#!/usr/bin/env python3
"""Fill FANUC (189) family_name / family_key / family_url (+ variant / scope).

Convention (same as KUKA/Estun):
  family_key  = fanuc:<series-slug>
  family_name = reviewer-facing series label (e.g. LR Mate, CRX, M-710)
  family_url  = official series hub (prefer fanucamerica.com/products/robots/series/…)
  variant_code / model_name = SKU from the robot name
  product_url_scope = family | exact_variant

Usage:
  python fix_fanuc_family.py
  python fix_fanuc_family.py --apply
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env
from api_client import ResearchApiClient

load_research_env(local="--local" in sys.argv)

COMPANY_ID = 189
SERIES_BASE = "https://www.fanucamerica.com/products/robots/series"

# Canonical series hubs: slug → (family_name, family_url)
# URL slug aliases (r-2000ic → r-2000) normalized via SERIES_ALIAS.
SERIES: dict[str, tuple[str, str]] = {
    "lr-mate": ("LR Mate", f"{SERIES_BASE}/lr-mate"),
    "lr-10ia": ("LR-10iA", f"{SERIES_BASE}/lr-mate"),  # closest OEM hub
    "crx": ("CRX", f"{SERIES_BASE}/crx"),
    "m-1ia": ("M-1iA", f"{SERIES_BASE}/m-1ia"),
    "m-2ia": ("M-2iA", f"{SERIES_BASE}/m-2ia"),
    "m-3ia": ("M-3iA", f"{SERIES_BASE}/m-3ia"),
    "m-10": ("M-10", f"{SERIES_BASE}/m-10"),
    "m-20": ("M-20", f"{SERIES_BASE}/m-20"),
    "m-410": ("M-410", f"{SERIES_BASE}/m-410"),
    "m-710": ("M-710", f"{SERIES_BASE}/m-710"),
    "m-800": ("M-800iA", f"{SERIES_BASE}/m-800"),
    "m-810": ("M-810iA", f"{SERIES_BASE}/m-810"),
    "m-900": ("M-900", f"{SERIES_BASE}/m-900"),
    "m-950": ("M-950iA", f"{SERIES_BASE}/m-900"),  # heavy handling neighbor hub
    "m-1000": ("M-1000iA", "https://www.fanucamerica.com/products/robot/m-1000ia"),
    "m-2000": ("M-2000iA", f"{SERIES_BASE}/m-2000"),
    "r-1000": ("R-1000iA", f"{SERIES_BASE}/r-1000ia"),
    "r-2000": ("R-2000", f"{SERIES_BASE}/r-2000"),
    "scara": ("SCARA (SR)", f"{SERIES_BASE}/scara"),
    "arc-mate": ("ARC Mate", f"{SERIES_BASE}/arc-mate"),
    "paint": ("Paint (P-series)", f"{SERIES_BASE}/paint"),
    "dr-3ib": ("DR Delta", f"{SERIES_BASE}/dr-3ib"),
    "er": ("ER Education", "https://www.fanucamerica.com/products/robot/er-4ia"),
}

SERIES_ALIAS = {
    "r-2000ic": "r-2000",
    "r-1000ia": "r-1000",
    "m-1ia": "m-1ia",
    "m-2ia": "m-2ia",
    "m-3ia": "m-3ia",
}

# Name → series slug (first match wins; longest patterns first)
NAME_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bLR[\s-]?Mate\b", re.I), "lr-mate"),
    (re.compile(r"\bLR-?10iA\b", re.I), "lr-10ia"),
    (re.compile(r"\bCRX\b", re.I), "crx"),
    (re.compile(r"\bARC\s*Mate\b", re.I), "arc-mate"),
    (re.compile(r"\bSR-\d", re.I), "scara"),
    (re.compile(r"\bDR-\d", re.I), "dr-3ib"),
    (re.compile(r"\bER-\d", re.I), "er"),
    (re.compile(r"\bP-\d", re.I), "paint"),
    (re.compile(r"\bM-2000", re.I), "m-2000"),
    (re.compile(r"\bM-1000", re.I), "m-1000"),
    (re.compile(r"\bM-950", re.I), "m-950"),
    (re.compile(r"\bM-900", re.I), "m-900"),
    (re.compile(r"\bM-810", re.I), "m-810"),
    (re.compile(r"\bM-800", re.I), "m-800"),
    (re.compile(r"\bM-710", re.I), "m-710"),
    (re.compile(r"\bM-410", re.I), "m-410"),
    (re.compile(r"\bM-20", re.I), "m-20"),
    (re.compile(r"\bM-10", re.I), "m-10"),
    (re.compile(r"\bM-3iA\b", re.I), "m-3ia"),
    (re.compile(r"\bM-2iA\b", re.I), "m-2ia"),
    (re.compile(r"\bM-1iA\b", re.I), "m-1ia"),
    (re.compile(r"\bR-2000", re.I), "r-2000"),
    (re.compile(r"\bR-1000", re.I), "r-1000"),
]


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


def series_from_url(url: str) -> str | None:
    m = re.search(r"/series/([^/?#]+)", url or "", re.I)
    if not m:
        return None
    slug = m.group(1).lower().strip()
    return SERIES_ALIAS.get(slug, slug)


def series_from_name(name: str) -> str | None:
    for pat, slug in NAME_RULES:
        if pat.search(name or ""):
            return slug
    return None


def series_from_crx_host(url: str) -> str | None:
    host = urlparse(url or "").netloc.lower()
    if host.startswith("crx.") or "/crx-" in (url or "").lower():
        return "crx"
    return None


def clean_model_name(name: str) -> str:
    return re.sub(r"^FANUC\s+", "", (name or "").strip(), flags=re.I)


def derive(robot: dict[str, Any]) -> dict[str, str]:
    name = robot.get("name") or ""
    url = (robot.get("url") or "").strip()
    slug = series_from_url(url) or series_from_crx_host(url) or series_from_name(name)
    if not slug:
        raise ValueError(f"no family for id={robot.get('id')} name={name!r} url={url!r}")
    if slug not in SERIES:
        # Unknown series slug from URL — still set key/url from OEM path
        fam_name = slug.replace("-", " ").upper()
        fam_url = f"{SERIES_BASE}/{slug}" if series_from_url(url) else url
    else:
        fam_name, fam_url = SERIES[slug]

    model = clean_model_name(name)
    # Scope: series hub URL → family; dedicated product page → exact_variant
    if "/series/" in url or not url:
        scope = "family"
    else:
        scope = "exact_variant"

    return {
        "family_key": f"fanuc:{slug}",
        "family_name": fam_name,
        "family_url": fam_url,
        "model_name": model,
        "variant_code": model,
        "variant_label": model,
        "product_url_scope": scope,
    }


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

    plan = []
    errors = []
    for r in robots:
        try:
            meta = derive(r)
        except ValueError as e:
            errors.append(str(e))
            continue
        plan.append({"id": int(r["id"]), "name": r.get("name"), **meta, "url": r.get("url")})

    by_key: dict[str, int] = {}
    for row in plan:
        by_key[row["family_key"]] = by_key.get(row["family_key"], 0) + 1
    print("families:", dict(sorted(by_key.items(), key=lambda x: -x[1])))
    if errors:
        print("ERRORS", len(errors))
        for e in errors[:20]:
            print(" ", e)

    out = _HERE / "staging" / "reports" / "fanuc-family-fix.json"
    out.write_text(
        json.dumps({"apply": args.apply, "n": len(plan), "errors": errors, "plan": plan}, indent=2),
        encoding="utf-8",
    )
    print("wrote", out)

    if not args.apply:
        print("dry-run only; pass --apply to PATCH")
        return 1 if errors else 0

    ok = 0
    for row in plan:
        rid = row["id"]
        body = {
            "family_key": row["family_key"],
            "family_name": row["family_name"],
            "family_url": row["family_url"],
            "model_name": row["model_name"],
            "variant_code": row["variant_code"],
            "variant_label": row["variant_label"],
            "product_url_scope": row["product_url_scope"],
        }
        try:
            client._patch(f"robots/robots/{rid}/", body)
            ok += 1
            print(f"  patched {rid} {row['family_key']} scope={row['product_url_scope']}")
        except Exception as e:
            print(f"  ERROR {rid}: {e}")
            errors.append(f"{rid}: {e}")
        time.sleep(0.1)
    print(f"done {ok}/{len(plan)} errors={len(errors)}")
    return 0 if ok == len(plan) and not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
