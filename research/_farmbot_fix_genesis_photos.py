"""Replace broken FarmBot Genesis CDN placeholders with OEM shop renders."""
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
OUT = _RESEARCH / "staging" / "tmp" / "farmbot-final"
OUT.mkdir(parents=True, exist_ok=True)
BUCKET = "cdn.robotaigeek.com"
CDN = "https://cdn.robotaigeek.com"
PREFIX = "research-staging/farmbot"
UA = {"User-Agent": "Mozilla/5.0"}

FIXES = {
    2760: {
        "name": "FarmBot Genesis v1.8",
        "slug": "genesis-v18",
        "src": "https://farm.bot/cdn/shop/files/FarmBot_Genesis_v1.8_Beta_1200x927.png?v=1732328603",
        "url": "https://farm.bot/products/farmbot-genesis-v1-8",
    },
    2761: {
        "name": "FarmBot Genesis XL v1.8",
        "slug": "genesis-xl-v18",
        "src": "https://farm.bot/cdn/shop/files/FarmBot_Genesis_XL_v1.8_Beta_1200x800.png?v=1732328684",
        "url": "https://farm.bot/products/farmbot-genesis-xl-v1-8",
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
    Image.open(__import__("io").BytesIO(r.content)).convert("RGB").save(
        local, quality=92, optimize=True
    )
    s3.put_object(
        Bucket=BUCKET,
        Key=key,
        Body=local.read_bytes(),
        ContentType="image/jpeg",
        CacheControl="public, max-age=31536000",
    )
    cdn = f"{CDN}/{key}"
    for _ in range(20):
        c = requests.get(cdn, headers=UA, timeout=30)
        if c.status_code == 200 and len(c.content) > 5000:
            print("OK", cdn, len(c.content))
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
    staging = _RESEARCH / "staging" / "robots" / "farmbot-inc"
    staging.mkdir(parents=True, exist_ok=True)
    for rid, spec in FIXES.items():
        url = upload(s3, spec["src"], f"{PREFIX}/{spec['slug']}-0-20260720.jpg")
        row = {
            "id": rid,
            "name": spec["name"],
            "company_slug": "farmbot-inc",
            "company_name": "FarmBot Inc.",
            "manufacturer_country_code": "US",
            "image": url,
            "images": [url],
            "url": spec["url"],
            "availability_status": 11,
        }
        path = staging / f"{spec['slug']}-photo-fix.json"
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
        client._patch(
            f"robots/robots/{rid}/",
            {"image": url, "s3_image": None, "manufacturer_countries": [20], "availability_status": 11},
        )
        print("copy", rid, copy_media(rid))
        after = client._get(f"robots/robots/{rid}/")
        img = after.get("image") or ""
        r = requests.get(img, headers=UA, timeout=30)
        print("verify", rid, r.status_code, len(r.content), img[-60:])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
