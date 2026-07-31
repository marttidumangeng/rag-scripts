"""Upload Neo 2W studio hero (from official 1-pager PDF) to research-staging CDN."""
from __future__ import annotations

import hashlib
import os
import sys
import time
from pathlib import Path

import boto3
import requests
from PIL import Image

_RESEARCH = Path(__file__).resolve().parent
SERVER = _RESEARCH.parents[1] / "robotaigeek-server"
BUCKET = "cdn.robotaigeek.com"
CDN = "https://cdn.robotaigeek.com"
PREFIX = "research-staging/avidbots"
SRC = (
    _RESEARCH
    / "staging"
    / "avidbots_raw"
    / "heroes"
    / "neo2w_1pager_x106_p0_967x834.png"
)
OUT = _RESEARCH / "staging" / "tmp" / "avidbots-heroes"
OUT.mkdir(parents=True, exist_ok=True)


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


def main() -> int:
    if not SRC.is_file():
        print("MISSING", SRC)
        return 1
    raw = SRC.read_bytes()
    md5 = hashlib.md5(raw).hexdigest()
    print("src md5", md5, "bytes", len(raw))
    jpg = OUT / "neo-2w-studio-hero.jpg"
    Image.open(SRC).convert("RGB").save(jpg, quality=92, optimize=True)
    _load_dotenv(SERVER / ".env")
    s3 = boto3.client(
        "s3",
        region_name=os.environ.get("AWS_S3_REGION_NAME") or "ap-southeast-1",
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
    )
    key = f"{PREFIX}/neo-2w-studio-hero.jpg"
    body = jpg.read_bytes()
    s3.put_object(
        Bucket=BUCKET,
        Key=key,
        Body=body,
        ContentType="image/jpeg",
        CacheControl="public, max-age=31536000",
    )
    url = f"{CDN}/{key}"
    for _ in range(20):
        r = requests.get(url, timeout=30)
        if r.status_code == 200 and r.content[:3] == b"\xff\xd8\xff":
            print("OK", url, "cdn_md5", hashlib.md5(r.content).hexdigest(), len(r.content))
            return 0
        time.sleep(0.5)
    print("CDN verify failed", url)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
