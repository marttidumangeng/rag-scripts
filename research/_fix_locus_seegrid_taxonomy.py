"""Fix taxonomy/tags/country on LocusBot + Seegrid approved junk warnings."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_RESEARCH = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient
from import_staging import import_staging, resolve_created_by_id

US_ID = 20
AVAILABLE = 11


def index_by_key(rows: list[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rows:
        key = (r.get("key") or r.get("slug") or "").strip().lower()
        rid = r.get("id")
        if key and rid:
            out[key] = int(rid)
    return out


def main() -> int:
    client = ResearchApiClient()
    uses = index_by_key(client._get("robots/uses/"))
    inds = index_by_key(client._get("robots/industries/"))
    movs = index_by_key(client._get("robots/movement-types/"))
    print("uses sample", list(uses.items())[:8])
    print("ind sample", list(inds.items())[:8])
    print("mov sample", list(movs.items())[:8])

    def ids(mapping: dict[str, int], keys: list[str]) -> list[int]:
        out = []
        for k in keys:
            if k not in mapping:
                print(f"  !! missing key {k}")
                continue
            out.append(mapping[k])
        return out

    patches: list[dict[str, Any]] = [
        {
            "id": 100,
            "name": "LocusBot",
            "note": "published shell — fill country/taxonomy/tags; align as Origin family",
            "body": {
                "manufacturer_countries": [US_ID],
                "manufacturer_country_ref": US_ID,
                "availability_status": AVAILABLE,
                "family_key": "locus:origin",
                "family_name": "Origin",
                "family_url": "https://locusrobotics.com/locusone/fleet/locus-origin-collaborative-robot",
                "product_url_scope": "family",
                "purpose": "Collaborative warehouse picking AMR (Locus Origin / LocusBot fleet)",
                "uses": ids(uses, ["pick-and-place", "warehouse", "logistics", "transport"]),
                "industries": ids(inds, ["logistics", "warehousing"]),
                "movement_types": ids(movs, ["wheeled"]),
                "tags": [
                    "AMR",
                    "Warehouse",
                    "Fulfillment",
                    "Collaborative",
                    "LocusONE",
                    "USA",
                    "LocusBot",
                ],
            },
            "staging": {
                "id": 100,
                "name": "LocusBot",
                "company_slug": "locus-robotics",
                "company_name": "Locus Robotics",
                "manufacturer_country_code": "US",
                "manufacturer_country_codes": "US",
                "purpose": "Collaborative warehouse picking AMR (Locus Origin / LocusBot fleet)",
                "description": (
                    "LocusBot is Locus Robotics' collaborative warehouse AMR brand "
                    "(Origin fleet) for goods-to-person picking orchestrated by LocusONE."
                ),
                "features": (
                    "Collaborative AMR for warehouse order fulfillment; tablet UI; "
                    "configurable totes/shelving; LocusONE orchestration. Soft: "
                    "marketing shell — detailed specs on Locus Origin (4884)."
                ),
                "url": "https://locusrobotics.com/",
                "availability_status": AVAILABLE,
                "family_key": "locus:origin",
                "family_name": "Origin",
                "family_url": "https://locusrobotics.com/locusone/fleet/locus-origin-collaborative-robot",
                "product_url_scope": "family",
                "movement_type_keys": "wheeled",
                "category_slugs": "industrial-robots",
                "use_keys": "pick-and-place|warehouse|logistics|transport",
                "industry_keys": "logistics|warehousing",
                "tags": "AMR|Warehouse|Fulfillment|Collaborative|LocusONE|USA|LocusBot",
                "source_locale": "en",
                "sources": [
                    {
                        "url": "https://www.locusrobotics.com/",
                        "type": "website",
                        "title": "Locus Robotics home",
                    }
                ],
                "information_source_urls": ["https://www.locusrobotics.com/"],
            },
        },
        {
            "id": 251,
            "name": "Palion AMR Series",
            "note": "Seegrid family shell — industries/tags/movement",
            "body": {
                "manufacturer_countries": [US_ID],
                "manufacturer_country_ref": US_ID,
                "availability_status": AVAILABLE,
                "family_key": "seegrid:palion",
                "family_name": "Palion",
                "family_url": "https://www.seegrid.com/",
                "uses": ids(uses, ["transport", "warehouse", "logistics"]),
                "industries": ids(inds, ["manufacturing", "logistics", "warehousing"]),
                "movement_types": ids(movs, ["wheeled"]),
                "tags": ["AMR", "Warehouse", "Lift Truck", "Tugger", "USA", "Seegrid", "Palion"],
            },
        },
        {
            "id": 2312,
            "name": "Seegrid Tow Tractor S7 AMR",
            "note": "fix junk education/humanoid tags + wrong uses",
            "body": {
                "manufacturer_countries": [US_ID],
                "manufacturer_country_ref": US_ID,
                "availability_status": AVAILABLE,
                "uses": ids(uses, ["transport", "warehouse", "logistics"]),
                "industries": ids(inds, ["manufacturing", "logistics", "warehousing"]),
                "movement_types": ids(movs, ["wheeled"]),
                "tags": [
                    "AMR",
                    "Tugger",
                    "Tow Tractor",
                    "Warehouse",
                    "Manufacturing",
                    "Logistics",
                    "USA",
                    "Seegrid",
                ],
            },
        },
        {
            "id": 2408,
            "name": "Seegrid Lift CR1 AMR",
            "note": "scrub Humanoid/Drone junk tags",
            "body": {
                "uses": ids(uses, ["transport", "warehouse", "logistics", "palletizing"]),
                "industries": ids(inds, ["manufacturing", "logistics", "warehousing"]),
                "movement_types": ids(movs, ["wheeled"]),
                "tags": [
                    "AMR",
                    "Lift Truck",
                    "Warehouse",
                    "Manufacturing",
                    "Logistics",
                    "AI",
                    "USA",
                    "Seegrid",
                ],
            },
        },
        {
            "id": 2409,
            "name": "Seegrid Lift RS1 AMR",
            "note": "scrub Humanoid/Drone junk tags",
            "body": {
                "uses": ids(uses, ["transport", "warehouse", "logistics", "palletizing"]),
                "industries": ids(inds, ["manufacturing", "logistics", "warehousing"]),
                "movement_types": ids(movs, ["wheeled"]),
                "tags": [
                    "AMR",
                    "Lift Truck",
                    "Warehouse",
                    "Manufacturing",
                    "Logistics",
                    "AI",
                    "USA",
                    "Seegrid",
                ],
            },
        },
        {
            "id": 5558,
            "name": "Seegrid Lift EL1 AMR",
            "note": "ensure industries/tags complete",
            "body": {
                "uses": ids(uses, ["transport", "warehouse", "logistics"]),
                "industries": ids(inds, ["logistics", "warehousing", "manufacturing"]),
                "movement_types": ids(movs, ["wheeled"]),
                "tags": [
                    "AMR",
                    "Lift Truck",
                    "Warehouse",
                    "VDA5050",
                    "USA",
                    "Seegrid",
                    "Compact",
                ],
            },
        },
        # Also re-assert Locus pending avail that got wiped
        {
            "id": 2536,
            "name": "Locus Array",
            "note": "re-assert Available after gallery import wipe",
            "body": {
                "manufacturer_countries": [US_ID],
                "manufacturer_country_ref": US_ID,
                "availability_status": AVAILABLE,
                "uses": ids(uses, ["pick-and-place", "warehouse", "logistics"]),
                "industries": ids(inds, ["logistics", "warehousing"]),
                "movement_types": ids(movs, ["wheeled"]),
                "tags": ["AMR", "Fulfillment", "LocusONE", "USA", "Warehouse", "Array", "R2G"],
            },
        },
        {
            "id": 4884,
            "name": "Locus Origin",
            "note": "re-assert taxonomy",
            "body": {
                "manufacturer_countries": [US_ID],
                "manufacturer_country_ref": US_ID,
                "availability_status": AVAILABLE,
                "uses": ids(uses, ["pick-and-place", "warehouse", "logistics", "transport"]),
                "industries": ids(inds, ["logistics", "warehousing"]),
                "movement_types": ids(movs, ["wheeled"]),
                "tags": [
                    "AMR",
                    "Fulfillment",
                    "LocusONE",
                    "USA",
                    "Warehouse",
                    "Collaborative",
                    "Origin",
                ],
            },
        },
        {
            "id": 4885,
            "name": "Locus Vector",
            "note": "re-assert Available + taxonomy",
            "body": {
                "manufacturer_countries": [US_ID],
                "manufacturer_country_ref": US_ID,
                "availability_status": AVAILABLE,
                "uses": ids(uses, ["transport", "warehouse", "logistics"]),
                "industries": ids(inds, ["logistics", "warehousing", "manufacturing"]),
                "movement_types": ids(movs, ["wheeled"]),
                "tags": [
                    "AMR",
                    "Fulfillment",
                    "LocusONE",
                    "USA",
                    "Warehouse",
                    "Material Handling",
                    "Vector",
                ],
            },
        },
    ]

    staging_dir = _RESEARCH / "staging" / "robots" / "_taxonomy_fix"
    staging_dir.mkdir(parents=True, exist_ok=True)

    for spec in patches:
        rid = spec["id"]
        if spec.get("staging"):
            path = staging_dir / f"{rid}.json"
            path.write_text(json.dumps(spec["staging"], indent=2), encoding="utf-8")
            # Keep published status for already-approved shells.
            keep_status = "published" if rid in (100, 251) else "pending_review"
            print(
                f"import {rid}",
                import_staging(
                    path,
                    dry_run=False,
                    patch=True,
                    force_overwrite=True,
                    replace_media=False,
                    status=keep_status,
                    created_by_id=resolve_created_by_id(1),
                    skip_company_update=True,
                ),
            )
        body = {k: v for k, v in spec["body"].items() if v not in (None, [], "")}
        try:
            client._patch(f"robots/robots/{rid}/", body)
            print(f"patched {rid} {spec['name']}")
        except Exception as e:  # noqa: BLE001
            # retry without tags if tag validation fails
            body2 = dict(body)
            body2.pop("tags", None)
            try:
                client._patch(f"robots/robots/{rid}/", body2)
                print(f"patched {rid} {spec['name']} (no tags) warn={e}")
            except Exception as e2:  # noqa: BLE001
                print(f"FAIL {rid}: {e} / {e2}")
                continue
        after = client._get(f"robots/robots/{rid}/")
        print(
            f"  verify country={bool(after.get('manufacturer_countries'))} "
            f"uses={len(after.get('uses') or [])} ind={len(after.get('industries') or [])} "
            f"tags={len(after.get('tags') or [])} mov={len(after.get('movement_types') or [])}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
