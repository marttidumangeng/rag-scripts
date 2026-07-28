#!/usr/bin/env python3
"""Fix Unitree Robotics (company 109) remaining content-queue QA gaps.

Root cause for "features won't PATCH": research API key user prefers zh-CN, so
RobotSerializer overlays RobotTranslation.features on every GET/PATCH response.
English source CAN be updated (bulk-import / PATCH), but reads keep showing the
stale zh-CN translation until translation-sync?force=1 overwrites it.

This script:
  1. force_overwrite bulk-import for curated English narrative + OEM URLs/years
  2. force-syncs zh-CN translation narrative fields to the same English text
     (so zh-preferring clients see correct copy until a proper zh retranslate)
  3. surgical PATCH for typed specs cited on unitree.com PDPs
  4. leaves price/videos alone (optional per stakeholder)

Usage:
  python -u fix_unitree_robots.py           # dry-run
  python -u fix_unitree_robots.py --apply
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from load_env import load_research_env

load_research_env()

from api_client import ResearchApiClient

COMPANY_ID = 109
COMPANY_SLUG = "unitree-robotics"
COMPANY_NAME = "Unitree Robotics"

# Curated from official unitree.com PDPs (fetched 2026-07-18). No invented numbers.
FIXES: dict[int, dict[str, Any]] = {
    40: {  # H1 — https://www.unitree.com/h1
        "url": "https://www.unitree.com/h1",
        "source_locale": "en",
        "release_year": 2023,
        "description": (
            "Unitree H1 is Unitree's first full-size universal humanoid robot, "
            "designed for research and industrial exploration with high-torque "
            "joints, 360° depth perception (3D LiDAR + depth camera), and a "
            "quickly replaceable battery."
        ),
        "purpose": (
            "Full-size universal humanoid platform for research, development, "
            "and industrial exploration."
        ),
        "features": (
            "Full-size universal humanoid (H1 / H1-2 family)\n"
            "About 180 cm tall / ~47 kg (H1); H1-2 ~178 cm / ~70 kg\n"
            "Moving speed 3.3 m/s claimed (potential >5 m/s on H1)\n"
            "Max joint torque up to ~360 N·m (knee)\n"
            "360° depth sensing: 3D LiDAR + depth camera\n"
            "Battery ~864 Wh (15 Ah), quickly replaceable\n"
            "Developer compute: Intel Core i5/i7 with optional Orin NX"
        ),
        "specs": {
            "weight_kg": 47.0,
            "height_mm": 1800.0,
            "walking_speed": 3.3,
            "battery_wh": 864.0,
            "battery_capacity": "15Ah (0.864 kWh)",
            "joint_torque_nm": 360.0,
        },
    },
    126: {  # G1 — https://www.unitree.com/g1
        "url": "https://www.unitree.com/g1",
        "source_locale": "en",
        "release_year": 2024,
        "description": (
            "Unitree G1 is a compact humanoid agent platform for embodied-AI "
            "development, with 23–43 joint degrees of freedom (EDU configs), "
            "depth camera + 3D LiDAR sensing, and optional force-control "
            "dexterous hands."
        ),
        "purpose": (
            "Compact humanoid robot for research, education, and embodied-AI "
            "avatar development."
        ),
        "features": (
            "Compact humanoid agent / AI avatar platform\n"
            "Stand size 1320×450×200 mm; fold 690×450×300 mm\n"
            "Weight about 35 kg with battery\n"
            "Total DOF 23 (base) up to 23–43 on EDU configs\n"
            "Depth camera + 3D LiDAR; Wi-Fi 6 / Bluetooth 5.2\n"
            "Smart battery 9000 mAh; about 2 h battery life\n"
            "EDU supports secondary development and optional Dex3-1 hands"
        ),
        "specs": {
            "weight_kg": 35.0,
            "height_mm": 1320.0,
            "dof": 23,
            "battery_capacity": "9000mAh",
            "runtime": "About 2h",
            "payload_kg": 2.0,  # arm max load ~2 kg (base G1)
        },
    },
    44: {  # B2 — https://www.unitree.com/b2
        "url": "https://www.unitree.com/b2",
        "source_locale": "en",
        "release_year": 2023,
        "description": (
            "Unitree B2 is an industrial-grade quadruped for inspection and "
            "outdoor work, with IP67 protection, high payload, multi-hour "
            "endurance, and optional wheeled-foot configurations."
        ),
        "purpose": (
            "Industrial quadruped for inspection, logistics, and all-terrain "
            "outdoor mobility."
        ),
        "features": (
            "Industrial quadruped; standing size ≈1098×450×645 mm\n"
            "Total weight ≈60 kg including battery\n"
            "Standing load ≥120 kg; continuous walking load >40 kg\n"
            "Max running speed >6 m/s (special configs; speed-limited in practice)\n"
            "Battery 45 Ah (2250 Wh) / 58 V; endurance typically 4–6 h\n"
            "IP67 ingress protection; operating −20°C to 55°C\n"
            "Sensing: 3D LiDAR + depth/optical cameras (config-dependent)\n"
            "Optional wheeled-foot and autonomous charging"
        ),
        "specs": {
            "weight_kg": 60.0,
            "height_mm": 645.0,
            "payload_kg": 40.0,  # continuous walking load (conservative vs 120 standing)
            "battery_wh": 2250.0,
            "battery_capacity": "45Ah (2250Wh)",
            "runtime": "4-6h",
            "joint_torque_nm": 360.0,
            "walking_speed": 6.0,  # m/s; OEM claims >6 m/s in special configs
        },
    },
    42: {  # Go2 base — https://www.unitree.com/go2
        "url": "https://www.unitree.com/go2",
        "source_locale": "en",
        "release_year": 2023,
        "description": (
            "Unitree Go2 is a consumer and research quadruped with onboard "
            "4D LiDAR L2, ISS 2.0 side-follow, OTA upgrades, and Air/Pro/Edu "
            "hardware tiers."
        ),
        "purpose": (
            "Consumer and research quadruped for education, development, and "
            "embodied-AI exploration."
        ),
        "features": (
            "Quadruped with Unitree 4D LiDAR L2 (360°×96° hemispherical)\n"
            "Standing size ~70×31×40 cm; weight about 15 kg with battery\n"
            "Hardware tiers: Air / Pro / Edu (and related X variants)\n"
            "ISS 2.0 intelligent side-follow; OTA upgrades\n"
            "Peak knee joint torque about 45 N·m (Pro/Edu)\n"
            "Battery life about 1–2 h (Air/Pro) up to ~2–4 h (Edu long pack)\n"
            "Wi-Fi 6 / Bluetooth; Edu adds secondary development hooks"
        ),
        "specs": {
            "weight_kg": 15.0,
            "height_mm": 400.0,
            "payload_kg": 7.0,  # Air ≈7 kg continuous (shared family floor)
            "battery_capacity": "8000mAh (standard)",
            "runtime": "About 1-2h",
            "joint_torque_nm": 45.0,
        },
    },
    348: {  # H2 — https://www.unitree.com/H2
        "url": "https://www.unitree.com/H2",
        "source_locale": "en",
        "release_year": 2025,
        "description": (
            "Unitree H2 is Unitree's next-generation full-size humanoid platform "
            "for industrial, commercial, and research deployments, with EDU/PLUS "
            "and dual-arm (H2-D) configurations."
        ),
        "purpose": (
            "Full-size humanoid robot platform for industrial and research "
            "applications."
        ),
        "features": (
            "Next-generation full-size humanoid platform\n"
            "Supports secondary development and system customization\n"
            "Aimed at industrial, commercial, and research deployments\n"
            "Family includes EDU / PLUS / H2-D dual-arm configurations\n"
            "High-DOF articulated body with high-torque joint actuators"
        ),
        # Specs left sparse — confirm per-variant numbers on H2 PDP before typing
    },
    282: {  # Laikago — legacy; no live PDP
        "url": "https://www.unitree.com/",
        "source_locale": "en",
        "release_year": 2017,
        "description": (
            "Laikago was Unitree's early high-performance research quadruped, "
            "globally pre-sold in 2017 and a predecessor to the AlienGo / Go "
            "consumer and research lines."
        ),
        "purpose": "Legacy research quadruped from Unitree's early product line.",
        "features": (
            "Unitree's early research quadruped platform (legacy)\n"
            "Four-legged dynamic locomotion research platform\n"
            "Predecessor line to AlienGo / A1 / Go series\n"
            "No dedicated live product page on unitree.com as of 2026-07"
        ),
        "notes_append": (
            "[IMAGE/URL NOTE — legacy model]\n"
            "No dedicated live product page found on unitree.com during 2026-07-18 "
            "enrich; URL left as company homepage. Confirm archive/datasheet if "
            "deeper specs needed."
        ),
    },
    601: {  # Unitree GD01 — no confirmed EN PDP
        "url": "https://www.unitree.com/",
        "source_locale": "en",
        "description": (
            "Unitree GD01 appears in catalog signals but no confirmed public "
            "English product page was verified in this pass."
        ),
        "purpose": "Unitree catalog listing pending dedicated product-page confirmation.",
        "features": (
            "Unitree GD01 listing captured from company catalog signals\n"
            "Exact public English PDP not confirmed — verify on unitree.com\n"
            "Likely overlaps with sibling CRM row GD01 (id 660) — review for merge"
        ),
        "notes_append": (
            "[URL/FEATURES TO-DO]\n"
            "Homepage-only source. Need dedicated GD01 product page before typed "
            "specs. Review merge with robot 660."
        ),
    },
    660: {  # GD01 junk homepage chrome
        "url": "https://www.unitree.com/",
        "source_locale": "en",
        "description": (
            "GD01 CRM row previously stored homepage chrome as features. "
            "Treated as incomplete / possible duplicate of Unitree GD01 (601)."
        ),
        "purpose": "Incomplete GD01 listing — verify identity and merge with 601 if duplicate.",
        "features": (
            "Incomplete GD01 record (homepage chrome previously scraped)\n"
            "Likely duplicate/overlap with Unitree GD01 (601)\n"
            "ACTION: confirm model identity on unitree.com or merge/delete"
        ),
        "notes_append": (
            "[URL/FEATURES TO-DO]\n"
            "Homepage-only source; features previously scraped from homepage chrome. "
            "Likely duplicate/overlap with Unitree GD01 (601) — review for merge."
        ),
    },
    5368: {  # Go1 — https://www.unitree.com/go1 (specs missing)
        "url": "https://www.unitree.com/go1",
        "source_locale": "en",
        "release_year": 2021,
        "description": (
            "Unitree Go1 is a consumer-level bionic quadruped companion with "
            "SSS super-sensing, ISS intelligent concomitant follow, and Air/Pro/Edu "
            "tiers."
        ),
        "purpose": "Consumer-level intelligent bionic quadruped companion and education platform.",
        "features": (
            "Consumer-level bionic quadruped companion\n"
            "Weight about 12 kg; fold size 0.588×0.22×0.29 m\n"
            "Adaptive load ≈3–5 kg (Air/Pro ≈4 kg; Edu ≈6 kg continuous)\n"
            "High dynamics up to ~17 km/h / ~5 m/s peak (lab / limit)\n"
            "SSS super-sensing + ISS intelligent concomitant follow\n"
            "Air / Pro / Edu hardware tiers with progressive SDK access"
        ),
        "specs": {
            "weight_kg": 12.0,
            "height_mm": 290.0,
            "payload_kg": 4.0,
            "walking_speed": 3.5,  # Pro mid-tier continuous range upper
        },
    },
}

# URL-only surgical patches (never force-overwrite narrative — GET returns zh overlay)
URL_ONLY: dict[int, str] = {
    5366: "https://www.unitree.com/go1",  # was /cn/go1
}

NARRATIVE_KEYS = ("description", "purpose", "features")


def _tag_string(robot: dict[str, Any]) -> str:
    tags = robot.get("tags") or []
    if isinstance(tags, str):
        return tags
    if isinstance(tags, list):
        names = []
        for t in tags:
            if isinstance(t, dict):
                names.append(str(t.get("name") or t.get("slug") or "").strip())
            else:
                names.append(str(t).strip())
        return "|".join(n for n in names if n)
    return ""


def preserve_base(robot: dict[str, Any], fix: dict[str, Any]) -> dict[str, Any]:
    """Preserve CRM fields under force_overwrite.

    Never copy narrative from GET into the row unless the fix supplies English —
    GET returns zh-CN translation overlay for this API key user, which would
    otherwise corrupt source_locale=en fields.
    """
    img = (robot.get("s3_image") or robot.get("image") or "").strip()
    row = {
        "id": robot["id"],
        "name": robot.get("name") or "",
        "model_name": robot.get("model_name") or robot.get("name") or "",
        "company": COMPANY_NAME,
        "company_ref": COMPANY_ID,
        "company_slug": COMPANY_SLUG,
        "company_name": COMPANY_NAME,
        "url": robot.get("website_url") or robot.get("url") or "",
        "image": img,
        "notes": robot.get("notes") or "",
        "tags": _tag_string(robot),
        "source_locale": "en",
        "release_year": robot.get("release_year"),
        "weight_kg": robot.get("weight_kg"),
        "weight": robot.get("weight") or "",
        "height_mm": robot.get("height_mm"),
        "payload_kg": robot.get("payload_kg"),
        "dof": robot.get("dof"),
        "status": robot.get("status") or "pending_review",
    }
    for key in NARRATIVE_KEYS:
        if key not in fix or not fix[key]:
            raise ValueError(
                f"robot {robot.get('id')}: force_overwrite requires curated English {key}"
            )
        row[key] = fix[key]
    return row


def build_row(robot: dict[str, Any], fix: dict[str, Any]) -> dict[str, Any]:
    row = preserve_base(robot, fix)
    for key, val in fix.items():
        if key in ("specs", "notes_append"):
            continue
        if key in NARRATIVE_KEYS:
            continue
        if val is not None and val != "":
            row[key] = val
    note = fix.get("notes_append")
    if note:
        existing = row.get("notes") or ""
        if note not in existing:
            row["notes"] = (note + "\n---\n" + existing).strip() if existing else note
    if "url" in row and row["url"]:
        row["website_url"] = row["url"]
    return row


def force_sync_zh(client: ResearchApiClient, robot_id: int, fields: dict[str, str]) -> dict[str, Any]:
    """Overwrite zh-CN translation narrative so zh-preferring clients see updates."""
    body = {
        "updates": [
            {
                "id": robot_id,
                "locale": "zh-CN",
                "source_hash": f"unitree-qa-force-{robot_id}-20260718",
                "translated_fields": fields,
            }
        ]
    }
    resp = client._session.post(
        client._url("robots/robots/translation-sync/?force=1"),
        json=body,
        timeout=client.timeout,
    )
    resp.raise_for_status()
    return resp.json()


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix Unitree (109) QA remainders")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--only", type=int, nargs="*", help="Limit to robot ids")
    parser.add_argument("--created-by-id", type=int, default=1)
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    client = ResearchApiClient()
    targets = {
        rid: fix
        for rid, fix in FIXES.items()
        if not args.only or rid in args.only
    }
    url_only = {
        rid: url
        for rid, url in URL_ONLY.items()
        if not args.only or rid in args.only
    }

    plan = []
    for rid, fix in targets.items():
        robot = client._get(f"robots/robots/{rid}/")
        row = build_row(robot, fix)
        narrative = {k: row[k] for k in NARRATIVE_KEYS if row.get(k)}
        plan.append(
            {
                "id": rid,
                "name": robot.get("name"),
                "url": row.get("url"),
                "narrative_keys": sorted(narrative),
                "specs": fix.get("specs") or {},
                "row": row,
                "narrative": narrative,
            }
        )
        time.sleep(0.15)

    report_path = (
        _RESEARCH_DIR / "staging" / "reports" / "unitree_fix_plan.json"
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(
            {
                "narrative_fixes": [
                    {
                        "id": p["id"],
                        "name": p["name"],
                        "url": p["url"],
                        "narrative_keys": p["narrative_keys"],
                        "specs": p["specs"],
                    }
                    for p in plan
                ],
                "url_only": url_only,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"plan {len(plan)} narrative + {len(url_only)} url-only → {report_path}")
    for p in plan:
        print(f"  {p['id']} {p['name']} narrative={p['narrative_keys']} specs={list(p['specs'])}")
    for rid, url in url_only.items():
        print(f"  url-only {rid} → {url}")

    if not args.apply:
        print("dry-run only; pass --apply to write")
        return 0

    # 1) bulk force_overwrite one-at-a-time (preserve media/tags via filled row)
    for p in plan:
        result = client.bulk_import_robots(
            [p["row"]],
            update_existing=True,
            patch_existing=False,
            skip_company_update=True,
            created_by_id=args.created_by_id,
            status="pending_review",
        )
        print(
            f"bulk {p['id']}: updated={result.get('updated_count')} "
            f"errors={result.get('error_count')} warnings={result.get('warnings')}"
        )
        time.sleep(0.2)

    # 2) force-sync zh-CN translations for narrative
    for p in plan:
        if not p["narrative"]:
            continue
        sync = force_sync_zh(client, p["id"], p["narrative"])
        print(f"zh-sync {p['id']}: {sync}")
        time.sleep(0.2)

    # 3) typed specs via PATCH (bulk-import may park some in notes)
    for p in plan:
        specs = p["specs"]
        if not specs:
            continue
        patched = client._patch(f"robots/robots/{p['id']}/", specs)
        print(
            f"specs {p['id']}: weight_kg={patched.get('weight_kg')} "
            f"height_mm={patched.get('height_mm')} dof={patched.get('dof')} "
            f"payload_kg={patched.get('payload_kg')}"
        )
        time.sleep(0.2)

    # 4) URL-only surgical patches (no narrative overwrite)
    for rid, url in url_only.items():
        patched = client._patch(
            f"robots/robots/{rid}/",
            {"url": url, "website_url": url, "source_locale": "en"},
        )
        print(f"url {rid}: {patched.get('website_url') or patched.get('url')}")
        time.sleep(0.2)

    # Verify reads (zh overlay should now show English narrative)
    print("\n--- verify ---")
    verify_ids = [p["id"] for p in plan] + list(url_only)
    for rid in verify_ids:
        r = client._get(f"robots/robots/{rid}/")
        feats = (r.get("features") or "")[:80].replace("\n", " | ")
        print(
            f"{rid} resolved={r.get('resolved_language')} "
            f"w={r.get('weight_kg')} h={r.get('height_mm')} "
            f"url={r.get('website_url') or r.get('url')} "
            f"features={feats!r}"
        )
        time.sleep(0.1)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
