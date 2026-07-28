"""Fix Locus Vector (wrong shelf photo) + Array (tote-only primary)."""
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

SERVER = _RESEARCH.parents[1] / "robotaigeek-server"
OUT = _RESEARCH / "staging" / "tmp" / "locus-final"
OUT.mkdir(parents=True, exist_ok=True)
BUCKET = "cdn.robotaigeek.com"
CDN = "https://cdn.robotaigeek.com"
UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://locusrobotics.com/",
}

FIXES = {
    4885: {
        "name": "Locus Vector",
        "slug": "vector",
        "srcs": [
            "https://locusrobotics.com/wp-content/uploads/2023/09/vector-graphic.png",
            "https://embed-ssl.wistia.com/deliveries/43eae94cdd34c2eed9a873189abec6fc.jpg",
            "https://locusrobotics.com/wp-content/uploads/2026/03/Vector-2-in-Customer-Warehouse-with-Platform-e1773435497177.webp",
        ],
    },
    2536: {
        "name": "Locus Array",
        "slug": "array",
        "srcs": [
            "https://locusrobotics.com/wp-content/uploads/2026/05/locus-array1.png",
            "https://locusrobotics.com/wp-content/uploads/2026/04/Array_360_20260318_0027.png",
            "https://locusrobotics.com/wp-content/uploads/2026/06/locus-array-1_locus-robotics-Custom1.png",
            "https://locusrobotics.com/wp-content/uploads/2026/03/3Z5A0004-Edit-scaled.jpg",
        ],
    },
}


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


def upload(s3, url: str, key: str) -> str:
    r = requests.get(url, headers=UA, timeout=90)
    r.raise_for_status()
    local = OUT / Path(key).name
    local.write_bytes(r.content)
    jpg = local.with_suffix(".jpg")
    Image.open(local).convert("RGB").save(jpg, quality=92, optimize=True)
    key = key.rsplit(".", 1)[0] + ".jpg"
    s3.put_object(
        Bucket=BUCKET,
        Key=key,
        Body=jpg.read_bytes(),
        ContentType="image/jpeg",
        CacheControl="public, max-age=31536000",
    )
    cdn = f"{CDN}/{key}"
    for _ in range(15):
        c = requests.get(cdn, timeout=30)
        if c.status_code == 200 and len(c.content) > 2000:
            print("OK", cdn)
            return cdn
        time.sleep(0.4)
    raise RuntimeError(cdn)


def copy_media(rid: int) -> str:
    secret = os.environ.get("INTERNAL_API_SECRET", "").strip()
    if not secret:
        for line in (SERVER / ".env").read_text(encoding="utf-8").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                secret = line.split("=", 1)[1].strip()
    api = (
        os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/").replace("/api/v1", "")
        or "https://ragadmin.robotaigeek.com"
    )
    url = f"{api}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/?force=1"
    resp = requests.post(url, headers={"X-Internal-Secret": secret}, timeout=180)
    return f"{resp.status_code} {resp.text[:100]}"


def main() -> int:
    _load_aws()
    s3 = boto3.client(
        "s3",
        region_name=os.environ.get("AWS_S3_REGION_NAME") or "ap-southeast-1",
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
    )
    client = ResearchApiClient()
    for rid, spec in FIXES.items():
        urls = []
        for i, src in enumerate(spec["srcs"]):
            urls.append(
                upload(s3, src, f"research-staging/locus/{spec['slug']}-fix-{i}-20260720.jpg")
            )
        row = {
            "id": rid,
            "name": spec["name"],
            "company_slug": "locus-robotics",
            "company_name": "Locus Robotics",
            "image": urls[0],
            "images": urls,
            "manufacturer_country_code": "US",
            "availability_status": 11,
        }
        path = _RESEARCH / "staging" / "robots" / "locus-robotics" / f"{spec['slug']}-photo-fix.json"
        path.write_text(json.dumps(row, indent=2), encoding="utf-8")
        print(
            import_staging(
                path,
                dry_run=False,
                patch=True,
                force_overwrite=True,
                replace_media=True,
                status="pending_review",
                created_by_id=resolve_created_by_id(1),
                skip_company_update=True,
            )
        )
        client._patch(f"robots/robots/{rid}/", {"s3_image": None})
        print("copy", copy_media(rid))
        after = client._get(f"robots/robots/{rid}/")
        print(rid, "image", after.get("image"), "photos", len(after.get("photos") or []))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
