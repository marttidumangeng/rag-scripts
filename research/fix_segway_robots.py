"""Gap-only backfill for Segway Robotics (company 237).

Fills missing videos, tags, movement, model_name, and cited specs only.
Does NOT overwrite existing description/features/url/image (patch_existing).
No Gemini.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient
from import_staging import resolve_created_by_id
from map_to_bulk_import import staging_dict_to_bulk_import_row
from robot_auto_research import slugify_robot_name
from youtube_metadata import enrich_video_list

COMPANY_ID = 237
COMPANY_SLUG = "segway-robotics"
COMPANY_NAME = "Segway Robotics"

# Curated gap fills only. Specs/years cited from robotics.segway.com (+ OEM PDFs).
# Videos: title-matched official/product demos (reject scooter/go-kart junk).
# release_year only when OEM press/docs support it — leave null when uncertain.
ROBOT_DATA: dict[str, dict[str, Any]] = {
    "Nova Carter": {
        "model_name": "Nova Carter",
        "url": "https://robotics.segway.com/nova-carter/",
        "release_year": 2023,
        "movement_type_keys": "wheeled",
        "availability_status_key": "available",
        "category_slugs": "service-robots",
        "sub_category_slug": "logistics-warehouse",
        "tags": (
            "AMR|Autonomous Mobile Robot|Mobile Robot|Wheeled|"
            "Research Platform|Research|Warehouse|Logistics"
        ),
        "weight_kg": 51.2,
        "weight": "51.2 kg",
        "payload_kg": 50.0,
        "dimensions_mm": "722 x 500 x 556",
        "length_mm": 722.0,
        "width_mm": 500.0,
        "height_mm": 556.0,
        "battery_wh": 1033.0,
        "battery_capacity": "1033 Wh",
        "runtime": "≥8 h",
        "speed": 12.0,  # km/h unloaded (Product Manual v1.0: ≥12 km/h)
        "operating_temp_min_c": "0",
        "operating_temp_max_c": "35",
        "ip_rating": "IPX7",  # battery IP on product page
        "notes_append": (
            "Payload (max load): 50 kg | Tire: 11 in (280 mm) | Charging time: 5 h | "
            "Overrun height: 25 mm | Working temp: 0–35 °C | Battery IPX7 "
            "(robotics.segway.com/nova-carter/ + Nova Carter Product Manual v1.0)"
        ),
        "videos": [
            "https://www.youtube.com/watch?v=-1MdZIkh2mE",
        ],
        "source_note": (
            "release_year=2023 from OEM Download Center (OnePager Oct 2023, Product Manual "
            "20231031) + Mar 2024 news 'introduced last year'. "
            "Specs: /nova-carter/ milestones + Product Manual v1.0 PDF. "
            "YouTube: Introducing Nova Carter."
        ),
    },
    "Segway DeliveryBot": {
        "model_name": "DeliveryBot",
        "url": "https://robotics.segway.com/products/",
        # No OEM launch year — /products/ Learn More routes to E1; leave release_year unset.
        "movement_type_keys": "wheeled",
        "availability_status_key": "available",
        "category_slugs": "service-robots",
        "sub_category_slug": "logistics-warehouse",
        "tags": (
            "Delivery|delivery robot|AMR|Outdoor|Outdoor Transport|"
            "Logistics|Wheeled|Mobile Robot"
        ),
        "videos": [
            "https://www.youtube.com/watch?v=7YSjr-2wmxY",
        ],
        "source_note": (
            "No dedicated DeliveryBot PDP — listed on /products/; site Learn More points at /e1/. "
            "No OEM numeric spec table and no citable OEM release year (left null). "
            "YouTube: Introducing Segway ServeBot and DeliveryBot Capability."
        ),
    },
    "E1 Outdoor Delivery Robot": {
        "model_name": "E1",
        "url": "https://robotics.segway.com/e1/",
        # No explicit OEM "launched in YEAR" — WP asset folder 2022/10 is not enough; leave null.
        "movement_type_keys": "wheeled",
        "availability_status_key": "available",
        "category_slugs": "service-robots",
        "sub_category_slug": "logistics-warehouse",
        "tags": (
            "Delivery|delivery robot|AMR|Outdoor|Outdoor Transport|"
            "Logistics|Wheeled|Mobile Robot"
        ),
        "operating_temp_min_c": "-10",
        "operating_temp_max_c": "50",
        "notes_append": (
            "Payload Weight: 44 lbs (≈19.96 kg) | Cargo Volume: ≥60 L | Range: 60+ km | "
            "Operating Temp.: -10 ~ 50 °C (robotics.segway.com/e1/; range subject to environment)"
        ),
        "videos": [
            "https://www.youtube.com/watch?v=D2k6bp24oPs",
            "https://www.youtube.com/watch?v=ghGAAnaWxGM",
            "https://www.youtube.com/watch?v=20qKZ6lNgC4",
        ],
        "source_note": (
            "Specs from /e1/ milestones (44 lbs / ≥60 L / 60+ km / -10~50 °C). "
            "No explicit OEM launch-year statement — release_year left null "
            "(2022 media asset dates only). "
            "CRM description already says '44 kg' — left unchanged. "
            "YouTube: E1 product guides / Meet E1 & COCO / Redefining Food Delivery."
        ),
    },
    "RMP 401 Plus": {
        "model_name": "RMP 401 Plus",
        "url": "https://robotics.segway.com/rmp/",
        # No OEM launch year or numeric datasheet on robotics.segway.com.
        "movement_type_keys": "wheeled",
        "availability_status_key": "available",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "manufacturing-industrial",
        "tags": (
            "Research Platform|Mobile Robot|Wheeled|Wheeled Base|Research"
        ),
        "videos": [
            "https://www.youtube.com/watch?v=gSi954TaMms",
            "https://www.youtube.com/watch?v=khoLEzWUtVA",
        ],
        "source_note": (
            "Shared RMP hub /rmp/ — qualitative 4WD platform copy only. "
            "No OEM numeric datasheet and no citable release year (left null). "
            "YouTube: Testing RMP 401-PLUS; RMP 200/400 Capabilities."
        ),
    },
    "RMP Lite 220": {
        "model_name": "RMP Lite 220",
        "url": "https://robotics.segway.com/rmp/",
        "release_year": 2021,
        "movement_type_keys": "wheeled",
        "availability_status_key": "available",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "logistics-warehouse",
        "tags": (
            "AMR|Mobile Robot|Wheeled|Wheeled Base|Warehouse|"
            "Research Platform|Logistics"
        ),
        # Primary: Segway-RMP-220Lite-Specs.pdf (2021/04) on OEM download path.
        "weight_kg": 33.0,
        "weight": "33 kg",
        "payload_kg": 50.0,
        "dimensions_mm": "730 x 499 x 280",
        "length_mm": 730.0,
        "width_mm": 499.0,
        "height_mm": 280.0,
        "battery_wh": 1152.0,
        "battery_capacity": "1152 Wh (48 V)",
        "runtime": "10 h",
        "speed_ms": 3.0,
        "ip_rating": "IP65",
        "notes_append": (
            "Standard load: 50 kg | Max speed: 3 m/s | Battery: 48 V, 20–24 Ah, 1152 Wh | "
            "IP65 | Wheelbase×tread×clearance: 513.5×413×69 mm | Tire: 11 in hub motor | "
            "Obstacle: 5 cm / 8° (Segway-RMP-220Lite-Specs.pdf). "
            "User Manual Appendix also lists 27.2 kg with battery / IPX5 — Specs PDF preferred."
        ),
        "videos": [
            "https://www.youtube.com/watch?v=vpoiqBzuGNA",
            "https://www.youtube.com/watch?v=-1MdZIkh2mE",
        ],
        "source_note": (
            "release_year=2021 from OEM press 2021-06-22 (RMP Lite 220 + NVIDIA Carter v2.0) "
            "+ Specs PDF path /wp-content/uploads/2021/04/Segway-RMP-220Lite-Specs.pdf. "
            "Typed specs from that PDF. YouTube: RMP lobby demo; Nova Carter intro."
        ),
    },
}


def build_gap_row(robot: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    """Build staging dict with gap fields only + identity for company-scoped patch."""
    videos = enrich_video_list(data.get("videos") or [])
    row: dict[str, Any] = {
        "name": robot["name"],
        "company_slug": COMPANY_SLUG,
        "company_name": COMPANY_NAME,
        "model_name": data.get("model_name") or robot.get("model_name") or "",
        "url": data.get("url") or robot.get("url") or "",
        "movement_type_keys": data.get("movement_type_keys") or "",
        "availability_status_key": data.get("availability_status_key") or "",
        "category_slugs": data.get("category_slugs") or "",
        "sub_category_slug": data.get("sub_category_slug") or "",
        "tags": data.get("tags") or "",
        "video_urls": videos,
        "sources": [
            {
                "url": data.get("url") or robot.get("url") or "",
                "type": "website",
                "title": robot["name"],
            }
        ],
        "research_notes": data.get("source_note") or "",
        "source_locale": "en",
    }
    if data.get("release_year"):
        row["release_year"] = int(data["release_year"])
    for key in (
        "weight_kg",
        "weight",
        "payload_kg",
        "dimensions_mm",
        "length_mm",
        "width_mm",
        "height_mm",
        "battery_wh",
        "battery_capacity",
        "runtime",
        "operating_temp_min_c",
        "operating_temp_max_c",
        "speed",
        "speed_ms",
        "ip_rating",
    ):
        if key in data and data[key] not in (None, ""):
            row[key] = data[key]
    # Do NOT send description/features/image — preserve CRM values under patch.
    return row


def append_notes_if_needed(client: ResearchApiClient, robot: dict[str, Any], data: dict[str, Any]) -> str:
    """Append OEM payload/extra specs into notes without dropping existing Sources line."""
    append = (data.get("notes_append") or "").strip()
    if not append:
        return "skip"
    existing = (robot.get("notes") or "").strip()
    # Already applied?
    marker = append.split("|")[0].strip()
    if marker and marker in existing:
        return "already"
    merged = f"{existing} | {append}" if existing else append
    rid = int(robot["id"])
    try:
        client._patch(f"robots/robots/{rid}/", {"notes": merged})
        return "patched"
    except Exception as exc:
        return f"fail:{exc}"


def patch_release_year_if_needed(client: ResearchApiClient, robot: dict[str, Any], data: dict[str, Any]) -> str:
    year = data.get("release_year")
    if not year:
        return "skip"
    if robot.get("release_year"):
        return "already"
    rid = int(robot["id"])
    try:
        client._patch(f"robots/robots/{rid}/", {"release_year": int(year)})
        return "patched"
    except Exception as exc:
        return f"fail:{exc}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Gap-only fix Segway Robotics company 237")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--created-by-id", type=int, default=1)
    args = parser.parse_args()

    client = ResearchApiClient()
    robots = [
        r
        for r in client.list_robots_for_company(COMPANY_ID)
        if str(r.get("status") or "").lower() == "pending_review"
    ]
    print(f"targets: {len(robots)} pending_review")

    plan: list[dict[str, Any]] = []
    staging: dict[int, dict[str, Any]] = {}
    for robot in robots:
        name = str(robot.get("name") or "")
        data = ROBOT_DATA.get(name)
        if not data:
            print(f"SKIP unknown robot name: {name!r} id={robot.get('id')}")
            continue
        rid = int(robot["id"])
        row = build_gap_row(robot, data)
        staging[rid] = row
        plan.append(
            {
                "id": rid,
                "name": name,
                "videos": len(row.get("video_urls") or []),
                "tags": bool(row.get("tags")),
                "release_year": data.get("release_year"),
                "has_specs": any(
                    row.get(k) not in (None, "")
                    for k in ("weight_kg", "payload_kg", "dimensions_mm", "length_mm", "battery_wh", "speed", "speed_ms")
                ) or bool(data.get("notes_append")),
                "movement": row.get("movement_type_keys") or "",
            }
        )
        print(
            f"  {rid} {name}: year={data.get('release_year') or '-'} "
            f"vids={plan[-1]['videos']} tags={'yes' if plan[-1]['tags'] else 'no'} "
            f"specs={'yes' if plan[-1]['has_specs'] else 'no'} "
            f"move={plan[-1]['movement']}"
        )

    preview = _RESEARCH_DIR / "staging" / "reports" / "segway-fix-preview.json"
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if not plan:
        print("ERROR: nothing to import", file=sys.stderr)
        return 1
    if any(p["videos"] < 1 or not p["tags"] for p in plan):
        print("ERROR: incomplete enrichment (need ≥1 video + tags)", file=sys.stderr)
        return 1
    if not args.apply:
        print(f"Preview: {preview}. Re-run with --apply")
        return 0

    tmp = Path(tempfile.mkdtemp(prefix="segway-fix-"))
    totals = {"updated_count": 0, "error_count": 0, "skipped_count": 0, "created_count": 0}
    extras: list[dict[str, Any]] = []
    all_ok = True
    robots_by_id = {int(r["id"]): r for r in robots}
    for item in plan:
        rid = item["id"]
        row = staging[rid]
        data = ROBOT_DATA[item["name"]]
        # Map to bulk-import shape, then inject id for company-scoped PK match.
        bulk_row = staging_dict_to_bulk_import_row(row)
        bulk_row["id"] = rid
        fpath = tmp / f"{slugify_robot_name(row['name'])}-{rid}.json"
        fpath.write_text(json.dumps([row], indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        try:
            result = client.bulk_import_robots(
                [bulk_row],
                update_existing=True,
                patch_existing=True,
                replace_media=False,
                status="pending_review",
                skip_company_update=True,
                created_by_id=resolve_created_by_id(args.created_by_id),
            )
        except Exception as exc:
            all_ok = False
            print(f"IMPORT FAIL {rid}: {exc}", file=sys.stderr)
            continue
        err = int(result.get("error_count") or 0)
        if err:
            all_ok = False
            print(f"IMPORT FAIL {rid}: {result}", file=sys.stderr)
        for k in totals:
            totals[k] += int(result.get(k) or 0)
        print(f"  imported {rid}: {result.get('results')}")

        live = robots_by_id.get(rid) or {}
        year_status = patch_release_year_if_needed(client, live, data)
        notes_status = append_notes_if_needed(client, live, data)
        extras.append({"id": rid, "release_year": year_status, "notes_append": notes_status})
        print(f"  extras {rid}: year={year_status} notes={notes_status}")

    out = {"ok": all_ok, **totals, "extras": extras, "preview": str(preview)}
    print(json.dumps(out, indent=2))
    (_RESEARCH_DIR / "staging" / "reports" / "segway-fix-result.json").write_text(
        json.dumps(out, indent=2) + "\n", encoding="utf-8"
    )
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
