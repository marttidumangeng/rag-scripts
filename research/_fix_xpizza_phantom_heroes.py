"""Promote Foundation Phantom full-body gallery still + xPizza closed Hero-Size."""
from __future__ import annotations

import hashlib
import io
import os
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
BUCKET = "cdn.robotaigeek.com"
CDN = "https://cdn.robotaigeek.com"
UA = {"User-Agent": "Mozilla/5.0"}

FIXES = [
    {
        "id": 2883,
        "src": "https://framerusercontent.com/images/2w3k3rSCuwTu8rDr2OvOnUEznk.png?width=2032&height=4938",
        "key_prefix": "research-staging/foundation/phantom-fullbody",
        "out": _RESEARCH / "staging" / "tmp" / "foundation" / "phantom-fullbody.jpg",
    },
    {
        "id": 5289,
        "src": "https://cdn.prod.website-files.com/67292a4f5ed6a199622adaa7/6a466c1d745604e571f72f7a_Hero-Size.png",
        "key_prefix": "research-staging/xrobotics/xpizza-cube-closed",
        "out": _RESEARCH / "staging" / "tmp" / "xrobotics" / "xpizza-closed.jpg",
    },
]


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


def upload(s3, src: str, key_prefix: str, out: Path) -> str:
    raw = requests.get(src, headers=UA, timeout=90).content
    im = Image.open(io.BytesIO(raw)).convert("RGB")
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out, quality=92, optimize=True)
    digest = hashlib.sha1(out.read_bytes()).hexdigest()[:10]
    key = f"{key_prefix}-{digest}-20260720.jpg"
    s3.put_object(
        Bucket=BUCKET,
        Key=key,
        Body=out.read_bytes(),
        ContentType="image/jpeg",
        CacheControl="public, max-age=31536000",
    )
    cdn = f"{CDN}/{key}"
    for _ in range(25):
        c = requests.get(cdn, headers=UA, timeout=30)
        if c.status_code == 200 and len(c.content) > 5000:
            print("OK", cdn, len(c.content), im.size)
            return cdn
        time.sleep(0.4)
    raise RuntimeError(cdn)


def main() -> int:
    _load_aws()
    s3 = boto3.client(
        "s3",
        aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
        region_name=os.environ.get("AWS_S3_REGION_NAME") or "ap-southeast-1",
    )
    client = ResearchApiClient()
    for fix in FIXES:
        cdn = upload(s3, fix["src"], fix["key_prefix"], fix["out"])
        existing = client._get(f"robots/robots/{fix['id']}/")
        old = existing.get("image") or ""
        photos = [cdn]
        if old and old != cdn:
            photos.append(old)
        for p in existing.get("photos") or []:
            url = p if isinstance(p, str) else (p.get("url") or p.get("image") or "")
            if url and url not in photos:
                photos.append(url)
        client._patch(
            f"robots/robots/{fix['id']}/",
            {"image": cdn, "photos": photos[:8], "s3_image": None},
        )
        print("copy", fix["id"], copy_media(fix["id"]))
        after = client._get(f"robots/robots/{fix['id']}/")
        print("image", after.get("image"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
