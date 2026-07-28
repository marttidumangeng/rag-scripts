"""Lumos Robotics (70) full soft enrich — 5 pending platforms.

OEM: https://www.lumosbot.tech/ (China / Shenzhen). Specs from live product PDPs
2026-07-20. Heroes already owned CDN for 4/5; LUS 2 (5291) refreshes from OEM
front.webp (CDN was a thin 32 KB compress).

Usage:
  python discover_lumos_robots.py
  python discover_lumos_robots.py --apply
  python discover_lumos_robots.py --apply --copy-media
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import boto3
import requests

_RESEARCH = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient
from import_staging import import_staging, resolve_created_by_id

COMPANY_ID = 70
COMPANY_SLUG = "lumos-robotics"
COMPANY_NAME = "Lumos Robotics"
CN_ID = 3
AVAILABLE = 11
SERVER = _RESEARCH.parents[1] / "robotaigeek-server"
BUCKET = "cdn.robotaigeek.com"
CDN = "https://cdn.robotaigeek.com"
UA = {"User-Agent": "Mozilla/5.0"}
REPORT = _RESEARCH / "staging" / "reports" / "lumos-70-enrich.json"

# OEM front renders (product-specific)
OEM_FRONTS = {
    5290: "https://www.lumosbot.tech/images/products/lud/front.webp",
    5291: "https://www.lumosbot.tech/images/products/lus2/front.webp",
    5292: "https://www.lumosbot.tech/images/products/mos/front.webp",
    5293: "https://www.lumosbot.tech/images/products/luxiaoming/front.webp",
    5294: "https://www.lumosbot.tech/images/products/touch/front.webp",
}

PRODUCTS: list[dict[str, Any]] = [
    {
        "id": 5290,
        "name": "Lumos LUD",
        "model_name": "LUD",
        "variant_code": "LUD",
        "url": "https://www.lumosbot.tech/products/lud",
        "family_key": "lumos:lud",
        "family_name": "LUD",
        "family_url": "https://www.lumosbot.tech/products/lud",
        "product_url_scope": "exact_variant",
        "refresh_hero": False,  # CDN matches OEM front bytes class
        "length_mm": 920.0,
        "width_mm": 500.0,
        "height_mm": 570.0,
        "weight_kg": 45.0,
        "payload_kg": 50.0,
        "dof": 12,
        "speed": 28.8,  # max wheel-foot 8 m/s
        "voltage": "57.6 V",
        "battery_capacity": "20 Ah × 2",
        "runtime_minutes": 480,  # unloaded ≥8 h
        "purpose": (
            "Complex-terrain outdoor and industrial mobility\n"
            "Inspection and payload tasks across slopes, stairs, and obstacles"
        ),
        "description": (
            "Lumos LUD is a wheeled-legged robot platform for challenging terrain "
            "and real-world tasks. It combines wheel–leg mode switching, RL-based "
            "self-balancing with self-righting, dual Wi-Fi/RF links (RF to ~1500 m), "
            "and multimodal perception (dual Livox Mid-360 + RealSense D435i) with "
            "a 50 kg working payload and ≤45 kg all-up weight."
        ),
        "features": (
            "OEM lumosbot.tech/products/lud: standing 920×500×570 mm; ≤45 kg incl. "
            "battery; 12 DoF (per leg 3+1 wheel-foot); stable working payload 50 kg; "
            "unloaded runtime ≥8 h / full load ≥4 h; max walking 4 m/s, max wheel-foot "
            "8 m/s; climb ±45°; obstacle/gap crossing 80 cm; stair step 22 cm; "
            "battery 20 Ah×2 @ 57.6 V hot-swap; dual Livox Mid-360 + RealSense D435i; "
            "Wi-Fi + RF to 1500 m; -5°C to 50°C."
        ),
        "use_keys": "inspection|material-handling",
        "industry_keys": "industrial|logistics|research",
        "category_slugs": "mobile-robots|legged-robots",
        "movement_keys": "wheeled|legged",
        "tags": [
            "Lumos",
            "LUD",
            "Wheeled-Legged",
            "Quadruped",
            "China",
            "Inspection",
            "AMR",
        ],
    },
    {
        "id": 5291,
        "name": "Lumos LUS 2",
        "model_name": "LUS 2",
        "variant_code": "LUS-2",
        "url": "https://www.lumosbot.tech/products/lus2",
        "family_key": "lumos:lus",
        "family_name": "LUS",
        "family_url": "https://www.lumosbot.tech/products/lus2",
        "product_url_scope": "exact_variant",
        "refresh_hero": True,  # replace thin CDN compress with OEM front.webp
        "height_mm": 1600.0,
        "weight_kg": 57.0,
        "payload_kg": 3.0,  # single-arm
        "dof": 28,
        "joint_torque_nm": 360.0,
        "runtime_minutes": 120,
        "release_year": 2025,
        "voltage": "54 V",
        "battery_capacity": "10 Ah",
        "purpose": (
            "Research and education humanoid platform\n"
            "Commercial interaction, guidance, and entertainment motion"
        ),
        "description": (
            "Lumos LUS 2 is a full-size bipedal humanoid (~160 cm, 57 kg, 28 DoF) "
            "for research, education, and commercial applications. It features "
            "straight-leg gait, up to 360 N·m joint torque, 7-DoF arms with ~3 kg "
            "payload, multi-sensor fusion (3D LiDAR + binocular depth), and the "
            "OEM-claimed 1-second recovery to standing."
        ),
        "features": (
            "OEM lumosbot.tech/products/lus2: height 160 cm; weight 57 kg; aluminum "
            "alloy; 28 joint DoF (leg 6 / waist 1 / arm 7); max joint torque 360 N·m; "
            "single-arm payload 3 kg; arm weight 5.5 kg excl. hand; forearm+upper arm "
            "520 mm; lower+thigh 800 mm; 54 V / 10 Ah ternary Li; Jetson AGX Orin "
            "275 TOPS; 3D LiDAR + binocular depth; 4-mic array; ~2 h battery life; "
            "OTA + secondary development; open architecture."
        ),
        "use_keys": "research|education|entertainment|helping",
        "industry_keys": "research|education|entertainment|consumer",
        "category_slugs": "humanoid-robots",
        "movement_keys": "legged",
        "tags": [
            "Lumos",
            "LUS 2",
            "Humanoid",
            "Bipedal",
            "China",
            "Research",
            "Education",
        ],
    },
    {
        "id": 5292,
        "name": "Lumos MOS 2",
        "model_name": "MOS 2",
        "variant_code": "MOS-2",
        "url": "https://www.lumosbot.tech/products/mos",
        "family_key": "lumos:mos",
        "family_name": "MOS",
        "family_url": "https://www.lumosbot.tech/products/mos",
        "product_url_scope": "exact_variant",
        "refresh_hero": False,
        "height_mm": 1650.0,
        "length_mm": 735.0,
        "width_mm": 700.0,
        # base height 300 mm is chassis only; overall height 1650
        "weight_kg": 350.0,
        "payload_kg": 50.0,  # dual-arm max; rated 30 kg
        "dof": 22,
        "speed": 5.4,  # ≤1.5 m/s
        "joint_torque_nm": 380.0,
        "voltage": "48 V",
        "battery_capacity": "19.5 Ah × 2 LiFePO4",
        "release_year": 2026,
        "purpose": (
            "Heavy-load industrial material handling\n"
            "Hazardous-environment teleoperation and flexible inspection"
        ),
        "description": (
            "Lumos MOS 2 is a heavy-duty wheeled mobile manipulator (~1650 mm, "
            "≤350 kg) with 7-DoF dual arms (rated 30 kg / max 50 kg dual-arm "
            "payload), omnidirectional swerve base, hot-swappable dual 19.5 Ah "
            "LiFePO4 packs, and up to 275 TOPS edge compute for industrial "
            "handling, teleoperation, and inspection."
        ),
        "features": (
            "OEM lumosbot.tech/products/mos: height 1650 mm; ≤350 kg incl. battery; "
            "base 735×700×300 mm; 22 DoF; dual-arm rated 30 kg / max 50 kg; max "
            "joint torque 380 N·m; travel ≤1.5 m/s; lift travel 750 mm; omnidirectional "
            "swerve; up to 3× 3D LiDAR + 6-axis F/T on both arms; dual 19.5 Ah "
            "LiFePO4 hot-swap @ 48 V; 275 TOPS; VR teleop ready; ROS/SDK; 0–45°C."
        ),
        "use_keys": "material-handling|inspection",
        "industry_keys": "industrial|logistics|manufacturing",
        "category_slugs": "mobile-robots|manipulator-robots",
        "movement_keys": "wheeled",
        "tags": [
            "Lumos",
            "MOS 2",
            "Mobile Manipulator",
            "Dual Arm",
            "Industrial",
            "China",
            "Wheeled",
        ],
    },
    {
        "id": 5293,
        "name": "Lumos NIX S3",
        "model_name": "NIX S3",
        "variant_code": "NIX-S3",
        "url": "https://www.lumosbot.tech/products/luxiaoming",
        "family_key": "lumos:nix",
        "family_name": "NIX",
        "family_url": "https://www.lumosbot.tech/products/luxiaoming",
        "product_url_scope": "exact_variant",
        "refresh_hero": False,
        "length_mm": 892.0,
        "width_mm": 445.0,
        "height_mm": 890.0,  # OEM height 89 cm; footprint dims 892×445×176
        "weight_kg": 25.41,
        "payload_kg": 3.0,
        "dof": 21,
        "joint_torque_nm": 102.0,
        "battery_wh": 282.0,
        "runtime_minutes": 120,
        "purpose": (
            "Culture and tourism greeting and interactive performance\n"
            "Companionship showcase and brand entertainment"
        ),
        "description": (
            "Lumos NIX S3 is an ~89 cm AI mini bipedal humanoid (25.41 kg, 21 DoF) "
            "for agile motion and intelligent companionship. It offers black/white "
            "color options, peak joint torque to 102 N·m, ~3 kg payload, 282 Wh "
            "battery (~2 h), and Professional/Education editions with dance and "
            "SDK options."
        ),
        "features": (
            "OEM lumosbot.tech/products/luxiaoming: dims 892×445×176 mm; height 89 cm; "
            "25.41 kg incl. battery; 21 DoF (arm 4 / waist 1 / leg 6); peak joint "
            "torque 102 N·m; max payload 3 kg; battery 282 Wh / ~2 h; RGB camera; "
            "4-mic + speaker + mini wireless mic; Wi-Fi/4G/Bluetooth; RK3588 compute; "
            "RJ45; OTA + secondary development; Pro + Education editions."
        ),
        "use_keys": "entertainment|helping|education",
        "industry_keys": "entertainment|consumer|education|hospitality",
        "category_slugs": "humanoid-robots|service-robots",
        "movement_keys": "legged",
        "tags": [
            "Lumos",
            "NIX S3",
            "Humanoid",
            "Mini",
            "Companionship",
            "China",
            "Entertainment",
        ],
    },
    {
        "id": 5294,
        "name": "Lumos Touch R1",
        "model_name": "Touch R1",
        "variant_code": "Touch-R1",
        "url": "https://www.lumosbot.tech/products/touch",
        "family_key": "lumos:touch",
        "family_name": "Touch",
        "family_url": "https://www.lumosbot.tech/products/touch",
        "product_url_scope": "exact_variant",
        "refresh_hero": False,
        "payload_kg": 1.5,
        "reach_mm": 657.0,
        "repeatability_mm": 0.1,
        "dof": 6,
        "voltage": "DC 24 V",
        "purpose": (
            "Embodied-AI data collection and policy deployment validation\n"
            "Tabletop precision handling, assembly, and sorting"
        ),
        "description": (
            "Lumos Touch R1 is a 6-DoF desktop research arm designed to pair with "
            "FastUMI Pro for imitation/RL/VLA workflows. It offers ~1.5 kg payload, "
            "max reach 657 mm, ±0.1 mm repeatability, CAN control with drag "
            "teaching, and ROS/ROS2 SDK support."
        ),
        "features": (
            "OEM lumosbot.tech/products/touch: 6-DoF integrated servo joints; "
            "payload 1.5 kg; reach max 657 mm; repeatability ±0.1 mm; standard "
            "gripper rated 130 N; DC 24 V; CAN 1 Mbps + CAN-USB; drag teaching / "
            "offline trajectory / API; Ubuntu 20.04–24.04 + Python 3.10 + ROS/ROS2 "
            "SDK; upright/inverted/side mount; -20°C to 50°C; noise <60 dB."
        ),
        "use_keys": "research|assembly|material-handling",
        "industry_keys": "research|education|industrial",
        "category_slugs": "robotic-arms|manipulator-robots",
        "movement_keys": "fixed",
        "tags": [
            "Lumos",
            "Touch R1",
            "Robotic Arm",
            "6-DoF",
            "Research",
            "China",
            "Desktop",
        ],
    },
]


def _load_aws() -> None:
    for line in (SERVER / ".env").read_text(encoding="utf-8").splitlines():
        if "=" not in line or line.strip().startswith("#"):
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if " #" in v:
            v = v.split(" #", 1)[0].strip()
        if k.startswith("AWS_") or not str(os.environ.get(k) or "").strip():
            os.environ[k] = v


def _internal_secret() -> str:
    secret = os.environ.get("INTERNAL_API_SECRET", "").strip()
    if secret:
        return secret
    for line in (SERVER / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("INTERNAL_API_SECRET="):
            return line.split("=", 1)[1].strip()
    return ""


def copy_media(rid: int) -> dict[str, Any]:
    api = (
        os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/").replace("/api/v1", "")
        or "https://ragadmin.robotaigeek.com"
    )
    url = f"{api}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/?force=1"
    resp = requests.post(url, headers={"X-Internal-Secret": _internal_secret()}, timeout=180)
    return {"status": resp.status_code, "body": (resp.text or "")[:200]}


def upload_oem_hero(rid: int) -> str:
    _load_aws()
    src = OEM_FRONTS[rid]
    raw = requests.get(src, headers=UA, timeout=60).content
    assert len(raw) > 40_000, f"{rid} OEM too small {len(raw)}"
    digest = hashlib.sha1(raw).hexdigest()[:10]
    key = f"research-staging/lumos/{rid}-front-{digest}-20260720.webp"
    s3 = boto3.client(
        "s3",
        aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
        region_name=os.environ.get("AWS_S3_REGION_NAME") or "ap-southeast-1",
    )
    s3.put_object(
        Bucket=BUCKET,
        Key=key,
        Body=raw,
        ContentType="image/webp",
        CacheControl="public, max-age=31536000",
    )
    cdn = f"{CDN}/{key}"
    for _ in range(30):
        r = requests.get(cdn, timeout=30)
        if r.status_code == 200 and len(r.content) > 40_000:
            print("uploaded", rid, len(r.content), cdn)
            return cdn
        time.sleep(0.4)
    raise RuntimeError(cdn)


def taxonomy_ids(client: ResearchApiClient) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {"uses": {}, "industries": {}, "movement": {}}
    try:
        for u in client._get("robots/uses/") or []:
            if isinstance(u, dict) and u.get("key"):
                out["uses"][u["key"]] = u["id"]
    except Exception:
        pass
    try:
        for u in client._get("robots/industries/") or []:
            if isinstance(u, dict) and u.get("key"):
                out["industries"][u["key"]] = u["id"]
    except Exception:
        pass
    try:
        for u in client._get("robots/movement-types/") or []:
            if isinstance(u, dict) and u.get("key"):
                out["movement"][u["key"]] = u["id"]
    except Exception:
        pass
    return out


def map_keys(tax: dict[str, dict[str, int]], kind: str, pipe: str) -> list[int]:
    ids = []
    for k in pipe.split("|"):
        k = k.strip()
        if k and k in tax.get(kind, {}):
            ids.append(tax[kind][k])
    return ids


def force_en(client: ResearchApiClient, rid: int, row: dict[str, Any]) -> None:
    try:
        client._patch(
            f"robots/robots/{rid}/translation-sync/?force=1",
            {
                "description": row["description"],
                "purpose": row["purpose"],
                "features": row["features"],
                "name": row["name"],
            },
        )
    except Exception as e:
        print("  translation-sync warn", rid, e)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--copy-media", action="store_true")
    args = ap.parse_args()

    client = ResearchApiClient()
    tax = taxonomy_ids(client)
    staging = _RESEARCH / "staging" / "robots" / COMPANY_SLUG
    staging.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    for spec in PRODUCTS:
        rid = spec["id"]
        existing = client._get(f"robots/robots/{rid}/")
        img = existing.get("image") or existing.get("s3_image") or ""
        hero = img
        if args.apply and spec.get("refresh_hero"):
            hero = upload_oem_hero(rid)

        notes = (
            f"[AI Research] Lumos enrich 2026-07-20: China; family {spec['family_key']}; "
            f"Available; OEM PDP specs from {spec['url']}."
        )
        sources = [
            {"url": spec["url"], "type": "website", "title": f"OEM {spec['name']}"},
            {"url": "https://www.lumosbot.tech/", "type": "website", "title": "Lumos home"},
            {"url": "https://www.lumosbot.tech/about/", "type": "website", "title": "About"},
        ]
        row: dict[str, Any] = {
            "id": rid,
            "name": spec["name"],
            "model_name": spec["model_name"],
            "variant_code": spec["variant_code"],
            "company_slug": COMPANY_SLUG,
            "company_name": COMPANY_NAME,
            "company_id": COMPANY_ID,
            "manufacturer_country_code": "CN",
            "manufacturer_country_codes": "CN",
            "description": spec["description"],
            "purpose": spec["purpose"],
            "features": spec["features"],
            "url": spec["url"],
            "image": hero,
            "images": [hero] if hero else [],
            "source_locale": "en",
            "availability_status": AVAILABLE,
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
            "sources": sources,
            "information_source_urls": [s["url"] for s in sources],
        }
        for k in (
            "length_mm",
            "width_mm",
            "height_mm",
            "weight_kg",
            "payload_kg",
            "dof",
            "speed",
            "joint_torque_nm",
            "reach_mm",
            "repeatability_mm",
            "runtime_minutes",
            "battery_wh",
            "release_year",
            "voltage",
            "battery_capacity",
        ):
            if spec.get(k) is not None:
                row[k] = spec[k]

        path = staging / f"{rid}-{spec['variant_code'].lower()}.json"
        path.write_text(json.dumps(row, indent=2, ensure_ascii=False), encoding="utf-8")
        print("staged", path.name, "hero_refresh=" + str(bool(spec.get("refresh_hero"))))

        entry: dict[str, Any] = {"id": rid, "staged": str(path), "hero": (hero or "")[:100]}
        if not args.apply:
            results.append(entry)
            continue

        print(
            "import",
            rid,
            import_staging(
                path,
                dry_run=False,
                patch=True,
                force_overwrite=True,
                replace_media=bool(spec.get("refresh_hero")),
                status="pending_review",
                created_by_id=resolve_created_by_id(1),
                skip_company_update=True,
            ),
        )
        body: dict[str, Any] = {
            "manufacturer_countries": [CN_ID],
            "manufacturer_country_ref": CN_ID,
            "availability_status": AVAILABLE,
            "description": spec["description"],
            "features": spec["features"],
            "purpose": spec["purpose"],
            "name": spec["name"],
            "model_name": spec["model_name"],
            "variant_code": spec["variant_code"],
            "family_key": spec["family_key"],
            "family_name": spec["family_name"],
            "family_url": spec["family_url"],
            "product_url_scope": spec["product_url_scope"],
            "url": spec["url"],
            "notes": notes,
            "tags": spec["tags"],
            "information_source_urls": [s["url"] for s in sources],
            "uses": map_keys(tax, "uses", spec["use_keys"]),
            "industries": map_keys(tax, "industries", spec["industry_keys"]),
            "movement_types": map_keys(tax, "movement", spec["movement_keys"]),
        }
        if hero and spec.get("refresh_hero"):
            body["image"] = hero
            body["s3_image"] = None
        for k in (
            "length_mm",
            "width_mm",
            "height_mm",
            "weight_kg",
            "payload_kg",
            "dof",
            "speed",
            "joint_torque_nm",
            "reach_mm",
            "repeatability_mm",
            "runtime_minutes",
            "battery_wh",
            "release_year",
            "voltage",
            "battery_capacity",
        ):
            if spec.get(k) is not None:
                body[k] = spec[k]
        client._patch(f"robots/robots/{rid}/", body)
        force_en(client, rid, row)
        if args.copy_media and spec.get("refresh_hero"):
            entry["copy_media"] = copy_media(rid)
            print("  copy-media", entry["copy_media"])
        # Reassert availability after import wipe risk
        client._patch(
            f"robots/robots/{rid}/",
            {"availability_status": AVAILABLE, "manufacturer_countries": [CN_ID]},
        )
        after = client._get(f"robots/robots/{rid}/")
        entry["after"] = {
            "family_key": after.get("family_key"),
            "countries": bool(after.get("manufacturer_countries")),
            "avail": after.get("availability_status"),
            "payload": after.get("payload_kg"),
            "weight": after.get("weight_kg"),
            "dof": after.get("dof"),
            "speed": after.get("speed"),
            "feat_len": len(after.get("features") or ""),
            "img": (after.get("s3_image") or after.get("image") or "")[:90],
        }
        print("  after", entry["after"])
        results.append(entry)

    REPORT.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print("report", REPORT, "apply=", args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
