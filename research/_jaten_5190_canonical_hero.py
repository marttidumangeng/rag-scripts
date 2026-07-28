"""Copy Jaten 5190 research-staging hero into robots/original/ and stamp published_at if possible."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import boto3
import requests

_RESEARCH = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from api_client import ResearchApiClient
from load_env import load_research_env

load_research_env()

SERVER = _RESEARCH.parents[1] / "robotaigeek-server"
BUCKET = "cdn.robotaigeek.com"
CDN = "https://cdn.robotaigeek.com"
SRC = "https://cdn.robotaigeek.com/research-staging/jaten/mn30-164-hero-079c81182f-20260720.png"
RID = 5190
KEY = "robots/original/robot-5190-mn30-164-restored-20260720.png"


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


def main() -> int:
    _load_aws()
    raw = requests.get(SRC, timeout=60).content
    assert len(raw) > 100_000
    s3 = boto3.client(
        "s3",
        aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
        region_name=os.environ.get("AWS_S3_REGION_NAME") or "ap-southeast-1",
    )
    s3.put_object(
        Bucket=BUCKET,
        Key=KEY,
        Body=raw,
        ContentType="image/png",
        CacheControl="public, max-age=31536000",
    )
    cdn = f"{CDN}/{KEY}"
    for _ in range(25):
        r = requests.get(cdn, timeout=30)
        if r.status_code == 200 and len(r.content) > 100_000:
            break
        time.sleep(0.4)
    else:
        raise RuntimeError(cdn)
    print("uploaded", cdn, len(raw))

    c = ResearchApiClient()
    c._patch(
        f"robots/robots/{RID}/",
        {"image": cdn, "s3_image": cdn, "status": "published", "rejection_reason": ""},
    )
    d = c._get(f"robots/robots/{RID}/")
    img = d.get("s3_image") or d.get("image") or ""
    r = requests.get(img, timeout=30)
    print(f"status={d.get('status')} pub_at={d.get('published_at')} bytes={len(r.content)} {img}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
