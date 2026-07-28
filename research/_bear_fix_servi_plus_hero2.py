"""Force Servi Plus (2686) hero to high-capacity Servi-only OEM still (not duo)."""
from __future__ import annotations

import hashlib
import io
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

SERVER = _RESEARCH.parents[1] / "robotaigeek-server"
OUT = _RESEARCH / "staging" / "tmp" / "bear"
OUT.mkdir(parents=True, exist_ok=True)
BUCKET = "cdn.robotaigeek.com"
CDN = "https://cdn.robotaigeek.com"
UA = {"User-Agent": "Mozilla/5.0"}
RID = 2686

# Explicit Servi Plus product stills from OEM page (skip front-and-side duo).
CANDIDATES = [
    "https://images.squarespace-cdn.com/content/v1/652cbb3fb1f91809d4610dc0/f1749b18-5665-453f-a417-f58767a78b3a/high-capacity-robot-servi-plus.webp",
    "https://images.squarespace-cdn.com/content/v1/652cbb3fb1f91809d4610dc0/64f51f79-0931-4e59-b0da-b0d372240ead/high-capacity-robot-servi-plus.webp",
    "http://static1.squarespace.com/static/652cbb3fb1f91809d4610dc0/t/6a27bc020e27a1031791573b/1780988930416/+high-capacity-robot-servi-plus.webp",
]


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
    pick = None
    for u in CANDIDATES:
        # Try common format query variants
        tries = [u, u + "?format=1000w", u.replace(".webp", "") + "?format=original"]
        for t in tries:
            try:
                r = requests.get(t, headers=UA, timeout=60)
                if r.status_code != 200 or len(r.content) < 5000:
                    continue
                im = Image.open(io.BytesIO(r.content)).convert("RGB")
            except Exception as e:
                print("skip", t[:80], e)
                continue
            print(f"ok {im.size} {len(r.content)} {t[:100]}")
            pick = (t, im)
            break
        if pick:
            break

    if not pick:
        print("failed all candidates")
        return 1

    src, im = pick
    local = OUT / "servi-plus-solo.jpg"
    im.save(local, quality=92, optimize=True)
    digest = hashlib.sha1(local.read_bytes()).hexdigest()[:10]
    key = f"research-staging/bear/servi-plus-solo-{digest}-20260720.jpg"
    s3 = boto3.client(
        "s3",
        aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
        region_name=os.environ.get("AWS_S3_REGION_NAME") or "ap-southeast-1",
    )
    s3.put_object(
        Bucket=BUCKET,
        Key=key,
        Body=local.read_bytes(),
        ContentType="image/jpeg",
        CacheControl="public, max-age=31536000",
    )
    cdn = f"{CDN}/{key}"
    for _ in range(25):
        c = requests.get(cdn, headers=UA, timeout=30)
        if c.status_code == 200 and len(c.content) > 5000:
            print("CDN OK", cdn, len(c.content))
            break
        time.sleep(0.4)
    else:
        raise RuntimeError(cdn)

    client = ResearchApiClient()
    existing = client._get(f"robots/robots/{RID}/")
    old = existing.get("image") or ""
    photos = [cdn]
    if old and old != cdn:
        photos.append(old)
    client._patch(f"robots/robots/{RID}/", {"image": cdn, "photos": photos[:6]})
    # Verify patch stuck
    again = client._get(f"robots/robots/{RID}/")
    print("image now", again.get("image"))
    print("from", src[:100])
    # Save preview
    Image.open(io.BytesIO(requests.get(cdn, headers=UA, timeout=30).content)).convert(
        "RGB"
    ).save(OUT / "2686-preview.jpg", quality=85)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
