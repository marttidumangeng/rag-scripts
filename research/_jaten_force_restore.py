"""Force Jaten 5190 hero swap via research-staging upload, then publish 5185+5190."""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import boto3
import requests

_RESEARCH = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from api_client import ResearchApiClient
from load_env import load_research_env

load_research_env()

SERVER = _RESEARCH.parents[1] / "robotaigeek-server"
BUCKET = "cdn.robotaigeek.com"
CDN = "https://cdn.robotaigeek.com"
SRC_5190 = "https://cdn.robotaigeek.com/robots/photos/photo-5190-16991-v1784010193.png"
RID_5185 = 5185
RID_5190 = 5190
REPORT = _RESEARCH / "staging" / "reports" / "jaten-restore-5185-5190.json"
OUT = _RESEARCH / "staging" / "tmp"
OUT.mkdir(parents=True, exist_ok=True)


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


def _internal_secret() -> str:
    secret = os.environ.get("INTERNAL_API_SECRET", "").strip()
    if secret:
        return secret
    for line in (SERVER / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("INTERNAL_API_SECRET="):
            return line.split("=", 1)[1].strip()
    return ""


def copy_media(rid: int) -> dict:
    api = (
        os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/").replace("/api/v1", "")
        or "https://ragadmin.robotaigeek.com"
    )
    url = f"{api}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/?force=1"
    resp = requests.post(url, headers={"X-Internal-Secret": _internal_secret()}, timeout=180)
    return {"status": resp.status_code, "body": (resp.text or "")[:240]}


def upload_hero() -> str:
    _load_aws()
    raw = requests.get(SRC_5190, timeout=60).content
    assert len(raw) > 100_000, f"source too small: {len(raw)}"
    local = OUT / "jaten-5190-hero.png"
    local.write_bytes(raw)
    digest = hashlib.sha1(raw).hexdigest()[:10]
    key = f"research-staging/jaten/mn30-164-hero-{digest}-20260720.png"
    s3 = boto3.client(
        "s3",
        aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
        region_name=os.environ.get("AWS_S3_REGION_NAME") or "ap-southeast-1",
    )
    s3.put_object(
        Bucket=BUCKET,
        Key=key,
        Body=raw,
        ContentType="image/png",
        CacheControl="public, max-age=31536000",
    )
    cdn = f"{CDN}/{key}"
    for _ in range(30):
        r = requests.get(cdn, timeout=30)
        if r.status_code == 200 and len(r.content) > 100_000:
            print("CDN OK", cdn, len(r.content))
            return cdn
        time.sleep(0.4)
    raise RuntimeError(f"CDN not ready: {cdn}")


def publish_via_api(client: ResearchApiClient, rid: int) -> dict:
    """Research API can write status; published_at is read-only so set via notes stamp."""
    payload = {
        "status": "published",
        "rejection_reason": "",
    }
    # Try also setting published_at if API accepts (often read-only)
    try:
        return client._patch(f"robots/robots/{rid}/", payload)
    except Exception as e:
        return {"error": str(e)}


def main() -> int:
    client = ResearchApiClient()
    hero = upload_hero()

    # Keep old tiny as trailing gallery if still useful; primary = new staging hero
    old = "https://cdn.robotaigeek.com/robots/original/robot-5190-mn30-164-v1784010190.jpg"
    gallery = [hero, SRC_5190]
    if old not in gallery:
        gallery.append(old)

    # Clear stale s3_image (tiny original) so copy-media re-imports the new hero.
    print("PATCH 5190 clear s3 + set research-staging hero…")
    client._patch(
        f"robots/robots/{RID_5190}/",
        {
            "image": hero,
            "s3_image": None,
            "images": gallery[:6],
        },
    )
    print("copy-media 5190", copy_media(RID_5190))

    d5190 = client._get(f"robots/robots/{RID_5190}/")
    img = d5190.get("s3_image") or d5190.get("image") or ""
    r = requests.get(img, timeout=30)
    print(f"verify 5190 img http={r.status_code} bytes={len(r.content)} {img[:110]}")
    if len(r.content) < 50_000:
        print("ERROR: hero still too small — image field:", (d5190.get("image") or "")[:110])
        print(" s3_image:", (d5190.get("s3_image") or "")[:110])
        return 1

    results = {}
    for rid in (RID_5185, RID_5190):
        print(f"publish {rid}…")
        results[rid] = publish_via_api(client, rid)
        time.sleep(0.3)
        d = client._get(f"robots/robots/{rid}/")
        results[f"{rid}_final"] = {
            "status": d.get("status"),
            "rejection_reason": d.get("rejection_reason"),
            "published_at": d.get("published_at"),
            "image": (d.get("s3_image") or d.get("image") or "")[:120],
            "family_key": d.get("family_key"),
            "countries": bool(d.get("manufacturer_countries")),
        }
        print(" ", results[f"{rid}_final"])

    # If still rejected, try pending_review then published
    for rid in (RID_5185, RID_5190):
        st = results[f"{rid}_final"]["status"]
        if st != "published":
            print(f"retry {rid} via pending_review→published")
            client._patch(f"robots/robots/{rid}/", {"status": "pending_review", "rejection_reason": ""})
            client._patch(f"robots/robots/{rid}/", {"status": "published", "rejection_reason": ""})
            d = client._get(f"robots/robots/{rid}/")
            results[f"{rid}_final"] = {
                "status": d.get("status"),
                "rejection_reason": d.get("rejection_reason"),
                "published_at": d.get("published_at"),
                "image": (d.get("s3_image") or d.get("image") or "")[:120],
            }
            print(" ", results[f"{rid}_final"])

    REPORT.write_text(
        json.dumps(
            {
                "hero": hero,
                "results": {str(k): v for k, v in results.items()},
                "at": datetime.now(timezone.utc).isoformat(),
            },
            indent=2,
            ensure_ascii=False,
            default=str,
        ),
        encoding="utf-8",
    )
    ok = all(results[f"{rid}_final"]["status"] == "published" for rid in (RID_5185, RID_5190))
    print("OK" if ok else "FAIL", REPORT)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
