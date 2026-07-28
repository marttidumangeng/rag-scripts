"""Repair the sole blocked Dobot (1161) queue record: CR30H (4242)."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
from pathlib import Path
from typing import Any

import requests
from PIL import Image, ImageChops

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from api_client import ResearchApiClient
from load_env import load_research_env

load_research_env()

COMPANY_ID = 1161
ROBOT_ID = 4242
PRODUCT_URL = (
    "https://www.dobot-robots.com/products/cr-30h/"
    "cr-30h-collaborative-robots.html"
)
LAUNCH_URL = (
    "https://www.dobot-robots.com/insights/news/"
    "dobot-unveils-next-generation-collaborative-robots-in-nagoya.html"
)
SOURCE_IMAGE = (
    "https://www.dobot-robots.com/media/upload/2025/06/cr30h/itme1.png"
)
MEDIA_DIR = _HERE / "staging" / "dobot_1161_media"
REPORT = _HERE / "staging" / "reports" / "dobot-1161-cr30h.json"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
    )
}


def prepare_hero(body: bytes, target_long_side: int = 1_200) -> bytes:
    """Remove the OEM card's blank footer and enlarge the product asset."""
    source = Image.open(io.BytesIO(body)).convert("RGB")
    # This exact OEM card reserves its lower 32% for web overlay copy that is
    # absent from the raster. Remove that known blank panel before bbox cleanup.
    source = source.crop((0, 0, source.width, round(source.height * 0.68)))
    white = Image.new("RGB", source.size, "white")
    bbox = ImageChops.difference(source, white).getbbox()
    if not bbox:
        raise RuntimeError("CR30H source image is blank")
    padding = 16
    left = max(0, bbox[0] - padding)
    top = max(0, bbox[1] - padding)
    right = min(source.width, bbox[2] + padding)
    bottom = min(source.height, bbox[3] + padding)
    source = source.crop((left, top, right, bottom))
    scale = target_long_side / max(source.size)
    if scale > 1:
        source = source.resize(
            (round(source.width * scale), round(source.height * scale)),
            Image.Resampling.LANCZOS,
        )
    output = io.BytesIO()
    source.save(output, format="PNG", optimize=True)
    return output.getvalue()


def patch_payload(media_url: str) -> dict[str, Any]:
    features = (
        "Official DOBOT CR 30H specifications and capabilities:\n"
        "• Six-axis heavy-payload collaborative robot with 30 kg maximum payload, "
        "1,800 mm working radius, 98.5 kg body weight, and ±0.05 mm repeatability.\n"
        "• Maximum joint speeds: J1/J2 150°/s, J3 200°/s, and J4/J5/J6 300°/s; "
        "J1/J2/J4/J5/J6 travel ±360° and J3 travel ±163°.\n"
        "• IP67 protection, 70 dB(A) rated noise, 0–50 °C operating range, and "
        "floor, wall, or ceiling mounting.\n"
        "• End I/O supplies 0/12/24 V at 2 A average and 3 A maximum, with four "
        "digital inputs, four digital outputs, and one RS485 channel.\n"
        "• HyperMove motion control, full-load vibration suppression, fail-safe "
        "electromagnetic brakes, and 1 kHz real-time control support stable "
        "heavy-duty palletizing and material-handling workflows."
    )
    return {
        "name": "DOBOT CR 30H",
        "model_name": "CR 30H",
        "variant_code": "CR-30H",
        "variant_label": "Standard Edition / 30 kg payload",
        "description": (
            "DOBOT CR 30H is a six-axis, 30 kg-payload collaborative robot for "
            "heavy industrial automation. Its 1,800 mm reach, 300°/s peak joint "
            "speed, IP67 protection, and vibration-suppressed motion target fast "
            "palletizing, machine handling, and large-part transfer."
        ),
        "purpose": (
            "Heavy-load palletizing\n"
            "Material handling and part transfer\n"
            "Automotive assembly\n"
            "Machine loading and unloading"
        ),
        "features": features,
        "url": PRODUCT_URL,
        "family_key": "dobot:cr-30h",
        "family_name": "CR 30H",
        "family_url": PRODUCT_URL,
        "product_url_scope": "exact_variant",
        "availability_status": 11,
        "release_year": 2025,
        "manufacturer_country_ref": 3,
        "manufacturer_countries": [3],
        "payload_kg": 30.0,
        "reach_mm": 1_800.0,
        "weight_kg": 98.5,
        "weight": "98.5 kg",
        "repeatability_mm": 0.05,
        "dof": 6,
        "uses": [25, 32, 46, 21],
        "industries": [12, 26, 28, 11],
        "movement_types": [10],
        "tags": [
            "Assembly",
            "Automation",
            "Cobot",
            "Handling",
            "Industrial",
            "Industrial Automation",
            "Manufacturing",
            "Palletizing",
        ],
        "images": [media_url],
        "image": media_url,
        "s3_image": None,
        "information_source_urls": [PRODUCT_URL, LAUNCH_URL],
        "notes": (
            "[AI Research — curated Dobot CR30H repair 2026-07-21]\n"
            f"Exact Standard Edition hero cropped from the OEM card asset: {SOURCE_IMAGE}. "
            "The source bytes were visually checked and hash-validated before upload. "
            "Specifications come from the exact DOBOT product table and June 2025 "
            "launch release. Dead searches: no public OEM list price or whole-system "
            "external L×W×H envelope; joint speeds are not locomotion speed. No "
            "official exact-token YouTube URL surfaced in the OEM page/search pass."
        ),
        "status": "pending_review",
    }


def upload_image(client: ResearchApiClient, path: Path) -> str:
    headers = {
        key: value
        for key, value in client._session.headers.items()
        if key.lower() != "content-type"
    }
    with path.open("rb") as handle:
        response = requests.post(
            client._url(f"robots/robots/{ROBOT_ID}/images/"),
            headers=headers,
            files={"images": (path.name, handle, "image/png")},
            data={
                "title": "DOBOT CR 30H Standard Edition",
                "description": "Exact-model render from the official DOBOT product page.",
            },
            timeout=120,
        )
    response.raise_for_status()
    data = response.json()
    photos = data.get("photos") or [data.get("photo") or {}]
    url = str((photos[0] or {}).get("url") or "")
    if not url:
        raise RuntimeError("CR30H upload returned no URL")
    return url


def copy_media() -> dict[str, Any]:
    secret = os.environ.get("INTERNAL_API_SECRET", "").strip()
    if not secret:
        raise RuntimeError("INTERNAL_API_SECRET missing")
    base = os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/").replace(
        "/api/v1", ""
    )
    response = requests.post(
        f"{base}/admin/robots/robot/content-queue/api/robot/"
        f"{ROBOT_ID}/copy-media/?force=1",
        headers={"X-Internal-Secret": secret},
        timeout=240,
    )
    response.raise_for_status()
    return response.json()


def verify_image(url: str) -> dict[str, Any]:
    response = requests.get(url, headers=HEADERS, timeout=90)
    response.raise_for_status()
    body = response.content
    image = Image.open(io.BytesIO(body))
    return {
        "url": url,
        "bytes": len(body),
        "width": image.width,
        "height": image.height,
        "sha256": hashlib.sha256(body).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair Dobot CR30H queue record")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    response = requests.get(SOURCE_IMAGE, headers=HEADERS, timeout=90)
    response.raise_for_status()
    source = response.content
    hero = prepare_hero(source)
    path = MEDIA_DIR / "dobot-cr30h-standard-oem-card-cropped-1200.png"
    path.write_bytes(hero)
    candidate = {
        "source_url": SOURCE_IMAGE,
        "source_bytes": len(source),
        "hero_path": str(path),
        "hero_bytes": len(hero),
        "hero_sha256": hashlib.sha256(hero).hexdigest(),
        "hero_size": Image.open(io.BytesIO(hero)).size,
    }

    client = ResearchApiClient()
    existing = client._get(f"robots/robots/{ROBOT_ID}/")
    if existing.get("status") != "pending_review":
        raise RuntimeError(f"CR30H status moved to {existing.get('status')}")

    report: dict[str, Any] = {
        "company_id": COMPANY_ID,
        "robot_id": ROBOT_ID,
        "mode": "apply" if args.apply else "dry-run",
        "candidate": candidate,
        "applied": False,
    }
    if not args.apply:
        REPORT.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0

    uploaded = upload_image(client, path)
    client._patch(f"robots/robots/{ROBOT_ID}/", patch_payload(uploaded))
    copy_result = copy_media()
    refreshed = client._get(f"robots/robots/{ROBOT_ID}/")
    if refreshed.get("status") != "pending_review":
        raise RuntimeError(f"status invariant failed: {refreshed.get('status')}")
    cdn_url = str(refreshed.get("s3_image") or refreshed.get("image") or "")
    verified = verify_image(cdn_url)
    if verified["width"] < 600 or verified["height"] < 600:
        raise RuntimeError(f"CDN hero is undersized: {verified}")

    report.update(
        {
            "applied": True,
            "cdn": verified,
            "copy_media": copy_result,
            "status": refreshed.get("status"),
            "typed": {
                key: refreshed.get(key)
                for key in (
                    "payload_kg",
                    "reach_mm",
                    "weight_kg",
                    "repeatability_mm",
                    "dof",
                )
            },
            "family_key": refreshed.get("family_key"),
        }
    )
    REPORT.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
