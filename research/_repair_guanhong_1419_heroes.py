"""Repair Guanhong 1419 heroes: thefastimg OEM assets → research-staging CDN → copy-media."""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path

import requests
from PIL import Image

_RESEARCH = Path(__file__).resolve().parent
if str(_RESEARCH) not in sys.path:
    sys.path.insert(0, str(_RESEARCH))

from load_env import load_research_env

load_research_env()

from api_client import ResearchApiClient

SCRAPE = _RESEARCH / "staging" / "reports" / "guanhong-1419-scrape.json"
RAW = _RESEARCH / "staging" / "tmp" / "guanhong-heroes"
RAW.mkdir(parents=True, exist_ok=True)
PREFIX = "research-staging/guanhong"
BUCKET = "cdn.robotaigeek.com"
CDN = "https://cdn.robotaigeek.com"


def _load_aws() -> None:
    root = _RESEARCH.parents[1]  # scripts/ -> repo root? research.parent=scripts, scripts.parent=repo
    # Path(__file__).parent = scripts/research → parents[0]=research, [1]=scripts, [2]=repo
    repo = _RESEARCH.parent.parent
    for candidate in (
        repo / "robotaigeek-server" / ".env",
        repo / "robotaigeek-server" / ".env.local",
    ):
        if not candidate.is_file():
            continue
        for line in candidate.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if " #" in v:
                v = v.split(" #", 1)[0].strip()
            if k.startswith("AWS_") or not str(os.environ.get(k) or "").strip():
                os.environ[k] = v
        print(f"loaded AWS from {candidate}")
        break
    else:
        raise RuntimeError("no robotaigeek-server/.env with AWS_* found")


def download(url: str, dest: Path) -> Path:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.szghrobot.com/",
    }
    r = requests.get(url, timeout=60, headers=headers)
    r.raise_for_status()
    body = r.content
    if body.startswith(b"\xff\xd8\xff"):
        ext = ".jpg"
    elif body.startswith(b"\x89PNG"):
        ext = ".png"
    elif body[:4] == b"RIFF" and body[8:12] == b"WEBP":
        ext = ".webp"
    else:
        raise RuntimeError(f"not image magic={body[:12]!r} url={url[:80]}")
    path = dest.with_suffix(ext)
    path.write_bytes(body)
    print(f"  downloaded {path.name} md5={hashlib.md5(body).hexdigest()[:12]} bytes={len(body)}")
    return path


def upload_jpg(local: Path, key: str) -> str:
    import boto3

    _load_aws()
    jpg = local.with_suffix(".jpg")
    Image.open(local).convert("RGB").save(jpg, quality=92, optimize=True)
    s3 = boto3.client(
        "s3",
        region_name=os.environ.get("AWS_S3_REGION_NAME") or "ap-southeast-1",
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
    )
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
            print(f"  CDN OK {url} md5={hashlib.md5(r.content).hexdigest()[:12]}")
            return url
        time.sleep(0.4)
    raise RuntimeError(f"CDN verify failed {url}")


def copy_media(rid: int) -> str:
    secret = os.environ.get("INTERNAL_API_SECRET") or ""
    if not secret:
        env = _RESEARCH.parent.parent / "robotaigeek-server" / ".env"
        if env.is_file():
            for line in env.read_text(encoding="utf-8", errors="ignore").splitlines():
                if line.startswith("INTERNAL_API_SECRET="):
                    secret = line.split("=", 1)[1].strip().strip('"').strip("'")
    api = (os.environ.get("ADMIN_BASE") or "https://ragadmin.robotaigeek.com").rstrip("/")
    url = f"{api}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/?force=1"
    resp = requests.post(url, headers={"X-Internal-Secret": secret}, timeout=180)
    return f"HTTP {resp.status_code} {(resp.text or '')[:120]}"


def main() -> int:
    client = ResearchApiClient()
    rows = [r for r in json.loads(SCRAPE.read_text(encoding="utf-8")) if r.get("parse_ok")]
    mapping = {}
    for row in rows:
        rid = int(row["id"])
        src = row.get("image") or ""
        print(f"Robot {rid} {row.get('model_name')}…")
        local = download(src, RAW / f"robot-{rid}")
        key = f"{PREFIX}/{row['model_name'].lower()}-{hashlib.md5(local.read_bytes()).hexdigest()[:10]}.jpg"
        cdn = upload_jpg(local, key)
        mapping[rid] = cdn
        # Patch image to staging CDN then force copy-media
        client._patch(
            f"robots/robots/{rid}/",
            {"image": cdn, "images": [cdn]},
        )
        # bulk-import replace_media one-liner
        from import_staging import resolve_created_by_id
        from map_to_bulk_import import staging_dict_to_bulk_import_row

        bulk = staging_dict_to_bulk_import_row(
            {
                "company_slug": "shenzhen-guanhong-automation-co-ltd",
                "company_name": "Shenzhen Guanhong Automation",
                "name": row["model_name"],
                "image": cdn,
                "images": [cdn],
                "source_locale": "en",
            }
        )
        bulk["id"] = rid
        bulk["name"] = row["model_name"]
        bulk["status"] = "pending_review"
        result = client.bulk_import_robots(
            [bulk],
            update_existing=True,
            patch_existing=True,
            replace_media=True,
            status="pending_review",
            skip_company_update=True,
            created_by_id=resolve_created_by_id(1),
        )
        print(f"  import {result.get('updated_count')} created={result.get('created_count')}")
        if int(result.get("created_count") or 0):
            print("ERROR unexpected create", result)
            return 1
        msg = copy_media(rid)
        print(f"  copy-media {msg}")
        time.sleep(0.2)

    out = _RESEARCH / "staging" / "reports" / "guanhong-1419-hero-repair.json"
    out.write_text(json.dumps(mapping, indent=2) + "\n", encoding="utf-8")
    print("Wrote", out)
    # verify
    import subprocess

    subprocess.check_call(
        [sys.executable, str(_RESEARCH / "verify_cdn_images.py"), "--company-id", "1419"],
        cwd=str(_RESEARCH),
    )
    subprocess.check_call(
        [sys.executable, str(_RESEARCH / "triage_content_queue.py"), "--mark-done", "1419"],
        cwd=str(_RESEARCH),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
