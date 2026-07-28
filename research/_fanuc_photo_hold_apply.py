#!/usr/bin/env python3
"""Fix FANUC photo holds left in To Review (company 189).

Targets:
  4119 CRX-30iA/L  — replace CRX-10iA/L-labeled duo with OEM CRX-30iA still
  1754 CRX-20iA/L  — promote clean OEM beauty; demote Southwestern PTS overlay
  4115 M-800iA/60W — attach OEM still arm-labeled M-800iA/60W
  4117 M-810iA/45  — still no model-specific still (series page is 190/270 only)

Usage:
  python _fanuc_photo_hold_apply.py
  python _fanuc_photo_hold_apply.py --apply
"""
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

_RESEARCH = Path(__file__).resolve().parent
ROOT = _RESEARCH.parent.parent
SERVER = ROOT / "robotaigeek-server"
sys.path.insert(0, str(_RESEARCH))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env
from api_client import ResearchApiClient

load_research_env()

CAND = _RESEARCH / "staging" / "media" / "fanuc-photo-fix" / "candidates"
FINAL = _RESEARCH / "staging" / "media" / "fanuc-photo-fix" / "final"
FINAL.mkdir(parents=True, exist_ok=True)

CDN = "https://cdn.robotaigeek.com"
BUCKET = "cdn.robotaigeek.com"
PREFIX = "research-staging/fanuc"

# Visually verified sources (arm label / no wrong-model text)
FIXES = {
    4119: {
        "name": "CRX-30iA-L",
        "src": CAND / "crx30_4_a3b87a12.jpg",  # Inverted-CRX-30iA-Hood-Opener
        "note": "OEM CRX-30iA inverted hood-opener still; arm labeled CRX-30iA (replaced CRX-10iA/L duo)",
        "keep_old_as_gallery": False,
    },
    1754: {
        "name": "CRX-20iA-L",
        "src": CAND / "pick_crx20_beauty.png",
        "note": "OEM CRX-20iA/L beauty shot; arm labeled CRX-20iA/L; demoted Southwestern PTS overlay",
        "keep_old_as_gallery": True,
    },
    4115: {
        "name": "M-800iA-60W",
        "src": CAND / "pick_m810_close.jpg",  # nav name misleading; arm says M-800iA/60W
        "note": "OEM still arm-labeled M-800iA/60W (craft path under m-810 nav; verified label)",
        "keep_old_as_gallery": False,
        "clear_image_todo": True,
    },
}

IMAGE_TODO_4117 = """[IMAGE TO-DO — no hero, deliberate]
M-810iA/45 — no OEM model-specific still found.
fanucamerica.com/products/series/m-810 documents M-810/190-20B + M-810/270-27B only (not iA/45).
Series page photos are those heavy machining models / an M-800iA/60W still misfiled under m-810 — do not reuse.
ACTION FOR TEAM: source a licensed M-810iA/45-specific still from OEM archive, or merge/retire if the SKU is obsolete.
Do NOT substitute M-800iA/60W, M-810/190, or M-810/270 renders.
---
"""


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


def to_jpeg(src: Path, dst: Path, max_edge: int = 2000) -> tuple[Path, str]:
    im = Image.open(src).convert("RGB")
    if max(im.size) > max_edge:
        im.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
    dst.parent.mkdir(parents=True, exist_ok=True)
    im.save(dst, quality=92, optimize=True)
    md5 = hashlib.md5(dst.read_bytes()).hexdigest()
    return dst, md5


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
    raise RuntimeError(f"CDN verify failed {url} status={getattr(r, 'status_code', None)}")


def build_plan() -> dict:
    plan = {}
    hashes: dict[str, int] = {}
    for rid, meta in FIXES.items():
        src = meta["src"]
        assert src.is_file(), src
        dst = FINAL / f"{rid}-{meta['name']}-hero.jpg"
        path, md5 = to_jpeg(src, dst)
        if md5 in hashes:
            raise SystemExit(f"DUPLICATE HASH {md5} between {hashes[md5]} and {rid}")
        hashes[md5] = rid
        plan[rid] = {
            **meta,
            "path": str(path),
            "md5": md5,
            "size_bytes": path.stat().st_size,
        }
        print(f"FINAL {rid} {meta['name']} md5={md5[:12]} bytes={path.stat().st_size}")
    return plan


def strip_image_todo(notes: str) -> str:
    text = notes or ""
    if "[IMAGE TO-DO" not in text:
        return text
    # drop first IMAGE TO-DO block through --- separator if present
    start = text.find("[IMAGE TO-DO")
    if start < 0:
        return text
    rest = text[start:]
    end = rest.find("\n---\n")
    if end >= 0:
        removed = rest[: end + 5]
        return (text[:start] + rest[end + 5 :]).strip()
    # else drop through end of first paragraph block
    return text[:start].strip()


def apply(plan: dict) -> None:
    s3 = s3_client()
    client = ResearchApiClient()
    report: dict = {"patched": [], "held": [], "errors": []}

    for rid, row in plan.items():
        try:
            full = client._get(f"robots/robots/{rid}/")
            old_img = (full.get("s3_image") or full.get("image") or "").strip()
            local = Path(row["path"])
            key = f"{PREFIX}/{rid}-{row['name'].lower()}-hero.jpg"
            hero = upload(s3, local, key)
            images = [hero]
            if row.get("keep_old_as_gallery") and old_img and old_img != hero:
                images.append(old_img)
            payload: dict = {
                "image": hero,
                "images": images,
                "s3_image": None,
                "availability_status": 11,
            }
            if row.get("clear_image_todo"):
                payload["notes"] = strip_image_todo(full.get("notes") or "")
            client._patch(f"robots/robots/{rid}/", payload)
            verify = client._get(f"robots/robots/{rid}/")
            api_img = verify.get("image") or verify.get("s3_image") or ""
            print(f"PATCHED {rid} {row['name']} -> {api_img[:90]}")
            report["patched"].append(
                {
                    "id": rid,
                    "name": row["name"],
                    "hero": hero,
                    "api_image": api_img,
                    "md5": row["md5"],
                    "note": row["note"],
                    "gallery": images,
                }
            )
            time.sleep(0.2)
        except Exception as e:
            print(f"ERROR {rid}: {e}")
            report["errors"].append({"id": rid, "error": str(e)})

    # Refresh IMAGE TO-DO on 4117
    try:
        full = client._get("robots/robots/4117/")
        notes = full.get("notes") or ""
        if "M-810/190" not in notes:
            # replace prior IMAGE TO-DO with updated reason
            cleaned = strip_image_todo(notes)
            new_notes = IMAGE_TODO_4117 + (("\n" + cleaned) if cleaned else "")
            client._patch(
                "robots/robots/4117/",
                {"notes": new_notes, "availability_status": 11},
            )
        report["held"].append(
            {
                "id": 4117,
                "name": "M-810iA/45",
                "reason": "No OEM iA/45 still; series page is M-810/190 + M-810/270 only",
            }
        )
        print("HELD 4117 M-810iA/45 — IMAGE TO-DO refreshed")
    except Exception as e:
        report["errors"].append({"id": 4117, "error": str(e)})

    out = _RESEARCH / "staging" / "reports" / "fanuc-photo-hold-apply.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("wrote", out)
    print(
        "done patched=",
        len(report["patched"]),
        "held=",
        len(report["held"]),
        "errors=",
        len(report["errors"]),
    )


def main() -> int:
    apply_flag = "--apply" in sys.argv
    plan = build_plan()
    if not apply_flag:
        print("dry-run only; pass --apply to upload+patch")
        return 0
    apply(plan)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
