"""Soft enrich Nitto Seiko America (1415) industrial screw-driving robots.

OEM US: https://nittoseikoamerica.com
Parent JP catalogs used only to cite typed specs that match US SKUs.
Manufacturer country: US=20 (America subsidiary / overnight US drain).

Pending SR Yθ fleet + PD400UR (UR+ screwdriving unit — EOAT, kept as queue SKU).

Usage:
  python discover_nitto_robots.py
  python discover_nitto_robots.py --apply --copy-media
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

COMPANY_ID = 1415
COMPANY_SLUG = "nitto-seiko-america"
COMPANY_NAME = "Nitto Seiko America"
COMPANY_WEBSITE = "https://nittoseikoamerica.com"
US_ID = 20
AVAILABLE = 11
UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}
SERVER = _RESEARCH.parents[1] / "robotaigeek-server"
FAMILY_URL = "https://nittoseikoamerica.com/"
JP_SR580_PDF = "https://www.nittoseiko.co.jp/dcms_media/other/NS-056-E_SR580.pdf"
JP_PD400 = (
    "https://www.nittoseiko.co.jp/en/en_products/search/index.php/item"
    "?cell003=AUTOMATIC+ASSEMBLY+MACHINE"
    "&cell004=Screw+Driving+Unit+for+Collaborative+Robots"
    "&id=4150&label=1&name=PD400UR"
)

PRODUCTS: list[dict[str, Any]] = [
    {
        "id": 4239,
        "name": "SR375Y-THETA",
        "model_name": "SR375Yθ",
        "variant_code": "SR375Y-THETA",
        "variant_label": "Light-Duty",
        "url": "https://nittoseikoamerica.com/Product/Detail/SR375YO",
        "family_key": "nitto:sr375",
        "family_name": "SR375Yθ",
        "family_url": "https://nittoseikoamerica.com/Product/Detail/SR375YO",
        "hero_url": "https://nittoseikoamerica.com/img/products/product-SR375YO.jpg",
        "dof": 2,
        "purpose": (
            "Automated light-duty screw fastening\n"
            "Yθ linear + swivel blow-fed assembly cell"
        ),
        "description": (
            "The SR375Y-THETA (SR375Yθ) is Nitto Seiko America's light-duty Yθ screw "
            "driving robot: AC-servo Y and θ axes with a pneumatic screwdriver stroke "
            "and NITTO spindle driver, automatically blow-fed from a centerboard hopper "
            "feeder with single-shuttle escapement."
        ),
        "features": (
            "OEM nittoseikoamerica.com/Product/Detail/SR375YO: light-duty Yθ (linear + "
            "swivel) screw driving robot; THETA and Y powered by AC servo motors; "
            "screwdriver stroke pneumatic; spindle rotation by NITTO driver; screws "
            "blow-fed via centerboard hopper with single-shuttle air escapement. Soft: "
            "typed torque/screw size/weight not on US detail page this pass."
        ),
        "use_keys": "assembly|pick-and-place|quality-inspection",
        "industry_keys": "manufacturing|automotive|electronics",
        "category_slugs": "Industrial-Robot",
        "movement_keys": "stationary|fixed",
        "tags": ["Nitto", "SR375", "Screw Driving", "Y-theta", "Assembly", "USA"],
        "sources": [
            {
                "url": "https://nittoseikoamerica.com/Product/Detail/SR375YO",
                "type": "website",
                "title": "OEM SR375Yθ",
            },
        ],
    },
    {
        "id": 3183,
        "name": "SR580Y-THETA-Z",
        "model_name": "SR580Yθ-Z",
        "variant_code": "SR580Y-THETA-Z",
        "variant_label": "Medium-Duty",
        "url": "https://nittoseikoamerica.com/Product/Detail/SR565YOZ",
        "family_key": "nitto:sr580",
        "family_name": "SR580Yθ-Z",
        "family_url": "https://nittoseikoamerica.com/Product/Detail/SR565YOZ",
        "hero_url": "https://nittoseikoamerica.com/img/products/product-SR565YO.jpg",
        "dof": 3,
        "weight_kg": 37.0,
        "purpose": (
            "Automated medium-duty screw fastening\n"
            "Thrust-controlled Yθ-Z assembly fastening"
        ),
        "description": (
            "The SR580Y-THETA-Z (SR580Yθ-Z) is Nitto Seiko America's medium-duty "
            "three-axis Yθ-Z screw driving robot for space-saving automated fastening "
            "of M2–M5 screws with closed-loop thrust control and blow-feed or pickup."
        ),
        "features": (
            "OEM US SR565YOZ + JP NS-056-E SR580Yθ-Z: screws M2–M5 (max length 18 mm; "
            "US page); torque 0.29–2.94 Nm (US) / 0.3–3.0 N·m (JP); three axes "
            "simultaneous; Z fastening stroke 100 mm [150 opt]; locating ±0.05 mm; "
            "Y envelope 200–500 mm; θ radius 200–300 mm / 180°; max speeds Y "
            "1000 mm/s, θ 360°/s, Z 720 mm/s; machine weight ~37 kg; air 0.4–0.5 MPa; "
            "vacuum tube screw hold; KX/[NX] driver. Soft: vehicle speed N/A "
            "(stationary cell); price not public."
        ),
        "use_keys": "assembly|pick-and-place|quality-inspection",
        "industry_keys": "manufacturing|automotive|electronics",
        "category_slugs": "Industrial-Robot",
        "movement_keys": "stationary|fixed",
        "tags": ["Nitto", "SR580", "Screw Driving", "Y-theta", "Assembly", "USA"],
        "sources": [
            {
                "url": "https://nittoseikoamerica.com/Product/Detail/SR565YOZ",
                "type": "website",
                "title": "OEM SR580Yθ-Z (US)",
            },
            {"url": JP_SR580_PDF, "type": "datasheet", "title": "NS-056-E SR580 PDF"},
        ],
    },
    {
        "id": 3184,
        "name": "SR580Y-THETA-Z Vision Guided",
        "model_name": "SR580Yθ-Z Vision",
        "variant_code": "SR580Y-THETA-Z-V",
        "variant_label": "Vision Guided",
        "url": "https://nittoseikoamerica.com/Product/Detail/SR565YOZ-V",
        "family_key": "nitto:sr580",
        "family_name": "SR580Yθ-Z",
        "family_url": "https://nittoseikoamerica.com/Product/Detail/SR565YOZ",
        # OEM PDP references SR580_SD600T.jpg → HTTP 404; fail-closed (no sibling hero)
        "hero_url": None,
        "dof": 3,
        "weight_kg": 37.0,
        "purpose": (
            "Vision-guided automated screw fastening\n"
            "Position-corrected Yθ-Z driving on misaligned parts"
        ),
        "description": (
            "Vision-guided SR580Y-THETA-Z corrects up to 10 mm of hole misalignment to "
            "less than 10% of nominal screw diameter before fastening, combining the "
            "medium-duty Yθ-Z cell with a vision position-correction system."
        ),
        "features": (
            "OEM nittoseikoamerica.com/Product/Detail/SR565YOZ-V: Vision Guided "
            "SR580YθZ — max 10 mm misalignment corrected to <10% of nominal screw "
            "diameter. Shares SR580Yθ-Z platform specs (M2–M5, ~0.3–3.0 N·m, ~37 kg, "
            "3 axes, ±0.05 mm). Soft: camera SKU / FOV not typed on US page."
        ),
        "use_keys": "assembly|quality-inspection|pick-and-place",
        "industry_keys": "manufacturing|automotive|electronics",
        "category_slugs": "Industrial-Robot",
        "movement_keys": "stationary|fixed",
        "tags": [
            "Nitto", "SR580", "Vision", "Screw Driving", "Y-theta", "Assembly", "USA"
        ],
        "sources": [
            {
                "url": "https://nittoseikoamerica.com/Product/Detail/SR565YOZ-V",
                "type": "website",
                "title": "OEM Vision Guided SR580Yθ-Z",
            },
            {"url": JP_SR580_PDF, "type": "datasheet", "title": "NS-056-E SR580 PDF"},
        ],
    },
    {
        "id": 3185,
        "name": "SR780Y-THETA-Z",
        "model_name": "SR780Yθ",
        "variant_code": "SR780Y-THETA-Z",
        "variant_label": "Heavy-Duty",
        "url": "https://nittoseikoamerica.com/Product/Detail/SR765YO",
        "family_key": "nitto:sr780",
        "family_name": "SR780Yθ",
        "family_url": "https://nittoseikoamerica.com/Product/Detail/SR765YO",
        # OEM PDP references SR765YO.jpg → HTTP 404; fail-closed
        "hero_url": None,
        "dof": 3,
        "purpose": (
            "Automated heavy-duty screw fastening\n"
            "High-torque Yθ screw driving for M5–M8 bolts"
        ),
        "description": (
            "The SR780Y-THETA-Z (SR780Yθ) is Nitto Seiko America's heavy-duty Yθ screw "
            "driving robot for high-power fastening of M5–M8 screws, with AC-servo Y/θ "
            "and Z stroke, NITTO spindle driver, and blow-fed centerboard hopper feed."
        ),
        "features": (
            "OEM nittoseikoamerica.com/Product/Detail/SR765YO: screw sizes M5–M8 "
            "(max length 35 mm); torque range 3.92–15.70 Nm; max chuck stroke 100 mm "
            "(3.94 in); Yθ + Z AC servo axes; NITTO driver; blow-fed hopper with "
            "single-shuttle escapement. Parent JP SR780Yθ cites up to 22 Nm max class. "
            "Soft: machine weight / envelope not on US detail page this pass."
        ),
        "use_keys": "assembly|pick-and-place|quality-inspection",
        "industry_keys": "manufacturing|automotive|electronics",
        "category_slugs": "Industrial-Robot",
        "movement_keys": "stationary|fixed",
        "tags": ["Nitto", "SR780", "Heavy Duty", "Screw Driving", "Assembly", "USA"],
        "sources": [
            {
                "url": "https://nittoseikoamerica.com/Product/Detail/SR765YO",
                "type": "website",
                "title": "OEM SR780Yθ",
            },
        ],
    },
    {
        "id": 2204,
        "name": "PD400UR",
        "model_name": "PD400UR",
        "variant_code": "PD400UR",
        "variant_label": "UR+ Screw Unit",
        "url": "https://nittoseikoamerica.com/Product/Detail/1100",
        "family_key": "nitto:pd400",
        "family_name": "PD400UR",
        "family_url": "https://nittoseikoamerica.com/Product/Detail/1100",
        "hero_url": "https://nittoseikoamerica.com/img/products/1_PD400UR.800.jpg",
        "weight_kg": 1.7,  # unit 1.6–1.8 kg mid
        "dof": None,  # EOAT on UR arm
        "purpose": (
            "Screwdriving end-effector for Universal Robots cobots\n"
            "UR+ certified automated fastening unit"
        ),
        "description": (
            "PD400UR is Nitto Seiko's UR+ certified screwdriving unit for Universal "
            "Robots collaborative arms (magnet or vacuum bit). It pairs NX-series "
            "drivers with the SD600T controller for teach-pendant setup and rundown "
            "data — an EOAT/unit, not a standalone robot arm."
        ),
        "features": (
            "OEM US Product/Detail/1100 + JP PD400UR release: torque 0.5–6.0 N·m; max "
            "1100 rpm; screws M2.5–M5 (length ≤15 mm); unit mass 1.6–1.8 kg; controller "
            "SD600T ~1.4 kg; ISO 9409-1-50-4-M6 flange; URCap NS SD600T; Polyscope 5.4+; "
            "magnet (PD400URM) / vacuum (PD400URV) variants; first Japanese-made UR+ "
            "screwdriving unit. Soft: this is EOAT — kept as pending queue SKU."
        ),
        "use_keys": "assembly|pick-and-place",
        "industry_keys": "manufacturing|electronics|automotive",
        "category_slugs": "Industrial-Robot",
        "movement_keys": "stationary|fixed",
        "tags": ["Nitto", "PD400UR", "UR+", "Cobot", "Screwdriving", "EOAT", "USA"],
        "sources": [
            {
                "url": "https://nittoseikoamerica.com/Product/Detail/1100",
                "type": "website",
                "title": "OEM PD400UR (US)",
            },
            {"url": JP_PD400, "type": "website", "title": "OEM PD400UR (JP)"},
            {
                "url": "http://nittoseikoamerica.com/files/PD400UR%20(Low%20Resolution).pdf",
                "type": "datasheet",
                "title": "PD400UR brochure PDF",
            },
        ],
    },
]


def taxonomy_ids(client: ResearchApiClient) -> dict[str, dict[str, int]]:
    def idx(path: str) -> dict[str, int]:
        rows = client._get(path)
        if isinstance(rows, dict):
            rows = rows.get("results") or []
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
                "source_hash": f"nitto-en-{rid}-20260720-{loc}",
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
                return f"fail {resp.status_code} {resp.text[:120]}"
        except requests.RequestException as e:
            last = str(e)
        time.sleep(2 + attempt)
    return "fail after retries"


def patch_company(client: ResearchApiClient) -> None:
    body = {"website": COMPANY_WEBSITE, "country_id": US_ID}
    for path in (f"companies/{COMPANY_ID}/", f"companies/companies/{COMPANY_ID}/"):
        try:
            client._patch(path, body)
            print("company patched", path)
            return
        except Exception as e:
            print("company patch warn", path, e)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--copy-media", action="store_true")
    args = ap.parse_args()

    if not args.apply:
        for p in PRODUCTS:
            print(p["id"], p["name"], p["family_key"], p["url"])
        return 0

    client = ResearchApiClient()
    tax = taxonomy_ids(client)
    staging = _RESEARCH / "staging" / "robots" / "nitto-seiko"
    staging.mkdir(parents=True, exist_ok=True)
    patch_company(client)

    for spec in PRODUCTS:
        notes = (
            f"[AI Research] Nitto enrich 2026-07-20: US; family {spec['family_key']}; "
            "Available; soft fills from US PDP + JP datasheet where cited."
        )
        info_urls = [s["url"] for s in spec["sources"]]
        hero = spec.get("hero_url") or ""
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
            "image": hero,
            "images": [hero] if hero else [],
            "source_locale": "en",
            "availability_status": AVAILABLE,
            "family_key": spec["family_key"],
            "family_name": spec["family_name"],
            "family_url": spec["family_url"],
            "product_url_scope": "exact_variant",
            "movement_type_keys": spec["movement_keys"],
            "category_slugs": spec["category_slugs"],
            "use_keys": spec["use_keys"],
            "industry_keys": spec["industry_keys"],
            "tags": spec["tags"],
            "notes": notes,
            "research_notes": notes,
            "sources": spec["sources"],
            "information_source_urls": info_urls,
            "weight_kg": spec.get("weight_kg"),
            "dof": spec.get("dof"),
        }
        path = staging / f"{spec['variant_code'].lower().replace(' ', '-')}.json"
        path.write_text(json.dumps(row, indent=2, ensure_ascii=False), encoding="utf-8")
        print(
            "import",
            spec["id"],
            import_staging(
                path,
                dry_run=False,
                patch=True,
                force_overwrite=True,
                replace_media=bool(hero),
                status="pending_review",
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
            "product_url_scope": "exact_variant",
            "notes": notes,
            "tags": spec["tags"],
            "uses": map_keys(tax, "uses", spec["use_keys"]),
            "industries": map_keys(tax, "industries", spec["industry_keys"]),
            "movement_types": map_keys(tax, "movement", spec["movement_keys"]),
        }
        if spec.get("weight_kg") is not None:
            body["weight_kg"] = spec["weight_kg"]
        if spec.get("dof") is not None:
            body["dof"] = spec["dof"]
        try:
            client._patch(f"robots/robots/{spec['id']}/", body)
            print("patch OK", spec["id"])
        except Exception as e:
            print("patch FAIL", spec["id"], e)
            slim = {
                k: body[k]
                for k in body
                if k not in ("tags", "uses", "industries", "movement_types")
            }
            try:
                client._patch(f"robots/robots/{spec['id']}/", slim)
                print("slim patch OK", spec["id"])
            except Exception as e2:
                print("slim FAIL", spec["id"], e2)
        force_en(client, spec["id"], row)
        if args.copy_media and hero:
            print("  copy-media", copy_media(spec["id"]))

    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
