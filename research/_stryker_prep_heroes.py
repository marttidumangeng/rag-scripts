"""Prepare distinct Stryker Mako heroes and upload to research-staging."""
from __future__ import annotations

import hashlib
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

FAMILY_URL = (
    "https://www.stryker.com/content/dam/stryker/joint-replacement/"
    "systems/mako-system-overview/images/Mako%204%20Family%205_ALL%20GRAY.png"
)
SYSTEM_URL = (
    "https://cdn.robotaigeek.com/robots/original/robot-225-mako-smartrobotics.jpg"
)


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
    ctype = "image/jpeg" if local.suffix.lower() in (".jpg", ".jpeg") else "image/png"
    s3.put_object(
        Bucket=BUCKET,
        Key=key,
        Body=body,
        ContentType=ctype,
        CacheControl="public, max-age=31536000",
    )
    url = f"{CDN}/{key}"
    for _ in range(12):
        r = requests.get(url, timeout=30)
        if r.status_code == 200 and len(r.content) > 1000:
            return url
        time.sleep(0.4)
    raise RuntimeError(f"CDN verify failed {url}")


def save_jpg(im: Image.Image, path: Path, quality: int = 92) -> Path:
    rgb = im.convert("RGB")
    rgb.save(path, quality=quality, optimize=True)
    return path


def main() -> None:
    fam_path = OUT / "family-src.png"
    if not fam_path.exists():
        r = requests.get(FAMILY_URL, timeout=120)
        r.raise_for_status()
        fam_path.write_bytes(r.content)
    fam = Image.open(fam_path).convert("RGB")
    w, h = fam.size
    print("family", w, h)

    # Five units across ~equal columns; pad slightly inward to avoid edge cutoffs.
    n = 5
    crops = []
    for i in range(n):
        x0 = int(w * i / n) + int(w * 0.01)
        x1 = int(w * (i + 1) / n) - int(w * 0.01)
        crop = fam.crop((x0, 0, x1, h))
        crops.append(crop)
        print(f"  unit{i}", crop.size)

    # Assign: Mako4=full family; TK=unit1; TH=unit2; PK=unit3 (center-ish distinct poses)
    mako4 = save_jpg(fam, OUT / "mako4-family-hero.jpg")
    tk = save_jpg(crops[1], OUT / "mako-total-knee-hero.jpg")
    th = save_jpg(crops[2], OUT / "mako-total-hip-hero.jpg")
    pk = save_jpg(crops[3], OUT / "mako-partial-knee-hero.jpg")

    # Gallery secondary for Mako4: published system+guidance still (unique)
    sys_path = OUT / "mako-system-guidance.jpg"
    if not sys_path.exists():
        r = requests.get(SYSTEM_URL, timeout=120)
        r.raise_for_status()
        sys_path.write_bytes(r.content)

    files = {
        "mako4-family-hero.jpg": mako4,
        "mako-total-knee-hero.jpg": tk,
        "mako-total-hip-hero.jpg": th,
        "mako-partial-knee-hero.jpg": pk,
        "mako-system-guidance.jpg": sys_path,
    }
    hashes = {}
    for name, p in files.items():
        h = hashlib.md5(p.read_bytes()).hexdigest()
        hashes[name] = h
        print(name, p.stat().st_size, h[:12])
    assert len(set(hashes.values())) == len(hashes), "hash collision"

    # QA thumbs
    for p in files.values():
        im = Image.open(p).convert("RGB")
        t = im.copy()
        t.thumbnail((800, 800))
        t.save(p.with_suffix(".qa.jpg"), quality=85)

    if "--upload" not in sys.argv:
        print("dry-run only; pass --upload")
        return

    s3 = s3_client()
    urls = {}
    for name, p in files.items():
        key = f"{PREFIX}/{name}"
        url = upload(s3, p, key)
        urls[name] = url
        print("uploaded", url)
    (OUT / "urls.json").write_text(
        __import__("json").dumps(urls, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
