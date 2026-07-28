"""Curated Diversey / Solenis (367) enrich — TASKI Ecobot 40 + 50 Pro.

OEM: TASKI (Solenis brand) floor-cleaning robots — not solenis.com home.
PDPs (verified 2026-07-20):
  Ecobot 40     https://nam.taski.com/taski-products/ecobot-40/
  Ecobot 50 Pro https://taski.com/taski-products/ecobot-50-pro/
Family hub:     https://taski.com/products-innovations-solutions/products/robotics/

Shared family_key taski:ecobot. US country 20. Soft typed dims/weight/speed
from OEM Technical Data tables. Height/pass-width columns list cm values under
an "mm" header (34 in ↔ 88) — convert as cm→mm. Uptime is a range → not typed.

Usage:
  python discover_taski_ecobot_robots.py
  python discover_taski_ecobot_robots.py --apply --copy-media
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

COMPANY_ID = 367
COMPANY_SLUG = "diversey-solenis"
COMPANY_NAME = "Diversey (Solenis)"
US_ID = 20
AVAILABLE = 11
BUCKET = "cdn.robotaigeek.com"
CDN = "https://cdn.robotaigeek.com"
PREFIX = "research-staging/taski"
SERVER = _RESEARCH.parents[1] / "robotaigeek-server"
OUT = _RESEARCH / "staging" / "tmp" / "taski"
OUT.mkdir(parents=True, exist_ok=True)
UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://nam.taski.com/",
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
}

FAMILY_URL = "https://taski.com/products-innovations-solutions/products/robotics/"
ECOBOT40 = "https://nam.taski.com/taski-products/ecobot-40/"
ECOBOT50 = "https://taski.com/taski-products/ecobot-50-pro/"

HERO40 = "https://nam.taski.com/wp-content/uploads/2022/12/ecobot-40-1.jpg"
HERO50 = "https://taski.com/wp-content/uploads/2022/12/TASKI_ECOBOT-07881-618x608.jpg"

PRODUCTS: list[dict[str, Any]] = [
    {
        "id": 5148,
        "name": "TASKI Ecobot 40",
        "model_name": "Ecobot 40",
        "variant_code": "Ecobot-40",
        "variant_label": "40",
        "url": ECOBOT40,
        "family_key": "taski:ecobot",
        "family_name": "TASKI Ecobot",
        "family_url": FAMILY_URL,
        "product_url_scope": "exact_variant",
        "availability_status": AVAILABLE,
        "hero_src": HERO40,
        "hero_key": "ecobot-40-0-20260720.jpg",
        "weight_kg": 80.0,
        "length_mm": 700,
        "width_mm": 720,
        "height_mm": 880,  # OEM table 88 under mm col + 34 in → treat as 88 cm
        "speed": 3.6,  # 1 m/s
        "runtime_minutes": None,  # OEM uptime 3–18 h range
        "purpose": (
            "Autonomous carpet and hard-floor sweeping\n"
            "Autonomous vacuuming of commercial floor areas"
        ),
        "description": (
            "TASKI Ecobot 40 is an autonomous sweeper/vacuum robot for commercial "
            "carpet and hard floors. It combines HEPA H13 filtration with a "
            "multi-sensor navigation stack and optional charging-station autonomy."
        ),
        "features": (
            "OEM nam.taski.com Ecobot 40 Technical Data + key features: "
            "autonomous sweeper/vacuum for carpet and hard floors; max theoretical "
            "productivity 1,200 m²/h (12,916 ft²/h); cleaning width 40 cm; HEPA H13 "
            "filter standard; dust bag 12 L; trash tray 2.5 L; max vacuum 24 kPa; "
            "unladen weight 80 kg; dims 70×72×88 cm (OEM inches 27×28×34 — mm column "
            "lists cm values); max moving speed 1 m/s (2 mph); Li-ion phosphate "
            "40 Ah / 24 VDC; charge ~2 h; uptime 3–18 h (range — not typed); sensors "
            "2D LiDAR, 3D depth, 3D ToF, RFID cliff, RGB; full autonomy via charging "
            "station. Soft: MSRP not on PDP."
        ),
        "use_keys": "cleaning|floor-cleaning",
        "industry_keys": "hospitality|retail|facility-management",
        "tags": ["AMR", "TASKI", "Ecobot", "Floor Cleaning", "Vacuum", "Sweeper", "USA"],
    },
    {
        "id": 5147,
        "name": "TASKI Ecobot 50 Pro",
        "model_name": "Ecobot 50 Pro",
        "variant_code": "Ecobot-50-Pro",
        "variant_label": "50 Pro",
        "url": ECOBOT50,
        "family_key": "taski:ecobot",
        "family_name": "TASKI Ecobot",
        "family_url": FAMILY_URL,
        "product_url_scope": "exact_variant",
        "availability_status": AVAILABLE,
        "hero_src": HERO50,
        "hero_key": "ecobot-50-pro-0-20260720.jpg",
        "weight_kg": 155.5,
        "length_mm": 860,
        "width_mm": 700,
        "height_mm": 1030,
        "speed": 3.6,
        "runtime_minutes": None,  # OEM uptime 3–8 h range
        "purpose": (
            "Autonomous hard-floor scrubbing and drying\n"
            "Commercial scrubber-drier floor care"
        ),
        "description": (
            "TASKI Ecobot 50 Pro is an autonomous scrubber-drier for hard floors. "
            "It pairs sensor-guided navigation with scrub-and-dry cleaning and "
            "optional work/docking-station autonomy, including water recycling."
        ),
        "features": (
            "OEM taski.com Ecobot 50 Pro Technical Data + key features: autonomous "
            "scrubber-drier for hard floors; max theoretical productivity 1,800 m²/h "
            "(19,375 ft²/h); working width 50 cm / dual brushes 2×22.9 cm; brush "
            "pressure 25 kg; clean water 30 L / recovered 24 L; squeegee 700 mm; "
            "unladen weight 155.5 kg; dims 860×700×1,030 mm; max moving speed 1 m/s "
            "(2 mph); Li-ion phosphate 60 Ah / 24 VDC; charge ~2 h; uptime 3–8 h "
            "(range — not typed); sensors 2D LiDAR, 3D depth, 3D ToF, RFID cliff, "
            "RGB; full autonomy via work & docking station; water recycling claimed "
            "on PDP. Soft: MSRP not on PDP."
        ),
        "use_keys": "cleaning|floor-cleaning",
        "industry_keys": "hospitality|retail|facility-management",
        "tags": ["AMR", "TASKI", "Ecobot", "Floor Cleaning", "Scrubber", "USA"],
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
    Image.open(local).convert("RGB").save(jpg, quality=92, optimize=True)
    key = key.rsplit(".", 1)[0] + ".jpg"
    s3c.put_object(
        Bucket=BUCKET,
        Key=key,
        Body=jpg.read_bytes(),
        ContentType="image/jpeg",
        CacheControl="public, max-age=31536000",
    )
    cdn = f"{CDN}/{key}"
    for _ in range(20):
        chk = requests.get(cdn, headers=UA, timeout=30)
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
                return f"ok {resp.text[:100]}"
            if resp.status_code not in (500, 502, 503, 504):
                return f"HTTP {resp.status_code}"
        except requests.RequestException:
            pass
        time.sleep(2**attempt)
    return "fail"


def taxonomy_ids(client: ResearchApiClient) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {"uses": {}, "industries": {}, "movement": {}}
    for group, path in (
        ("uses", "robots/uses/"),
        ("industries", "robots/industries/"),
        ("movement", "robots/movement-types/"),
    ):
        try:
            rows = client._get(path) or []
            if isinstance(rows, dict):
                rows = rows.get("results") or rows.get("data") or []
            for row in rows:
                key = (row.get("key") or row.get("slug") or "").lower()
                if key and row.get("id"):
                    out[group][key] = int(row["id"])
        except Exception as e:  # noqa: BLE001
            print("tax warn", group, e)
    return out


def force_en(client: ResearchApiClient, rid: int, row: dict[str, Any]) -> None:
    sync = {
        "updates": [
            {
                "id": rid,
                "locale": loc,
                "source_hash": f"taski-en-force-{rid}-20260720-{loc}",
                "translated_fields": {
                    "description": row.get("description") or "",
                    "features": row.get("features") or "",
                    "purpose": row.get("purpose") or "",
                    "name": row.get("name") or "",
                },
            }
            for loc in ("zh-CN", "zh-TW")
        ]
    }
    try:
        client._post("robots/translations/sync/", sync)
        print(f"  en-force {rid}")
    except Exception as e:  # noqa: BLE001
        print(f"  en-force warn {rid}: {e}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--copy-media", action="store_true")
    args = ap.parse_args()

    client = ResearchApiClient()
    tax = taxonomy_ids(client)
    s3c = s3_client() if args.apply else None
    staging = _RESEARCH / "staging" / "robots" / COMPANY_SLUG
    staging.mkdir(parents=True, exist_ok=True)

    def map_keys(group: str, keys: str) -> list[int]:
        out = []
        for k in keys.split("|"):
            kid = tax[group].get(k.strip().lower())
            if kid:
                out.append(kid)
            else:
                print(f"  warn missing {group} key={k}")
        return out

    uploaded: dict[str, str] = {}
    plan: list[dict[str, Any]] = []

    for spec in PRODUCTS:
        urls: list[str] = []
        if spec.get("hero_src") and spec.get("hero_key"):
            key = f"{PREFIX}/{spec['hero_key']}"
            if args.apply:
                if key not in uploaded:
                    uploaded[key] = upload_url(s3c, spec["hero_src"], key)
                urls = [uploaded[key]]
            else:
                urls = [spec["hero_src"]]

        notes = (
            f"[AI Research] TASKI Ecobot enrich 2026-07-20: US; family taski:ecobot; "
            f"OEM PDP {spec['url']}; uptime range not typed as runtime_minutes."
        )
        row: dict[str, Any] = {
            "id": spec["id"],
            "name": spec["name"],
            "model_name": spec["model_name"],
            "variant_code": spec["variant_code"],
            "variant_label": spec["variant_label"],
            "company_slug": COMPANY_SLUG,
            "company_name": COMPANY_NAME,
            "manufacturer_country_code": "US",
            "manufacturer_country_codes": "US",
            "description": spec["description"],
            "purpose": spec["purpose"],
            "features": spec["features"],
            "url": spec["url"],
            "source_locale": "en",
            "availability_status": spec["availability_status"],
            "family_key": spec["family_key"],
            "family_name": spec["family_name"],
            "family_url": spec["family_url"],
            "product_url_scope": spec["product_url_scope"],
            "movement_type_keys": "wheeled",
            "category_slugs": "mobile-robots|service-robots",
            "use_keys": spec["use_keys"],
            "industry_keys": spec["industry_keys"],
            "tags": spec["tags"],
            "weight_kg": spec.get("weight_kg"),
            "length_mm": spec.get("length_mm"),
            "width_mm": spec.get("width_mm"),
            "height_mm": spec.get("height_mm"),
            "speed": spec.get("speed"),
            "runtime_minutes": spec.get("runtime_minutes"),
            "notes": notes,
            "research_notes": notes,
            "sources": [
                {"url": spec["url"], "type": "website", "title": f"TASKI {spec['name']}"},
                {"url": FAMILY_URL, "type": "website", "title": "TASKI Robotics hub"},
            ],
            "information_source_urls": [spec["url"], FAMILY_URL],
        }
        if urls:
            row["image"] = urls[0]
            row["images"] = urls

        path = staging / f"{spec['model_name'].lower().replace(' ', '-')}.json"
        path.write_text(json.dumps(row, indent=2, ensure_ascii=False), encoding="utf-8")
        print("staged", path.name, "hero", bool(urls))
        plan.append({"id": spec["id"], "name": spec["name"], "url": spec["url"]})

        if not args.apply:
            continue

        result = import_staging(
            path,
            dry_run=False,
            patch=True,
            force_overwrite=True,
            replace_media=bool(urls),
            status="pending_review",
            created_by_id=resolve_created_by_id(1),
            skip_company_update=True,
        )
        print(" import", spec["id"], result)

        body: dict[str, Any] = {
            "manufacturer_countries": [US_ID],
            "manufacturer_country_ref": US_ID,
            "availability_status": spec["availability_status"],
            "description": spec["description"],
            "features": spec["features"],
            "purpose": spec["purpose"],
            "name": spec["name"],
            "model_name": spec["model_name"],
            "variant_code": spec["variant_code"],
            "variant_label": spec["variant_label"],
            "url": spec["url"],
            "family_key": spec["family_key"],
            "family_name": spec["family_name"],
            "family_url": spec["family_url"],
            "product_url_scope": spec["product_url_scope"],
            "notes": notes,
            "weight_kg": spec.get("weight_kg"),
            "length_mm": spec.get("length_mm"),
            "width_mm": spec.get("width_mm"),
            "height_mm": spec.get("height_mm"),
            "speed": spec.get("speed"),
            "runtime_minutes": None,
            "uses": map_keys("uses", spec["use_keys"]),
            "industries": map_keys("industries", spec["industry_keys"]),
            "movement_types": map_keys("movement", "wheeled"),
        }
        if urls:
            body["image"] = urls[0]
            body["s3_image"] = None
        try:
            client._patch(f"robots/robots/{spec['id']}/", body)
            print("  patched", spec["id"])
        except Exception as e:  # noqa: BLE001
            print("  patch warn", spec["id"], e)
        force_en(client, spec["id"], row)
        if args.copy_media and urls:
            print("copy-media", spec["id"], copy_media(spec["id"]))

    report = _RESEARCH / "staging" / "reports" / "taski-ecobot-discover.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        json.dumps({"apply": args.apply, "robots": plan}, indent=2),
        encoding="utf-8",
    )
    print("Report ->", report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
