"""Find and upload OEM xPizza Cube product hero; replace logo primary on 5289."""
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
from import_staging import import_staging, resolve_created_by_id
import json

SERVER = _RESEARCH.parents[1] / "robotaigeek-server"
OUT = _RESEARCH / "staging" / "tmp" / "xrobotics"
OUT.mkdir(parents=True, exist_ok=True)
BUCKET = "cdn.robotaigeek.com"
CDN = "https://cdn.robotaigeek.com"
UA = {"User-Agent": "Mozilla/5.0"}
RID = 5289


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
    pages = [
        "https://www.xrobotics.io/",
        "https://www.xrobotics.io/specification",
        "https://pizzacube.us/",
    ]
    urls: list[str] = []
    for page in pages:
        html = requests.get(page, headers=UA, timeout=60).text
        found = re.findall(
            r"https?://[^\"'\s>]+\.(?:webp|jpg|jpeg|png)",
            html,
            flags=re.I,
        )
        # also relative uploads
        for rel in re.findall(r'["\'](/[^"\']+\.(?:webp|jpg|jpeg|png))["\']', html, flags=re.I):
            from urllib.parse import urljoin

            found.append(urljoin(page, rel))
        print(page, "imgs", len(found))
        urls.extend(found)

    scored: list[tuple[int, str]] = []
    for u in sorted(set(urls)):
        low = u.lower()
        if any(x in low for x in ("logo", "favicon", "icon", "sprite", "avatar")):
            continue
        score = 0
        if "pizza" in low or "cube" in low or "xpizza" in low:
            score += 3
        if "product" in low or "hero" in low or "machine" in low:
            score += 2
        if "cdn.prod.website" in low or "uploads" in low or "images" in low:
            score += 1
        if score:
            scored.append((score, u))
    scored.sort(reverse=True)
    for s, u in scored[:25]:
        print(f"  score={s} {u[:140]}")

    pick = None
    for _, u in scored[:20]:
        try:
            raw = requests.get(u, headers=UA, timeout=60).content
            im = Image.open(io.BytesIO(raw)).convert("RGB")
        except Exception as e:
            print("skip", e)
            continue
        w, h = im.size
        print(f"  try {w}x{h} {len(raw)} {u[:100]}")
        # skip tiny logos / ultra-wide banners
        if w < 400 or h < 300 or len(raw) < 15_000:
            continue
        if w / max(h, 1) > 3.2:
            continue
        # skip near-solid logo-like small files already filtered by size
        pick = (u, im)
        break

    if not pick:
        print("NO PRODUCT IMAGE FOUND")
        return 1

    src, im = pick
    local = OUT / "xpizza-hero.jpg"
    im.save(local, quality=92, optimize=True)
    digest = hashlib.sha1(local.read_bytes()).hexdigest()[:10]
    key = f"research-staging/xrobotics/xpizza-cube-hero-{digest}-20260720.jpg"
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
            print("CDN OK", cdn, len(c.content), "from", src[:100])
            break
        time.sleep(0.4)
    else:
        raise RuntimeError(cdn)

    # preview
    Image.open(io.BytesIO(requests.get(cdn, headers=UA, timeout=30).content)).convert(
        "RGB"
    ).save(OUT / "xpizza-preview.jpg", quality=85)

    row = {
        "id": RID,
        "name": "xPizza Cube",
        "company_slug": "xrobotics",
        "company_name": "XRobotics",
        "manufacturer_country_code": "US",
        "image": cdn,
        "images": [cdn],
        "url": "https://www.xrobotics.io/specification",
        "availability_status": 11,
    }
    path = _RESEARCH / "staging" / "robots" / "xrobotics" / "xpizza-cube-photo.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(row, indent=2), encoding="utf-8")
    print(
        import_staging(
            path,
            dry_run=False,
            patch=True,
            force_overwrite=True,
            replace_media=True,
            status="pending_review",
            created_by_id=resolve_created_by_id(1),
            skip_company_update=True,
        )
    )
    client = ResearchApiClient()
    client._patch(
        f"robots/robots/{RID}/",
        {"image": cdn, "s3_image": None, "manufacturer_countries": [20]},
    )
    print("copy-media", copy_media(RID))
    after = client._get(f"robots/robots/{RID}/")
    print("image now", after.get("image"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
