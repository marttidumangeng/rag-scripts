#!/usr/bin/env python3
"""Recheck + force-fix dead PNG thumbs for Mitsubishi 73 (same pattern as 1028/239)."""
from __future__ import annotations

import io
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests

_RESEARCH_DIR = Path(__file__).resolve().parent
ROOT = _RESEARCH_DIR.parents[1]
SERVER = ROOT / "robotaigeek-server"
sys.path.insert(0, str(SERVER))
sys.path.insert(0, str(_RESEARCH_DIR))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

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
        k, v = k.strip(), v.strip().strip('"').strip("'")
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

from api_client import ResearchApiClient
from _audit_company_media import collect_variant_urls, ok

IDS = [2074, 2077, 2080, 2083, 2086]
BUCKET = "cdn.robotaigeek.com"


def main() -> int:
    c = ResearchApiClient()
    s3 = boto3.client(
        "s3",
        region_name=os.environ.get("AWS_S3_REGION_NAME", "ap-southeast-1"),
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
    )
    still = []
    for rid in IDS:
        r = c._get(f"robots/robots/{rid}/")
        photo_map = {
            int(p["id"]): (p.get("s3_image") or p.get("url") or "").strip()
            for p in (r.get("photos") or [])
            if isinstance(p, dict) and p.get("id")
        }
        primary = (r.get("s3_image") or r.get("image") or "").strip()
        for label, u in collect_variant_urls(r):
            good, code = ok(u)
            if good:
                continue
            print(f"dead {rid} {label} {code} {u[-70:]}")
            if not u.endswith((".png", ".jpg", ".jpeg", ".webp")):
                still.append({"id": rid, "label": label, "error": "bad_ext"})
                continue
            if label.startswith("primary_"):
                src = primary
            elif "#" in label:
                pid = int(label.split("#", 1)[1].split(":", 1)[0])
                src = photo_map.get(pid) or primary
            else:
                src = primary
            key = urlparse(u).path.lstrip("/")
            m = re.search(r"_w(\d+)\.", key)
            width = int(m.group(1)) if m else 1280
            raw = requests.get(src, timeout=90).content
            image = ImageOps.exif_transpose(Image.open(io.BytesIO(raw)))
            if width < image.width:
                ratio = width / float(image.width)
                resized = image.resize((width, max(1, int(image.height * ratio))), Image.LANCZOS)
            else:
                resized = image.copy()
            buf = io.BytesIO()
            rgb = resized if resized.mode in ("RGB", "L") else resized.convert("RGB")
            ext = Path(key).suffix.lower()
            if ext == ".webp":
                rgb.save(buf, format="WEBP", quality=85, method=4)
                ctype = "image/webp"
            elif ext == ".png":
                rgb.save(buf, format="PNG", optimize=True)
                ctype = "image/png"
            else:
                rgb.save(buf, format="JPEG", quality=85, optimize=True, progressive=True)
                ctype = "image/jpeg"
            body = buf.getvalue()
            s3.put_object(
                Bucket=BUCKET,
                Key=key,
                Body=body,
                ContentType=ctype,
                CacheControl="public, max-age=31536000",
            )
            vcode = requests.get(u, headers={"Range": "bytes=0-32"}, timeout=20).status_code
            print(f"  put {key[-55:]} verify={vcode}")
            if vcode not in (200, 206):
                still.append({"id": rid, "label": label, "verify": vcode})

    Path("staging/reports/company-73-force-variants.json").write_text(
        json.dumps({"still": still}, indent=2) + "\n", encoding="utf-8"
    )
    print("still_bad", len(still))
    return 0 if not still else 1


if __name__ == "__main__":
    raise SystemExit(main())
