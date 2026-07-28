"""Curate Foshan Tefude Automation (company 1404).

Maps SEO/solution shells onto citeable OEM SKUs (TFD-RD4 / TFD-RP4),
rejects category/packaging-machine shells, replaces shared banner heroes
with distinct TEFUDE product photos. Leaves status=pending_review.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
from pathlib import Path
from typing import Any

import requests
from PIL import Image

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from api_client import ResearchApiClient
from load_env import load_research_env
from tag_suggest import TagCatalog

load_research_env(local="--local" in sys.argv)

COMPANY_ID = 1404
COMPANY_SLUG = "foshan-tefude-automation"
COMPANY_NAME = "Foshan Tefude Automation Co., Ltd."
COMPANY_WEBSITE = "https://www.tefude.com/"
CHINA = 3
AVAILABLE = 11
REPORT = _HERE / "staging" / "reports" / "tefude-1404-curated-report.json"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
    ),
    "Referer": "https://www.tefude.com/",
}

URL_RD4 = (
    "https://www.tefude.com/industrial-robotic-arm/pick-and-place-robotic-arm/"
    "high-speed-pick-place-delta-parallel-robot.html"
)
URL_RP4 = (
    "https://www.tefude.com/industrial-robotic-arm/industrial-palletizing-robot/"
    "4-axis-industrial-palletizing-robot-for.html"
)
URL_JOINT = (
    "https://www.tefude.com/industrial-robotic-arm/"
    "4-axis-industrial-joint-parallel-robot.html"
)
HUB_ARM = "https://www.tefude.com/industrial-robotic-arm/"

# Distinct official gallery heroes (no shared site banner 728e8af0…).
# RD4 packing-line composites fail the robot-dominant gate — after scalar apply,
# run fix_tefude_1404_rd4_heroes.py --apply (DETAIL DISPLAY crops + cell).
# These URLs are preflight placeholders only; RD4 CDN heroes are crop uploads.
IMG_RD4_600 = (
    "https://www.tefude.com/uploads/202643607/"
    "high-speed-pick-place-delta-parallel-robotc228bd29-4308-4d2e-8855-6b4042b7776a.jpg"
)
IMG_RD4_800 = (
    "https://www.tefude.com/uploads/43607/products/p2026070611155300b3f.jpg"
)
IMG_RD4_1200 = (
    "https://www.tefude.com/uploads/202643607/"
    "high-speed-pick-place-delta-parallel-robotb810bcfa-4ea9-4af5-97fe-6df71c90c5cd.jpg"
)
IMG_RD4_1600 = (
    "https://www.tefude.com/uploads/43607/4-axis-robotic-armd5003.jpg"
)
IMG_RP4_30 = (
    "https://www.tefude.com/uploads/202643607/"
    "4-axis-industrial-palletizing-robot-for3433efd6-0b77-4319-9d9d-524b9693b6a7.jpg"
)
IMG_RP4_50 = (
    "https://www.tefude.com/uploads/202643607/"
    "4-axis-industrial-palletizing-robot-fordc094dda-4f06-49ea-baf1-d6ac3e6e1a4e.jpg"
)
IMG_JOINT = (
    "https://www.tefude.com/uploads/43607/4-axis-industrial-joint-parallel-robotc217c.jpg"
)

USES_PICK = [21, 25, 46, 30]
USES_PALLET = [21, 25, 48, 49]
INDUSTRIES = [12]
MOV_STATIONARY = [10]

TAGS_DELTA = [
    "Delta",
    "Pick-and-Place",
    "Industrial",
    "Industrial Arm",
    "Food Handling",
    "Factory Automation",
    "Automation",
    "4-axis",
]
TAGS_PALLET = [
    "Palletizing",
    "Industrial",
    "Industrial Arm",
    "Material Handling",
    "Factory Automation",
    "Automation",
    "4-axis",
    "Logistics",
]
TAGS_JOINT = [
    "SCARA",
    "Pick-and-Place",
    "Industrial",
    "Industrial Arm",
    "Factory Automation",
    "Automation",
    "4-axis",
    "Food Handling",
]


def _rd4(
    *,
    name: str,
    model: str,
    payload_kg: float,
    reach_mm: float,
    weight_kg: float,
    rep: float,
    z_mm: float,
    cycles: int,
    image: str,
) -> dict[str, Any]:
    return {
        "name": name,
        "model_name": model,
        "variant_code": model,
        "variant_label": model,
        "url": URL_RD4,
        "family_key": f"{COMPANY_SLUG}:tfd-rd4",
        "family_name": "TFD-RD4",
        "family_url": URL_RD4,
        "product_url_scope": "family",
        "description": (
            f"{name} is Tefude's 3+1-axis Delta parallel pick-and-place robot "
            "for high-speed food and packaging lines, typically integrated with "
            "vision, conveying, and cartoning cells."
        ),
        "features": (
            f"{payload_kg:g} kg max payload; R{reach_mm:g} mm working diameter; "
            f"{z_mm:g} mm pick/place height; ±{rep:g} mm XYZ repeatability; "
            f"up to {cycles} cycles/min; {weight_kg:g} kg machine mass; "
            "hoisting installation; IP54; 8in/8out expandable I/O."
        ),
        "purpose": (
            "High-speed pick-and-place\n"
            "Tray loading and cartoning\n"
            "Food and pharma packaging"
        ),
        "typed": {
            "payload_kg": payload_kg,
            "reach_mm": reach_mm,
            "weight_kg": weight_kg,
            "repeatability_mm": rep,
            "dof": 4,
            "height_mm": z_mm,
        },
        "image": image,
        "tags": TAGS_DELTA,
        "sources": [URL_RD4, HUB_ARM],
        "categories": ["Delta-Robot", "Industrial-Robot"],
        "uses": USES_PICK,
        "industries": INDUSTRIES,
        "movement_types": MOV_STATIONARY,
        "extra_notes": (
            "Typed specs from TFD-RD4 model column on OEM high-speed pick & place "
            "Delta packaging-line page. Hero is an official TFD-RD4 line gallery "
            "photo (OEM does not publish exclusive per-SKU studio heroes)."
        ),
    }


PRODUCTS: dict[int, dict[str, Any]] = {
    2503: _rd4(
        name="TFD-RD4-600A",
        model="TFD-RD4-600A",
        payload_kg=2,
        reach_mm=600,
        weight_kg=35,
        rep=0.1,
        z_mm=150,
        cycles=120,
        image=IMG_RD4_600,
    ),
    1972: _rd4(
        name="TFD-RD4-800A",
        model="TFD-RD4-800A",
        payload_kg=2.5,
        reach_mm=800,
        weight_kg=81,
        rep=0.1,
        z_mm=200,
        cycles=200,
        image=IMG_RD4_800,
    ),
    2504: _rd4(
        name="TFD-RD4-1200A",
        model="TFD-RD4-1200A",
        payload_kg=3,
        reach_mm=1200,
        weight_kg=82,
        rep=0.1,
        z_mm=230,
        cycles=200,
        image=IMG_RD4_1200,
    ),
    1973: _rd4(
        name="TFD-RD4-1600A",
        model="TFD-RD4-1600A",
        payload_kg=4.5,
        reach_mm=1600,
        weight_kg=83,
        rep=0.15,
        z_mm=250,
        cycles=160,
        image=IMG_RD4_1600,
    ),
    1975: {
        "name": "TFD-RP4-2200-30",
        "model_name": "TFD-RP4-2200-30",
        "variant_code": "TFD-RP4-2200-30",
        "variant_label": "30 kg",
        "url": URL_RP4,
        "family_key": f"{COMPANY_SLUG}:tfd-rp4-2200",
        "family_name": "TFD-RP4-2200",
        "family_url": URL_RP4,
        "product_url_scope": "family",
        "description": (
            "TFD-RP4-2200-30 is Tefude's 4-axis industrial palletizing robot with "
            "a 2200 mm working radius and 30 kg payload for carton, bag, and case "
            "stacking in factories and warehouses."
        ),
        "features": (
            "30 kg max payload; R2200 mm working radius; 1800–2200 mm pick/place "
            "height; ±0.1 mm XYZ repeatability; 6–10 cycles/min; 160 kg machine "
            "mass; floor mounting; IP54; AC380 / 4.5 kW; vacuum or clamp grippers."
        ),
        "purpose": (
            "Carton and case palletizing\n"
            "Bag and beverage end-of-line stacking\n"
            "Warehouse pallet building"
        ),
        "typed": {
            "payload_kg": 30,
            "reach_mm": 2200,
            "weight_kg": 160,
            "repeatability_mm": 0.1,
            "dof": 4,
        },
        "image": IMG_RP4_30,
        "tags": TAGS_PALLET,
        "sources": [URL_RP4, HUB_ARM],
        "categories": ["Industrial-Robot"],
        "uses": USES_PALLET,
        "industries": INDUSTRIES,
        "movement_types": MOV_STATIONARY,
        "extra_notes": (
            "Specs from TFD-RP4-2200-30 column on OEM 4-axis industrial "
            "palletizing robot page. Hero is TEFUDE-branded factory photo."
        ),
    },
    1974: {
        "name": "TFD-RP4-2200-50",
        "model_name": "TFD-RP4-2200-50",
        "variant_code": "TFD-RP4-2200-50",
        "variant_label": "50 kg",
        "url": URL_RP4,
        "family_key": f"{COMPANY_SLUG}:tfd-rp4-2200",
        "family_name": "TFD-RP4-2200",
        "family_url": URL_RP4,
        "product_url_scope": "family",
        "description": (
            "TFD-RP4-2200-50 is the 50 kg-payload variant of Tefude's TFD-RP4-2200 "
            "4-axis palletizing robot with a 2200 mm working radius for heavier "
            "cartons, bags, and cases."
        ),
        "features": (
            "50 kg max payload; R2200 mm working radius; 1800–2200 mm pick/place "
            "height; ±0.1 mm XYZ repeatability; 6–15 cycles/min; 175 kg machine "
            "mass; floor mounting; IP54; AC380 / 8.7 kW; carbon-fiber arm options."
        ),
        "purpose": (
            "Heavy carton and bag palletizing\n"
            "End-of-line case stacking\n"
            "Logistics pallet building"
        ),
        "typed": {
            "payload_kg": 50,
            "reach_mm": 2200,
            "weight_kg": 175,
            "repeatability_mm": 0.1,
            "dof": 4,
        },
        "image": IMG_RP4_50,
        "tags": TAGS_PALLET,
        "sources": [URL_RP4, HUB_ARM],
        "categories": ["Industrial-Robot"],
        "uses": USES_PALLET,
        "industries": INDUSTRIES,
        "movement_types": MOV_STATIONARY,
        "extra_notes": (
            "Specs from TFD-RP4-2200-50 column. Hero is a distinct TEFUDE-branded "
            "factory photo from the same RP4 gallery (avoided TOPSTAR-marked "
            "marketing stills on the intelligent palletizer page)."
        ),
    },
    1978: {
        "name": "4-Axis Industrial Joint Parallel Robot",
        "model_name": "Joint Parallel 4-Axis",
        "variant_code": "joint-parallel-4axis",
        "variant_label": "4-Axis",
        "url": URL_JOINT,
        "family_key": f"{COMPANY_SLUG}:joint-parallel",
        "family_name": "Joint Parallel",
        "family_url": URL_JOINT,
        "product_url_scope": "exact_variant",
        "description": (
            "Tefude's 4-axis industrial joint parallel robot is a hybrid "
            "high-speed pick-and-place arm for industrial automation cells, "
            "offered as a TEFUDE-branded packaging/handling robot."
        ),
        "features": (
            "4-axis hybrid joint-parallel kinematics; TEFUDE-branded pedestal "
            "arm with customizable end effectors; marketed for high-speed "
            "industrial automation and packaging handling."
        ),
        "purpose": (
            "Pick-and-place handling\n"
            "Packaging line automation"
        ),
        "typed": {"dof": 4},
        "image": IMG_JOINT,
        "tags": TAGS_JOINT,
        "sources": [URL_JOINT, HUB_ARM],
        "categories": ["Industrial-Robot"],
        "uses": USES_PICK,
        "industries": INDUSTRIES,
        "movement_types": MOV_STATIONARY,
        "extra_notes": (
            "OEM joint-parallel PDP lacks a citeable typed payload/reach table "
            "in this pass; dof=4 from product naming. Payload/reach left blank."
        ),
    },
}

REJECTS: dict[int, str] = {
    1970: (
        "seo_category_shell: 'Parallel & Serial Packing Robots' is a category/"
        "solution title, not a citeable SKU; keep TFD-RD4 keepers"
    ),
    1971: (
        "solution_cell_shell: Fully Automatic Box-packing Robot is a multi-station "
        "packing cell page, not a single robot SKU"
    ),
    1976: (
        "non_robot_packaging_machine: Automated Biscuit Packaging Robot hero depicts "
        "a carton sealer/taper, not a robot arm; packaging-line SEO shell"
    ),
    1977: (
        "seo_duplicate: Parallel Robotic Arm duplicates TFD-RD4 / joint-parallel "
        "keepers; shared banner hero collision"
    ),
}


def resolve_tags(catalog: TagCatalog, names: list[str]) -> list[str]:
    out: list[str] = []
    missing: list[str] = []
    for name in names:
        hit = catalog._by_name.get(name.casefold())
        if not hit:
            missing.append(name)
            continue
        out.append(str(hit["name"]))
    if missing:
        raise RuntimeError("unresolved TagCatalog name(s): " + ", ".join(missing))
    return out


def build_tag_map(client: ResearchApiClient) -> dict[int, list[str]]:
    catalog = TagCatalog.load(client=client)
    return {rid: resolve_tags(catalog, data["tags"]) for rid, data in PRODUCTS.items()}


def payload(rid: int, tag_map: dict[int, list[str]]) -> dict[str, Any]:
    data = PRODUCTS[rid]
    notes = (
        f"[AI Research — Tefude curated full enrichment 2026-07-22] "
        f"OEM sources: {', '.join(data['sources'])}."
    )
    if data.get("extra_notes"):
        notes += f" Notes: {data['extra_notes']}"
    body: dict[str, Any] = {
        "name": data["name"],
        "model_name": data["model_name"],
        "variant_code": data["variant_code"],
        "variant_label": data["variant_label"],
        "description": data["description"],
        "features": data["features"],
        "purpose": data["purpose"],
        "url": data["url"],
        "family_key": data["family_key"],
        "family_name": data["family_name"],
        "family_url": data["family_url"],
        "product_url_scope": data["product_url_scope"],
        "availability_status": AVAILABLE,
        "manufacturer_country_ref": CHINA,
        "manufacturer_countries": [CHINA],
        "uses": data["uses"],
        "industries": data["industries"],
        "movement_types": data["movement_types"],
        "tags": tag_map[rid],
        "information_source_urls": data["sources"],
        "notes": notes,
        "status": "pending_review",
        "categories": data["categories"],
        "image": data["image"],
        "images": [data["image"]],
        "s3_image": None,
    }
    body.update(data.get("typed") or {})
    return body


def scalar_payload(rid: int, tag_map: dict[int, list[str]]) -> dict[str, Any]:
    body = payload(rid, tag_map)
    for key in ("image", "images", "s3_image"):
        body.pop(key, None)
    return body


def _admin_base() -> str:
    return os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/").replace(
        "/api/v1", ""
    )


def _internal_headers() -> dict[str, str]:
    secret = os.environ.get("INTERNAL_API_SECRET", "").strip()
    if not secret:
        raise RuntimeError("INTERNAL_API_SECRET missing")
    return {"X-Internal-Secret": secret}


def preflight_images() -> dict[str, Any]:
    hashes: dict[str, int] = {}
    rows = []
    for rid, data in PRODUCTS.items():
        resp = requests.get(data["image"], headers=HEADERS, timeout=90)
        resp.raise_for_status()
        content = resp.content
        if len(content) < 8_000:
            raise RuntimeError(f"{rid} image too small: {len(content)}")
        magic = content[:4]
        if not (
            content[:3] == b"\xff\xd8\xff"
            or magic == bytes([0x89, 0x50, 0x4E, 0x47])
            or magic == b"RIFF"
        ):
            raise RuntimeError(f"{rid} non-image magic {magic.hex()}")
        digest = hashlib.sha256(content).hexdigest()
        if digest in hashes:
            raise RuntimeError(f"hash collision {rid} vs {hashes[digest]}")
        # Fail closed on known shared banner
        if hashlib.md5(content).hexdigest() == "728e8af02af165f75a8bce8a57a8c889":
            raise RuntimeError(f"{rid} still using shared site banner")
        hashes[digest] = rid
        image = Image.open(io.BytesIO(content))
        rows.append(
            {
                "id": rid,
                "url": data["image"],
                "bytes": len(content),
                "sha256": digest,
                "size": list(image.size),
            }
        )
    return {"heroes": rows, "unique_hashes": len(hashes)}


def patch_company(client: ResearchApiClient) -> dict[str, Any]:
    return client._patch(
        f"companies/{COMPANY_ID}/",
        {"website": COMPANY_WEBSITE, "country_id": CHINA},
    )


def reject_invalid_rows(client: ResearchApiClient) -> list[dict[str, Any]]:
    results = []
    for rid, reason in REJECTS.items():
        client._patch(
            f"robots/robots/{rid}/",
            {
                "status": "rejected",
                "rejection_reason": reason[:500],
                "notes": f"[CURATED FULL 2026-07-22] {reason}",
            },
        )
        results.append({"id": rid, "rejection_reason": reason})
    return results


def replace_media(client: ResearchApiClient, rid: int, tag_map: dict[int, list[str]]) -> dict[str, Any]:
    row = payload(rid, tag_map)
    row.update(
        {
            "id": rid,
            "company_slug": COMPANY_SLUG,
            "company_name": COMPANY_NAME,
            "manufacturer_country_code": "CN",
            "manufacturer_country_codes": "CN",
        }
    )
    return client.bulk_import_robots(
        [row],
        update_existing=True,
        patch_existing=True,
        status="pending_review",
        skip_company_update=True,
        replace_media=True,
    )


def copy_media(rid: int) -> dict[str, Any]:
    response = requests.post(
        f"{_admin_base()}/admin/robots/robot/content-queue/api/robot/"
        f"{rid}/copy-media/?force=1",
        headers=_internal_headers(),
        timeout=240,
    )
    response.raise_for_status()
    return response.json()


def verify(client: ResearchApiClient) -> dict[str, Any]:
    hashes: dict[str, int] = {}
    media = []
    issues = []
    robots = {int(r["id"]): r for r in client.list_robots_for_company(COMPANY_ID)}
    for rid, data in PRODUCTS.items():
        robot = client._get(f"robots/robots/{rid}/")
        if robot.get("status") != "pending_review":
            issues.append(f"{rid} status={robot.get('status')}")
        if robot.get("family_key") != data["family_key"]:
            issues.append(f"{rid} family_key mismatch")
        if not (robot.get("tags") or []):
            issues.append(f"{rid} missing tags")
        for key, expected in (data.get("typed") or {}).items():
            if not isinstance(expected, (int, float)):
                continue
            actual = robot.get(key)
            if actual is None:
                issues.append(f"{rid} missing typed {key}")
            elif abs(float(actual) - float(expected)) > 0.051:
                issues.append(f"{rid} typed {key}={actual} != {expected}")
        url = str(robot.get("s3_image") or robot.get("image") or "")
        if "cdn.robotaigeek.com" not in url:
            issues.append(f"{rid} missing owned CDN: {url}")
            continue
        resp = requests.get(url, headers=HEADERS, timeout=90)
        if resp.status_code != 200 or len(resp.content) < 8_000:
            issues.append(f"{rid} CDN bad {resp.status_code} {len(resp.content)}b")
            continue
        digest = hashlib.sha256(resp.content).hexdigest()
        if digest in hashes:
            issues.append(f"{rid} CDN hash collides with {hashes[digest]}")
        hashes[digest] = rid
        if hashlib.md5(resp.content).hexdigest() == "728e8af02af165f75a8bce8a57a8c889":
            issues.append(f"{rid} CDN still shared banner")
        image = Image.open(io.BytesIO(resp.content))
        media.append(
            {
                "id": rid,
                "name": robot.get("name"),
                "cdn": url,
                "bytes": len(resp.content),
                "size": list(image.size),
                "sha256": digest,
            }
        )
    for rid in REJECTS:
        robot = robots.get(rid)
        if robot and robot.get("status") != "rejected":
            issues.append(f"reject {rid} still {robot.get('status')}")
    return {
        "ok": not issues,
        "issues": issues,
        "media": media,
        "unique_hashes": len(hashes),
        "pending_keepers": len(PRODUCTS),
        "rejects": len(REJECTS),
    }


def approve_allowlist() -> list[int]:
    return sorted(PRODUCTS)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--local", action="store_true")
    args = parser.parse_args()

    client = ResearchApiClient()
    live = {
        int(r["id"]): r
        for r in client.list_robots_for_company(COMPANY_ID)
        if r.get("status") == "pending_review"
    }
    expected = set(PRODUCTS) | set(REJECTS)
    if set(live) != expected:
        raise RuntimeError(
            f"pending set drift missing={sorted(expected - set(live))} "
            f"unexpected={sorted(set(live) - expected)}"
        )

    tag_map = build_tag_map(client)
    preflight = preflight_images()
    report: dict[str, Any] = {
        "company_id": COMPANY_ID,
        "mode": "apply" if args.apply else "dry-run",
        "company_website": COMPANY_WEBSITE,
        "preflight": preflight,
        "keepers": sorted(PRODUCTS),
        "rejects": REJECTS,
        "approve_allowlist": approve_allowlist(),
        "sample_payload": scalar_payload(next(iter(PRODUCTS)), tag_map),
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    if not args.apply:
        REPORT.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0

    print("patching company...", flush=True)
    company = patch_company(client)
    import_results: dict[int, Any] = {}
    copy_results: dict[int, Any] = {}
    for rid in sorted(PRODUCTS):
        print(f"import {rid} {PRODUCTS[rid]['name']}...", flush=True)
        import_results[rid] = replace_media(client, rid, tag_map)
        if import_results[rid].get("error_count"):
            raise RuntimeError(f"import failed {rid}: {import_results[rid]}")
        client._patch(f"robots/robots/{rid}/", scalar_payload(rid, tag_map))
        print(f"copy-media {rid}...", flush=True)
        copy_results[rid] = copy_media(rid)
    print("rejecting shells...", flush=True)
    rejects = reject_invalid_rows(client)
    print("verifying...", flush=True)
    verified = verify(client)
    report.update(
        {
            "applied": True,
            "company_result": company,
            "import_results": import_results,
            "copy_media": copy_results,
            "rejects_applied": rejects,
            "verified": verified,
            "rd4_hero_note": (
                "RD4 keepers still need robot-dominant crops: "
                "python -u fix_tefude_1404_rd4_heroes.py --apply"
            ),
        }
    )
    REPORT.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    if not verified["ok"]:
        raise SystemExit(f"verify failed: {verified['issues']}")
    print(
        f"apply OK: {len(PRODUCTS)} keepers / {len(REJECTS)} rejects / "
        f"CDN {verified['unique_hashes']}/{len(PRODUCTS)} distinct",
        flush=True,
    )
    print(
        "NOTE: run fix_tefude_1404_rd4_heroes.py --apply to replace RD4 "
        "DETAIL DISPLAY / packing composites with robot-dominant crops.",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
