"""Re-crop Stryker Mako single-unit heroes with better framing; re-upload."""
from __future__ import annotations

import hashlib
import json
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
PREFIX = "research-staging/stryker"
OUT = _RESEARCH / "staging" / "tmp" / "stryker-final"
OUT.mkdir(parents=True, exist_ok=True)

FAMILY_SRC = OUT / "family-src.png"


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
    for _ in range(12):
        r = requests.get(url, timeout=30)
        if r.status_code == 200 and r.content[:3] == b"\xff\xd8\xff":
            return url
        time.sleep(0.4)
    raise RuntimeError(f"CDN verify failed {url}")


def unit_crop(im: Image.Image, index: int, n: int = 5, span: float = 0.26) -> Image.Image:
    """Crop a window centered on unit `index` spanning `span` of image width."""
    w, h = im.size
    center = (index + 0.5) / n
    half = span / 2
    x0 = max(0, int(w * (center - half)))
    x1 = min(w, int(w * (center + half)))
    # Prefer nearly square / portrait product framing
    crop_w = x1 - x0
    y0 = 0
    y1 = h
    if crop_w < h * 0.55:
        # expand horizontally if possible
        need = int(h * 0.55) - crop_w
        x0 = max(0, x0 - need // 2)
        x1 = min(w, x1 + need // 2)
    return im.crop((x0, y0, x1, y1))


def main() -> None:
    fam = Image.open(FAMILY_SRC).convert("RGB")
    # Units 1,2,3 (0-indexed) — avoid edge units that clip
    tk = unit_crop(fam, 1)
    th = unit_crop(fam, 2)
    pk = unit_crop(fam, 3)
    paths = {
        "mako-total-knee-hero.jpg": OUT / "mako-total-knee-hero.jpg",
        "mako-total-hip-hero.jpg": OUT / "mako-total-hip-hero.jpg",
        "mako-partial-knee-hero.jpg": OUT / "mako-partial-knee-hero.jpg",
    }
    for name, im in [
        ("mako-total-knee-hero.jpg", tk),
        ("mako-total-hip-hero.jpg", th),
        ("mako-partial-knee-hero.jpg", pk),
    ]:
        p = paths[name]
        im.convert("RGB").save(p, quality=92, optimize=True)
        qa = im.copy()
        qa.thumbnail((800, 800))
        qa.save(p.with_suffix(".qa.jpg"), quality=85)
        print(name, im.size, hashlib.md5(p.read_bytes()).hexdigest()[:12])

    # Also keep mako4 + guidance already uploaded
    hashes = {
        n: hashlib.md5(p.read_bytes()).hexdigest()
        for n, p in {
            **paths,
            "mako4-family-hero.jpg": OUT / "mako4-family-hero.jpg",
            "mako-system-guidance.jpg": OUT / "mako-system-guidance.jpg",
        }.items()
    }
    assert len(set(hashes.values())) == 5, hashes

    if "--upload" not in sys.argv:
        print("dry-run")
        return
    s3 = s3_client()
    urls = {}
    for name, p in paths.items():
        urls[name] = upload(s3, p, f"{PREFIX}/{name}")
        print("uploaded", urls[name])
    urls["mako4-family-hero.jpg"] = f"{CDN}/{PREFIX}/mako4-family-hero.jpg"
    urls["mako-system-guidance.jpg"] = f"{CDN}/{PREFIX}/mako-system-guidance.jpg"
    (OUT / "urls.json").write_text(json.dumps(urls, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
