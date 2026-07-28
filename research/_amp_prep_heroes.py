"""Upload AMP Delta + Compact heroes to research-staging CDN."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import boto3
import requests
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_RESEARCH = Path(__file__).resolve().parent
SERVER = _RESEARCH.parents[1] / "robotaigeek-server"
BUCKET = "cdn.robotaigeek.com"
CDN = "https://cdn.robotaigeek.com"
PREFIX = "research-staging/amp"
SRC = _RESEARCH / "staging" / "tmp" / "amp-heroes"
OUT = _RESEARCH / "staging" / "tmp" / "amp-final"
OUT.mkdir(parents=True, exist_ok=True)

# Distinct product photos (content-hash verified visually):
# Delta studio frame = c3ab0447d417; Compact in-facility effector = c93ada391f55
UPLOADS = {
    "amp-delta-studio-hero.jpg": SRC / "c3ab0447d417.png",
    "amp-delta-compact-facility-hero.jpg": SRC / "c93ada391f55.png",
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
    region = os.environ.get("AWS_S3_REGION_NAME") or "ap-southeast-1"
    return boto3.client(
        "s3",
        region_name=region,
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
    )


def to_jpg(src: Path, dest: Path, quality: int = 92) -> Path:
    im = Image.open(src).convert("RGB")
    im.save(dest, quality=quality, optimize=True)
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
    for _ in range(15):
        r = requests.get(url, timeout=30)
        if r.status_code == 200 and len(r.content) > 2000 and r.content[:3] == b"\xff\xd8\xff":
            return url
        time.sleep(0.4)
    raise RuntimeError(f"CDN verify failed {url}")


def main() -> int:
    s3 = s3_client()
    for name, src in UPLOADS.items():
        if not src.is_file():
            print("MISSING", src)
            return 1
        local = to_jpg(src, OUT / name)
        key = f"{PREFIX}/{name}"
        url = upload(s3, local, key)
        print("OK", local.name, local.stat().st_size, url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
