"""Curated Aethon (7) enrich — live T3/Zena fleet; reject dupes + old TUG SKUs.

OEM catalog (aethon.com nav, 2026-07-20): T3, Zena RX, Zena.
Enabling tech ReadyElevator / Carrello are not robot SKUs.

KEEP / ENRICH (pending → stay pending_review):
  1533 T3          — Available; US; family aethon:t3; 750 lb / 12 h from stored OEM feats
  1534 T3 XL       — Available; US; same family; 1000 lb / 12 h
  1532 Zena Rx     — rename Zena RX; Available; family aethon:zena-rx
  1769 Aethon Zena — rename Zena; Available; family aethon:zena

REJECT:
  1766 Aethon TUG T3     — duplicate of 1533 T3
  1767 Aethon TUG T3 XL  — duplicate of 1534 T3 XL
  1768 Aethon Zena RX    — duplicate of 1532 Zena RX
  1770 TUG Exchange, 1771–1773 TUG Drawer, 1774 TUG Door — off-catalog
    discontinued part-number shells (not on current OEM nav)
  86 TUG, 567 TUG T4 — wrong-brand / non-Aethon heroes; superseded by live catalog

Media: research-staging/aethon/*-20260720.jpg from cdn.aethon.com studio stills.
T3 + T3 XL historically share one family studio still — keep distinct records;
do not invent a second XL-only hero.

Usage:
  python discover_aethon_robots.py
  python discover_aethon_robots.py --apply --copy-media
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

COMPANY_ID = 7
COMPANY_SLUG = "aethon"
COMPANY_NAME = "Aethon"
US_ID = 20
AVAILABLE = 11
DISCONTINUED = 4
BUCKET = "cdn.robotaigeek.com"
CDN = "https://cdn.robotaigeek.com"
PREFIX = "research-staging/aethon"
SERVER = _RESEARCH.parents[1] / "robotaigeek-server"
OUT = _RESEARCH / "staging" / "tmp" / "aethon-final"
OUT.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (compatible; RobotAIGeekResearch/1.0)"}

# OEM CDN studio stills (verified 2026-07-20)
HERO_T3 = "https://cdn.aethon.com/wp-content/uploads/2026/06/Aethon_Website_Robot_T3.webp"
HERO_ZENA = (
    "https://cdn.aethon.com/wp-content/uploads/2026/06/"
    "Aethon_Website_Robot_Zena_FaceForward.webp"
)
HERO_ZENA_RX = (
    "https://cdn.aethon.com/wp-content/uploads/2026/06/"
    "Aethon_Website_Robot_ZenaRx_Solo_DarkTopandBottom.webp"
)

REJECTS: list[tuple[int, str]] = [
    (1766, "duplicate: keep T3 (1533)"),
    (1767, "duplicate: keep T3 XL (1534)"),
    (1768, "duplicate: keep Zena RX (1532)"),
    (1770, "phantom_sku: TUG Exchange off current OEM catalog"),
    (1771, "phantom_sku: TUG Drawer part-number shell off current OEM catalog"),
    (1772, "phantom_sku: TUG Drawer part-number shell off current OEM catalog"),
    (1773, "phantom_sku: TUG Drawer part-number shell off current OEM catalog"),
    (1774, "phantom_sku: TUG Door part-number shell off current OEM catalog"),
    (
        86,
        "wrong_media: Locus Vector primary; classic TUG superseded by T3/Zena catalog",
    ),
    (
        567,
        "wrong_media: non-Aethon warehouse AMR primary; TUG T4 off current OEM nav",
    ),
]

PRODUCTS: list[dict[str, Any]] = [
    {
        "id": 1533,
        "name": "T3",
        "model_name": "T3",
        "variant_code": "T3",
        "variant_label": "Standard",
        "url": "https://www.aethon.com/t3/",
        "family_key": "aethon:t3",
        "family_name": "T3",
        "family_url": "https://www.aethon.com/t3/",
        "product_url_scope": "exact_variant",
        "availability_status": AVAILABLE,
        "hero_src": HERO_T3,
        "hero_key": "t3-0-20260720.jpg",
        "payload_kg": 340.2,  # 750 lb
        "runtime_minutes": 720,  # 12 h
        "purpose": (
            "Autonomous cart transport in hospitals\n"
            "Material handling in hospitality facilities"
        ),
        "description": (
            "T3 is Aethon's autonomous cart-transport AMR for healthcare and "
            "hospitality. It locates, lifts, and secures carts for unattended "
            "delivery across facility floors."
        ),
        "features": (
            "OEM aethon.com/t3 (stored product copy + capacity claims): cart "
            "carrying 750 lb (340 kg); ~12-hour run-time with auto charging; "
            "omnidirectional 4-wheel drive; automatic cart pickup and drop-off; "
            "wireless elevator integration (ReadyElevator). Soft: detailed curb "
            "weight/dims not extracted (T3 PDP Wordfence-blocked this session); "
            "family studio hero shared historically with T3 XL."
        ),
        "use_keys": "material-handling|delivery|logistics",
        "industry_keys": "healthcare|hospitality|logistics",
        "tags": ["AMR", "Aethon", "T3", "TUG", "Healthcare", "Hospitality", "Cart", "USA"],
    },
    {
        "id": 1534,
        "name": "T3 XL",
        "model_name": "T3 XL",
        "variant_code": "T3-XL",
        "variant_label": "XL",
        "url": "https://www.aethon.com/t3/#t3-xl",
        "family_key": "aethon:t3",
        "family_name": "T3",
        "family_url": "https://www.aethon.com/t3/",
        "product_url_scope": "exact_variant",
        "availability_status": AVAILABLE,
        "hero_src": None,  # no distinct OEM XL still — keep existing CDN primary
        "payload_kg": 453.6,  # 1000 lb
        "runtime_minutes": 720,
        "purpose": (
            "Heavier autonomous cart transport in hospitals\n"
            "High-capacity material handling in hospitality"
        ),
        "description": (
            "T3 XL is the higher-capacity cart-transport variant of Aethon's T3 "
            "AMR, rated for heavier carts in healthcare and hospitality."
        ),
        "features": (
            "OEM aethon.com/t3/#t3-xl (stored product copy): cart carrying "
            "1,000 lb (454 kg); ~12-hour run-time with auto charging; "
            "omnidirectional 4-wheel drive; automatic cart pickup/drop-off; "
            "same T3 navigation/elevator stack. Soft: no distinct XL-only OEM "
            "studio still published — primary remains prior CDN family render "
            "(content-hash historically shared with T3)."
        ),
        "use_keys": "material-handling|delivery|logistics",
        "industry_keys": "healthcare|hospitality|logistics",
        "tags": ["AMR", "Aethon", "T3", "T3 XL", "Healthcare", "Hospitality", "Cart", "USA"],
    },
    {
        "id": 1532,
        "name": "Zena RX",
        "model_name": "Zena RX",
        "variant_code": "Zena-RX",
        "variant_label": "RX",
        "url": "https://www.aethon.com/zena-rx/",
        "family_key": "aethon:zena-rx",
        "family_name": "Zena RX",
        "family_url": "https://www.aethon.com/zena-rx/",
        "product_url_scope": "exact_variant",
        "availability_status": AVAILABLE,
        "hero_src": HERO_ZENA_RX,
        "hero_key": "zena-rx-0-20260720.jpg",
        "payload_kg": None,
        "runtime_minutes": None,
        "purpose": (
            "Secure pharmacy and lab specimen delivery\n"
            "Multi-stop hospital material transport"
        ),
        "description": (
            "Zena RX is Aethon's healthcare AMR with a high-capacity secure "
            "cabinet for pharmacy doses, lab specimens, and clinical materials."
        ),
        "features": (
            "OEM aethon.com/zena-rx: flexible high-capacity cabinet >10,000 "
            "cubic inches (~164 L); up to 4 secure deliveries per run; biometric "
            "access; basket accessories up to 16 baskets / 4 compartments; "
            "on-the-fly touchscreen reconfiguration; successor positioning vs "
            "T2 TUG. Soft: no public curb-weight kg on page text scrape."
        ),
        "use_keys": "delivery|material-handling|logistics",
        "industry_keys": "healthcare|logistics",
        "tags": ["AMR", "Aethon", "Zena", "Zena RX", "Healthcare", "Pharmacy", "USA"],
    },
    {
        "id": 1769,
        "name": "Zena",
        "model_name": "Zena",
        "variant_code": "Zena",
        "variant_label": "Hospitality",
        "url": "https://www.aethon.com/hospitality-robot-zena/",
        "family_key": "aethon:zena",
        "family_name": "Zena",
        "family_url": "https://www.aethon.com/hospitality-robot-zena/",
        "product_url_scope": "exact_variant",
        "availability_status": AVAILABLE,
        "hero_src": HERO_ZENA,
        "hero_key": "zena-0-20260720.jpg",
        "payload_kg": None,
        "runtime_minutes": None,
        "purpose": (
            "Guest-room amenity and food delivery in hotels\n"
            "Secure multi-compartment hospitality logistics"
        ),
        "description": (
            "Zena is Aethon's hospitality delivery AMR with four independently "
            "secured compartments for guest-room amenities, linens, food, and packages."
        ),
        "features": (
            "OEM aethon.com/hospitality-robot-zena: largest configurable "
            "hospitality payload claimed; 4 independently secured metal "
            "compartments (combinable to 2 larger); PIN/QR guest access; "
            "wireless elevator integration (no button-pushing arms); SMS guest "
            "notification; CE & FCC certified. Soft: no public curb-weight kg."
        ),
        "use_keys": "delivery|room-service|material-handling",
        "industry_keys": "hospitality|logistics",
        "tags": ["AMR", "Aethon", "Zena", "Hospitality", "Hotel", "USA"],
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


def reject_robot(client: ResearchApiClient, rid: int, reason: str) -> str:
    try:
        client._patch(
            f"robots/robots/{rid}/",
            {
                "status": "rejected",
                "notes": f"[REJECTED 2026-07-20] {reason}\n---\n",
                "rejection_reason": reason[:500],
            },
        )
        return "ok"
    except Exception as e:  # noqa: BLE001
        return f"fail {e}"


def force_en(client: ResearchApiClient, rid: int, row: dict[str, Any]) -> None:
    sync = {
        "updates": [
            {
                "id": rid,
                "locale": loc,
                "source_hash": f"aethon-en-force-{rid}-20260720-{loc}",
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
        resp = client._session.post(
            client._url("robots/robots/translation-sync/?force=1"),
            json=sync,
            timeout=60,
        )
        print(f"  translation-sync {rid}: {resp.status_code}")
    except requests.RequestException as e:
        print(f"  translation-sync warn {rid}: {e}")


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

    # Resolve use/industry keys that exist
    def map_keys(group: str, keys: str) -> list[int]:
        out = []
        for k in keys.split("|"):
            kid = tax[group].get(k.strip().lower())
            if kid:
                out.append(kid)
            else:
                print(f"  warn missing {group} key={k}")
        return out

    if args.apply:
        for rid, reason in REJECTS:
            print("reject", rid, reject_robot(client, rid, reason), reason)

    uploaded: dict[str, str] = {}
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
            f"[AI Research] Aethon enrich 2026-07-20: US; family {spec['family_key']}; "
            f"avail={spec['availability_status']}; catalog T3/Zena/Zena RX + legacy TUG."
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
            "payload_kg": spec.get("payload_kg"),
            "runtime_minutes": spec.get("runtime_minutes"),
            "notes": notes,
            "research_notes": notes,
            "sources": [
                {"url": spec["url"], "type": "website", "title": f"Aethon {spec['name']}"},
                {"url": "https://www.aethon.com/", "type": "website", "title": "Aethon home"},
            ],
            "information_source_urls": [spec["url"], "https://www.aethon.com/"],
        }
        if urls:
            row["image"] = urls[0]
            row["images"] = urls

        path = staging / f"{spec['model_name'].lower().replace(' ', '-')}.json"
        path.write_text(json.dumps(row, indent=2, ensure_ascii=False), encoding="utf-8")
        print("staged", path.name, "hero", bool(urls))

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
            "family_key": spec["family_key"],
            "family_name": spec["family_name"],
            "family_url": spec["family_url"],
            "notes": notes,
            "uses": map_keys("uses", spec["use_keys"]),
            "industries": map_keys("industries", spec["industry_keys"]),
            "movement_types": map_keys("movement", "wheeled"),
        }
        if spec.get("payload_kg") is not None:
            body["payload_kg"] = spec["payload_kg"]
        if spec.get("runtime_minutes") is not None:
            body["runtime_minutes"] = spec["runtime_minutes"]
        if urls:
            body["image"] = urls[0]
            body["s3_image"] = None
        client._patch(f"robots/robots/{spec['id']}/", body)
        force_en(client, spec["id"], row)
        if args.copy_media and urls:
            print(" copy-media", spec["id"], copy_media(spec["id"]))

    print("done apply=", args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
