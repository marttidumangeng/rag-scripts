"""Upload DAIHEN banner-crop heroes to prod CDN; PATCH image + demote banners.

Only applies crops that passed visual QA (single-model banners).
Family-lineup models keep existing heroes (title overlays cannot be cleanly removed).
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import boto3
import requests

_RESEARCH = Path(__file__).resolve().parent
ROOT = _RESEARCH.parent.parent
SERVER = ROOT / "robotaigeek-server"
sys.path.insert(0, str(_RESEARCH))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env
from api_client import ResearchApiClient

load_research_env()

COMPANY_ID = 1402
CDN = "https://cdn.robotaigeek.com"
BUCKET = "cdn.robotaigeek.com"
PREFIX = "research-staging/daihen"

# Visual-QA passed: single-model mv_ crops (qa5). Banners demoted to gallery.
APPLY = {
    5551: ("FD-V25L", "staging/reports/daihen_qa5/crop_5551.jpg",
           "https://www.daihen-robot.com/assets/img/en/robot/items/mv_FD-V25L.jpg"),
    5550: ("FD-V25", "staging/reports/daihen_qa5/crop_5550.jpg",
           "https://www.daihen-robot.com/assets/img/en/robot/items/mv_FD-V25.jpg"),
    3053: ("FD-BT6L", "staging/reports/daihen_qa5/crop_3053.jpg",
           "https://www.daihen-robot.com/assets/img/en/robot/items/mv_FD-BT6L.jpg"),
    3052: ("FD-V210", "staging/reports/daihen_qa5/crop_3052.jpg",
           "https://www.daihen-robot.com/assets/img/en/robot/items/mv_FD-V210.jpg"),
    3050: ("FD-B26", "staging/reports/daihen_qa5/crop_3050.jpg",
           "https://www.daihen-robot.com/assets/img/en/robot/items/mv_FD-B26.jpg"),
    3049: ("FD-H5", "staging/reports/daihen_qa5/crop_3049.jpg",
           "https://www.daihen-robot.com/assets/img/en/robot/items/mv_FD-H5.jpg"),
    3048: ("FD-B6L", "staging/reports/daihen_qa5/crop_3048.jpg",
           "https://www.daihen-robot.com/assets/img/en/robot/items/mv_FD-B6L.jpg"),
    3047: ("FD-B6", "staging/reports/daihen_qa5/crop_3047.jpg",
           "https://www.daihen-robot.com/assets/img/en/robot/items/mv_FD-B6.jpg"),
    1900: ("FD-A20", "staging/reports/daihen_qa5/crop_1900.jpg",
           "https://www.daihen-robot.com/assets/img/en/robot/items/mv_FD-A20.jpg"),
    1896: ("FD-VT8L", "staging/reports/daihen_qa5/crop_1896.jpg",
           "https://www.daihen-robot.com/assets/img/en/robot/items/mv_FD-VT8L.jpg"),
    1895: ("FD-BT6", "staging/reports/daihen_qa5/crop_1895.jpg",
           "https://www.daihen-robot.com/assets/img/en/robot/items/mv_FD-BT6.jpg"),
    1894: ("FD-V166", "staging/reports/daihen_qa5/crop_1894.jpg",
           "https://www.daihen-robot.com/assets/img/en/robot/items/mv_FD-V166.jpg"),
    1893: ("FD-B100", "staging/reports/daihen_qa5/crop_1893.jpg",
           "https://www.daihen-robot.com/assets/img/en/robot/items/mv_FD-B100.jpg"),
    1892: ("FD-V8L", "staging/reports/daihen_qa5/crop_1892.jpg",
           "https://www.daihen-robot.com/assets/img/en/robot/items/mv_FD-V8L.jpg"),
    1891: ("FD-V8", "staging/reports/daihen_qa5/crop_1891.jpg",
           "https://www.daihen-robot.com/assets/img/en/robot/items/mv_FD-V8.jpg"),
    5552: ("FD-VC4", "staging/reports/daihen_qa5/crop_5552.jpg",
           "https://www.daihen-robot.com/assets/img/en/robot/items/mv_FD-VC4.jpg"),
}

# Family-lineup banners: large title overlays baked across robots — no clean primary
SKIP_FAMILY = {
    3054: "FD-V350 (family lineup banner)",
    3051: "FD-V80 (family lineup banner)",
    2472: "FD-V400L (family lineup banner)",
    1904: "FD-V130 (family lineup banner)",
    1903: "FD-V100 (family lineup banner)",
    1899: "FD-V700 (family lineup banner)",
    1898: "FD-V600 (family lineup banner)",
}


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
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
    os.environ["AWS_STORAGE_BUCKET_NAME"] = BUCKET
    region = os.environ.get("AWS_S3_REGION_NAME") or "ap-southeast-1"
    return boto3.client(
        "s3",
        region_name=region,
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
    )


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
    # verify
    for _ in range(8):
        r = requests.get(url, timeout=30)
        if r.status_code == 200 and len(r.content) > 1000:
            return url
        time.sleep(0.6)
    raise RuntimeError(f"CDN verify failed {url} {r.status_code}")


def gallery_urls(robot: dict, crop_url: str, banner_url: str) -> list[str]:
    """Primary=crop, then full banner, then other existing (deduped)."""
    seen: set[str] = set()
    out: list[str] = []
    for u in (crop_url, banner_url):
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    existing = robot.get("images") or []
    if isinstance(existing, str):
        existing = [existing]
    for item in existing:
        if isinstance(item, dict):
            u = (item.get("image") or item.get("url") or "").strip()
        else:
            u = str(item or "").strip()
        if not u or u in seen:
            continue
        # skip if it's already a crop we just set, or duplicate of primary
        seen.add(u)
        out.append(u)
    return out[:8]


def main() -> None:
    dry = "--apply" not in sys.argv
    s3 = s3_client()
    client = ResearchApiClient()
    report = {"uploaded": [], "patched": [], "skipped_family": SKIP_FAMILY, "dry": dry}

    print(f"{'DRY RUN' if dry else 'APPLY'} — {len(APPLY)} crops, skip {len(SKIP_FAMILY)} family")

    for rid, (name, rel, banner) in APPLY.items():
        local = _RESEARCH / rel
        if not local.is_file():
            print(f"MISSING {rid} {local}")
            continue
        key = f"{PREFIX}/{rid}-{name.lower()}-hero-crop.jpg"
        crop_url = f"{CDN}/{key}"
        if dry:
            print(f"would upload {rid} {name} -> {crop_url}")
            report["uploaded"].append({"id": rid, "url": crop_url, "dry": True})
            continue

        crop_url = upload(s3, local, key)
        print(f"uploaded {rid} {name} {crop_url}")
        report["uploaded"].append({"id": rid, "url": crop_url})

        # images must be URL strings (dicts get str()'d by serializer → corrupt photos)
        # First URL becomes primary RobotPhoto + robot.image; rest are gallery (banner demoted).
        # Clear s3_image so to_representation does not keep preferring the old owned banner.
        images = [crop_url, banner]
        payload = {"image": crop_url, "images": images, "s3_image": None}
        client._patch(f"robots/robots/{rid}/", payload)
        # Soft-required: re-assert availability after media replace (id 11 = Available)
        client._patch(f"robots/robots/{rid}/", {"availability_status": 11})
        r = requests.get(crop_url, timeout=30)
        # Confirm API surface shows crop (not stale s3_image)
        full = client._get(f"robots/robots/{rid}/")
        shown = (full.get("image") or "").strip()
        print(f"  patched {rid} primary={r.status_code} gallery={len(images)} shown_crop={'hero-crop' in shown}")
        report["patched"].append(
            {
                "id": rid,
                "name": name,
                "image": crop_url,
                "api_image": shown,
                "n_images": len(images),
            }
        )
        time.sleep(0.3)

    out = _RESEARCH / "staging/reports/daihen-image-apply.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("wrote", out)


if __name__ == "__main__":
    main()
