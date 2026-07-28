"""Curated soft enrich — Glydways (1454) Glydcar ATN vehicle.

OEM: https://www.glydways.com
US HQ (Richmond, CA). Manufacturer country US=20.
Soft: public typed dims/weight/speed not published — documented dead search.
Availability: Announced (launching 2026 onward).

Usage:
  python discover_glydways_robots.py
  python discover_glydways_robots.py --apply --copy-media
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests

_RESEARCH = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient
from import_staging import import_staging, resolve_created_by_id

COMPANY_ID = 1454
COMPANY_SLUG = "glydways"
COMPANY_NAME = "Glydways"
COMPANY_WEBSITE = "https://www.glydways.com"
US_ID = 20
ANNOUNCED = 10
UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}
SERVER = _RESEARCH.parents[1] / "robotaigeek-server"

PRODUCTS: list[dict[str, Any]] = [
    {
        "id": 2878,
        "name": "Glydcar",
        "model_name": "Glydcar",
        "variant_code": "glydcar",
        "variant_label": "Glydcar",
        "url": "https://www.glydways.com/",
        "family_key": "glydways:glydcar",
        "family_name": "Glydcar",
        "family_url": "https://www.glydways.com/",
        "product_url_scope": "family",
        "availability_status": ANNOUNCED,
        "hero_url": "https://www.glydways.com/wp-content/uploads/2025/05/WebsiteViz2_Updated_Purple-scaled.jpg",
        "gallery": [
            "https://www.glydways.com/wp-content/uploads/2025/05/WebsiteViz2_Updated_Purple-scaled.jpg",
            "https://www.glydways.com/wp-content/uploads/2025/06/AP-Birds-Eye.jpg",
        ],
        "purpose": (
            "On-demand autonomous urban transit on dedicated guideways\n"
            "Point-to-point Automated Transit Network passenger service"
        ),
        "description": (
            "Glydcar is Glydways' small electric autonomous vehicle for Automated "
            "Transit Networks: private on-demand rides on narrow dedicated guideways, "
            "orchestrated by AI for congestion-free urban mobility. First public "
            "networks are planned from 2026 (Atlanta, Contra Costa, San Jose)."
        ),
        "features": (
            "OEM glydways.com: self-driving Glydcar fleet on dedicated guideways; "
            "system claims up to 10,000 people/hour at scale; ~90% lower build cost "
            "and ~30% operating cost vs other transit modes; zero-emission electric "
            "vehicles; 24/7 on-demand nonstop origin-to-destination service; "
            "ADA-compliant stations. Soft: curb weight, exterior dims, top speed, "
            "passenger count, and MSRP not published on OEM pages this pass "
            "(checked homepage, /story/, /av-america/, press)."
        ),
        "use_keys": "transport|logistics",
        "industry_keys": "airports|government|commercial|construction",
        "category_slugs": "Mobile-Robots",
        "movement_keys": "wheeled|mobile",
        "tags": [
            "Glydways", "Glydcar", "ATN", "Autonomous", "Transit", "Electric", "USA"
        ],
        "sources": [
            {"url": "https://www.glydways.com/", "type": "website", "title": "Glydways"},
            {"url": "https://www.glydways.com/story/", "type": "website", "title": "Glydways story"},
            {
                "url": "https://www.glydways.com/san-jose-city-council-unanimously-approves-next-phase-of-san-jose-airport-connector-project/",
                "type": "website",
                "title": "San José Airport Connector",
            },
        ],
    },
]


def taxonomy_ids(client: ResearchApiClient) -> dict[str, dict[str, int]]:
    def idx(path: str) -> dict[str, int]:
        rows = client._get(path)
        if isinstance(rows, dict):
            rows = rows.get("results") or []
        return {
            (r.get("key") or "").lower(): int(r["id"])
            for r in rows
            if r.get("key") and r.get("id")
        }

    return {
        "uses": idx("robots/uses/"),
        "industries": idx("robots/industries/"),
        "movement": idx("robots/movement-types/"),
    }


def map_keys(tax: dict[str, dict[str, int]], group: str, keys: str) -> list[int]:
    out = []
    for k in keys.split("|"):
        kid = tax[group].get(k.strip().lower())
        if kid:
            out.append(kid)
        else:
            print(f"  warn missing {group}={k}")
    return out


def force_en(client: ResearchApiClient, rid: int, row: dict[str, Any]) -> None:
    sync = {
        "updates": [
            {
                "id": rid,
                "locale": loc,
                "source_hash": f"glydways-en-{rid}-20260720-{loc}",
                "translated_fields": {
                    "description": row.get("description") or "",
                    "features": row.get("features") or "",
                    "purpose": row.get("purpose") or "",
                    "name": row.get("name") or "",
                },
            }
            for loc in ("zh-CN", "zh-TW")
        ]
    }
    try:
        resp = client._session.post(
            client._url("robots/robots/translation-sync/?force=1"),
            json=sync,
            timeout=60,
        )
        print(f"  translation-sync {rid}: {resp.status_code}")
    except requests.RequestException as e:
        print(f"  translation-sync warn {rid}: {e}")


def copy_media(rid: int) -> str:
    secret = os.environ.get("INTERNAL_API_SECRET", "").strip()
    if not secret and (SERVER / ".env").is_file():
        for line in (SERVER / ".env").read_text(encoding="utf-8").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                secret = line.split("=", 1)[1].strip()
                break
    api = (
        os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/").replace("/api/v1", "")
        or "https://ragadmin.robotaigeek.com"
    )
    url = f"{api}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/?force=1"
    for attempt in range(4):
        try:
            resp = requests.post(url, headers={"X-Internal-Secret": secret}, timeout=180)
            if resp.ok:
                return f"ok {resp.text[:120]}"
            if resp.status_code not in (500, 502, 503, 504):
                return f"fail {resp.status_code} {resp.text[:120]}"
        except requests.RequestException as e:
            last = str(e)
        time.sleep(2 + attempt)
    return f"fail after retries"


def patch_company(client: ResearchApiClient) -> None:
    body = {"website": COMPANY_WEBSITE, "country_id": US_ID}
    for path in (f"companies/{COMPANY_ID}/", f"companies/companies/{COMPANY_ID}/"):
        try:
            client._patch(path, body)
            print("company patched", path)
            return
        except Exception as e:
            print("company patch warn", path, e)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--copy-media", action="store_true")
    args = ap.parse_args()

    if not args.apply:
        for p in PRODUCTS:
            print(p["id"], p["name"], p["family_key"], p["url"])
        return 0

    client = ResearchApiClient()
    tax = taxonomy_ids(client)
    staging = _RESEARCH / "staging" / "robots" / "glydways"
    staging.mkdir(parents=True, exist_ok=True)
    patch_company(client)

    for spec in PRODUCTS:
        notes = (
            f"[AI Research] Glydways enrich 2026-07-20: US; family {spec['family_key']}; "
            "Announced (2026 launches); soft specs absent on OEM."
        )
        info_urls = [s["url"] for s in spec["sources"]]
        hero = spec["hero_url"]
        row: dict[str, Any] = {
            "id": spec["id"],
            "name": spec["name"],
            "model_name": spec["model_name"],
            "variant_code": spec["variant_code"],
            "variant_label": spec["variant_label"],
            "company_slug": COMPANY_SLUG,
            "company_name": COMPANY_NAME,
            "manufacturer_country_code": "US",
            "manufacturer_country_codes": "US",
            "description": spec["description"],
            "purpose": spec["purpose"],
            "features": spec["features"],
            "url": spec["url"],
            "image": hero,
            "images": spec["gallery"],
            "source_locale": "en",
            "availability_status": ANNOUNCED,
            "family_key": spec["family_key"],
            "family_name": spec["family_name"],
            "family_url": spec["family_url"],
            "product_url_scope": spec["product_url_scope"],
            "movement_type_keys": spec["movement_keys"],
            "category_slugs": spec["category_slugs"],
            "use_keys": spec["use_keys"],
            "industry_keys": spec["industry_keys"],
            "tags": spec["tags"],
            "notes": notes,
            "research_notes": notes,
            "sources": spec["sources"],
            "information_source_urls": info_urls,
        }
        path = staging / "glydcar.json"
        path.write_text(json.dumps(row, indent=2, ensure_ascii=False), encoding="utf-8")
        print(
            "import",
            spec["id"],
            import_staging(
                path,
                dry_run=False,
                patch=True,
                force_overwrite=True,
                replace_media=True,
                status="pending_review",
                created_by_id=resolve_created_by_id(1),
                skip_company_update=True,
            ),
        )
        body: dict[str, Any] = {
            "name": spec["name"],
            "manufacturer_countries": [US_ID],
            "manufacturer_country_ref": US_ID,
            "availability_status": ANNOUNCED,
            "description": spec["description"],
            "features": spec["features"],
            "purpose": spec["purpose"],
            "url": spec["url"],
            "information_source_urls": info_urls,
            "family_key": spec["family_key"],
            "family_name": spec["family_name"],
            "family_url": spec["family_url"],
            "model_name": spec["model_name"],
            "variant_code": spec["variant_code"],
            "variant_label": spec["variant_label"],
            "product_url_scope": spec["product_url_scope"],
            "notes": notes,
            "tags": spec["tags"],
            "uses": map_keys(tax, "uses", spec["use_keys"]),
            "industries": map_keys(tax, "industries", spec["industry_keys"]),
            "movement_types": map_keys(tax, "movement", spec["movement_keys"]),
        }
        try:
            client._patch(f"robots/robots/{spec['id']}/", body)
            print("patch OK", spec["id"])
        except Exception as e:
            print("patch FAIL", spec["id"], e)
        force_en(client, spec["id"], row)
        if args.copy_media:
            print("  copy-media", copy_media(spec["id"]))

    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
