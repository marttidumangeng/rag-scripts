"""Replace Servi Plus (2686) duo marketing hero with Servi-only OEM still."""
from __future__ import annotations

import hashlib
import io
import os
import re
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
PREFIX = "research-staging/bear"
UA = {"User-Agent": "Mozilla/5.0"}
RID = 2686
OEM = "https://www.bearrobotics.ai/servi-plus"


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
    return f"{resp.status_code} {resp.text[:120]}"


def main() -> int:
    _load_aws()
    html = requests.get(OEM, headers=UA, timeout=60).text
    urls = sorted(
        set(re.findall(r"https?://[^\"'\s>]+\.(?:webp|jpg|jpeg|png)", html, flags=re.I))
    )
    print(f"found {len(urls)} urls")
    scored: list[tuple[int, str]] = []
    for u in urls:
        low = u.lower()
        if any(x in low for x in ("carti", "compare", "duo", "clean", "favicon", "logo")):
            continue
        score = 0
        if "servi" in low and "plus" in low:
            score += 3
        elif "servi" in low:
            score += 2
        if "hero" in low or "header" in low:
            score += 1
        if score:
            scored.append((score, u.split("?")[0] if "format=" not in u else u))
    scored = sorted(set(scored), reverse=True)
    for s, u in scored[:20]:
        print(f"  score={s} {u[:130]}")

    pick = None
    for _, u in scored[:12]:
        try:
            raw = requests.get(u, headers=UA, timeout=60).content
            im = Image.open(io.BytesIO(raw)).convert("RGB")
        except Exception as e:
            print("skip", e)
            continue
        w, h = im.size
        print(f"  try {w}x{h} {len(raw)} {u[:90]}")
        if h < 250 or w / max(h, 1) > 3.5:
            continue
        if w * h < 150_000:
            continue
        pick = (u, im)
        break

    if not pick:
        print("no suitable image — listing all servi urls for manual pick")
        for u in urls:
            if "servi" in u.lower():
                print(" ", u[:140])
        return 1

    src, im = pick
    local = OUT / "servi-plus-hero.jpg"
    im.save(local, quality=92, optimize=True)
    digest = hashlib.sha1(local.read_bytes()).hexdigest()[:10]
    key = f"{PREFIX}/servi-plus-hero-{digest}-20260720.jpg"
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
            print("OK", cdn, len(c.content), "from", src[:100])
            break
        time.sleep(0.4)
    else:
        raise RuntimeError(cdn)

    client = ResearchApiClient()
    existing = client._get(f"robots/robots/{RID}/")
    old = existing.get("image") or existing.get("s3_image") or ""
    photos = [cdn]
    if old and old != cdn:
        photos.append(old)
    for p in existing.get("photos") or []:
        url = p if isinstance(p, str) else (p.get("url") or p.get("image") or "")
        if url and url not in photos:
            photos.append(url)
    client._patch(f"robots/robots/{RID}/", {"image": cdn, "photos": photos[:8]})
    print("copy-media", copy_media(RID))
    print("patched", RID)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
