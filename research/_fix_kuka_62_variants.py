#!/usr/bin/env python3
"""Force-regenerate missing primary PNG thumbs for KUKA KR 6 (robot 62)."""
from __future__ import annotations

import io
import os
import sys
from pathlib import Path

import requests

_RESEARCH_DIR = Path(__file__).resolve().parent
ROOT = _RESEARCH_DIR.parents[1]
SERVER = ROOT / "robotaigeek-server"
sys.path.insert(0, str(SERVER))
sys.path.insert(0, str(_RESEARCH_DIR))

from load_env import load_research_env

load_research_env()


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if " #" in v:
            v = v.split(" #", 1)[0].strip()
        if k.startswith("AWS_") or k not in os.environ or not str(os.environ.get(k) or "").strip():
            os.environ[k] = v


_load_dotenv(SERVER / ".env")
os.environ["AWS_STORAGE_BUCKET_NAME"] = "cdn.robotaigeek.com"
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

import django

django.setup()

import boto3
from PIL import Image, ImageOps
from common.image_variants import get_variant_key

KEY = "robots/original/robot-62-kuka-kr-6_8zfm7hy.png"
BUCKET = "cdn.robotaigeek.com"
MISSING = [640, 960, 1280]


def main() -> int:
    url = f"https://cdn.robotaigeek.com/{KEY}"
    raw = requests.get(url, timeout=90).content
    image = ImageOps.exif_transpose(Image.open(io.BytesIO(raw)))
    print(f"source {image.size} {image.mode} bytes={len(raw)}")

    s3 = boto3.client(
        "s3",
        region_name=os.environ.get("AWS_S3_REGION_NAME", "ap-southeast-1"),
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
    )

    for width in MISSING:
        if width < image.width:
            ratio = width / float(image.width)
            resized = image.resize(
                (width, max(1, int(image.height * ratio))), Image.LANCZOS
            )
        else:
            resized = image.copy()
        # API JPEG-map keeps .png extension when source is .png
        out_key = get_variant_key(KEY, width, ext_override=".png")
        buf = io.BytesIO()
        rgb = resized if resized.mode in ("RGB", "L") else resized.convert("RGB")
        rgb.save(buf, format="PNG", optimize=True)
        s3.put_object(
            Bucket=BUCKET,
            Key=out_key,
            Body=buf.getvalue(),
            ContentType="image/png",
            CacheControl="public, max-age=31536000",
        )
        print(f"put {out_key} ({len(buf.getvalue())} B)")

    for width in [320, *MISSING]:
        u = f"https://cdn.robotaigeek.com/{get_variant_key(KEY, width, ext_override='.png')}"
        code = requests.get(u, headers={"Range": "bytes=0-32"}, timeout=20).status_code
        print(f"verify {width}: {code}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
