"""Clean CTRL Robotics (782) ownership and curate its Box offering."""

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

load_research_env()

COMPANY_ID = 782
ROBOT_ID = 5086
REPORT = _HERE / "staging" / "reports" / "ctrl-782-ownership-cleanup.json"
MEDIA_DIR = _HERE / "staging" / "ctrl_782_media"
BOX_URL = "https://ctrlrobotics.com/project/box/"
BOX_IMAGE = (
    "https://ctrlrobotics.com/wp-content/uploads/2024/06/"
    "Artboard-5-copy-1.jpg"
)
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
    )
}

PRODUCTS: dict[int, dict[str, Any]] = {
    5086: {
        "name": "Box",
        "model_name": "Box",
        "family_key": "ctrl:box",
        "description": (
            "Box is CTRL Robotics' branded secure in-building delivery solution "
            "for hospitals, hotels, and large workplaces. It uses four enclosed "
            "compartments and CTRL's smart-building integration to travel through "
            "automatic doors and elevators."
        ),
        "features": (
            "Official CTRL specifications: four secure compartments; 140 L total "
            "delivery volume; 40 kg carrying capacity; 1 m/s travel speed; "
            "1.5-hour charging; 6–8 hours operating time. CTRL markets Box for "
            "hospital medicine delivery, hotel room service, and accountable "
            "high-value item transport through integrated doors and elevators."
        ),
        "purpose": (
            "Secure medicine and supply delivery\n"
            "Hotel room service\n"
            "Inter-floor workplace item transport"
        ),
        "typed": {
            "payload_kg": 40,
            "speed": 3.6,
            "charging_time": "1.5 hours",
            "charging_time_minutes": 90,
            "runtime": "6–8 hours",
        },
        "notes": (
            "[AI Research — CTRL ownership cleanup 2026-07-21] "
            "Current CTRL-branded Box offering retained under CTRL. CTRL is an "
            "integrator/branded-solution provider; underlying hardware OEM and "
            "exact OEM SKU remain undisclosed, so no external manufacturer is "
            "asserted. Dead searches: physical dimensions, robot mass, battery "
            "capacity, release year, public price, and exact conventional video. "
            "The official Vectary embed is a 3D model, not a video."
        ),
    }
}

REPARENT = {
    5085: ("Pudu Robotics", 148),
    5083: ("REEMAN", 1421),
    5082: ("REEMAN", 1421),
}

REPARENT_DATA: dict[int, dict[str, Any]] = {
    5085: {
        "name": "PuduBot",
        "model_name": "PuduBot",
        "variant_code": "PuduBot",
        "url": "https://www.pudurobotics.com/en/products/pudubot",
        "family_key": "pudu:pudubot",
        "family_name": "PuduBot",
        "family_url": "https://www.pudurobotics.com/en/products/pudubot",
        "product_url_scope": "exact_variant",
        "manufacturer_country_ref": 3,
        "manufacturer_countries": [3],
        "payload_kg": 30,
        "speed": 4.32,
        "length_mm": 516,
        "width_mm": 500,
        "height_mm": 1288,
        "notes": (
            "[AI Research — ownership correction 2026-07-21] CTRL's AX Delivery "
            "specifications and imagery identify the original PuduBot, not a CTRL "
            "hardware model and not PuduBot 2. Reparented to Pudu Robotics for its "
            "catalog curation pass."
        ),
        "status": "pending_review",
    },
    5083: {
        "name": "Hot Wheels Robot Chassis (WBOT11B)",
        "model_name": "WBOT11B",
        "variant_code": "WBOT11B",
        "url": (
            "https://www.reemanrobot.com/robot-chassis/circular-robot-chassis/"
            "automatic-circular-robot-chassis.html"
        ),
        "family_key": "reeman:wbot11b",
        "family_name": "Hot Wheels Robot Chassis",
        "family_url": (
            "https://www.reemanrobot.com/robot-chassis/circular-robot-chassis/"
            "automatic-circular-robot-chassis.html"
        ),
        "product_url_scope": "exact_variant",
        "manufacturer_country_ref": 3,
        "manufacturer_countries": [3],
        "payload_kg": 60,
        "weight_kg": 28,
        "weight": "28 kg",
        "speed": 2.88,
        "length_mm": 450,
        "width_mm": 450,
        "height_mm": 317,
        "notes": (
            "[AI Research — ownership correction 2026-07-21] Exact REEMAN "
            "WBOT11B circular open-SDK chassis; reparented from CTRL integrator "
            "company to OEM REEMAN."
        ),
        "status": "pending_review",
    },
    5082: {
        "name": "Moon Knight Robot Chassis (FBOT13B)",
        "model_name": "FBOT13B",
        "variant_code": "FBOT13B",
        "url": (
            "https://www.reemanrobot.com/robot-chassis/square-robot-chassis/"
            "open-sdk-square-robot-chassis.html"
        ),
        "family_key": "reeman:fbot13b",
        "family_name": "Moon Knight Robot Chassis",
        "family_url": (
            "https://www.reemanrobot.com/robot-chassis/square-robot-chassis/"
            "open-sdk-square-robot-chassis.html"
        ),
        "product_url_scope": "exact_variant",
        "manufacturer_country_ref": 3,
        "manufacturer_countries": [3],
        "payload_kg": 60,
        "weight_kg": 34,
        "weight": "34 kg",
        "speed": 3.6,
        "length_mm": 500,
        "width_mm": 500,
        "height_mm": 310,
        "notes": (
            "[AI Research — ownership correction 2026-07-21] Exact REEMAN "
            "FBOT13B square open-SDK chassis; reparented from CTRL integrator "
            "company to OEM REEMAN."
        ),
        "status": "pending_review",
    },
}

REJECTS: dict[int, str] = {
    5087: (
        "unverifiable_product: Kiki URL is dead and no current/historical CTRL "
        "catalog, OEM identity, image, specifications, or source evidence exists"
    ),
    5084: (
        "duplicate: REEMAN R1D1; keep OEM queue record 4656 using the exact same PDP"
    ),
    5081: (
        "duplicate_misattributed: original Pudu KettyBot; keep Pudu record 234 "
        "(KettyBot Pro 3202 is distinct)"
    ),
    5080: (
        "duplicate_misattributed: original Pudu BellaBot; consolidate under Pudu "
        "company during its catalog pass"
    ),
    2815: (
        "duplicate_misattributed: OrionStar LuckiBot; keep OEM queue record 297"
    ),
}


def upscale_box_hero(body: bytes, target_long_side: int = 1_200) -> bytes:
    source = Image.open(io.BytesIO(body)).convert("RGB")
    scale = target_long_side / max(source.size)
    if scale > 1:
        source = source.resize(
            (round(source.width * scale), round(source.height * scale)),
            Image.Resampling.LANCZOS,
        )
    output = io.BytesIO()
    source.save(output, format="JPEG", quality=92, optimize=True)
    return output.getvalue()


def box_payload(media_url: str) -> dict[str, Any]:
    data = PRODUCTS[ROBOT_ID]
    body: dict[str, Any] = {
        "name": data["name"],
        "model_name": data["model_name"],
        "variant_code": "Box",
        "description": data["description"],
        "features": data["features"],
        "purpose": data["purpose"],
        "url": BOX_URL,
        "family_key": data["family_key"],
        "family_name": "Box",
        "family_url": BOX_URL,
        "product_url_scope": "exact_variant",
        "availability_status": 11,
        "manufacturer_country_ref": 27,
        "manufacturer_countries": [27],
        "uses": [53, 4, 16, 52, 74, 62],
        "industries": [46, 8, 10, 11],
        "movement_types": [4],
        "tags": [
            "AMR",
            "Automation",
            "Delivery",
            "Hospitality",
            "Hotel",
            "Indoor Delivery",
            "Logistics",
            "Service Robot",
        ],
        "information_source_urls": [BOX_URL],
        "image": media_url,
        "images": [media_url],
        "s3_image": None,
        "notes": data["notes"],
        "status": "pending_review",
    }
    body.update(data["typed"])
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


def upload_box_hero(client: ResearchApiClient) -> tuple[str, dict[str, Any]]:
    response = requests.get(BOX_IMAGE, headers=HEADERS, timeout=90)
    response.raise_for_status()
    hero = upscale_box_hero(response.content)
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    path = MEDIA_DIR / "ctrl-box-official-1200.jpg"
    path.write_bytes(hero)
    headers = {
        key: value
        for key, value in client._session.headers.items()
        if key.lower() != "content-type"
    }
    with path.open("rb") as handle:
        uploaded = requests.post(
            client._url(f"robots/robots/{ROBOT_ID}/images/"),
            headers=headers,
            files={"images": (path.name, handle, "image/jpeg")},
            data={
                "title": "CTRL Box",
                "description": "Exact current official CTRL Box product image.",
            },
            timeout=120,
        )
    uploaded.raise_for_status()
    result = uploaded.json()
    photos = result.get("photos") or [result.get("photo") or {}]
    url = str((photos[0] or {}).get("url") or "")
    if not url:
        raise RuntimeError("Box upload returned no URL")
    image = Image.open(io.BytesIO(hero))
    return url, {
        "source_url": BOX_IMAGE,
        "source_size": list(Image.open(io.BytesIO(response.content)).size),
        "hero_size": list(image.size),
        "hero_sha256": hashlib.sha256(hero).hexdigest(),
    }


def ensure_box_hero(client: ResearchApiClient) -> tuple[str, dict[str, Any]]:
    detail = client._get(f"robots/robots/{ROBOT_ID}/")
    current_url = str(detail.get("s3_image") or detail.get("image") or "")
    if current_url and "cdn.robotaigeek.com/" in current_url:
        response = requests.get(current_url, headers=HEADERS, timeout=90)
        if response.ok:
            image = Image.open(io.BytesIO(response.content))
            if image.width >= 1_000 and image.height >= 700:
                return current_url, {
                    "reused": True,
                    "hero_size": list(image.size),
                    "hero_sha256": hashlib.sha256(response.content).hexdigest(),
                }
    return upload_box_hero(client)


def copy_media() -> dict[str, Any]:
    response = requests.post(
        f"{_admin_base()}/admin/robots/robot/content-queue/api/robot/"
        f"{ROBOT_ID}/copy-media/?force=1",
        headers=_internal_headers(),
        timeout=240,
    )
    response.raise_for_status()
    return response.json()


def reparent_rows(client: ResearchApiClient) -> list[dict[str, Any]]:
    results = []
    for rid, (company_name, company_id) in REPARENT.items():
        body = {
            "company": company_name,
            "company_owner_ids": [company_id],
            **REPARENT_DATA[rid],
        }
        client._patch(f"robots/robots/{rid}/", body)
        detail = client._get(f"robots/robots/{rid}/")
        actual_id = int((detail.get("company_ref") or {}).get("id") or 0)
        owner_ids = {
            int(owner["id"]) for owner in detail.get("company_owners") or []
        }
        if actual_id != company_id or owner_ids != {company_id}:
            raise RuntimeError(
                f"reparent failed for {rid}: primary={actual_id}, owners={owner_ids}"
            )
        results.append({"id": rid, "company_id": actual_id})
    return results


def reject_invalid_rows(client: ResearchApiClient) -> list[dict[str, Any]]:
    results = []
    for rid, reason in REJECTS.items():
        client._patch(
            f"robots/robots/{rid}/",
            {
                "status": "rejected",
                "rejection_reason": reason,
                "notes": f"[CURATED OWNERSHIP 2026-07-21] {reason}",
            },
        )
        results.append({"id": rid, "reason": reason})
    return results


def verify(client: ResearchApiClient) -> dict[str, Any]:
    ctrl_rows = client.list_robots_for_company(COMPANY_ID)
    pending = [row for row in ctrl_rows if row.get("status") == "pending_review"]
    if [int(row["id"]) for row in pending] != [ROBOT_ID]:
        raise RuntimeError(
            f"CTRL pending set mismatch: {[row['id'] for row in pending]}"
        )
    for rid, (_, company_id) in REPARENT.items():
        detail = client._get(f"robots/robots/{rid}/")
        actual_id = int((detail.get("company_ref") or {}).get("id") or 0)
        owner_ids = {
            int(owner["id"]) for owner in detail.get("company_owners") or []
        }
        if (
            actual_id != company_id
            or owner_ids != {company_id}
            or detail.get("status") != "pending_review"
        ):
            raise RuntimeError(
                f"ownership invariant failed for {rid}: "
                f"{actual_id}/{owner_ids}/{detail.get('status')}"
            )
    box = client._get(f"robots/robots/{ROBOT_ID}/")
    media_url = str(box.get("s3_image") or box.get("image") or "")
    response = requests.get(media_url, headers=HEADERS, timeout=90)
    response.raise_for_status()
    image = Image.open(io.BytesIO(response.content))
    if image.width < 1_000 or image.height < 700:
        raise RuntimeError(f"Box CDN hero undersized: {image.size}")
    return {
        "ctrl_pending_ids": [ROBOT_ID],
        "reparented_ids": sorted(REPARENT),
        "rejected_ids": sorted(REJECTS),
        "box_media": {
            "url": media_url,
            "size": list(image.size),
            "bytes": len(response.content),
            "sha256": hashlib.sha256(response.content).hexdigest(),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean CTRL company ownership")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    client = ResearchApiClient()
    ctrl_rows = client.list_robots_for_company(COMPANY_ID)
    pending_ids = {
        int(row["id"])
        for row in ctrl_rows
        if row.get("status") == "pending_review"
    }
    expected = set(PRODUCTS) | set(REPARENT) | set(REJECTS)
    if not set(PRODUCTS).issubset(pending_ids) or not pending_ids.issubset(expected):
        raise RuntimeError(
            f"live queue drift: missing={sorted(expected-pending_ids)} "
            f"unexpected={sorted(pending_ids-expected)}"
        )

    report: dict[str, Any] = {
        "company_id": COMPANY_ID,
        "mode": "apply" if args.apply else "dry-run",
        "keepers": sorted(PRODUCTS),
        "reparent": REPARENT,
        "rejects": REJECTS,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    if not args.apply:
        REPORT.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0

    media_url, media_report = ensure_box_hero(client)
    client._patch(f"robots/robots/{ROBOT_ID}/", box_payload(media_url))
    copy_result = copy_media()
    reparent_results = reparent_rows(client)
    reject_results = reject_invalid_rows(client)
    verified = verify(client)
    report.update(
        {
            "applied": True,
            "media_source": media_report,
            "copy_media": copy_result,
            "reparent_results": reparent_results,
            "reject_results": reject_results,
            "verified": verified,
        }
    )
    REPORT.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(verified, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
