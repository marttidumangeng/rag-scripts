#!/usr/bin/env python3
"""Stage SIASUN (1424) pending heroes onto owned CDN so approve can copy-media.

Approve fails when robots still point at en.siasun.com (esp. Chinese-filename
URLs the server cannot download). Download locally → research-staging/siasun/
→ PATCH image/images + clear s3_image.

Usage:
  python fix_siasun_cdn_heroes.py
  python fix_siasun_cdn_heroes.py --apply
  python fix_siasun_cdn_heroes.py --apply --ids 5549
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

import boto3
import requests
from PIL import Image

_HERE = Path(__file__).resolve().parent
ROOT = _HERE.parent.parent
SERVER = ROOT / "robotaigeek-server"
sys.path.insert(0, str(_HERE))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env
from api_client import ResearchApiClient

load_research_env(local="--local" in sys.argv)

COMPANY_ID = 1424
CDN = "https://cdn.robotaigeek.com"
BUCKET = "cdn.robotaigeek.com"
PREFIX = "research-staging/siasun"
OUT = _HERE / "staging" / "media" / "siasun-cdn"
OUT.mkdir(parents=True, exist_ok=True)
UA = {
    "User-Agent": "Mozilla/5.0 (compatible; RobotAIGeekResearch/1.0)",
    "Referer": "https://en.siasun.com/",
}


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
        if k.startswith("AWS_") or not str(os.environ.get(k) or "").strip():
            os.environ[k] = v


def s3_client():
    _load_dotenv(SERVER / ".env")
    os.environ["AWS_STORAGE_BUCKET_NAME"] = BUCKET
    region = os.environ.get("AWS_S3_REGION_NAME") or "ap-southeast-1"
    return boto3.client(
        "s3",
        region_name=region,
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
    )


def encode_url(url: str) -> str:
    parts = urlsplit(url)
    segs = [quote(seg, safe=".-_~%") for seg in parts.path.split("/")]
    path = "/".join(segs)
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


def download(url: str) -> bytes:
    last_err: Exception | None = None
    for u in (url, encode_url(url)):
        try:
            r = requests.get(u, timeout=60, headers=UA)
            if r.status_code == 200 and len(r.content) > 2000:
                magic = r.content[:12]
                if magic[:3] == b"\xff\xd8\xff" or magic[:8] == b"\x89PNG\r\n\x1a\n" or magic[:4] == b"RIFF":
                    return r.content
            last_err = RuntimeError(f"HTTP {r.status_code} len={len(r.content)}")
        except Exception as e:  # noqa: BLE001
            last_err = e
    raise RuntimeError(f"download failed {url}: {last_err}")


def to_jpeg(data: bytes, max_edge: int = 2000) -> bytes:
    im = Image.open(io.BytesIO(data)).convert("RGB")
    if max(im.size) > max_edge:
        im.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=90, optimize=True)
    return buf.getvalue()


def slugify(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", (name or "").strip()).strip("-").lower()
    return (s or "robot")[:60]


def upload(s3, body: bytes, key: str) -> str:
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
        time.sleep(0.35)
    raise RuntimeError(f"CDN verify failed {url}")


def needs_staging(full: dict) -> bool:
    img = (full.get("image") or "").strip()
    s3 = (full.get("s3_image") or "").strip()
    if s3 and "cdn.robotaigeek.com" in s3:
        return False
    if img and "cdn.robotaigeek.com" in img and "research-staging" in img:
        # already staged — still may need s3_image link on approve; OK to skip re-upload
        return False
    if img and "cdn.robotaigeek.com" in img:
        return False
    return bool(img)


def primary_url(full: dict) -> str:
    img = (full.get("image") or "").strip()
    if img:
        return img
    for ph in full.get("photos") or []:
        if ph.get("is_primary") and ph.get("url"):
            return ph["url"]
    for ph in full.get("photos") or []:
        if ph.get("url"):
            return ph["url"]
    return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--ids", type=int, nargs="*")
    args = ap.parse_args()

    client = ResearchApiClient()
    robots = [
        r
        for r in client.list_robots_for_company(COMPANY_ID)
        if (r.get("status") or "") == "pending_review"
    ]
    if args.ids:
        want = set(args.ids)
        robots = [r for r in robots if int(r["id"]) in want]
    print(f"pending={len(robots)}")

    plan = []
    errors = []
    for r in robots:
        rid = int(r["id"])
        full = client._get(f"robots/robots/{rid}/")
        if not needs_staging(full):
            print(f"  skip {rid} already owned CDN")
            continue
        src = primary_url(full)
        if not src:
            errors.append({"id": rid, "error": "no image url"})
            print(f"  NOIMG {rid} {r.get('name')}")
            continue
        plan.append({"id": rid, "name": r.get("name"), "src": src})
        time.sleep(0.05)

    print(f"to_stage={len(plan)} errors={len(errors)}")
    out = _HERE / "staging" / "reports" / "siasun-cdn-plan.json"
    out.write_text(json.dumps({"plan": plan, "errors": errors}, indent=2, ensure_ascii=False), encoding="utf-8")
    print("wrote", out)

    if not args.apply:
        print("dry-run; pass --apply to upload+patch")
        for p in plan[:8]:
            print(f"  {p['id']} {p['name'][:40]} <- {p['src'][-60:]}")
        return 0

    s3 = s3_client()
    report = {"patched": [], "errors": list(errors)}
    hashes: dict[str, int] = {}
    for p in plan:
        rid = p["id"]
        try:
            raw = download(p["src"])
            jpeg = to_jpeg(raw)
            md5 = hashlib.md5(jpeg).hexdigest()
            # allow same product family hash across robots only if unavoidable;
            # still upload per-robot key so approve has a reachable owned URL.
            if md5 in hashes:
                print(f"  WARN same-bytes {rid} shares hash with {hashes[md5]}")
            hashes[md5] = rid
            local = OUT / f"{rid}-{slugify(p['name'] or 'robot')}.jpg"
            local.write_bytes(jpeg)
            key = f"{PREFIX}/{rid}-{slugify(p['name'] or 'robot')}-hero.jpg"
            hero = upload(s3, jpeg, key)
            client._patch(
                f"robots/robots/{rid}/",
                {
                    "image": hero,
                    "images": [hero],
                    "s3_image": None,
                    "availability_status": 11,
                },
            )
            print(f"  PATCHED {rid} {p['name'][:36]} -> {hero}")
            report["patched"].append({"id": rid, "name": p["name"], "hero": hero, "md5": md5})
            time.sleep(0.12)
        except Exception as e:  # noqa: BLE001
            print(f"  ERROR {rid}: {e}")
            report["errors"].append({"id": rid, "error": str(e), "src": p["src"]})

    report_path = _HERE / "staging" / "reports" / "siasun-cdn-apply.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print("wrote", report_path)
    print(f"done patched={len(report['patched'])} errors={len(report['errors'])}")
    return 0 if not report["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
