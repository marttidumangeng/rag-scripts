"""Replace Foundation Phantom (2883) logo primary with OEM product still."""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

import boto3
import requests
from PIL import Image

_RESEARCH = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient
from import_staging import import_staging, resolve_created_by_id

SERVER = _RESEARCH.parents[1] / "robotaigeek-server"
OUT = _RESEARCH / "staging" / "tmp" / "foundation"
OUT.mkdir(parents=True, exist_ok=True)
BUCKET = "cdn.robotaigeek.com"
CDN = "https://cdn.robotaigeek.com"
UA = {"User-Agent": "Mozilla/5.0"}
RID = 2883


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


def copy_media(rid: int) -> str:
    secret = os.environ.get("INTERNAL_API_SECRET", "").strip()
    if not secret:
        for line in (SERVER / ".env").read_text(encoding="utf-8").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                secret = line.split("=", 1)[1].strip()
    api = (
        os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/").replace("/api/v1", "")
        or "https://ragadmin.robotaigeek.com"
    )
    url = f"{api}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/?force=1"
    resp = requests.post(url, headers={"X-Internal-Secret": secret}, timeout=180)
    return f"{resp.status_code} {resp.text[:160]}"


def main() -> int:
    _load_aws()
    pages = ["https://foundation.bot/phantom", "https://foundation.bot/"]
    urls: list[str] = []
    for page in pages:
        html = requests.get(page, headers=UA, timeout=60).text
        found = re.findall(
            r"https?://[^\"'\s>]+\.(?:webp|jpg|jpeg|png|avif)",
            html,
            flags=re.I,
        )
        for rel in re.findall(
            r'["\'](/[^"\']+\.(?:webp|jpg|jpeg|png|avif))["\']', html, flags=re.I
        ):
            found.append(urljoin(page, rel))
        # next/image style
        for m in re.findall(r"url\\?u?=([^&\"']+)", html):
            if m.startswith("http") and any(
                m.lower().endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp")
            ):
                found.append(m)
        print(page, len(found))
        urls.extend(found)

    scored: list[tuple[int, str]] = []
    for u in sorted(set(urls)):
        low = u.lower()
        if any(
            x in low
            for x in ("logo", "favicon", "icon", "sprite", "wordmark", "mk1", "font")
        ):
            continue
        score = 0
        if "phantom" in low:
            score += 2
        if any(x in low for x in ("robot", "humanoid", "hero", "product", "media")):
            score += 2
        if "cdn" in low or "uploads" in low or "images" in low or "assets" in low:
            score += 1
        if score:
            scored.append((score, u))
    scored.sort(reverse=True)
    for s, u in scored[:30]:
        print(f"  score={s} {u[:150]}")

    pick = None
    for _, u in scored[:25]:
        try:
            raw = requests.get(u, headers=UA, timeout=60).content
            im = Image.open(io.BytesIO(raw)).convert("RGB")
        except Exception as e:
            print("skip", str(e)[:80])
            continue
        w, h = im.size
        print(f"  try {w}x{h} {len(raw)} {u[:110]}")
        if w < 500 or h < 400 or len(raw) < 20_000:
            continue
        # Prefer portrait/standing robot over ultra-wide logos
        if w / max(h, 1) > 2.8:
            continue
        pick = (u, im)
        break

    if not pick:
        print("NO IMAGE — dump all urls with phantom")
        for u in sorted(set(urls)):
            if "phantom" in u.lower() or "robot" in u.lower():
                print(" ", u[:160])
        return 1

    src, im = pick
    local = OUT / "phantom-hero.jpg"
    im.save(local, quality=92, optimize=True)
    digest = hashlib.sha1(local.read_bytes()).hexdigest()[:10]
    key = f"research-staging/foundation/phantom-hero-{digest}-20260720.jpg"
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

    Image.open(io.BytesIO(requests.get(cdn, headers=UA, timeout=30).content)).convert(
        "RGB"
    ).save(OUT / "phantom-preview.jpg", quality=85)

    client = ResearchApiClient()
    client._patch(
        f"robots/robots/{RID}/",
        {
            "image": cdn,
            "photos": [cdn],
            "s3_image": None,
            "manufacturer_countries": [20],
            "description": (
                "Phantom is Foundation's first production humanoid robot, designed for "
                "strong, fluid motion in human environments with cycloid actuators and "
                "a modular architecture."
            ),
            "purpose": (
                "General-purpose humanoid manipulation and locomotion\n"
                "Autonomous work in human-scale industrial environments"
            ),
            "notes": "[AI Research] Phantom hero replaced logo→OEM product still 2026-07-20",
        },
    )
    print("copy-media", copy_media(RID))
    after = client._get(f"robots/robots/{RID}/")
    print("image now", after.get("image"))
    print("from", src[:120])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
