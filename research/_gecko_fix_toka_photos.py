"""Fix Gecko TOKA 4 / TOKA Flex heroes after stakeholder photo hold.

TOKA 4 (4947): replace face-forward Navy stills with robot-only DVIDS 7463870.
TOKA Flex (3578): robot-only Gizmos/OEM stills as primary; demote text marketing
graphic to gallery #3.

Usage:
  python _gecko_fix_toka_photos.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import boto3
import requests
from PIL import Image

_RESEARCH = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient
from import_staging import import_staging, resolve_created_by_id

COMPANY_SLUG = "gecko-robotics"
COMPANY_NAME = "Gecko Robotics"
US_ID = 20
AVAILABLE = 11
BUCKET = "cdn.robotaigeek.com"
CDN = "https://cdn.robotaigeek.com"
PREFIX = "research-staging/gecko"
SERVER = _RESEARCH.parents[1] / "robotaigeek-server"
QA = _RESEARCH / "staging" / "tmp" / "gecko-qa2"
OUT = _RESEARCH / "staging" / "tmp" / "gecko-photo-fix"
OUT.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (compatible; RobotAIGeekResearch/1.0)"}

# stamp keys so copy-media / CloudFront get new objects
STAMP = "20260720b"

FIXES = {
    4947: {
        "name": "Gecko Robotics TOKA 4",
        "model_name": "TOKA 4",
        "slug": "toka-4",
        "url": "https://www.geckorobotics.com/",
        "locals": [
            QA / "toka4-dvids-2000.jpg",  # DVIDS 7463870 — robot-only hull
        ],
        "purpose": "Magnetic ultrasonic thickness mapping of boilers, tanks, vessels, and hulls",
        "description": (
            "TOKA 4 is Gecko's magnetic wall-climbing ultrasonic inspection robot for "
            "boilers, tanks, pressure vessels, and ship hulls."
        ),
        "features": (
            "Press/aggregator specs (Robots HQ TOKA 4 table + PopSci/Navy deploy): "
            "magnetic-wheel wall climber for ferrous vertical/overhead/curved surfaces; "
            "ultrasonic thickness mapping 100,000+ readings/day; UT accuracy ±0.1 mm; "
            "scan ~0.15 m/s; ~12 kg; ~4 h battery; Cantilever cloud corrosion heatmaps. "
            "Used on U.S. Navy hull inspections (REPTX 2022). Soft: OEM PDP retired into "
            "Cantilever RaaS. Photo fix 2026-07-20: primary is DVIDS 7463870 robot-only "
            "hull still (no faces); previous deploy stills with identifiable people removed."
        ),
        "weight_kg": 12.0,
        "speed": 0.54,
        "runtime_minutes": 240,
        "sources": [
            {
                "url": "https://www.dvidshub.net/image/7463870",
                "title": "U.S. Navy DVIDS — TOKA on hull (7463870)",
            },
            {
                "url": "https://www.popsci.com/technology/gecko-robotics-machine-inspects-navy-ships/",
                "title": "Popular Science — Navy TOKA 4 hull inspection",
            },
            {"url": "https://www.geckorobotics.com/", "title": "Gecko Robotics home"},
        ],
    },
    3578: {
        "name": "Gecko Robotics TOKA Flex",
        "model_name": "TOKA Flex",
        "slug": "toka-flex",
        "url": "https://resources.geckorobotics.com/toka-flex",
        "locals": [
            QA / "flex-gizmos.jpg",  # robot-only pipe close-up — new primary
            QA / "scrubber.jpg",  # OEM CDN tank interior — gallery
            QA / "cur-toka-flex-0-20260720.jpg",  # text marketing — demoted gallery
        ],
        "purpose": "Maneuverable UT inspection of small-diameter piping and elbows at height",
        "description": (
            "TOKA Flex is Gecko Robotics' piping-focused magnetic crawler for NDT of "
            "small-diameter lines, elbows, and elevated process piping."
        ),
        "features": (
            "OEM press (Inspectioneering / Gecko 2021-03-31): most maneuverable TOKA — "
            "independent suspension/drive on 4 permanent-magnetic wheels; adapts flat to "
            "pipes down to 6\" diameter; navigates elbows, ⅜\" obstacles, 180° turns; "
            "12 single-channel UT probes at 1\" spacing (optional 18 @ ¼\"); >30 sq ft/min "
            "coverage; heat-hardened to 275°F; climb/crawl up to 75' from operators; "
            "RUG A/B/C-scan via Gecko Portal. Soft: curb weight 18.1 kg retained from "
            "prior research (not re-cited on current OEM site). Photo fix 2026-07-20: "
            "primary is robot-only pipe close-up; text marketing graphic demoted to gallery."
        ),
        "weight_kg": 18.1,
        "speed": 0.549,
        "runtime_minutes": None,
        "sources": [
            {
                "url": "https://www.roboticgizmos.com/toka-flex-pipe-inspection-robot/",
                "title": "Robotic Gizmos — TOKA Flex pipe inspection",
            },
            {
                "url": "https://inspectioneering.com/news/2021-03-31/9580/gecko-robotics-unveils-latest-inspection-robot-the-toka-flex",
                "title": "Inspectioneering — TOKA Flex unveil (Gecko press)",
            },
            {
                "url": "https://resources.geckorobotics.com/toka-flex",
                "title": "Gecko resources — TOKA Flex",
            },
        ],
    },
}


def _load_aws() -> None:
    env = SERVER / ".env"
    if not env.is_file():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        if "=" not in line or line.strip().startswith("#"):
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if " #" in v:
            v = v.split(" #", 1)[0].strip()
        if k.startswith("AWS_") or not str(os.environ.get(k) or "").strip():
            os.environ[k] = v


def s3_client():
    _load_aws()
    return boto3.client(
        "s3",
        region_name=os.environ.get("AWS_S3_REGION_NAME") or "ap-southeast-1",
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
    )


def upload_jpg(s3c, src: Path, key: str) -> str:
    local = OUT / Path(key).name
    Image.open(src).convert("RGB").save(local, quality=92, optimize=True)
    body = local.read_bytes()
    s3c.put_object(
        Bucket=BUCKET,
        Key=key,
        Body=body,
        ContentType="image/jpeg",
        CacheControl="public, max-age=31536000",
    )
    cdn = f"{CDN}/{key}"
    for _ in range(20):
        r = requests.get(cdn, headers=UA, timeout=30)
        if r.status_code == 200 and len(r.content) > 2000 and r.content[:3] == b"\xff\xd8\xff":
            print("OK", cdn)
            return cdn
        time.sleep(0.4)
    raise RuntimeError(f"CDN verify failed {cdn}")


def copy_media(rid: int) -> str:
    secret = os.environ.get("INTERNAL_API_SECRET", "").strip()
    if not secret and (SERVER / ".env").is_file():
        for line in (SERVER / ".env").read_text(encoding="utf-8").splitlines():
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
                return f"ok {resp.text[:120]}"
            if resp.status_code not in (500, 502, 503, 504):
                return f"HTTP {resp.status_code} {resp.text[:80]}"
        except requests.RequestException:
            pass
        time.sleep(2**attempt)
    return "fail"


def main() -> int:
    s3c = s3_client()
    api = ResearchApiClient()
    staging = _RESEARCH / "staging" / "robots" / COMPANY_SLUG
    staging.mkdir(parents=True, exist_ok=True)

    for rid, spec in FIXES.items():
        urls: list[str] = []
        for i, src in enumerate(spec["locals"]):
            if not src.is_file():
                print("MISSING", src)
                return 1
            key = f"{PREFIX}/{spec['slug']}-{i}-{STAMP}.jpg"
            urls.append(upload_jpg(s3c, src, key))

        notes = (
            f"[AI Research] Photo fix {STAMP}: "
            + (
                "TOKA 4 primary → DVIDS 7463870 robot-only hull (no faces)."
                if rid == 4947
                else "TOKA Flex primary → robot-only pipe still; text marketing demoted to gallery."
            )
        )
        row = {
            "id": rid,
            "name": spec["name"],
            "model_name": spec["model_name"],
            "company_slug": COMPANY_SLUG,
            "company_name": COMPANY_NAME,
            "manufacturer_country_code": "US",
            "manufacturer_country_codes": "US",
            "description": spec["description"],
            "purpose": spec["purpose"],
            "features": spec["features"],
            "url": spec["url"],
            "image": urls[0],
            "images": urls,
            "source_locale": "en",
            "availability_status": AVAILABLE,
            "family_key": "gecko:toka",
            "family_name": "TOKA",
            "family_url": "https://www.geckorobotics.com/",
            "product_url_scope": "exact_variant",
            "movement_type_keys": "wheeled",
            "category_slugs": "industrial-robots",
            "use_keys": "inspection|monitoring",
            "industry_keys": "defence|energy|oil-gas|manufacturing",
            "weight_kg": spec["weight_kg"],
            "speed": spec["speed"],
            "runtime_minutes": spec["runtime_minutes"],
            "notes": notes,
            "research_notes": notes,
            "sources": [
                {"url": s["url"], "type": "website", "title": s["title"]} for s in spec["sources"]
            ],
            "information_source_urls": [s["url"] for s in spec["sources"]],
            "tags": (
                ["Cantilever", "Gecko", "Inspection", "Magnetic", "NDT", "TOKA", "USA", "UT", "Wall-Climbing"]
                + ([spec["model_name"]] if spec["model_name"] not in ("TOKA 4", "TOKA Flex") else [spec["model_name"]])
            ),
        }
        path = staging / f"{spec['slug']}-photo-fix.json"
        path.write_text(json.dumps(row, indent=2, ensure_ascii=False), encoding="utf-8")
        print(
            "import",
            rid,
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
        api._patch(
            f"robots/robots/{rid}/",
            {
                "manufacturer_countries": [US_ID],
                "manufacturer_country_ref": US_ID,
                "availability_status": AVAILABLE,
                "image": urls[0],
                "s3_image": None,
                "weight_kg": spec["weight_kg"],
                "speed": spec["speed"],
                "runtime_minutes": spec["runtime_minutes"],
                "family_key": "gecko:toka",
                "family_name": "TOKA",
                "family_url": "https://www.geckorobotics.com/",
                "notes": notes,
            },
        )
        print("copy-media", rid, copy_media(rid))
        after = api._get(f"robots/robots/{rid}/")
        img = after.get("image") or ""
        r = requests.get(img, headers=UA, timeout=30)
        photos = after.get("photos") or []
        print(
            "verify",
            rid,
            after.get("name"),
            "status",
            after.get("status"),
            "primary",
            r.status_code,
            len(r.content),
            "photos",
            len(photos),
            "img",
            img[-60:],
        )
        for i, p in enumerate(photos[:5]):
            u = p.get("url") if isinstance(p, dict) else str(p)
            prim = p.get("is_primary") if isinstance(p, dict) else None
            print(f"  photo[{i}] primary={prim} {(u or '')[-70:]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
