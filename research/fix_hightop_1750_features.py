"""Fill missing features for Hightop HT06 (#6338) and HT360W (#6343).

Sources: official OEM PDPs on hightopmachinery.com (scraped 2026-08-02).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_RESEARCH_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH_DIR))
from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient
from import_staging import resolve_created_by_id
from map_to_bulk_import import staging_dict_to_bulk_import_row

COMPANY_ID = 1750
CN = 3

# OEM: https://www.hightopmachinery.com/product1542
HT06_FEATURES = (
    "Hightop HT06 mini excavator for tight indoor/yard/basement work. "
    "Transport envelope 1,889 × 700 × 2,086 mm (L×W×H); rear turning radius "
    "650 mm; operating weight 600 kg (pickup-truck transportable). Digging "
    "envelope: max height 2,017 mm, max depth 1,118 mm, max reach 2,025 mm; "
    "max dumping height 1,284 mm; min swing radius 1,239 mm; 30° gradeability. "
    "Bucket 0.01 m³; dozer blade ground clearance 92 mm / digging depth 93 mm. "
    "150 mm track shoes, track contact 782 mm / total track 1,126 mm for low "
    "ground pressure. Power: Runtong R300 or Briggs & Stratton engine; Tengfei "
    "main hydraulic valve; optional rearview mirror and removable canopy for "
    "low-ceiling indoor use."
)

# OEM: https://www.hightopmachinery.com/product1493
HT360W_FEATURES = (
    "Hightop HT360W wheeled skid steer loader. Rated load 220 kg; bucket "
    "0.09 m³; max lift force 375 kg; working speed 0–6.5 km/h; hydraulic "
    "system 17 MPa. Cycle times: lift 4.5 s, lower 3.5 s, tip 1.5 s. Working "
    "weight 720 kg. RATO R420D gasoline single-cylinder engine, 8.5 kW "
    "(15 hp) @ 3,600 rpm, electric start; fuel use ≤4.1 L/h; tanks: fuel "
    "6.7 L, engine oil 1.1 L, hydraulic 25 L. Overall size 2,400 × 1,030 × "
    "1,330 mm (L×W×H)."
)

HT06_PURPOSE = (
    "Compact excavation\n"
    "Site leveling and dredging\n"
    "Landscaping\n"
    "Indoor renovation digs\n"
    "Pipeline installation support"
)

HT360W_PURPOSE = (
    "Material loading\n"
    "Bucket lifting and dumping\n"
    "Yard and farm material handling\n"
    "Compact site cleanup"
)

ROBOTS: dict[int, dict[str, Any]] = {
    6338: {
        "name": "HT06 Mini Excavator",
        "url": "https://www.hightopmachinery.com/product1542",
        "features": HT06_FEATURES,
        "purpose": HT06_PURPOSE,
        "family_key": "shandong-hightop-group:ht06-mini-excavator",
        "family_name": "HT06 Mini Excavator",
        "patch_specs": {
            # OEM operating weight / digging reach / envelope — clear fabricated
            # payload that duplicated operating weight.
            "payload_kg": None,
            "weight_kg": 600.0,
            "reach_mm": 2025.0,
            "length_mm": 1889.0,
            "width_mm": 700.0,
            "height_mm": 2086.0,
        },
        "tags": "Compact|Agriculture|Industrial|Material Handling|Tracked",
    },
    6343: {
        "name": "HT360W Skid Steer Loader",
        "url": "https://www.hightopmachinery.com/product1493",
        "features": HT360W_FEATURES,
        "purpose": HT360W_PURPOSE,
        "family_key": "shandong-hightop-group:ht360w-skid-steer-loader",
        "family_name": "HT360W Skid Steer Loader",
        "patch_specs": {
            "payload_kg": 220.0,
            "weight_kg": 720.0,
            "speed": 6.5,
            "length_mm": 2400.0,
            "width_mm": 1030.0,
            "height_mm": 1330.0,
        },
        "tags": "Wheeled|Agriculture|Logistics|Material Handling|Compact",
    },
}


def apply_one(client: ResearchApiClient, rid: int, cfg: dict[str, Any]) -> dict[str, Any]:
    robot = client._get(f"robots/robots/{rid}/")
    specs = cfg["patch_specs"]
    patch = {
        "features": cfg["features"],
        "purpose": cfg["purpose"],
        "status": "pending_review",
        "manufacturer_countries": [CN],
        "manufacturer_country_ref": CN,
        "availability_status": 11,
        "family_key": cfg["family_key"],
        "family_name": cfg["family_name"],
        "family_url": cfg["url"],
        "product_url_scope": "exact_variant",
        "model_name": cfg["name"],
        "tags": [t.strip() for t in cfg["tags"].split("|")],
        "notes": (
            (robot.get("notes") or "").rstrip()
            + "\n[AI Research] Features + typed specs from OEM PDP parameter/"
            "feature copy on hightopmachinery.com (2026-08-02)."
        ),
        **specs,
    }
    client._patch(f"robots/robots/{rid}/", patch)

    row = {
        "company_slug": "shandong-hightop-group",
        "company_name": "Shandong Hightop Group",
        "source_locale": "en",
        "name": cfg["name"],
        "model_name": cfg["name"],
        "url": cfg["url"],
        "description": robot.get("description") or cfg["name"],
        "purpose": cfg["purpose"],
        "features": cfg["features"],
        "information_source_urls": [cfg["url"]],
        "notes": patch["notes"],
        "manufacturer_country_code": "CN",
        "availability_status_key": "available",
        "family_key": cfg["family_key"],
        "family_name": cfg["family_name"],
        "family_url": cfg["url"],
        "product_url_scope": "exact_variant",
        "tags": cfg["tags"].replace("|", "|"),
        **{k: v for k, v in specs.items() if v is not None},
    }
    img = robot.get("s3_image") or robot.get("image")
    if img:
        row["image"] = img
    bulk = staging_dict_to_bulk_import_row(row)
    bulk["id"] = rid
    bulk["status"] = "pending_review"
    result = client.bulk_import_robots(
        [bulk],
        update_existing=True,
        patch_existing=False,
        replace_media=False,
        replace_videos=False,
        status="pending_review",
        skip_company_update=True,
        created_by_id=resolve_created_by_id(1),
    )
    # Re-assert after import (can wipe typed fields / country / availability).
    client._patch(f"robots/robots/{rid}/", patch)
    full = client._get(f"robots/robots/{rid}/")
    flags = full.get("quality_flags") or []
    return {
        "id": rid,
        "name": full.get("name"),
        "features_len": len((full.get("features") or "").strip()),
        "import_updated": result.get("updated_count"),
        "import_errors": result.get("error_count"),
        "errors": [
            f.get("flag")
            for f in flags
            if isinstance(f, dict) and f.get("severity") == "error"
        ],
        "warns": [
            f.get("flag")
            for f in flags
            if isinstance(f, dict) and f.get("severity") == "warn"
        ],
        "specs": {
            k: full.get(k)
            for k in (
                "payload_kg",
                "weight_kg",
                "reach_mm",
                "speed",
                "length_mm",
                "width_mm",
                "height_mm",
            )
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--local", action="store_true")
    args = parser.parse_args()
    preview = {
        rid: {"name": cfg["name"], "features": cfg["features"], "specs": cfg["patch_specs"]}
        for rid, cfg in ROBOTS.items()
    }
    out = _RESEARCH_DIR / "staging" / "reports" / "hightop-1750-features-preview.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(preview, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(preview, indent=2, ensure_ascii=False)[:1500])
    if not args.apply:
        print(f"Preview {out}. Re-run with --apply")
        return 0

    client = ResearchApiClient()
    results = []
    for rid, cfg in ROBOTS.items():
        print(f"Applying {rid} {cfg['name']}…", flush=True)
        results.append(apply_one(client, rid, cfg))
    print(json.dumps(results, indent=2, ensure_ascii=False))
    bad = [r for r in results if "missing_features" in (r.get("errors") or [])]
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
