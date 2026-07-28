"""Curated Bluefin Robotics / GDMS (160) enrich — UUV/AUV fleet.

OEM: https://gdmissionsystems.com/products/underwater-vehicles/
Company website: https://www.bluefinrobotics.com

Pending: Bluefin-9 (3607), Bluefin-12 (5043), HAUV (3608).
Published CJK Bluefin-21 (197) soft-filled EN; reject pending dupe 5044.

Speed: OEM knots → km/h (×1.852).

Usage:
  python discover_bluefin_robots.py --apply
"""
from __future__ import annotations

import argparse
import json
import os
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

COMPANY_SLUG = "bluefin-robotics"
COMPANY_NAME = "Bluefin Robotics (General Dynamics)"
US_ID = 20
AVAILABLE = 11
KT = 1.852  # knots → km/h
MEDIA = "https://gdmissionsystems.com/-/media/general-dynamics/maritime-and-strategic-systems/bluefin/images"
UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}
STAGING_IMG = _RESEARCH / "staging" / "research-staging" / "bluefin"
SERVER = _RESEARCH.parents[1] / "robotaigeek-server"

REJECTS = [
    (
        5044,
        "duplicate: keep published Bluefin-21 (197); 5044 is EN shell without media "
        "of the same GDMS Bluefin-21 UUV",
    ),
]

PRODUCTS: list[dict[str, Any]] = [
    {
        "id": 197,
        "published": True,
        "name": "Bluefin-21",
        "model_name": "Bluefin-21",
        "variant_code": "Bluefin-21",
        "variant_label": "21",
        "url": "https://gdmissionsystems.com/products/underwater-vehicles/bluefin-21-autonomous-underwater-vehicle",
        "family_key": "bluefin:21",
        "family_name": "Bluefin-21",
        "family_url": "https://gdmissionsystems.com/products/underwater-vehicles/bluefin-21-autonomous-underwater-vehicle",
        "product_url_scope": "exact_variant",
        "hero_url": None,  # keep existing CDN
        "speed": round(4.5 * KT, 2),  # up to 4.5 knots
        "length_mm": 4930,  # 16.2 ft
        "width_mm": 530,  # 21 in diameter
        "height_mm": 530,
        "weight_kg": 750.0,  # dry
        "runtime_minutes": 1500,  # 25 h @ 3 knots
        "purpose": (
            "Deep autonomous underwater survey and salvage\n"
            "Mine countermeasures and UXO search"
        ),
        "description": (
            "Bluefin-21 is General Dynamics Mission Systems' modular deep-rated "
            "unmanned underwater vehicle (UUV). Swappable payload and battery "
            "sections support extended missions to 4,500 m, launched from ships of "
            "opportunity worldwide."
        ),
        "features": (
            "OEM GDMS Bluefin-21: diameter 21 in (53 cm); length 16.2 ft (493 cm); "
            "dry weight 1,650 lb (750 kg); depth 14,763 ft (4,500 m); endurance 25 h "
            "@ 3 knots; speed up to 4.5 knots; 13.5 kWh Li-polymer (9×1.5 kWh); "
            "gimbaled ducted thruster; INS nav ≤0.1% DT CEP50; free-flooded modular "
            "payloads (side-scan, SBP, multibeam). Soft: MSRP not public."
        ),
        "use_keys": "inspection|monitoring|research|security",
        "industry_keys": "defense|marine-science-academia|oil-gas|research",
        "category_slugs": "Underwater|Marine",
        "movement_keys": "underwater|aquatic",
        "tags": ["Bluefin", "UUV", "AUV", "Underwater", "GDMS", "USA"],
        "sources": [
            {
                "url": "https://gdmissionsystems.com/products/underwater-vehicles/bluefin-21-autonomous-underwater-vehicle",
                "type": "website",
                "title": "OEM Bluefin-21",
            },
            {
                "url": "https://www.bluefinrobotics.com",
                "type": "website",
                "title": "Bluefin Robotics",
            },
        ],
    },
    {
        "id": 3607,
        "name": "Bluefin-9",
        "model_name": "Bluefin-9",
        "variant_code": "Bluefin-9",
        "variant_label": "9",
        "url": "https://gdmissionsystems.com/products/underwater-vehicles/bluefin-9-autonomous-underwater-vehicle",
        "family_key": "bluefin:9",
        "family_name": "Bluefin-9",
        "family_url": "https://gdmissionsystems.com/products/underwater-vehicles/bluefin-9-autonomous-underwater-vehicle",
        "product_url_scope": "exact_variant",
        "hero_url": f"{MEDIA}/bluefin-9-redesigned/bluefin-robotics-bluefin-9-uuv.ashx",
        "speed": round(6.0 * KT, 2),
        "length_mm": 2418,  # 95.2 in
        "width_mm": 238,  # 9.375 in
        "height_mm": 264,  # 10.375 in
        "weight_kg": 70.0,
        "runtime_minutes": 480,  # 8 h @ 3 kt
        "purpose": (
            "Two-person-portable high-resolution seabed survey\n"
            "Littoral hydrographic and environmental sensing"
        ),
        "description": (
            "Bluefin-9 is a two-man-portable autonomous UUV from General Dynamics "
            "Mission Systems / Bluefin Robotics. It integrates Sonardyne Solstice "
            "multi-aperture sonar, HD camera, and environmental sensors for "
            "high-resolution littoral surveys with rapid battery/RDSM swap."
        ),
        "features": (
            "OEM GDMS Bluefin-9: ~9.375×10.375 in cross-section; length 95.2 in "
            "(241.8 cm); 155 lb (70 kg); depth 656 ft (200 m); endurance 8 h @ 3 kt; "
            "sustained speed up to 6 knots; 1.9 kWh swappable Li-ion; Solstice MAS "
            "200 m swath / 0.15° along-track; nav ≤0.3% DT CEP50; 1 TB RDSM + HD "
            "camera. Soft: MSRP not public."
        ),
        "use_keys": "inspection|monitoring|research|security",
        "industry_keys": "defense|marine-science-academia|research",
        "category_slugs": "Underwater|Marine",
        "movement_keys": "underwater|aquatic",
        "tags": ["Bluefin", "Bluefin-9", "UUV", "AUV", "Solstice", "USA"],
        "sources": [
            {
                "url": "https://gdmissionsystems.com/products/underwater-vehicles/bluefin-9-autonomous-underwater-vehicle",
                "type": "website",
                "title": "OEM Bluefin-9",
            },
            {
                "url": "https://www.bluefinrobotics.com",
                "type": "website",
                "title": "Bluefin Robotics",
            },
        ],
    },
    {
        "id": 5043,
        "name": "Bluefin-12",
        "model_name": "Bluefin-12",
        "variant_code": "Bluefin-12",
        "variant_label": "12",
        "url": "https://gdmissionsystems.com/products/underwater-vehicles/bluefin-12-unmanned-underwater-vehicle",
        "family_key": "bluefin:12",
        "family_name": "Bluefin-12",
        "family_url": "https://gdmissionsystems.com/products/underwater-vehicles/bluefin-12-unmanned-underwater-vehicle",
        "product_url_scope": "exact_variant",
        "hero_url": f"{MEDIA}/bluefin-12-redesigned/bluefin-12-uuv-product-cut-out-right-front.ashx",
        "speed": round(6.0 * KT, 2),
        "length_mm": 4830,  # 15.8 ft
        "width_mm": 320,  # 12.8 in diameter
        "height_mm": 320,
        "weight_kg": 250.0,  # with survey package
        "runtime_minutes": 1440,  # 24 h @ 3 kt
        "purpose": (
            "Medium-class modular underwater survey missions\n"
            "Long-endurance hydrographic and MCM sensing"
        ),
        "description": (
            "Bluefin-12 is General Dynamics' lightweight medium-class UUV with an open "
            "payload bay (>4,000 cm³) and optional Integrated Survey Package "
            "(Solstice MAS, HD camera, environmental sensors) for long-endurance "
            "mission-critical underwater data collection."
        ),
        "features": (
            "OEM GDMS Bluefin-12: diameter 12.8 in (32 cm); length 15.8 ft (4.83 m); "
            "550 lb (250 kg) with survey package; depth 656 ft (200 m); endurance "
            "24 h @ 3 kt / 36 h @ 2 kt; speed up to 6 knots; four 1.9 kWh Li-ion; "
            "nav ≤0.1% DT CEP50; optional Solstice MAS + RDSM + FLS. Soft: MSRP not "
            "public; base vs survey weight differs."
        ),
        "use_keys": "inspection|monitoring|research|security",
        "industry_keys": "defense|marine-science-academia|oil-gas|research",
        "category_slugs": "Underwater|Marine",
        "movement_keys": "underwater|aquatic",
        "tags": ["Bluefin", "Bluefin-12", "UUV", "AUV", "Modular", "USA"],
        "sources": [
            {
                "url": "https://gdmissionsystems.com/products/underwater-vehicles/bluefin-12-unmanned-underwater-vehicle",
                "type": "website",
                "title": "OEM Bluefin-12",
            },
            {
                "url": "https://www.bluefinrobotics.com",
                "type": "website",
                "title": "Bluefin Robotics",
            },
        ],
    },
    {
        "id": 3608,
        "name": "Bluefin HAUV",
        "model_name": "Bluefin HAUV",
        "variant_code": "HAUV",
        "variant_label": "HAUV",
        "url": "https://gdmissionsystems.com/products/underwater-vehicles/bluefin-hauv",
        "family_key": "bluefin:hauv",
        "family_name": "Bluefin HAUV",
        "family_url": "https://gdmissionsystems.com/products/underwater-vehicles/bluefin-hauv",
        "product_url_scope": "exact_variant",
        "hero_url": f"{MEDIA}/bluefin-hauv/hauv-carousel-1.ashx",
        "speed": round(0.5 * KT, 2),  # up to 0.5 knots standard
        "length_mm": 1330,  # 52.5 in
        "width_mm": 930,  # 36.75 in
        "height_mm": 380,  # 15 in
        "weight_kg": 72.6,
        "runtime_minutes": 210,  # 3.5 h
        "purpose": (
            "Ship-hull and infrastructure hovering inspection\n"
            "Port security and MCM contact relocation"
        ),
        "description": (
            "Bluefin HAUV is a two-person-portable hovering autonomous underwater "
            "vehicle for ship hull and structure inspection. Five thrusters enable "
            "hover/rotate/translate; high-resolution imaging sonar (ARIS) supports "
            "autonomous surveys with optional tethered manual control."
        ),
        "features": (
            "OEM GDMS HAUV: 52.5×36.75×15 in (133×93×38 cm); dry 166.5 lb (72.6 kg); "
            "depth 100 ft (30 m) / optional 200 ft; endurance up to 3.5 h; speed up to "
            "0.5 knots (1.5 optional); 1.5 kWh battery; five thrusters; contact "
            "relocate ≤2 m CEP50; Sound Metrics ARIS Explorer 3000 imaging sonar. "
            "Soft: MSRP not public."
        ),
        "use_keys": "inspection|monitoring|security|research",
        "industry_keys": "defense|marine-science-academia|security|research",
        "category_slugs": "Underwater|Marine",
        "movement_keys": "underwater|aquatic",
        "tags": ["Bluefin", "HAUV", "Hovering", "Hull Inspection", "AUV", "USA"],
        "sources": [
            {
                "url": "https://gdmissionsystems.com/products/underwater-vehicles/bluefin-hauv",
                "type": "website",
                "title": "OEM Bluefin HAUV",
            },
            {
                "url": "https://www.bluefinrobotics.com",
                "type": "website",
                "title": "Bluefin Robotics",
            },
        ],
    },
]


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


def map_keys(tax: dict[str, dict[str, int]], group: str, keys: str) -> list[int]:
    out = []
    for k in keys.split("|"):
        kid = tax[group].get(k.strip().lower())
        if kid:
            out.append(kid)
        else:
            print(f"  warn missing {group}={k}")
    return out


def force_en(client: ResearchApiClient, rid: int, row: dict[str, Any]) -> None:
    sync = {
        "updates": [
            {
                "id": rid,
                "locale": loc,
                "source_hash": f"bluefin-en-{rid}-20260720-{loc}",
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


def download_hero(url: str, slug: str) -> Path:
    STAGING_IMG.mkdir(parents=True, exist_ok=True)
    dest = STAGING_IMG / f"{slug}.jpg"
    r = requests.get(url, headers=UA, timeout=120)
    r.raise_for_status()
    dest.write_bytes(r.content)
    print(f"  downloaded {dest.name} {len(r.content)} bytes ct={r.headers.get('content-type')}")
    return dest


def copy_media(rid: int) -> str:
    secret = os.environ.get("INTERNAL_API_SECRET", "").strip()
    if not secret and (SERVER / ".env").is_file():
        for line in (SERVER / ".env").read_text(encoding="utf-8").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                secret = line.split("=", 1)[1].strip()
                break
    api = (
        os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/").replace("/api/v1", "")
        or "https://ragadmin.robotaigeek.com"
    )
    url = f"{api}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/?force=1"
    for attempt in range(4):
        try:
            resp = requests.post(url, headers={"X-Internal-Secret": secret}, timeout=180)
            if resp.ok:
                return f"ok {resp.text[:120]}"
            if resp.status_code not in (500, 502, 503, 504):
                return f"HTTP {resp.status_code} {(resp.text or '')[:80]}"
        except requests.RequestException as e:
            last = str(e)
        time.sleep(2**attempt)
    return f"fail {last if 'last' in dir() else ''}"


def reject_dupes(client: ResearchApiClient) -> None:
    for rid, reason in REJECTS:
        try:
            client._patch(
                f"robots/robots/{rid}/",
                {
                    "status": "rejected",
                    "rejection_reason": reason[:500],
                    "notes": f"[AI Research] Rejected 2026-07-20: {reason}",
                },
            )
            print("rejected", rid)
        except Exception as e:
            print("reject FAIL", rid, e)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--local", action="store_true")
    args = ap.parse_args()
    if not args.apply:
        print("dry-run: pass --apply to write")
        for p in PRODUCTS:
            flag = "PUB" if p.get("published") else "PEND"
            print(f"  {flag} {p['id']} {p['name']} fam={p['family_key']}")
        for rid, reason in REJECTS:
            print(f"  REJECT {rid} {reason[:60]}")
        return 0

    client = ResearchApiClient()
    tax = taxonomy_ids(client)
    reject_dupes(client)
    staging = _RESEARCH / "staging" / "robots" / "bluefin"
    staging.mkdir(parents=True, exist_ok=True)

    for spec in PRODUCTS:
        existing = client._get(f"robots/robots/{spec['id']}/")
        img = existing.get("image") or existing.get("s3_image") or ""
        replace_media = False
        if spec.get("hero_url"):
            local = download_hero(spec["hero_url"], spec["variant_code"].lower())
            # Prefer absolute file URI for import when supported; else remote OEM URL
            img = str(local.resolve())
            replace_media = True
        notes = (
            f"[AI Research] Bluefin enrich 2026-07-20: US; family {spec['family_key']}; "
            f"OEM GDMS specs (knots→km/h); Available."
        )
        info_urls = [s["url"] for s in spec["sources"]]
        status = "published" if spec.get("published") else "pending_review"
        if spec.get("published"):
            status = existing.get("status") or "published"
        row = {
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
            "image": img if not replace_media else (spec["hero_url"] or img),
            "images": [img if not replace_media else (spec["hero_url"] or img)],
            "source_locale": "en",
            "availability_status": AVAILABLE,
            "family_key": spec["family_key"],
            "family_name": spec["family_name"],
            "family_url": spec["family_url"],
            "product_url_scope": spec["product_url_scope"],
            "movement_type_keys": spec["movement_keys"],
            "category_slugs": spec["category_slugs"],
            "use_keys": spec["use_keys"],
            "industry_keys": spec["industry_keys"],
            "tags": spec["tags"],
            "notes": notes,
            "research_notes": notes,
            "sources": spec["sources"],
            "information_source_urls": info_urls,
            "speed": spec["speed"],
            "length_mm": spec["length_mm"],
            "width_mm": spec["width_mm"],
            "height_mm": spec["height_mm"],
            "weight_kg": spec["weight_kg"],
            "runtime_minutes": spec["runtime_minutes"],
        }
        # For new heroes use OEM URL so import+copy-media can fetch
        if spec.get("hero_url"):
            row["image"] = spec["hero_url"]
            row["images"] = [spec["hero_url"]]
        path = staging / f"{spec['variant_code'].lower()}.json"
        path.write_text(json.dumps(row, indent=2, ensure_ascii=False), encoding="utf-8")
        print("staged", path.name)
        print(
            "import",
            spec["id"],
            import_staging(
                path,
                dry_run=False,
                patch=True,
                force_overwrite=True,
                replace_media=replace_media,
                status=status if spec.get("published") else "pending_review",
                created_by_id=resolve_created_by_id(1),
                skip_company_update=True,
            ),
        )
        body: dict[str, Any] = {
            "name": spec["name"],
            "manufacturer_countries": [US_ID],
            "manufacturer_country_ref": US_ID,
            "availability_status": AVAILABLE,
            "description": spec["description"],
            "features": spec["features"],
            "purpose": spec["purpose"],
            "url": spec["url"],
            "information_source_urls": info_urls,
            "family_key": spec["family_key"],
            "family_name": spec["family_name"],
            "family_url": spec["family_url"],
            "model_name": spec["model_name"],
            "variant_code": spec["variant_code"],
            "variant_label": spec["variant_label"],
            "product_url_scope": spec["product_url_scope"],
            "notes": notes,
            "tags": spec["tags"],
            "uses": map_keys(tax, "uses", spec["use_keys"]),
            "industries": map_keys(tax, "industries", spec["industry_keys"]),
            "movement_types": map_keys(tax, "movement", spec["movement_keys"]),
            "speed": spec["speed"],
            "length_mm": spec["length_mm"],
            "width_mm": spec["width_mm"],
            "height_mm": spec["height_mm"],
            "weight_kg": spec["weight_kg"],
            "runtime_minutes": spec["runtime_minutes"],
        }
        try:
            client._patch(f"robots/robots/{spec['id']}/", body)
            print("patch OK", spec["id"])
        except Exception as e:
            print("patch FAIL", spec["id"], e)
            slim = {k: body[k] for k in list(body) if k not in ("tags", "uses", "industries", "movement_types")}
            try:
                client._patch(f"robots/robots/{spec['id']}/", slim)
                print("slim patch OK", spec["id"])
            except Exception as e2:
                print("slim FAIL", spec["id"], e2)
        force_en(client, spec["id"], row)
        if replace_media:
            print("  copy-media", copy_media(spec["id"]))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
