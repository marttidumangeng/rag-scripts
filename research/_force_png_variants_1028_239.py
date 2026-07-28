#!/usr/bin/env python3
"""Force-upload missing PNG JPEG-map thumbs for Noblelift 1028 + RobCo 239.

repair-images writes .jpg/.webp and treats a width as done if WebP exists, but
build_variant_urls_from_key keeps .png for PNG sources — so 1280.png 403s.
"""
from __future__ import annotations

import io
import json
import os
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

BUCKET = "cdn.robotaigeek.com"
REPORT = Path("staging/reports/company-1028-239-variant-recheck.json")
OUT = Path("staging/reports/company-1028-239-force-png-variants.json")


def put_png_variant(s3, original_url: str, dead_url: str) -> dict:
    key = urlparse(dead_url).path.lstrip("/")
    # width from _wNNNN
    import re

    m = re.search(r"_w(\d+)\.", key)
    width = int(m.group(1)) if m else 1280
    raw = requests.get(original_url, timeout=90).content
    image = ImageOps.exif_transpose(Image.open(io.BytesIO(raw)))
    if width < image.width:
        ratio = width / float(image.width)
        resized = image.resize((width, max(1, int(image.height * ratio))), Image.LANCZOS)
    else:
        resized = image.copy()
    buf = io.BytesIO()
    rgb = resized if resized.mode in ("RGB", "L") else resized.convert("RGB")
    rgb.save(buf, format="PNG", optimize=True)
    body = buf.getvalue()
    s3.put_object(
        Bucket=BUCKET,
        Key=key,
        Body=body,
        ContentType="image/png",
        CacheControl="public, max-age=31536000",
    )
    code = requests.get(dead_url, headers={"Range": "bytes=0-32"}, timeout=20).status_code
    return {"key": key, "bytes": len(body), "verify": code, "src_size": image.size}


def main() -> int:
    data = json.loads(REPORT.read_text(encoding="utf-8"))
    c = ResearchApiClient()
    s3 = boto3.client(
        "s3",
        region_name=os.environ.get("AWS_S3_REGION_NAME", "ap-southeast-1"),
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
    )

    results = []
    for group in ("noblelift_still_dead", "robco_still_dead"):
        for entry in data.get(group) or []:
            rid = entry["id"]
            r = c._get(f"robots/robots/{rid}/")
            # map photo id -> s3 url; primary uses robot s3
            photo_map = {}
            for p in r.get("photos") or []:
                if isinstance(p, dict) and p.get("id"):
                    photo_map[int(p["id"])] = (p.get("s3_image") or p.get("url") or "").strip()
            primary = (r.get("s3_image") or r.get("image") or "").strip()

            for dead in entry.get("dead") or []:
                label = dead["label"]
                url = dead["url"]
                if not url.endswith(".png"):
                    print(f"skip non-png {label}")
                    continue
                if label.startswith("primary_"):
                    src = primary
                elif "photo_jpg#" in label or "photo_" in label:
                    # photo_jpg#22270:1280
                    pid = int(label.split("#", 1)[1].split(":", 1)[0])
                    src = photo_map.get(pid) or primary
                else:
                    src = primary
                if not src:
                    print(f"no src for {rid} {label}")
                    results.append({"id": rid, "label": label, "error": "no_src"})
                    continue
                try:
                    res = put_png_variant(s3, src, url)
                    print(f"ok {rid} {label} verify={res['verify']} {res['key'][-60:]}")
                    results.append({"id": rid, "label": label, **res})
                except Exception as e:
                    print(f"FAIL {rid} {label}: {e}")
                    results.append({"id": rid, "label": label, "error": str(e)})

    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    bad = [x for x in results if x.get("verify") not in (200, 206) or x.get("error")]
    print(f"done {len(results)} uploads, still_bad={len(bad)} -> {OUT}")
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
