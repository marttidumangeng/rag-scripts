"""Fill Dephy soft gaps: price_min/max on Starter Pack; EN + URL/sources on published Sidekick."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import requests

_RESEARCH = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient

US_ID = 20
AVAILABLE = 11

SIDEKICK_DESC = (
    "Sidekick is Dephy's powered ankle footwear system that adds a propulsive heel "
    "boost with each step so everyday walking takes less effort. It is a wellness "
    "product (not a medical device) sold for consumer use."
)
SIDEKICK_PURPOSE = (
    "Powered ankle boost for everyday walking\n"
    "Reduce walking effort with wearable propulsion"
)
SIDEKICK_FEATURES = (
    "OEM dephy.com / shop.dephy.com: wearable powered-at-the-ankle Sidekick; "
    "propulsive heel boost each step; walks with your stride (not for you); "
    "lightweight everyday design; custom fit; compatible shoes; wellness product "
    "explicitly not a medical device. Soft: kit accessories/price live on Starter Pack SKU."
)
STARTER_DESC = (
    "The Sidekick Starter Pack is Dephy's retail kit for the Sidekick powered ankle "
    "footwear system — a wearable that adds a propulsive heel boost each step to make "
    "everyday walking easier (wellness product, not a medical device)."
)
STARTER_PURPOSE = (
    "Powered ankle boost for everyday walking\n"
    "Retail starter kit with paired Sidekicks and accessories"
)
STARTER_FEATURES = (
    "OEM shop.dephy.com Sidekick Starter Pack ($4,500): wearable powered-at-the-ankle "
    "Sidekick pair; dual batteries + dual-bay charger; compatible shoes; carrying case; "
    "~1.4 kg class; custom fit; intuitive everyday use; 30-day return policy on shop. "
    "Soft: runtime/DoF not typed on PDP; OEM states not a medical device."
)


def taxonomy_ids(client: ResearchApiClient) -> dict[str, dict[str, int]]:
    def idx(path: str) -> dict[str, int]:
        rows = client._get(path)
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


def force_en(client: ResearchApiClient, rid: int, fields: dict[str, str]) -> None:
    sync = {
        "updates": [
            {
                "id": rid,
                "locale": loc,
                "source_hash": f"dephy-softfill-{rid}-20260720c-{loc}",
                "translated_fields": {
                    "description": fields.get("description") or "",
                    "features": fields.get("features") or "",
                    "purpose": fields.get("purpose") or "",
                    "name": fields.get("name") or "",
                },
            }
            for loc in ("zh-CN", "zh-TW")
        ]
    }
    resp = client._session.post(
        client._url("robots/robots/translation-sync/?force=1"),
        json=sync,
        timeout=60,
    )
    print(f"  translation-sync {rid}: {resp.status_code}")


def main() -> int:
    client = ResearchApiClient()
    tax = taxonomy_ids(client)

    # --- Published Sidekick (354): URL, sources, EN copy, taxonomy, variants ---
    body_354: dict[str, Any] = {
        "url": "https://dephy.com/",
        "information_source_urls": [
            "https://dephy.com/",
            "https://shop.dephy.com/products/sidekick-starter-pack",
        ],
        "name": "Sidekick",
        "model_name": "Sidekick",
        "variant_code": "Sidekick",
        "variant_label": "Sidekick",
        "family_key": "dephy:sidekick",
        "family_name": "Sidekick",
        "family_url": "https://dephy.com/",
        "product_url_scope": "exact_variant",
        "manufacturer_countries": [US_ID],
        "manufacturer_country_ref": US_ID,
        "availability_status": AVAILABLE,
        "description": SIDEKICK_DESC,
        "purpose": SIDEKICK_PURPOSE,
        "features": SIDEKICK_FEATURES,
        "weight_kg": 1.4,
        "tags": ["Dephy", "Sidekick", "Exoskeleton", "Ankle", "Wearable", "USA"],
        "uses": map_keys(tax, "uses", "rehabilitation|helping"),
        "industries": map_keys(tax, "industries", "healthcare|consumer"),
        "movement_types": map_keys(tax, "movement", "legged"),
        "notes": (
            "[AI Research] Soft-fill 2026-07-20: OEM URL + information_source_urls; "
            "EN rewrite; weight 1.4 kg; family/variant aligned with Starter Pack."
        ),
    }
    client._patch("robots/robots/354/", body_354)
    force_en(
        client,
        354,
        {
            "name": "Sidekick",
            "description": SIDEKICK_DESC,
            "features": SIDEKICK_FEATURES,
            "purpose": SIDEKICK_PURPOSE,
        },
    )

    # --- Starter Pack (5088): typed price_min/max + sources + clean tags ---
    body_5088: dict[str, Any] = {
        "url": "https://shop.dephy.com/products/sidekick-starter-pack",
        "information_source_urls": [
            "https://shop.dephy.com/products/sidekick-starter-pack",
            "https://dephy.com/",
        ],
        "price_min": 4500,
        "price_max": 4500,
        "price_currency": "USD",
        "weight_kg": 1.4,
        "availability_status": AVAILABLE,
        "manufacturer_countries": [US_ID],
        "manufacturer_country_ref": US_ID,
        "family_key": "dephy:sidekick",
        "family_name": "Sidekick",
        "family_url": "https://dephy.com/",
        "description": STARTER_DESC,
        "purpose": STARTER_PURPOSE,
        "features": STARTER_FEATURES,
        "tags": [
            "Dephy",
            "Sidekick",
            "Starter Pack",
            "Exoskeleton",
            "Ankle",
            "Wearable",
            "USA",
        ],
        "uses": map_keys(tax, "uses", "rehabilitation|helping"),
        "industries": map_keys(tax, "industries", "healthcare|consumer"),
        "movement_types": map_keys(tax, "movement", "legged"),
        "notes": (
            "[AI Research] Soft-fill 2026-07-20: price_min/max $4500 USD from OEM shop; "
            "information_source_urls set (was skipped as soft warn — fixed)."
        ),
    }
    client._patch("robots/robots/5088/", body_5088)
    force_en(
        client,
        5088,
        {
            "name": "Sidekick Starter Pack",
            "description": STARTER_DESC,
            "features": STARTER_FEATURES,
            "purpose": STARTER_PURPOSE,
        },
    )

    for rid in (354, 5088):
        r = client._get(f"robots/robots/{rid}/")
        print(
            f"=== {rid} {r.get('name')}",
            f"url={r.get('url')!r}",
            f"price={r.get('price_min')}-{r.get('price_max')} {r.get('price_currency')}",
            f"wt={r.get('weight_kg')}",
            f"feats={len(r.get('features') or '')}",
            f"purpose={(r.get('purpose') or '')[:60]!r}",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
