"""Curated Briggo / Costa Coffee (406) enrich — Smart Café (4419).

OEM lineage: Austin-based Briggo (Coffee Haus / Smart Café automation) acquired
by Costa Coffee (Coca-Cola) in 2020; briggo.com redirected/rebranded. Current
official product copy lives on Costa US business pages — not a solenis-style
homepage stub.

OEM URLs (verified via search / Costa business docs, 2026-07-20):
  https://www.us.costacoffee.com/costa-business/future-of-togo
  https://www.us.costacoffee.com/costa-business
  https://us.costacoffee.com/docs/costa-coffee-unlock-coffee-potential.pdf

Family briggo:smart-cafe. US country 20. Soft: 3'×3' footprint → 914×914 mm;
no public curb weight/speed on Costa pages. Hero restored in the follow-up
`fix_briggo_formic_images.py` pass from the current official Smart Café page.

Usage:
  python discover_briggo_robots.py
  python discover_briggo_robots.py --apply
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_RESEARCH = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient

COMPANY_ID = 406
COMPANY_SLUG = "briggo-costa-coffee"
COMPANY_NAME = "Briggo (Costa Coffee)"
US_ID = 20
AVAILABLE = 11

SMART_CAFE = "https://www.us.costacoffee.com/costa-business/future-of-togo"
COSTA_BIZ = "https://www.us.costacoffee.com/costa-business"
PDF = "https://us.costacoffee.com/docs/costa-coffee-unlock-coffee-potential.pdf"

PRODUCTS: list[dict[str, Any]] = [
    {
        "id": 4419,
        "name": "Smart Café",
        "model_name": "Smart Café",
        "variant_code": "Smart-Cafe",
        "variant_label": "Costa Smart Café",
        "url": SMART_CAFE,
        "family_key": "briggo:smart-cafe",
        "family_name": "Smart Café",
        "family_url": SMART_CAFE,
        "product_url_scope": "exact_variant",
        "availability_status": AVAILABLE,
        "length_mm": 914,  # OEM "Just 3'x3'"
        "width_mm": 914,
        "height_mm": None,
        "purpose": (
            "Autonomous barista-style espresso beverage dispensing\n"
            "24/7 self-serve specialty coffee in retail and foodservice"
        ),
        "description": (
            "Smart Café is Costa Coffee's autonomous coffee kiosk (from the "
            "Briggo acquisition lineage). The touchscreen unit prepares 200+ "
            "barista-quality drink combinations in under 90 seconds using real "
            "milk and freshly ground Signature Blend beans."
        ),
        "features": (
            "OEM us.costacoffee.com/costa-business/future-of-togo + costa-business "
            "+ unlock-coffee-potential PDF: autonomous touchscreen coffee system; "
            "200+ barista-quality drink combinations; each drink in <90 seconds; "
            "real milk + freshly ground Signature Blend beans; 24/7 operation; "
            "footprint just 3'×3' (~0.84 m² / 914×914 mm typed); ~30 min/day "
            "maintenance; needs water, waste, and power only; HUB sales/inventory "
            "telemetry with restock alerts; labor-saving vs trained barista staff. "
            "Partnering page cites 14,600+ Smart Café machines in 14 markets and "
            "2023 NRA Kitchen Innovations honoree. Soft: no public curb weight, "
            "height, or motor speed on Costa pages."
        ),
        "use_keys": "dispensing",
        "industry_keys": "food-beverage|retail|hospitality",
        "tags": ["Coffee", "Kiosk", "Briggo", "Costa", "Autonomous", "USA"],
    },
]


def taxonomy_ids(client: ResearchApiClient) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {"uses": {}, "industries": {}, "movement": {}}
    for group, path in (
        ("uses", "robots/uses/"),
        ("industries", "robots/industries/"),
        ("movement", "robots/movement-types/"),
    ):
        try:
            rows = client._get(path) or []
            if isinstance(rows, dict):
                rows = rows.get("results") or rows.get("data") or []
            for row in rows:
                key = (row.get("key") or row.get("slug") or "").lower()
                if key and row.get("id"):
                    out[group][key] = int(row["id"])
        except Exception as e:  # noqa: BLE001
            print("tax warn", group, e)
    return out


def force_en(client: ResearchApiClient, rid: int, row: dict[str, Any]) -> None:
    sync = {
        "updates": [
            {
                "id": rid,
                "locale": loc,
                "source_hash": f"briggo-en-force-{rid}-20260720-{loc}",
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
        client._post("robots/translations/sync/", sync)
        print(f"  en-force {rid}")
    except Exception as e:  # noqa: BLE001
        print(f"  en-force warn {rid}: {e}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    client = ResearchApiClient()
    tax = taxonomy_ids(client)
    staging = _RESEARCH / "staging" / "robots" / COMPANY_SLUG
    staging.mkdir(parents=True, exist_ok=True)

    def map_keys(group: str, keys: str) -> list[int]:
        out = []
        for k in keys.split("|"):
            kid = tax[group].get(k.strip().lower())
            if kid:
                out.append(kid)
            else:
                print(f"  warn missing {group} key={k}")
        return out

    # Company website: Costa US business (Briggo brand absorbed)
    if args.apply:
        try:
            client._patch(
                f"companies/{COMPANY_ID}/",
                {
                    "website": COSTA_BIZ,
                    "country": US_ID,
                    "manufacturer_countries": [US_ID],
                },
            )
            print("company patched website", COSTA_BIZ)
        except Exception as e:  # noqa: BLE001
            try:
                client._patch(f"companies/{COMPANY_ID}/", {"website": COSTA_BIZ})
                print("company website only", e)
            except Exception as e2:  # noqa: BLE001
                print("company patch warn", e, e2)

    plan: list[dict[str, Any]] = []
    for spec in PRODUCTS:
        notes = (
            "[AI Research] Briggo/Costa Smart Café enrich 2026-07-20. OEM lineage "
            "Briggo (Austin) → Costa Coffee 2020. Primary URL Costa future-of-togo "
            "(not briggo.com home). Hero restored 2026-07-21 from the current "
            "official Costa Smart Café page and copied to owned CDN."
        )
        row: dict[str, Any] = {
            "id": spec["id"],
            "name": spec["name"],
            "model_name": spec["model_name"],
            "variant_code": spec["variant_code"],
            "variant_label": spec["variant_label"],
            "company_slug": COMPANY_SLUG,
            "company_name": COMPANY_NAME,
            "manufacturer_country_code": "US",
            "description": spec["description"],
            "purpose": spec["purpose"],
            "features": spec["features"],
            "url": spec["url"],
            "family_key": spec["family_key"],
            "family_name": spec["family_name"],
            "family_url": spec["family_url"],
            "product_url_scope": spec["product_url_scope"],
            "availability_status": spec["availability_status"],
            "length_mm": spec.get("length_mm"),
            "width_mm": spec.get("width_mm"),
            "notes": notes,
            "sources": [
                {"url": SMART_CAFE, "type": "website", "title": "Costa Smart Café"},
                {"url": COSTA_BIZ, "type": "website", "title": "Costa US business"},
                {"url": PDF, "type": "datasheet", "title": "Unlock coffee potential PDF"},
            ],
            "information_source_urls": [SMART_CAFE, COSTA_BIZ, PDF],
        }
        path = staging / "smart-cafe.json"
        path.write_text(json.dumps(row, indent=2, ensure_ascii=False), encoding="utf-8")
        print("staged", path.name)
        plan.append({"id": spec["id"], "url": spec["url"]})

        if not args.apply:
            continue

        body: dict[str, Any] = {
            "manufacturer_countries": [US_ID],
            "manufacturer_country_ref": US_ID,
            "availability_status": AVAILABLE,
            "status": "pending_review",
            "name": spec["name"],
            "model_name": spec["model_name"],
            "variant_code": spec["variant_code"],
            "variant_label": spec["variant_label"],
            "description": spec["description"],
            "features": spec["features"],
            "purpose": spec["purpose"],
            "url": spec["url"],
            "family_key": spec["family_key"],
            "family_name": spec["family_name"],
            "family_url": spec["family_url"],
            "product_url_scope": spec["product_url_scope"],
            "length_mm": spec.get("length_mm"),
            "width_mm": spec.get("width_mm"),
            "notes": notes,
            "source_locale": "en",
            "uses": map_keys("uses", spec["use_keys"]),
            "industries": map_keys("industries", spec["industry_keys"]),
            "movement_types": map_keys("movement", "stationary"),
            "information_source_urls": [SMART_CAFE, COSTA_BIZ, PDF],
        }
        try:
            client._patch(f"robots/robots/{spec['id']}/", body)
            print("patched", spec["id"])
        except Exception as e:  # noqa: BLE001
            body.pop("uses", None)
            body.pop("industries", None)
            body.pop("movement_types", None)
            try:
                client._patch(f"robots/robots/{spec['id']}/", body)
                print("patched", spec["id"], "(no taxonomy)", e)
            except Exception as e2:  # noqa: BLE001
                print("patch fail", spec["id"], e2)
        force_en(client, spec["id"], row)

    report = _RESEARCH / "staging" / "reports" / "briggo-discover.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        json.dumps({"apply": args.apply, "robots": plan}, indent=2),
        encoding="utf-8",
    )
    print("Report ->", report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
