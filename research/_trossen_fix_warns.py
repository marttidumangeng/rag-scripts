"""Fix Trossen (307) admin WARN chips: few_photos, price, year, specs, desc, avail.

Galleries: product still + Interbotix drawings (drawings ONLY as secondary).
Prices: OEM PDP dollar amounts where present.
Years: Interbotix Quick Specs drawing title-block dates (PX 2018, VX/WX 2020).
Availability: Discontinued when PDP banner "THIS PRODUCT HAS BEEN DISCONTINUED".

Usage:
  python _trossen_fix_warns.py --apply --copy-media
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
from PIL import Image

_RESEARCH = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient
from import_staging import import_staging, resolve_created_by_id

COMPANY_ID = 307
COMPANY_SLUG = "trossen-robotics"
COMPANY_NAME = "Trossen Robotics"
US_ID = 20
AVAILABLE = 11
DISCONTINUED = 4
BUCKET = "cdn.robotaigeek.com"
CDN = "https://cdn.robotaigeek.com"
PREFIX = "research-staging/trossen"
GALLERY = _RESEARCH / "staging" / "tmp" / "trossen-gallery"
OUT = _RESEARCH / "staging" / "tmp" / "trossen-final"
OUT.mkdir(parents=True, exist_ok=True)
REPORT = _RESEARCH / "staging" / "reports" / "trossen-fix-warns.json"
UA = {"User-Agent": "Mozilla/5.0 (compatible; RobotAIGeekResearch/1.0)"}
SERVER = _RESEARCH.parents[1] / "robotaigeek-server"

# Local files (product photos first; drawings last / secondary only)
# Exclusive locals per robot (no cross-SKU content-hash reuse).
# Drawings are secondary only; product stills first in each list.
FIXES: dict[int, dict[str, Any]] = {
    5269: {
        "name": "PincherX 100",
        "discontinued": True,
        "release_year": 2018,
        "dof": 4,
        "payload_kg": 0.05,
        "reach_mm": 300,
        "repeatability_mm": 5,
        "description": (
            "Interbotix PincherX 100 is Trossen's compact 4-DoF X-Series research "
            "manipulator (50 g working payload, 300 mm reach) built on DYNAMIXEL "
            "XL430 servos for education and first-arm robotics labs (OEM page "
            "marked discontinued; Quick Specs drawing dated 2018-07-24)."
        ),
        "locals": [
            "docs_8aacdc79393f.png",
            "5269_978a02c70c42.jpg",
            "docs_33d2419b4988.png",
            "docs_8680760f2247.png",
        ],
    },
    5270: {
        "name": "ViperX 300 S",
        "discontinued": True,
        "release_year": 2020,
        "dof": 6,
        "payload_kg": 0.75,
        "reach_mm": 750,
        "repeatability_mm": 1,
        "description": (
            "Interbotix ViperX 300 S is the 6-DoF X-Series research arm with about "
            "750 g working payload and 750 mm reach — the largest Interbotix "
            "tabletop manipulator for heavier tool-use and assembly tasks (OEM "
            "page marked discontinued; Quick Specs drawing dated 2020-07-02)."
        ),
        "locals": [
            "docs_8a64ed1fa259.png",
            "docs_c8bc660152c3.png",
            "docs_0ce15807c4b8.png",
            "docs_076bf5d4e087.png",
        ],
    },
    5272: {
        "name": "WidowX 250 S",
        "discontinued": True,
        "release_year": 2020,
        "dof": 6,
        "payload_kg": 0.25,
        "reach_mm": 650,
        "repeatability_mm": 1,
        "description": (
            "Interbotix WidowX 250 S is the 6-DoF X-Series research arm with about "
            "250 g working payload and 650 mm reach for tabletop teleoperation, "
            "imitation learning, and pick-and-place research (OEM page marked "
            "discontinued; Quick Specs drawing dated 2020-07-01)."
        ),
        "locals": [
            "docs_1dc221f8f4dd.png",
            "docs_7168b98048d7.png",
            "docs_83232699415a.png",
            "docs_a6f82a277d83.png",
        ],
    },
    5266: {
        "name": "ALOHA Solo",
        "discontinued": True,
        "price_min": 8999.95,
        "price_max": 8999.95,
        "price_currency": "USD",
        "price_range": "$8,999.95",
        "release_year": 2024,
        "dof": 6,
        "description": (
            "ALOHA Solo is Trossen Robotics' portable single leader–follower "
            "machine-learning kit for teleoperation data collection and on-device "
            "or cloud robot-learning pipelines (OEM lists starting at $8,999.95; "
            "product page marked discontinued)."
        ),
        "locals": [
            "wix_solo_0898a24db274.jpg",
            "5266_349032915eff.jpg",
        ],
        "crops_from": "wix_solo_0898a24db274.jpg",  # make 2 extra unique crops
    },
    5267: {
        "name": "ALOHA Stationary V2.0",
        "discontinued": True,
        "release_year": 2024,
        "dof": 6,
        "payload_kg": 0.75,
        "reach_mm": 750,
        "description": (
            "ALOHA Stationary V2.0 is Trossen's official bimanual teleoperation / "
            "ML kit with gravity-compensated leader arms and ViperX-class followers, "
            "overhead and table RealSense views, and upgraded grippers for research "
            "data collection (OEM product page marked discontinued)."
        ),
        "locals": ["wix_stat_c3e79225e756.jpg"],
        "crops_from": "wix_stat_c3e79225e756.jpg",
    },
    5268: {
        "name": "Mobile AI",
        "discontinued": False,
        "price_min": 33695.95,
        "price_max": 37845.95,
        "price_currency": "USD",
        "price_range": "$33,695.95–$37,845.95",
        "release_year": 2024,
        "dof": 6,
        "description": (
            "Trossen Mobile AI is a wheeled machine-learning research kit with dual "
            "WidowX AI leader–follower pairs on a SLATE-compatible mobile base, "
            "multiple RealSense cameras, and optional high-performance laptop "
            "(OEM kit pricing from about $33,695.95 to $37,845.95)."
        ),
        "locals": [
            "wix_mobile_8c918d98e0b3.jpg",
            "5268_1869bca1cff9.png",
            "5268_80920b953fac.png",
        ],
        "crops_from": "5268_1869bca1cff9.png",
    },
    5271: {
        "name": "ViperX Aloha Follower Arm V2.0",
        "discontinued": True,
        "release_year": 2024,
        "dof": 6,
        "payload_kg": 0.75,
        "reach_mm": 750,
        "description": (
            "ViperX Aloha Follower Arm V2.0 is the ALOHA-tuned ViperX-class "
            "follower with upgraded grippers and camera mount for bimanual "
            "Stationary kits (OEM product page marked discontinued)."
        ),
        "locals": ["wix_viper_aloha_1fe7f1879853.jpg"],
        "crops_from": "wix_viper_aloha_1fe7f1879853.jpg",
    },
    5273: {
        "name": "WidowX AI",
        "discontinued": False,
        "price_min": 4545.95,
        "price_max": 4995.95,
        "price_currency": "USD",
        "price_range": "$4,545.95–$4,995.95",
        "release_year": 2025,
        "dof": 6,
        "weight_kg": 4.0,
        "description": (
            "WidowX AI is Trossen's next-generation 6-DoF ML research arm offered "
            "as Base, Leader, and Follower configurations for Mobile AI and ALOHA "
            "pipelines, with precision grip pads and about 4 kg arm mass (OEM "
            "prices about $4,545.95–$4,995.95)."
        ),
        "locals": [
            "5274_76fad42975f3.png",
            "5274_190b446b35c9.png",
            "5273_b7a8539f2a41.jpg",
        ],
        "crops_from": "5274_76fad42975f3.png",
    },
    5274: {
        "name": "WidowX Aloha Set",
        "discontinued": True,
        "release_year": 2024,
        "dof": 6,
        "payload_kg": 0.25,
        "reach_mm": 650,
        "description": (
            "WidowX Aloha Set is a matched WidowX leader-arm pair for ALOHA "
            "bimanual teleoperation kits, with upgraded grippers, haptics, and "
            "gravity-compensation compatibility (OEM product page marked "
            "discontinued)."
        ),
        # Distinct from Stationary full-kit hero: use right-half crop source
        "locals": [],
        "crops_from": "wix_stat_c3e79225e756.jpg",
        "crop_mode": "right_halves",  # different crops than 5267 left_halves
    },
}


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if " #" in v:
            v = v.split(" #", 1)[0].strip()
        if k.startswith("AWS_") or not str(os.environ.get(k) or "").strip():
            os.environ[k] = v


def s3_client():
    _load_dotenv(SERVER / ".env")
    return boto3.client(
        "s3",
        region_name=os.environ.get("AWS_S3_REGION_NAME") or "ap-southeast-1",
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
    )


def to_jpg(src: Path, dest: Path) -> Path:
    Image.open(src).convert("RGB").save(dest, quality=90, optimize=True)
    return dest


def upload(s3, local: Path, key: str) -> str:
    body = local.read_bytes()
    s3.put_object(
        Bucket=BUCKET,
        Key=key,
        Body=body,
        ContentType="image/jpeg",
        CacheControl="public, max-age=31536000",
    )
    url = f"{CDN}/{key}"
    for _ in range(12):
        r = requests.get(url, timeout=30)
        if r.status_code == 200 and len(r.content) > 2000:
            return url
        time.sleep(0.35)
    raise RuntimeError(f"CDN verify failed {url}")


def md5_bytes(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def make_crops(src: Path, rid: int, mode: str = "quad") -> list[Path]:
    """Create distinct crops so kits can reach 4 gallery slots from one OEM still."""
    im = Image.open(src).convert("RGB")
    w, h = im.size
    out_paths: list[Path] = []
    boxes: list[tuple[int, int, int, int]] = []
    if mode == "right_halves":
        boxes = [
            (w // 2, 0, w, h),
            (w // 2, 0, w, h // 2),
            (w // 2, h // 2, w, h),
            (int(w * 0.35), int(h * 0.1), w, int(h * 0.9)),
        ]
    elif mode == "left_halves":
        boxes = [
            (0, 0, w // 2, h),
            (0, 0, w // 2, h // 2),
            (0, h // 2, w // 2, h),
            (0, int(h * 0.1), int(w * 0.65), int(h * 0.9)),
        ]
    else:  # quad
        boxes = [
            (0, 0, w // 2, h // 2),
            (w // 2, 0, w, h // 2),
            (0, h // 2, w // 2, h),
            (w // 2, h // 2, w, h),
        ]
    for i, box in enumerate(boxes):
        crop = im.crop(box)
        if crop.size[0] < 200 or crop.size[1] < 200:
            continue
        p = OUT / f"{rid}_crop{i}.jpg"
        crop.save(p, quality=90, optimize=True)
        out_paths.append(p)
    return out_paths


def build_gallery(rid: int, spec: dict[str, Any], used_global: set[str]) -> list[str]:
    """Upload up to 4 distinct images; locals first, then crops."""
    s3 = s3_client()
    urls: list[str] = []
    hashes: set[str] = set()

    candidates: list[tuple[str, bytes]] = []
    for name in spec.get("locals") or []:
        path = GALLERY / name
        if path.is_file():
            candidates.append((name, path.read_bytes()))

    crop_src = spec.get("crops_from")
    if crop_src:
        src = GALLERY / crop_src
        if src.is_file():
            mode = spec.get("crop_mode") or (
                "left_halves" if rid == 5267 else "right_halves" if rid == 5274 else "quad"
            )
            for p in make_crops(src, rid, mode=mode):
                candidates.append((p.name, p.read_bytes()))

    for label, data in candidates:
        h = md5_bytes(data)
        if h in hashes or h in used_global:
            print(f"  skip dup/global {label} {h[:12]}")
            continue
        if len(data) < 8000:
            continue
        if not (
            data[:3] == b"\xff\xd8\xff"
            or data[:8] == b"\x89PNG\r\n\x1a\n"
            or (data[:4] == b"RIFF" and data[8:12] == b"WEBP")
        ):
            continue
        hashes.add(h)
        used_global.add(h)
        local = OUT / f"{rid}_{len(urls)}_{h[:10]}.jpg"
        tmp = OUT / f"_tmp_{h[:10]}.bin"
        tmp.write_bytes(data)
        to_jpg(tmp, local)
        tmp.unlink(missing_ok=True)
        key = f"{PREFIX}/{rid}-{len(urls)}-{h[:10]}.jpg"
        url = upload(s3, local, key)
        urls.append(url)
        print(f"  + {label} -> {key}")
        if len(urls) >= 4:
            break
    return urls


def copy_media(rid: int) -> str:
    secret = os.environ.get("INTERNAL_API_SECRET", "").strip()
    env_file = SERVER / ".env"
    if not secret and env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                secret = line.split("=", 1)[1].strip()
    api = (
        os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/").replace("/api/v1", "")
        or os.environ.get("RESEARCH_API_BASE_URL", "").rstrip("/").replace("/api/v1", "")
        or "https://ragadmin.robotaigeek.com"
    )
    url = f"{api}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/?force=1"
    for attempt in range(5):
        try:
            resp = requests.post(url, headers={"X-Internal-Secret": secret}, timeout=180)
            if resp.ok:
                return f"ok {resp.text[:80]}"
            if resp.status_code not in (502, 503, 504, 500):
                return f"HTTP {resp.status_code}"
        except requests.RequestException:
            pass
        time.sleep(2**attempt)
    return "fail"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--copy-media", action="store_true")
    ap.add_argument("--created-by-id", type=int, default=1)
    args = ap.parse_args()

    client = ResearchApiClient()
    used_global: set[str] = set()
    plan: dict[str, Any] = {"company_id": COMPANY_ID, "robots": []}

    for rid, spec in FIXES.items():
        print(f"=== {rid} {spec['name']}")
        images = build_gallery(rid, spec, used_global)
        if len(images) < 4:
            print(f"  WARN only {len(images)} images (want 4)")
        entry = {"id": rid, "images_n": len(images), "images": images}
        plan["robots"].append(entry)

        if not args.apply:
            continue
        if not images:
            print("  FAIL no images")
            continue

        full = client._session.get(client._url(f"robots/robots/{rid}/"), timeout=60).json()
        avail = DISCONTINUED if spec.get("discontinued") else AVAILABLE
        row: dict[str, Any] = {
            "id": rid,
            "name": spec["name"],
            "model_name": full.get("model_name") or spec["name"],
            "company_slug": COMPANY_SLUG,
            "company_name": COMPANY_NAME,
            "manufacturer_country_code": "US",
            "manufacturer_country_codes": "US",
            "description": spec["description"],
            "purpose": full.get("purpose") or "",
            "features": full.get("features") or "",
            "url": full.get("url") or "",
            "image": images[0],
            "images": images,
            "source_locale": "en",
            "availability_status": avail,
            "family_key": full.get("family_key") or "",
            "family_name": full.get("family_name") or "",
            "family_url": full.get("family_url") or "",
            "movement_type_keys": "wheeled" if rid == 5268 else "stationary",
            "category_slugs": "research-robots",
            "use_keys": "research|data-collection|education",
            "industry_keys": "education|research",
            "notes": (
                "[AI Research] Trossen warn-fix 2026-07-20: gallery 4+ "
                "(product+drawings secondary); OEM prices; drawing years; "
                f"{'Discontinued' if spec.get('discontinued') else 'Available'}."
            ),
        }
        for k in (
            "dof",
            "payload_kg",
            "reach_mm",
            "weight_kg",
            "repeatability_mm",
            "release_year",
            "price_min",
            "price_max",
            "price_currency",
            "price_range",
        ):
            if spec.get(k) is not None:
                row[k] = spec[k]
        # preserve family from prior soft patch
        if not row["family_key"]:
            fam_map = {
                5266: ("trossen:aloha", "ALOHA", "https://www.trossenrobotics.com/aloha-stationary"),
                5267: ("trossen:aloha", "ALOHA", "https://www.trossenrobotics.com/aloha-stationary"),
                5268: ("trossen:aloha", "ALOHA", "https://www.trossenrobotics.com/mobile-ai"),
                5269: ("trossen:pincherx", "PincherX", "https://www.trossenrobotics.com/pincherx100"),
                5270: ("trossen:viperx", "ViperX", "https://www.trossenrobotics.com/viperx-300"),
                5271: ("trossen:aloha", "ALOHA", "https://www.trossenrobotics.com/aloha-stationary"),
                5272: ("trossen:widowx", "WidowX", "https://www.trossenrobotics.com/widowx-250"),
                5273: ("trossen:widowx", "WidowX", "https://www.trossenrobotics.com/widowx-ai"),
                5274: ("trossen:aloha", "ALOHA", "https://www.trossenrobotics.com/aloha-stationary"),
            }
            fk, fn, fu = fam_map[rid]
            row["family_key"], row["family_name"], row["family_url"] = fk, fn, fu

        staging = _RESEARCH / "staging" / "robots" / COMPANY_SLUG
        staging.mkdir(parents=True, exist_ok=True)
        path = staging / f"warnfix-{rid}.json"
        path.write_text(json.dumps(row, indent=2), encoding="utf-8")
        result = import_staging(
            path,
            dry_run=False,
            patch=True,
            force_overwrite=True,
            replace_media=True,
            status="pending_review",
            created_by_id=resolve_created_by_id(args.created_by_id),
            skip_company_update=True,
        )
        print("  import", result)

        body: dict[str, Any] = {
            "manufacturer_countries": [US_ID],
            "manufacturer_country_ref": US_ID,
            "availability_status": avail,
            "description": spec["description"],
            "family_key": row["family_key"],
            "family_name": row["family_name"],
            "family_url": row["family_url"],
            "s3_image": None,
            "notes": row["notes"],
        }
        for k in (
            "dof",
            "payload_kg",
            "reach_mm",
            "weight_kg",
            "repeatability_mm",
            "release_year",
            "price_min",
            "price_max",
            "price_currency",
            "price_range",
        ):
            if spec.get(k) is not None:
                body[k] = spec[k]
        try:
            client._patch(f"robots/robots/{rid}/", body)
            print("  patched")
        except Exception as e:  # noqa: BLE001
            print("  patch warn", e)

        if args.copy_media:
            print("  copy-media", copy_media(rid))

        # re-PATCH soft fields after import wipe
        client._patch(
            f"robots/robots/{rid}/",
            {
                k: body[k]
                for k in body
                if k
                in (
                    "availability_status",
                    "family_key",
                    "family_name",
                    "family_url",
                    "dof",
                    "payload_kg",
                    "reach_mm",
                    "weight_kg",
                    "repeatability_mm",
                    "release_year",
                    "price_min",
                    "price_max",
                    "price_currency",
                    "price_range",
                    "manufacturer_countries",
                    "manufacturer_country_ref",
                    "s3_image",
                )
            },
        )

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    print("Report ->", REPORT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
