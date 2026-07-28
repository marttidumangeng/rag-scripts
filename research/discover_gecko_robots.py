"""Enrich Gecko Robotics (806) — TOKA 3/4/Flex soft patch + heroes.

TOKA 3 was imageless; TOKA 4 CDN was a logo. Prefer press/Navy photos
(Robot Report TOKA 3 still; DVIDS Navy TOKA 4 hull deploy).

Usage:
  python discover_gecko_robots.py --apply
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

COMPANY_ID = 806
COMPANY_SLUG = "gecko-robotics"
COMPANY_NAME = "Gecko Robotics"
US_ID = 20
AVAILABLE = 11
BUCKET = "cdn.robotaigeek.com"
CDN = "https://cdn.robotaigeek.com"
PREFIX = "research-staging/gecko"
SERVER = _RESEARCH.parents[1] / "robotaigeek-server"
OUT = _RESEARCH / "staging" / "tmp" / "gecko-final"
OUT.mkdir(parents=True, exist_ok=True)
UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

# 60 fpm = 1.097 km/h; 30 fpm = 0.549 km/h; 0.15 m/s = 0.54 km/h
PRODUCTS: list[dict[str, Any]] = [
    {
        "id": 4948,
        "name": "Gecko TOKA 3",
        "model_name": "TOKA 3",
        "url": "https://www.geckorobotics.com/",
        "family_key": "gecko:toka",
        "family_name": "TOKA",
        "family_url": "https://www.geckorobotics.com/",
        "replace_media": True,
        "images": [
            "https://www.therobotreport.com/wp-content/uploads/2022/03/featured-web-TOKA-3.jpg",
        ],
        "weight_kg": None,
        "speed": 1.097,  # 60 ft/min (Robot Report / Gecko Series C coverage)
        "runtime_minutes": None,
        "purpose": "Wall-climbing UT inspection of medium piping and high-temperature surfaces",
        "features": (
            "OEM/press (The Robot Report Series C coverage, sourcing Gecko): fastest "
            "TOKA series crawler at ~60 ft/min for medium piping and high-temperature "
            "surfaces. Magnetic wall-climbing NDT platform for power, oil & gas, heavy "
            "manufacturing, and defense. Soft: detailed curb weight/dims not on current "
            "geckorobotics.com (product pages folded into Cantilever RaaS narrative). "
            "Hero: Gecko-sourced TOKA 3 still via Robot Report."
        ),
        "description": (
            "TOKA 3 is Gecko Robotics' magnetic wall-climbing inspection robot optimized "
            "for medium-sized piping and high-temperature industrial surfaces."
        ),
        "sources": [
            {
                "url": "https://www.therobotreport.com/gecko-robotics-brings-in-73m-for-inspection-robots/",
                "title": "Robot Report — Gecko TOKA series overview",
            },
            {"url": "https://www.geckorobotics.com/", "title": "Gecko Robotics home"},
        ],
    },
    {
        "id": 4947,
        "name": "Gecko TOKA 4",
        "model_name": "TOKA 4",
        "url": "https://www.geckorobotics.com/",
        "family_key": "gecko:toka",
        "family_name": "TOKA",
        "family_url": "https://www.geckorobotics.com/",
        "replace_media": True,
        "images": [
            # Robot-only hull still — avoid 7463873/7477559 (clear human faces).
            "https://d1ldvf68ux039x.cloudfront.net/thumbs/photos/2210/7463870/2000w_q95.jpg",
        ],
        "weight_kg": 12.0,
        "speed": 0.54,  # 0.15 m/s scanning / ~30 fpm series speed
        "runtime_minutes": 240,
        "purpose": "Magnetic ultrasonic thickness mapping of boilers, tanks, vessels, and hulls",
        "features": (
            "Press/aggregator specs (Robots HQ TOKA 4 table + PopSci/Navy deploy): "
            "magnetic-wheel wall climber for ferrous vertical/overhead/curved surfaces; "
            "ultrasonic thickness mapping 100,000+ readings/day; UT accuracy ±0.1 mm; "
            "scan ~0.15 m/s; ~12 kg; ~4 h battery; Cantilever cloud corrosion heatmaps. "
            "Used on U.S. Navy hull inspections (REPTX 2022). Soft: OEM PDP retired into "
            "Cantilever RaaS. Replaced logo CDN primary with Navy DVIDS deploy stills."
        ),
        "description": (
            "TOKA 4 is Gecko's magnetic wall-climbing ultrasonic inspection robot for "
            "boilers, tanks, pressure vessels, and ship hulls."
        ),
        "sources": [
            {
                "url": "https://www.dvidshub.net/image/7463873/detection-unidentified-object-attached-hull-scenario",
                "title": "U.S. Navy DVIDS — TOKA 4 REPTX deploy",
            },
            {
                "url": "https://www.popsci.com/technology/gecko-robotics-machine-inspects-navy-ships/",
                "title": "Popular Science — Navy TOKA 4 hull inspection",
            },
            {"url": "https://www.geckorobotics.com/", "title": "Gecko Robotics home"},
        ],
    },
    {
        "id": 3578,
        "name": "Gecko TOKA Flex",
        "model_name": "TOKA Flex",
        "url": "https://resources.geckorobotics.com/toka-flex",
        "family_key": "gecko:toka",
        "family_name": "TOKA",
        "family_url": "https://www.geckorobotics.com/",
        "replace_media": True,
        "images": [
            # Robot-only primary; text marketing graphic only as gallery (demoted).
            "https://www.roboticgizmos.com/wp-content/uploads/2022/10/13/TOKA-Flex-Pipe-Inspection-Robot.jpg",
            "https://cdn.prod.website-files.com/63349fc0ae8d7c3feaab48a9/633d3ad9accedcc9eef32358_scrubber.jpg",
            "https://inspectioneering.com/media/image/News/2021/TOKAFlex_ProductPage_MetaGraphic.jpg",
        ],
        "weight_kg": 18.1,
        "speed": 0.549,  # ~30 fpm series; coverage >30 sq ft/min cited in OEM press
        "runtime_minutes": None,
        "purpose": "Maneuverable UT inspection of small-diameter piping and elbows at height",
        "features": (
            "OEM press (Inspectioneering / Gecko 2021-03-31): most maneuverable TOKA — "
            "independent suspension/drive on 4 permanent-magnetic wheels; adapts flat to "
            "pipes down to 6\" diameter; navigates elbows, ⅜\" obstacles, 180° turns; "
            "12 single-channel UT probes at 1\" spacing (optional 18 @ ¼\"); >30 sq ft/min "
            "coverage; heat-hardened to 275°F; climb/crawl up to 75' from operators; "
            "RUG A/B/C-scan via Gecko Portal. Soft: curb weight 18.1 kg retained from "
            "prior research (not re-cited on current OEM site)."
        ),
        "description": (
            "TOKA Flex is Gecko Robotics' piping-focused magnetic crawler for NDT of "
            "small-diameter lines, elbows, and elevated process piping."
        ),
        "sources": [
            {
                "url": "https://inspectioneering.com/news/2021-03-31/9580/gecko-robotics-unveils-latest-inspection-robot-the-toka-flex",
                "title": "Inspectioneering — TOKA Flex unveil (Gecko press)",
            },
            {
                "url": "https://resources.geckorobotics.com/toka-flex",
                "title": "Gecko resources — TOKA Flex",
            },
        ],
    },
]


def _load_aws() -> None:
    env = SERVER / ".env"
    if not env.is_file():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        if "=" not in line or line.strip().startswith("#"):
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if " #" in v:
            v = v.split(" #", 1)[0].strip()
        if k.startswith("AWS_") or not str(os.environ.get(k) or "").strip():
            os.environ[k] = v


def s3_client():
    _load_aws()
    return boto3.client(
        "s3",
        region_name=os.environ.get("AWS_S3_REGION_NAME") or "ap-southeast-1",
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
    )


def upload_url(s3c, url: str, key: str) -> str:
    r = requests.get(url, headers=UA, timeout=120)
    r.raise_for_status()
    local = OUT / Path(key).name
    local.write_bytes(r.content)
    jpg = local.with_suffix(".jpg")
    Image.open(local).convert("RGB").save(jpg, quality=90, optimize=True)
    key = key.rsplit(".", 1)[0] + ".jpg"
    s3c.put_object(
        Bucket=BUCKET,
        Key=key,
        Body=jpg.read_bytes(),
        ContentType="image/jpeg",
        CacheControl="public, max-age=31536000",
    )
    cdn = f"{CDN}/{key}"
    for _ in range(15):
        chk = requests.get(cdn, timeout=30)
        if chk.status_code == 200 and len(chk.content) > 2000:
            print("OK", cdn)
            return cdn
        time.sleep(0.4)
    raise RuntimeError(cdn)


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


def taxonomy_ids(client: ResearchApiClient) -> dict[str, dict[str, int]]:
    def idx(path: str) -> dict[str, int]:
        rows = client._get(path)
        return {
            (r.get("key") or "").lower(): int(r["id"])
            for r in rows
            if r.get("key") and r.get("id")
        }

    return {
        "uses": idx("robots/uses/"),
        "industries": idx("robots/industries/"),
        "movement": idx("robots/movement-types/"),
    }


def enrich_one(
    client: ResearchApiClient,
    s3c,
    tax: dict[str, dict[str, int]],
    spec: dict[str, Any],
    apply: bool,
) -> dict[str, Any]:
    rid = spec["id"]
    urls: list[str] = []
    if spec.get("replace_media"):
        for i, src in enumerate(spec.get("images") or []):
            key = f"{PREFIX}/{spec['model_name'].lower().replace(' ', '-')}-{i}-20260720.jpg"
            if apply:
                urls.append(upload_url(s3c, src, key))
            else:
                urls.append(src)

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
        "description": spec["description"],
        "availability_status": AVAILABLE,
        "family_key": spec["family_key"],
        "family_name": spec["family_name"],
        "family_url": spec["family_url"],
        "product_url_scope": "exact_variant",
        "movement_type_keys": "wheeled",
        "category_slugs": "industrial-robots",
        "use_keys": "inspection|monitoring",
        "industry_keys": "oil-gas|energy|manufacturing|defence",
        "tags": "NDT|Inspection|Wall-Climbing|Magnetic|UT|Cantilever|USA|Gecko|TOKA",
        "source_locale": "en",
        "sources": [
            {"url": s["url"], "type": "website", "title": s.get("title") or s["url"]}
            for s in spec.get("sources") or []
        ],
        "information_source_urls": [s["url"] for s in (spec.get("sources") or [])],
        "notes": (
            "[AI Research] Gecko 2026-07-20: US/Available/family gecko:toka; TOKA 3 "
            "hero + TOKA 4 logo→Navy still; Flex OEM press features."
        ),
    }
    if urls:
        row["image"] = urls[0]
        row["images"] = urls
    for k in ("weight_kg", "speed", "runtime_minutes"):
        if spec.get(k) is not None:
            row[k] = spec[k]

    staging = _RESEARCH / "staging" / "robots" / COMPANY_SLUG
    staging.mkdir(parents=True, exist_ok=True)
    path = staging / f"{spec['model_name'].lower().replace(' ', '-')}.json"
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
        replace_media=bool(urls),
        status="pending_review",
        created_by_id=resolve_created_by_id(1),
        skip_company_update=True,
    )
    result["import"] = imp

    def ids(kind: str, keys: list[str]) -> list[int]:
        m = tax[kind]
        return [m[k] for k in keys if k in m]

    body: dict[str, Any] = {
        "manufacturer_countries": [US_ID],
        "manufacturer_country_ref": US_ID,
        "availability_status": AVAILABLE,
        "family_key": spec["family_key"],
        "family_name": spec["family_name"],
        "family_url": spec["family_url"],
        "product_url_scope": "exact_variant",
        "purpose": spec["purpose"],
        "features": spec["features"],
        "description": spec["description"],
        "url": spec["url"],
        "uses": ids("uses", ["inspection", "monitoring"]),
        "industries": ids("industries", ["oil-gas", "energy", "manufacturing", "defence"]),
        "movement_types": ids("movement", ["wheeled"]),
        "tags": [
            "NDT",
            "Inspection",
            "Wall-Climbing",
            "Magnetic",
            "UT",
            "Cantilever",
            "USA",
            "Gecko",
            "TOKA",
            spec["model_name"],
        ],
        "s3_image": None,
    }
    if urls:
        body["image"] = urls[0]
    for k in ("weight_kg", "speed", "runtime_minutes"):
        if spec.get(k) is not None:
            body[k] = spec[k]
    client._patch(f"robots/robots/{rid}/", body)
    if urls:
        result["copy_media"] = copy_media(rid)
    after = client._get(f"robots/robots/{rid}/")
    result["after"] = {
        "image": after.get("image"),
        "photos": len(after.get("photos") or []),
        "country": bool(after.get("manufacturer_countries")),
        "uses": len(after.get("uses") or []),
        "tags": len(after.get("tags") or []),
        "speed": after.get("speed"),
        "weight_kg": after.get("weight_kg"),
    }
    print(
        f"patched {rid} {spec['name']} img={bool(after.get('image'))} "
        f"country={result['after']['country']} tags={result['after']['tags']}"
    )
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    client = ResearchApiClient()
    tax = taxonomy_ids(client)
    s3c = s3_client() if args.apply else None
    report = [enrich_one(client, s3c, tax, spec, args.apply) for spec in PRODUCTS]
    out = _RESEARCH / "staging" / "reports" / "gecko-discover.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("wrote", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
