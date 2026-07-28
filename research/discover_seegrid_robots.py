"""Soft enrich Seegrid (209) — keep 3 catalog SKUs, reject same-URL dupes, add EL1.

Keep:
  2409 Lift RS1 AMR
  2408 Lift CR1 AMR
  2312 Tow Tractor S7

Reject (same OEM PDP URL):
  2307 Lift RS1 → keep 2409
  2309 Lift CR1 → keep 2408
  4420 Palion Tow Tractor S7 AMR → keep 2312 (also imageless)

Discover:
  Lift EL1 AMR (catalog gap)

Usage:
  python discover_seegrid_robots.py --apply
  python discover_seegrid_robots.py --apply --reject-dupes
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

import requests

_RESEARCH = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient
from import_staging import import_staging, resolve_created_by_id

COMPANY_ID = 209
COMPANY_SLUG = "seegrid"
COMPANY_NAME = "Seegrid"
US_ID = 20
AVAILABLE = 11
UA = {"User-Agent": "Mozilla/5.0 (compatible; RobotAIGeekResearch/1.0)"}

# OEM specs from product pages (2026-07-20)
KEEPERS: list[dict[str, Any]] = [
    {
        "id": 2409,
        "name": "Seegrid Lift RS1 AMR",
        "model_name": "Lift RS1",
        "variant_label": "AMR",
        "url": "https://seegrid.com/autonomous-mobile-robots/lift-rs1-amr/",
        "family_key": "seegrid:lift-rs1",
        "family_name": "Lift RS1",
        "family_url": "https://seegrid.com/autonomous-mobile-robots/lift-rs1-amr/",
        "payload_kg": 1587.57,  # 3,500 lb
        "speed": 8.05,  # 5 mph
        "purpose": "Low-lift autonomous pallet transport and buffer management",
        "features": (
            "OEM seegrid.com Lift RS1: autonomous lift truck for low-lift staging and "
            "storage up to 6 ft lift height; 3,500 lb (≈1,588 kg) payload; max automatic "
            "speed 5 mph (≈8.05 km/h). Layered 2D/3D LiDAR safety; ITA forks 42\" "
            "standard (36–72\" optional); industry-leading payload detection; Fleet "
            "Central dispatch; infrastructure-free navigation. 2025 Material Handling "
            "Products of the Year Readers’ Choice. Soft: robot curb weight not on PDP."
        ),
    },
    {
        "id": 2408,
        "name": "Seegrid Lift CR1 AMR",
        "model_name": "Lift CR1",
        "variant_label": "AMR",
        "url": "https://seegrid.com/autonomous-mobile-robots/lift-cr1-amr/",
        "family_key": "seegrid:lift-cr1",
        "family_name": "Lift CR1",
        "family_url": "https://seegrid.com/autonomous-mobile-robots/lift-cr1-amr/",
        "payload_kg": 1814.37,  # 4,000 lb
        "speed": 8.05,  # 5.0 mph forward
        "width_mm": 1270.0,  # 50"
        "length_mm": 2337.0,  # 92" forks retracted
        "purpose": "High-lift heavy autonomous pallet handling for manufacturing",
        "features": (
            "OEM seegrid.com Lift CR1: autonomous lift truck for higher/heavier vertical "
            "handling — 15 ft max lift, 4,000 lb (≈1,814 kg) payload; max auto speed "
            "5.0 mph forward / −0.7 mph reverse. Chassis ~50\" W × 92\" L (forks "
            "retracted); reach 180\"; ride-on compartment; layered LiDAR safety; ITA "
            "forks. Soft: curb weight not on PDP."
        ),
    },
    {
        "id": 2312,
        "name": "Seegrid Tow Tractor S7 AMR",
        "model_name": "Tow Tractor S7",
        "variant_label": "AMR",
        "url": "https://seegrid.com/autonomous-mobile-robots/tow-tractor-s7-amr/",
        "family_key": "seegrid:tow-tractor-s7",
        "family_name": "Tow Tractor S7",
        "family_url": "https://seegrid.com/autonomous-mobile-robots/tow-tractor-s7-amr/",
        "payload_kg": 4535.92,  # 10,000 lb
        "speed": 6.44,  # 4.0 mph
        "width_mm": 914.0,  # 36"
        "length_mm": 1930.0,  # 76"
        "purpose": "Autonomous long-haul cart-train tugging for material movement",
        "features": (
            "OEM seegrid.com Tow Tractor S7: autonomous tugger for heavy horizontal "
            "cart trains — 10,000 lb (≈4,536 kg) capacity; max auto speed 4.0 mph "
            "forward / −0.7 mph reverse; chassis ~36\" W × 76\" L; auto-hitch and "
            "auto-charge; ANSI/ITSDF B56.5 + UL 583; layered 2D/3D LiDAR. Soft: curb "
            "weight not cited on PDP (prior 843.68 kg on imageless dupe row discarded)."
        ),
    },
]

REJECTS = [
    (2307, "duplicate: keep Lift RS1 AMR 2409 (same OEM PDP)"),
    (2309, "duplicate: keep Lift CR1 AMR 2408 (same OEM PDP)"),
    (4420, "duplicate: keep Tow Tractor S7 AMR 2312 (same OEM PDP; imageless)"),
]

EL1_URL = "https://seegrid.com/autonomous-mobile-robots/lift-el1-amr/"


def _admin_base() -> str:
    api = os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/")
    return api.replace("/api/v1", "") or "https://ragadmin.robotaigeek.com"


def reject_robot(rid: int, reason: str) -> str:
    sid = os.environ.get("ADMIN_SESSION_ID", "").strip()
    secret = os.environ.get("INTERNAL_API_SECRET", "").strip()
    env_file = _RESEARCH.parents[1] / "robotaigeek-server" / ".env"
    if not secret and env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                secret = line.split("=", 1)[1].strip()
    url = f"{_admin_base()}/admin/robots/robot/content-queue/api/robot/{rid}/reject/"
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if sid:
        headers["Cookie"] = f"sessionid={sid}"
    if secret:
        headers["X-Internal-Secret"] = secret
    try:
        resp = requests.post(
            url, headers=headers, json={"type": "robot", "reason": reason}, timeout=120
        )
        return f"{resp.status_code} {(resp.text or '')[:120]}"
    except requests.RequestException as e:
        return f"ERR {e}"


def find_el1_hero() -> str:
    html = requests.get(EL1_URL, headers=UA, timeout=60).text
    for pat in (
        r'og:image" content="([^"]+)"',
        r'property="og:image" content="([^"]+)"',
        r'(https://[^"\']+lift[^"\']+\.(?:jpg|jpeg|png|webp))',
        r'(https://seegrid\.com/wp-content/uploads/[^"\']+\.(?:jpg|jpeg|png|webp))',
    ):
        m = re.search(pat, html, re.I)
        if m:
            return m.group(1)
    return ""


def _load_aws_env() -> None:
    env_file = _RESEARCH.parents[1] / "robotaigeek-server" / ".env"
    if not env_file.is_file():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if "=" not in line or line.strip().startswith("#"):
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if " #" in v:
            v = v.split(" #", 1)[0].strip()
        if k.startswith("AWS_") or not str(os.environ.get(k) or "").strip():
            os.environ[k] = v


def upload_staging(local: Path, key: str) -> str:
    import boto3
    from PIL import Image

    _load_aws_env()
    bucket = "cdn.robotaigeek.com"
    out = _RESEARCH / "staging" / "tmp" / "seegrid-el1-rgb.jpg"
    Image.open(local).convert("RGB").save(out, quality=92, optimize=True)
    client = boto3.client(
        "s3",
        region_name=os.environ.get("AWS_S3_REGION_NAME") or "ap-southeast-1",
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
    )
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=out.read_bytes(),
        ContentType="image/jpeg",
        CacheControl="public, max-age=31536000",
    )
    url = f"https://cdn.robotaigeek.com/{key}"
    for _ in range(15):
        r = requests.get(url, timeout=30)
        if r.status_code == 200 and len(r.content) > 2000:
            return url
        time.sleep(0.4)
    raise RuntimeError(f"CDN verify failed {url}")


def copy_media(rid: int) -> str:
    secret = os.environ.get("INTERNAL_API_SECRET", "").strip()
    env_file = _RESEARCH.parents[1] / "robotaigeek-server" / ".env"
    if not secret and env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                secret = line.split("=", 1)[1].strip()
    url = (
        f"{_admin_base()}/admin/robots/robot/content-queue/api/robot/{rid}/"
        "copy-media/?force=1"
    )
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


def patch_keepers(client: ResearchApiClient, apply: bool) -> list[dict[str, Any]]:
    out = []
    for spec in KEEPERS:
        rid = spec["id"]
        body: dict[str, Any] = {
            "name": spec["name"],
            "model_name": spec["model_name"],
            "variant_label": spec.get("variant_label") or "",
            "manufacturer_countries": [US_ID],
            "manufacturer_country_ref": US_ID,
            "availability_status": AVAILABLE,
            "family_key": spec["family_key"],
            "family_name": spec["family_name"],
            "family_url": spec["family_url"],
            "product_url_scope": "exact_variant",
            "url": spec["url"],
            "purpose": spec["purpose"],
            "features": spec["features"],
            "payload_kg": spec["payload_kg"],
            "speed": spec["speed"],
            "category_slugs": None,  # don't wipe via patch if unsupported
        }
        for k in ("width_mm", "length_mm", "height_mm", "weight_kg"):
            if spec.get(k) is not None:
                body[k] = spec[k]
        # remove None
        body = {k: v for k, v in body.items() if v is not None}
        entry = {"id": rid, "name": spec["name"], "patch_keys": list(body.keys())}
        if apply:
            # taxonomy via dedicated keys if API accepts
            body2 = dict(body)
            body2.pop("category_slugs", None)
            client._patch(f"robots/robots/{rid}/", body2)
            # also set movement/uses if blank — patch common fields
            client._patch(
                f"robots/robots/{rid}/",
                {
                    "movement_type_keys": "wheeled",
                    "use_keys": "transport|warehouse|logistics",
                    "industry_keys": "manufacturing|logistics|warehousing",
                },
            )
            after = client._get(f"robots/robots/{rid}/")
            entry["after"] = {
                "payload_kg": after.get("payload_kg"),
                "speed": after.get("speed"),
                "family_key": after.get("family_key"),
                "availability": after.get("availability_status"),
                "country": after.get("manufacturer_countries"),
            }
            print(f"patched {rid} {spec['name']}")
        else:
            print(f"dry-run {rid} {list(body.keys())}")
        out.append(entry)
    return out


def create_el1(apply: bool) -> dict[str, Any]:
    hero_src = find_el1_hero()
    print(f"EL1 hero src: {hero_src[:100] if hero_src else 'NONE'}")
    images: list[str] = []
    if hero_src:
        try:
            raw = requests.get(hero_src, headers=UA, timeout=60).content
            tmp = _RESEARCH / "staging" / "tmp" / "seegrid-el1.jpg"
            tmp.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_bytes(raw)
            # re-upload if large enough
            if len(raw) > 2000:
                if apply:
                    cdn = upload_staging(tmp, "research-staging/seegrid/el1-hero-20260720.jpg")
                    images = [cdn]
                    print(f"EL1 CDN {cdn}")
                else:
                    images = [hero_src]
        except Exception as e:  # noqa: BLE001
            print(f"EL1 image warn: {e}")

    row: dict[str, Any] = {
        "name": "Seegrid Lift EL1 AMR",
        "model_name": "Lift EL1",
        "variant_label": "AMR",
        "company_slug": COMPANY_SLUG,
        "company_name": COMPANY_NAME,
        "manufacturer_country_code": "US",
        "manufacturer_country_codes": "US",
        "url": EL1_URL,
        "description": (
            "Seegrid Lift EL1 is a compact autonomous lift truck for space-constrained "
            "warehousing, 3PL, and retail fulfillment — high-frequency low-lift pallet "
            "moves with VDA 5050 2.1 interoperability."
        ),
        "purpose": "Compact low-lift autonomous pallet transport for tight warehouses",
        "features": (
            "OEM seegrid.com Lift EL1: compact AMR lift truck — max lift 5' 2\", "
            "2,500 lb (≈1,134 kg) payload, max automatic speed 3.4 mph (≈5.47 km/h). "
            "Fully VDA 5050 2.1 compliant; layered 2D/3D LiDAR; ITA forks 42\" standard "
            "(36–48\" optional). Built for inbound/buffer/putaway and wrapper/conveyor "
            "handoffs in tight aisles. Soft: curb weight/dims not on marketing PDP."
        ),
        "image": images[0] if images else "",
        "images": images,
        "availability_status": AVAILABLE,
        "family_key": "seegrid:lift-el1",
        "family_name": "Lift EL1",
        "family_url": EL1_URL,
        "product_url_scope": "exact_variant",
        "payload_kg": 1133.98,
        "speed": 5.47,
        "movement_type_keys": "wheeled",
        "category_slugs": "industrial-robots|amr",
        "use_keys": "transport|warehouse|logistics",
        "industry_keys": "logistics|warehousing",
        "tags": "AMR|Lift Truck|Warehouse|VDA5050|USA|Seegrid",
        "source_locale": "en",
        "sources": [
            {"url": EL1_URL, "type": "website", "title": "Seegrid Lift EL1 AMR"},
            {
                "url": "https://www.seegrid.com/",
                "type": "website",
                "title": "Seegrid home — AMR fleet",
            },
        ],
        "information_source_urls": [EL1_URL, "https://www.seegrid.com/"],
        "notes": (
            "[AI Research] Seegrid 2026-07-20: catalog gap EL1 added from OEM PDP. "
            "Reject same-URL dupes RS1/CR1/S7 shells."
        ),
        "research_notes": "[AI Research] EL1 OEM specs 2500 lb / 5'2\" lift / 3.4 mph.",
    }
    staging = _RESEARCH / "staging" / "robots" / COMPANY_SLUG
    staging.mkdir(parents=True, exist_ok=True)
    path = staging / "lift-el1.json"
    path.write_text(json.dumps(row, indent=2), encoding="utf-8")
    result: dict[str, Any] = {"staging": str(path), "images": images}
    if apply and images:
        imp = import_staging(
            path,
            dry_run=False,
            patch=False,
            force_overwrite=True,
            replace_media=True,
            status="pending_review",
            created_by_id=resolve_created_by_id(1),
            skip_company_update=True,
        )
        result["import"] = imp
        # find created id
        rid = None
        for r in (imp.get("results") or []):
            if r.get("id"):
                rid = r["id"]
        if rid:
            api = ResearchApiClient()
            api._patch(
                f"robots/robots/{rid}/",
                {
                    "manufacturer_countries": [US_ID],
                    "manufacturer_country_ref": US_ID,
                    "availability_status": AVAILABLE,
                    "payload_kg": 1133.98,
                    "speed": 5.47,
                    "family_key": "seegrid:lift-el1",
                    "family_name": "Lift EL1",
                    "family_url": EL1_URL,
                    "purpose": row["purpose"],
                    "features": row["features"],
                    "s3_image": None,
                },
            )
            result["copy_media"] = copy_media(rid)
            result["id"] = rid
            print(f"created EL1 id={rid}")
    else:
        print("EL1 staged (dry-run or no image)")
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--reject-dupes", action="store_true")
    ap.add_argument("--skip-el1", action="store_true")
    args = ap.parse_args()
    client = ResearchApiClient()
    report: dict[str, Any] = {
        "keepers": patch_keepers(client, args.apply),
        "rejects": [],
        "el1": None,
    }
    if args.reject_dupes and args.apply:
        for rid, reason in REJECTS:
            msg = reject_robot(rid, reason)
            print(f"reject {rid}: {msg}")
            report["rejects"].append({"id": rid, "reason": reason, "result": msg})
    elif args.reject_dupes:
        print("dry-run rejects:", REJECTS)
    if not args.skip_el1:
        report["el1"] = create_el1(args.apply)
    out = _RESEARCH / "staging" / "reports" / "seegrid-discover.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("wrote", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
