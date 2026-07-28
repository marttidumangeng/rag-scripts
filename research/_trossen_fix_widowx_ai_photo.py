"""Fix WidowX AI (5273): primary CDN 403 + OEM typed specs from PDP."""
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

COMPANY_SLUG = "trossen-robotics"
COMPANY_NAME = "Trossen Robotics"
US_ID = 20
AVAILABLE = 11
BUCKET = "cdn.robotaigeek.com"
CDN = "https://cdn.robotaigeek.com"
PREFIX = "research-staging/trossen"
SRC = _RESEARCH / "staging" / "tmp" / "trossen-wxai"
GALLERY = _RESEARCH / "staging" / "tmp" / "trossen-gallery"
OUT = _RESEARCH / "staging" / "tmp" / "trossen-final"
OUT.mkdir(parents=True, exist_ok=True)
SERVER = _RESEARCH.parents[1] / "robotaigeek-server"
UA = {"User-Agent": "Mozilla/5.0"}

# OEM widowx-ai: payload 1.5kg, reach 700mm, span 1400mm, DoF 6, rep 1mm, weight 4kg
# Primary: branded arm-from-box still (dde06074f3b5)
LOCALS = [
    SRC / "dde06074f3b5.png",  # TROSSEN branded arm / box — primary
    GALLERY / "5274_76fad42975f3.png",  # leader-style arm (re-upload new key)
    GALLERY / "5274_190b446b35c9.png",
    SRC / "16b2e3c26849.png",  # alternate crop of box/arm
]


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


def s3():
    _load_dotenv(SERVER / ".env")
    return boto3.client(
        "s3",
        region_name=os.environ.get("AWS_S3_REGION_NAME") or "ap-southeast-1",
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
    )


def upload_jpg(client, src: Path, key: str) -> str:
    local = OUT / Path(key).name
    Image.open(src).convert("RGB").save(local, quality=92, optimize=True)
    body = local.read_bytes()
    client.put_object(
        Bucket=BUCKET,
        Key=key,
        Body=body,
        ContentType="image/jpeg",
        CacheControl="public, max-age=31536000",
    )
    url = f"{CDN}/{key}"
    for _ in range(15):
        r = requests.get(url, timeout=30)
        if r.status_code == 200 and len(r.content) > 2000 and r.content[:3] == b"\xff\xd8\xff":
            return url
        time.sleep(0.4)
    raise RuntimeError(f"CDN verify failed {url} last={r.status_code}")


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
                return f"ok {resp.text[:120]}"
            if resp.status_code not in (502, 503, 504, 500):
                return f"HTTP {resp.status_code}"
        except requests.RequestException:
            pass
        time.sleep(2**attempt)
    return "fail"


def main() -> int:
    client_s3 = s3()
    urls: list[str] = []
    for i, src in enumerate(LOCALS):
        if not src.is_file():
            print("MISSING", src)
            return 1
        key = f"{PREFIX}/widowx-ai-{i}-20260720.jpg"
        url = upload_jpg(client_s3, src, key)
        print("OK", src.name, url)
        urls.append(url)

    api = ResearchApiClient()
    full = api._session.get(api._url("robots/robots/5273/"), timeout=60).json()
    product_url = "https://www.trossenrobotics.com/widowx-ai"
    notes = (
        "[AI Research] WidowX AI photo fix 2026-07-20: replaced CDN-403 primary "
        "with OEM Wix arm-from-box still + distinct gallery; typed payload 1.5 kg / "
        "reach 700 mm / weight 4 kg / DoF 6 / repeatability 1 mm from OEM PDP."
    )
    description = (
        "WidowX AI is Trossen's next-generation 6-DoF ML research arm offered as "
        "Base, Leader, and Follower configurations for Mobile AI and ALOHA pipelines. "
        "OEM specs: 1.5 kg payload, 700 mm reach, 1400 mm span, 1 mm repeatability, "
        "about 4 kg arm mass; prices about $4,545.95–$4,995.95."
    )
    features = (
        "OEM trossenrobotics.com/widowx-ai: WidowX AI 6-DoF manipulator; working "
        "payload 1.5 kg; reach 700 mm; span 1400 mm; repeatability 1 mm; weight 4 kg. "
        "Configurations: Base ($4,545.95) precision grip + silicone pads; Leader "
        "($4,685.95) ambidextrous hand grip with sliding rail pinchers; Follower "
        "($4,995.95) precision grip + Intel RealSense D405 wrist camera. Supports "
        "Hugging Face LeRobot, ROS 2, MuJoCo, Gazebo. Soft: Available."
    )
    row = {
        "id": 5273,
        "name": "WidowX AI",
        "model_name": "WidowX AI",
        "variant_code": "WX-AI",
        "variant_label": "AI",
        "company_slug": COMPANY_SLUG,
        "company_name": COMPANY_NAME,
        "manufacturer_country_code": "US",
        "manufacturer_country_codes": "US",
        "description": description,
        "purpose": "ML research arm for leader/follower learning kits",
        "features": features,
        "url": product_url,
        "image": urls[0],
        "images": urls,
        "source_locale": "en",
        "availability_status": AVAILABLE,
        "family_key": "trossen:widowx",
        "family_name": "WidowX",
        "family_url": product_url,
        "product_url_scope": "family",
        "movement_type_keys": "stationary",
        "category_slugs": "research-robots",
        "use_keys": "research|data-collection|education",
        "industry_keys": "education|research",
        "dof": 6,
        "payload_kg": 1.5,
        "reach_mm": 700,
        "weight_kg": 4.0,
        "repeatability_mm": 1.0,
        "release_year": 2025,
        "price_min": 4545.95,
        "price_max": 4995.95,
        "price_currency": "USD",
        "price_range": "$4,545.95–$4,995.95",
        "notes": notes,
        "research_notes": notes,
        "sources": [
            {"url": product_url, "type": "website", "title": "WidowX AI OEM PDP"},
            {
                "url": "https://docs.trossenrobotics.com/trossen_arm/main/index.html",
                "type": "website",
                "title": "Trossen AI arm docs",
            },
        ],
        "information_source_urls": [
            product_url,
            "https://docs.trossenrobotics.com/trossen_arm/main/index.html",
        ],
    }
    staging = _RESEARCH / "staging" / "robots" / COMPANY_SLUG
    staging.mkdir(parents=True, exist_ok=True)
    path = staging / "widowx-ai-photo-fix.json"
    path.write_text(json.dumps(row, indent=2), encoding="utf-8")
    result = import_staging(
        path,
        dry_run=False,
        patch=True,
        force_overwrite=True,
        replace_media=True,
        status="pending_review",
        created_by_id=resolve_created_by_id(1),
        skip_company_update=True,
    )
    print("import", result)
    print("copy-media", copy_media(5273))
    body = {
        "manufacturer_countries": [US_ID],
        "manufacturer_country_ref": US_ID,
        "availability_status": AVAILABLE,
        "description": description,
        "features": features,
        "purpose": row["purpose"],
        "dof": 6,
        "payload_kg": 1.5,
        "reach_mm": 700,
        "weight_kg": 4.0,
        "repeatability_mm": 1.0,
        "release_year": 2025,
        "price_min": 4545.95,
        "price_max": 4995.95,
        "price_currency": "USD",
        "price_range": "$4,545.95–$4,995.95",
        "family_key": "trossen:widowx",
        "family_name": "WidowX",
        "family_url": product_url,
        "notes": notes,
        "s3_image": None,
    }
    api._patch("robots/robots/5273/", body)
    full = api._session.get(api._url("robots/robots/5273/"), timeout=60).json()
    img = full.get("image") or ""
    r = requests.get(img, timeout=30)
    print(
        "verify primary",
        r.status_code,
        len(r.content),
        "photos",
        len(full.get("photos") or []),
        "payload",
        full.get("payload_kg"),
        "reach",
        full.get("reach_mm"),
    )
    return 0 if r.status_code == 200 else 1


if __name__ == "__main__":
    raise SystemExit(main())
