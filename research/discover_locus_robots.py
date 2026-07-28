"""Enrich Locus Robotics (69) — Array soft patch + Origin/Vector heroes + OEM specs.

Pending:
  2536 Locus Array — has photo; soft enrich
  4884 Locus Origin — no photo → OEM hero
  4885 Locus Vector — no photo → OEM hero

Published leave alone: LocusBot (100) CJK shell.

Usage:
  python discover_locus_robots.py --apply
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import boto3
import requests
from PIL import Image

_RESEARCH = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient
from import_staging import import_staging, resolve_created_by_id

COMPANY_ID = 69
COMPANY_SLUG = "locus-robotics"
COMPANY_NAME = "Locus Robotics"
US_ID = 20
AVAILABLE = 11
BUCKET = "cdn.robotaigeek.com"
CDN = "https://cdn.robotaigeek.com"
PREFIX = "research-staging/locus"
SERVER = _RESEARCH.parents[1] / "robotaigeek-server"
OUT = _RESEARCH / "staging" / "tmp" / "locus-final"
OUT.mkdir(parents=True, exist_ok=True)
UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://locusrobotics.com/",
}

# Prefer warehouse photos over marketing graphics when both exist.
ORIGIN_IMGS = [
    "https://locusrobotics.com/wp-content/uploads/2023/09/42170-22-Locus-Origin-II-3Columns-0005.png",
    "https://locusrobotics.com/wp-content/uploads/2023/09/origin-highly-configurable.png",
    "https://locusrobotics.com/wp-content/uploads/2023/11/LocusRobotics_Locus-Origin-hero-Graphic-564x689@2x.png",
]
VECTOR_IMGS = [
    "https://locusrobotics.com/wp-content/uploads/2023/09/vector-efficient-versatile.png",
    "https://locusrobotics.com/wp-content/uploads/2023/09/vector-graphic.png",
    "https://locusrobotics.com/wp-content/uploads/2023/11/LocusRobotics_Locus-Vector-hero-Graphic-564x689-1.png",
]


def _load_aws() -> None:
    if not SERVER.joinpath(".env").is_file():
        return
    for line in (SERVER / ".env").read_text(encoding="utf-8").splitlines():
        if "=" not in line or line.strip().startswith("#"):
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if " #" in v:
            v = v.split(" #", 1)[0].strip()
        if k.startswith("AWS_") or not str(os.environ.get(k) or "").strip():
            os.environ[k] = v


def s3():
    _load_aws()
    return boto3.client(
        "s3",
        region_name=os.environ.get("AWS_S3_REGION_NAME") or "ap-southeast-1",
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
    )


def upload_url(client, url: str, key: str) -> str:
    r = requests.get(url, headers=UA, timeout=90)
    r.raise_for_status()
    local = OUT / Path(key).name
    local.write_bytes(r.content)
    try:
        Image.open(local).convert("RGB").save(local.with_suffix(".jpg"), quality=92, optimize=True)
        local = local.with_suffix(".jpg")
        key = key.rsplit(".", 1)[0] + ".jpg"
    except Exception:  # noqa: BLE001
        pass
    body = local.read_bytes()
    client.put_object(
        Bucket=BUCKET,
        Key=key,
        Body=body,
        ContentType="image/jpeg" if key.endswith(".jpg") else "image/png",
        CacheControl="public, max-age=31536000",
    )
    cdn = f"{CDN}/{key}"
    for _ in range(15):
        chk = requests.get(cdn, timeout=30)
        if chk.status_code == 200 and len(chk.content) > 2000:
            print(f"OK {cdn}")
            return cdn
        time.sleep(0.4)
    raise RuntimeError(f"CDN fail {cdn}")


def copy_media(rid: int) -> str:
    secret = os.environ.get("INTERNAL_API_SECRET", "").strip()
    if not secret and (SERVER / ".env").is_file():
        for line in (SERVER / ".env").read_text(encoding="utf-8").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                secret = line.split("=", 1)[1].strip()
    api = (
        os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/").replace("/api/v1", "")
        or "https://ragadmin.robotaigeek.com"
    )
    url = f"{api}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/?force=1"
    for attempt in range(4):
        try:
            resp = requests.post(url, headers={"X-Internal-Secret": secret}, timeout=180)
            if resp.ok:
                return f"ok {resp.text[:80]}"
            if resp.status_code not in (500, 502, 503, 504):
                return f"HTTP {resp.status_code}"
        except requests.RequestException:
            pass
        time.sleep(2**attempt)
    return "fail"


PRODUCTS: list[dict[str, Any]] = [
    {
        "id": 2536,
        "name": "Locus Array",
        "model_name": "Array",
        "url": "https://locusrobotics.com/locusone/fleet/locus-array",
        "family_key": "locus:array",
        "family_name": "Array",
        "replace_media": False,
        "images": [],
        "payload_kg": None,  # soft — no curb payload on PDP
        "purpose": "Fully autonomous aisle picking and robots-to-goods fulfillment",
        "features": (
            "OEM locusrobotics.com/locus-array: Physical AI mobile manipulator for "
            "robots-to-goods (R2G) fulfillment — autonomous pick/putaway/induction/"
            "drop-off/slotting in the aisle. Six active order totes per robot; storage "
            "up to 10 ft; patented soft-membrane end-effector (NeuraGrasp) for broad "
            "SKU coverage (polybags, soft goods, porous/deformed/perforated items) "
            "without tool changes. Orchestrated by LocusONE. Soft: no public curb "
            "weight/dims/speed on marketing PDP."
        ),
        "runtime_minutes": None,
    },
    {
        "id": 4884,
        "name": "Locus Origin",
        "model_name": "Origin",
        "url": "https://locusrobotics.com/locusone/fleet/locus-origin-collaborative-robot",
        "family_key": "locus:origin",
        "family_name": "Origin",
        "replace_media": True,
        "images": ORIGIN_IMGS,
        "payload_kg": 36.0,
        "width_mm": 518.0,  # 20.4 in
        "length_mm": 579.0,  # 22.8 in
        "height_mm": 1575.0,  # 62 in
        "runtime_minutes": 840,  # 14 hours
        "charging_time_minutes": 50,
        "purpose": "Collaborative goods-to-person picking that cuts unproductive walking",
        "features": (
            "OEM locusrobotics.com Locus Origin: collaborative AMR for high-volume "
            "order fulfillment (>2× productivity). Configurable multi-level shelving / "
            "tote arrays / bins / shipping boxes; dynamic pick + putaway interleaving. "
            "Dims 20.4×22.8×62 in (51.8×57.9×157.5 cm); CE payload 36 kg / 80 lb; "
            "14 h runtime / ~50 min full charge; 8 sensors + cameras; tablet UI; "
            "opportunity charging. Soft: max speed not on PDP."
        ),
    },
    {
        "id": 4885,
        "name": "Locus Vector",
        "model_name": "Vector",
        "url": "https://locusrobotics.com/locusone/fleet/locus-vector-material-handling-robot",
        "family_key": "locus:vector",
        "family_name": "Vector",
        "replace_media": True,
        "images": VECTOR_IMGS,
        "payload_kg": 272.0,
        "width_mm": 565.0,  # 22.25 in
        "length_mm": 762.0,  # 30 in
        "height_mm": 508.0,  # 20 in
        "runtime_minutes": 540,  # mid of 8–10 h
        "charging_time_minutes": 60,
        "purpose": "Heavy omnidirectional AMR for case picking and point-to-point transport",
        "features": (
            "OEM locusrobotics.com Locus Vector: material-handling AMR with Mecanum "
            "omnidirectional drive — case picking, shelf/rack moves, conveyor feed, "
            "parts-to-line / milk runs. Payload up to 272 kg / 600 lb; chassis "
            "30×22.25×20 in (76.2×56.5×50.8 cm); dual safety-rated 2D LiDAR + 90 m "
            "3D LiDAR; 8–10 h runtime / ~60 min charge; opportunity charging. Soft: "
            "max speed not on PDP."
        ),
    },
]


def enrich_one(client: ResearchApiClient, s3c, spec: dict[str, Any], apply: bool) -> dict[str, Any]:
    rid = spec["id"]
    urls: list[str] = []
    if spec.get("replace_media") and spec.get("images"):
        for i, src in enumerate(spec["images"][:4]):
            key = f"{PREFIX}/{spec['model_name'].lower()}-{i}-20260720.jpg"
            if apply:
                urls.append(upload_url(s3c, src, key))
            else:
                urls.append(src)
                print(f"dry img {src[:80]}")

    row: dict[str, Any] = {
        "id": rid,
        "name": spec["name"],
        "model_name": spec["model_name"],
        "company_slug": COMPANY_SLUG,
        "company_name": COMPANY_NAME,
        "manufacturer_country_code": "US",
        "manufacturer_country_codes": "US",
        "url": spec["url"],
        "purpose": spec["purpose"],
        "features": spec["features"],
        "description": (
            f"{spec['name']} is a Locus Robotics warehouse AMR orchestrated by "
            f"LocusONE for flexible fulfillment automation."
        ),
        "availability_status": AVAILABLE,
        "family_key": spec["family_key"],
        "family_name": spec["family_name"],
        "family_url": spec["url"],
        "product_url_scope": "exact_variant",
        "movement_type_keys": "wheeled",
        "category_slugs": "industrial-robots",
        "use_keys": "pick-and-place|warehouse|logistics|transport",
        "industry_keys": "logistics|warehousing",
        "tags": "AMR|Warehouse|LocusONE|USA|Fulfillment",
        "source_locale": "en",
        "sources": [
            {"url": spec["url"], "type": "website", "title": f"{spec['name']} OEM page"},
            {
                "url": "https://www.locusrobotics.com/",
                "type": "website",
                "title": "Locus Robotics home",
            },
        ],
        "information_source_urls": [spec["url"], "https://www.locusrobotics.com/"],
        "notes": (
            "[AI Research] Locus 2026-07-20 soft enrich: US/Available/family + OEM "
            "typed specs; Origin/Vector heroes staged to research-staging/locus/."
        ),
    }
    if urls:
        row["image"] = urls[0]
        row["images"] = urls
    for k in (
        "payload_kg",
        "width_mm",
        "length_mm",
        "height_mm",
        "runtime_minutes",
        "charging_time_minutes",
        "speed",
        "weight_kg",
    ):
        if spec.get(k) is not None:
            row[k] = spec[k]

    staging = _RESEARCH / "staging" / "robots" / COMPANY_SLUG
    staging.mkdir(parents=True, exist_ok=True)
    path = staging / f"{spec['model_name'].lower()}.json"
    path.write_text(json.dumps(row, indent=2), encoding="utf-8")
    result: dict[str, Any] = {"id": rid, "name": spec["name"], "staging": str(path)}

    if not apply:
        print(f"dry-run {rid} {spec['name']}")
        return result

    imp = import_staging(
        path,
        dry_run=False,
        patch=True,
        force_overwrite=True,
        replace_media=bool(spec.get("replace_media") and urls),
        status="pending_review",
        created_by_id=resolve_created_by_id(1),
        skip_company_update=True,
    )
    result["import"] = imp
    body = {
        "manufacturer_countries": [US_ID],
        "manufacturer_country_ref": US_ID,
        "availability_status": AVAILABLE,
        "family_key": spec["family_key"],
        "family_name": spec["family_name"],
        "family_url": spec["url"],
        "product_url_scope": "exact_variant",
        "purpose": spec["purpose"],
        "features": spec["features"],
        "s3_image": None,
    }
    for k in (
        "payload_kg",
        "width_mm",
        "length_mm",
        "height_mm",
        "runtime_minutes",
        "charging_time_minutes",
    ):
        if spec.get(k) is not None:
            body[k] = spec[k]
    client._patch(f"robots/robots/{rid}/", body)
    if urls:
        result["copy_media"] = copy_media(rid)
    after = client._get(f"robots/robots/{rid}/")
    result["after"] = {
        "image": after.get("image"),
        "photos": len(after.get("photos") or []),
        "payload_kg": after.get("payload_kg"),
        "family_key": after.get("family_key"),
        "availability": after.get("availability_status"),
    }
    print(f"patched {rid} {spec['name']} img={bool(after.get('image'))}")
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    client = ResearchApiClient()
    s3c = s3() if args.apply else None
    report = [enrich_one(client, s3c, spec, args.apply) for spec in PRODUCTS]
    out = _RESEARCH / "staging" / "reports" / "locus-discover.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("wrote", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
