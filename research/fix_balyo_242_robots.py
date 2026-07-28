"""Curate BALYO company 242 into six canonical current robot records."""

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
from youtube_metadata import enrich_video_list

load_research_env()

COMPANY_ID = 242
COMPANY_SLUG = "balyo"
COMPANY_NAME = "Balyo"
REPORT = _HERE / "staging" / "reports" / "balyo-242-curated-report.json"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
    )
}
AVAILABLE = 11

CATALOG_URL = "https://www.balyo.com/agv-amr"
REACHY_LAUNCH = (
    "https://www.balyo.com/hubfs/Press%20Release/EN/"
    "PR_BALYO_-New-generation-of-robots_ENG_vdef.pdf"
)
LOWY_VIDEO = "https://www.balyo.com/hubfs/Files/Product-Pages/Lowy/Lowy_Intro_30s.mp4"


def cover(filename: str) -> str:
    return (
        "https://www.balyo.com/hs-fs/hubfs/Files/Product-Pages/"
        f"Products-Covers/{filename}?width=1200&height=900&name={filename}"
    )


COMMON_TAGS = [
    "AGV",
    "AMR",
    "Automation",
    "Forklift",
    "Industrial",
    "Intralogistics",
    "Logistics",
    "Material Handling",
    "Warehouse Automation",
]
USES = [74, 62, 32, 54, 78]
INDUSTRIES = [11, 12]

PRODUCTS: dict[int, dict[str, Any]] = {
    2680: {
        "name": "VEENY Turret Truck AGV/AMR",
        "model": "VEENY",
        "url": "https://www.balyo.com/agv-vna/veeny",
        "image": cover("VNA_Cover-photo.jpg"),
        "description": (
            "BALYO VEENY is an autonomous very-narrow-aisle turret truck for "
            "high-bay pallet storage. It operates in aisles from 1.8 m and can "
            "lift up to 1,500 kg to 17.2 m while retaining manual operation."
        ),
        "features": (
            "Official BALYO VEENY specifications: 1,500 kg capacity; maximum "
            "lift/drop height 17,200 mm; aisle width from 1,800 mm; speed up to "
            "2.2 m/s (7.92 km/h); dimensions 2,856 × 1,560 × 2,346 mm. "
            "Three-axis pallet detection and free-space checks, mast-oscillation "
            "compensation, PL-d 360° safety, 64-plane 3D LiDAR, infrastructure-free "
            "SLAM, dual manual/autonomous mode, barcode scanning, and WMS/ERP "
            "integration. Battery options: lead-acid, NMC, or TPPL with wireless, "
            "automatic, or manual charging."
        ),
        "purpose": (
            "Very-narrow-aisle pallet storage and retrieval\n"
            "High-bay warehouse automation\n"
            "Pallet transfer and rack replenishment"
        ),
        "typed": {
            "payload_kg": 1500,
            "speed": 7.92,
            "length_mm": 2856,
            "width_mm": 1560,
            "height_mm": 2346,
        },
        "videos": ["https://www.youtube.com/watch?v=2dm_Q_oCvCg"],
        "dead": "robot mass, runtime, public exact-model PDF, and release year",
    },
    2681: {
        "name": "REACHY Reach Forklift AGV/AMR",
        "model": "REACHY",
        "url": "https://www.balyo.com/agv-reach-trucks/reachy",
        "image": cover("Reachy-Cover-photo.jpg"),
        "description": (
            "BALYO REACHY is an autonomous reach forklift for high-bay pallet "
            "storage. It handles configured loads up to 1,600 kg, reaches 11 m, "
            "and works in aisles from 2.9 m."
        ),
        "features": (
            "Official BALYO REACHY specifications: 1,400–1,600 kg configuration "
            "range (1,600 kg maximum); lift height up to 11,000 mm; aisle width "
            "from 2,900 mm; speed up to 2 m/s (7.2 km/h); closed mast height "
            "2,350–4,950 mm depending on configuration. Supports over 100 pallet "
            "types, three-axis fork correction, 3D free-space checks, PL-D front/"
            "rear safety, anti-push/drag and overhang detection, barcode scanning, "
            "infrastructure-free SLAM, dual mode, and WMS/ERP integration. Battery "
            "options: lead-acid, TPPL, or NMC with automatic docking charge."
        ),
        "purpose": (
            "High-bay pallet storage and retrieval\n"
            "Autonomous reach-forklift operations\n"
            "Warehouse rack replenishment"
        ),
        "typed": {"payload_kg": 1600, "speed": 7.2, "release_year": 2020},
        "videos": ["https://www.youtube.com/watch?v=swXkiIincqs"],
        "sources": [REACHY_LAUNCH],
        "dead": "overall dimensions, robot mass, runtime, and direct current datasheet",
    },
    2682: {
        "name": "LOWY CB Counter Balanced Stacker AGV/AMR",
        "model": "LOWY CB",
        "url": "https://www.balyo.com/agv-counterbalanced-stackers/lowy-cb",
        "image": cover("Lowy-CB_Cover-photo.jpg"),
        "description": (
            "BALYO LOWY CB is an autonomous counterbalanced stacker for open and "
            "closed pallets. It handles configurations up to 1,600 kg and lifts "
            "to 4 m in warehouse and manufacturing workflows."
        ),
        "features": (
            "Official BALYO LOWY CB specifications: 1,200 kg and 1,600 kg "
            "configurations; 1,600 kg maximum; lift height up to 4,000 mm; aisle "
            "width from 3,400 mm; speed up to 2 m/s (7.2 km/h); dimensions "
            "3,247 × 890 × 2,097 mm. Standard counterbalanced forks handle open "
            "and closed pallets. Includes 3D pallet detection, PL-D 360° safety, "
            "optional mobile-detector laser/3D camera, 64-plane LiDAR, "
            "infrastructure-free SLAM, and dual mode. Battery options: lead-acid, "
            "TPPL, or NMC with automatic docking."
        ),
        "purpose": (
            "Open- and closed-pallet transport\n"
            "Counterbalanced pallet stacking\n"
            "Machine and conveyor interface automation"
        ),
        "typed": {
            "payload_kg": 1600,
            "speed": 7.2,
            "length_mm": 3247,
            "width_mm": 890,
            "height_mm": 2097,
        },
        "videos": [
            {
                "url": LOWY_VIDEO,
                "title": "BALYO LOWY family demonstration",
                "description": (
                    "Official BALYO LOWY-family overview; no exact LOWY CB "
                    "public video was found."
                ),
            }
        ],
        "dead": "robot mass, runtime, release year, exact-model video, and public PDF",
    },
    2683: {
        "name": "LOWY Stacker AGV/AMR",
        "model": "LOWY",
        "url": "https://www.balyo.com/agv-stackers/lowy",
        "image": cover("Lowy_Cover-photo.jpg"),
        "description": (
            "BALYO LOWY is an autonomous stacker for horizontal pallet movement "
            "and low-to-middle lift workflows in warehouses and manufacturing."
        ),
        "features": (
            "Current BALYO PDP specifications: lift to 2,930 mm; speed up to "
            "2 m/s (7.2 km/h); dimensions 2,350 × 811 × 2,327 mm. The current PDP "
            "states 1,600 kg capacity and aisle width from 2.9 m, while BALYO's "
            "current catalog still states 1,200 kg and 2.7 m; these conflicting "
            "values are retained as source notes rather than typed fields. Includes "
            "3D pallet detection, PL-D sensors, 64-plane 3D LiDAR, infrastructure-"
            "free SLAM, dual mode, and machine/door/conveyor integration. Battery "
            "options: lead-acid, NMC, or TPPL; automatic or wireless charging."
        ),
        "purpose": (
            "Horizontal pallet movement\n"
            "Low- and middle-lift stacking\n"
            "Conveyor and machine interface transport"
        ),
        "typed": {
            "speed": 7.2,
            "length_mm": 2350,
            "width_mm": 811,
            "height_mm": 2327,
        },
        "videos": [
            {
                "url": LOWY_VIDEO,
                "title": "BALYO LOWY product demonstration",
                "description": "Official exact-model LOWY introduction hosted by BALYO.",
            }
        ],
        "dead": "robot mass, runtime, release year, and current public PDF",
    },
    2684: {
        "name": "LOWY HD Heavy Duty Stacker AGV/AMR",
        "model": "LOWY HD",
        "url": "https://www.balyo.com/agv-stackers/lowy-hd",
        "image": cover("Lowy-HD_Cover-photo.jpg"),
        "description": (
            "BALYO LOWY HD is a heavy-duty autonomous stacker for open-pallet "
            "transport and machinery, conveyor, staging, and inbound-lane workflows."
        ),
        "features": (
            "Official BALYO LOWY HD specifications: 1,600 kg capacity; lift height "
            "up to 3,000 mm; aisle width from 2,950 mm; speed up to 2 m/s "
            "(7.2 km/h); dimensions 2,137 × 800 × 2,337 mm. Includes 3D pallet "
            "detection, PL-d and side safety lasers, 64-plane 3D LiDAR, "
            "infrastructure-free SLAM, dual mode, and machinery/conveyor "
            "integration. Battery options: lead-acid or LTO."
        ),
        "purpose": (
            "Heavy-duty open-pallet transport\n"
            "Pallet stacking to 3 m\n"
            "Machine, conveyor, and inbound-lane automation"
        ),
        "typed": {
            "payload_kg": 1600,
            "speed": 7.2,
            "length_mm": 2137,
            "width_mm": 800,
            "height_mm": 2337,
        },
        "videos": [
            {
                "url": LOWY_VIDEO,
                "title": "BALYO LOWY family demonstration",
                "description": (
                    "Official BALYO LOWY-family overview; no exact LOWY HD "
                    "public video was found."
                ),
            }
        ],
        "dead": "robot mass, runtime, release year, exact-model video, and public PDF",
    },
    2685: {
        "name": "TUGGY Tugger truck AGV/AMR",
        "model": "TUGGY",
        "url": "https://www.balyo.com/agv-tuggers/tuggy",
        "image": cover("Tuggy_Cover-photo.jpg"),
        "description": (
            "BALYO TUGGY is an autonomous industrial tugger for milk runs, "
            "just-in-time line supply, station transfers, and inter-building "
            "material movement, with up to 7,000 kg pulling capacity."
        ),
        "features": (
            "Official BALYO TUGGY specifications: 7,000 kg pulling capacity "
            "(not carried payload); speed up to 2 m/s (7.2 km/h); dimensions "
            "1,706 × 709 × 2,351 mm. Automatic hitch/unhitch, smart trailer "
            "interface, PL-d safety sensors, 3D curtain LiDAR, infrastructure-free "
            "SLAM, configurable full/semi-autonomy, and door/automation interfaces. "
            "Battery options: lead-acid, Li-ion, or TPPL; automatic or manual "
            "charging."
        ),
        "purpose": (
            "Industrial milk runs\n"
            "Just-in-time and just-in-sequence line supply\n"
            "Cart and trailer towing between stations"
        ),
        "typed": {
            "speed": 7.2,
            "length_mm": 1706,
            "width_mm": 709,
            "height_mm": 2351,
        },
        "videos": ["https://www.youtube.com/watch?v=8zl3C5NRKfQ"],
        "dead": "robot mass, runtime, lift height, release year, exact-model video, and public PDF",
    },
}

REJECTS = {
    4129: 2680,
    3850: 2681,
    4130: 2681,
    4131: 2682,
    3849: 2683,
    4132: 2683,
    4133: 2684,
    3851: 2685,
    4134: 2685,
}
STALE_PHOTOS = {12277: 2684, 12278: 2684, 12280: 2685}


def payload(rid: int, image_url: str | None = None) -> dict[str, Any]:
    data = PRODUCTS[rid]
    sources = [data["url"], CATALOG_URL, *(data.get("sources") or [])]
    body: dict[str, Any] = {
        "name": data["name"],
        "model_name": data["model"],
        "variant_code": data["model"].replace(" ", "-"),
        "description": data["description"],
        "features": data["features"],
        "purpose": data["purpose"],
        "url": data["url"],
        "family_key": f"balyo:{data['model'].lower().replace(' ', '-')}",
        "family_name": data["model"],
        "family_url": data["url"],
        "product_url_scope": "exact_variant",
        "availability_status": AVAILABLE,
        "uses": USES,
        "industries": INDUSTRIES,
        "tags": COMMON_TAGS,
        "information_source_urls": sources,
        "image": image_url or data["image"],
        "images": [image_url or data["image"]],
        "s3_image": None,
        "notes": (
            "[AI Research — BALYO curated catalog pass 2026-07-21] "
            f"Exact PDP and current catalog verified. Dead searches: {data['dead']}. "
            "Typed values use only exact-model current OEM claims; configuration "
            "ranges and conflicting values remain in sourced Features."
        ),
        "status": "pending_review",
    }
    body.update(data["typed"])
    return body


def scalar_payload(rid: int) -> dict[str, Any]:
    """Fields patched after bulk media replacement."""
    body = payload(rid)
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


def copy_media(rid: int) -> dict[str, Any]:
    response = requests.post(
        f"{_admin_base()}/admin/robots/robot/content-queue/api/robot/"
        f"{rid}/copy-media/?force=1",
        headers=_internal_headers(),
        timeout=240,
    )
    response.raise_for_status()
    return response.json()


def replace_media_and_videos(
    client: ResearchApiClient, rid: int
) -> dict[str, Any]:
    data = PRODUCTS[rid]
    row = payload(rid)
    row.update({
        "id": rid,
        "company_slug": COMPANY_SLUG,
        "company_name": COMPANY_NAME,
        "video_urls": enrich_video_list(data["videos"]),
    })
    return client.bulk_import_robots(
        [row],
        update_existing=True,
        patch_existing=True,
        status="pending_review",
        skip_company_update=True,
        replace_media=True,
        replace_videos=True,
    )


def desired_video_urls(rid: int) -> set[str]:
    return {
        str(item.get("url") if isinstance(item, dict) else item)
        for item in PRODUCTS[rid]["videos"]
    }


def prune_stale_videos(client: ResearchApiClient) -> list[dict[str, Any]]:
    results = []
    headers = _internal_headers()
    for rid in PRODUCTS:
        keep = desired_video_urls(rid)
        detail = client._get(f"robots/robots/{rid}/")
        for video in detail.get("videos") or []:
            if video.get("url") in keep:
                continue
            response = requests.post(
                f"{_admin_base()}/admin/robots/robot/content-queue/api/robot/"
                f"{rid}/videos/",
                headers=headers,
                json={"action": "delete", "video_id": video["id"]},
                timeout=60,
            )
            if not response.ok:
                raise RuntimeError(
                    f"stale video delete failed {rid}/{video['id']}: "
                    f"{response.status_code} {response.text[:200]}"
                )
            results.append({"robot_id": rid, "video_id": video["id"]})
    return results


def reject_duplicates(client: ResearchApiClient) -> list[dict[str, Any]]:
    results = []
    for duplicate_id, keeper_id in REJECTS.items():
        reason = (
            f"duplicate: exact BALYO model duplicate; keep canonical enriched "
            f"record {keeper_id}"
        )
        client._patch(
            f"robots/robots/{duplicate_id}/",
            {
                "status": "rejected",
                "rejection_reason": reason,
                "notes": f"[CURATED FULL 2026-07-21] {reason}",
            },
        )
        results.append({"id": duplicate_id, "keeper_id": keeper_id})
    return results


def verify_company(client: ResearchApiClient) -> dict[str, Any]:
    rows = client.list_robots_for_company(COMPANY_ID)
    pending = [row for row in rows if row.get("status") == "pending_review"]
    if {int(row["id"]) for row in pending} != set(PRODUCTS):
        raise RuntimeError(
            f"pending set mismatch: {[row['id'] for row in pending]}"
        )
    media = []
    hashes = set()
    for rid in PRODUCTS:
        robot = client._get(f"robots/robots/{rid}/")
        url = str(robot.get("s3_image") or robot.get("image") or "")
        response = requests.get(url, headers=HEADERS, timeout=90)
        response.raise_for_status()
        image = Image.open(io.BytesIO(response.content))
        digest = hashlib.sha256(response.content).hexdigest()
        hashes.add(digest)
        media.append(
            {
                "id": rid,
                "url": url,
                "size": list(image.size),
                "bytes": len(response.content),
                "sha256": digest,
            }
        )
        if image.width < 800 or image.height < 700:
            raise RuntimeError(f"undersized hero for {rid}: {image.size}")
        if robot.get("family_key") != payload(rid)["family_key"]:
            raise RuntimeError(f"family invariant failed for {rid}")
        photos = robot.get("photos") or []
        if len(photos) != 1 or int(photos[0]["id"]) in STALE_PHOTOS:
            raise RuntimeError(
                f"media replacement invariant failed for {rid}: "
                f"{[photo.get('id') for photo in photos]}"
            )
        actual_videos = {video.get("url") for video in robot.get("videos") or []}
        if actual_videos != desired_video_urls(rid):
            raise RuntimeError(
                f"video replacement invariant failed for {rid}: {actual_videos}"
            )
    if len(hashes) != len(PRODUCTS):
        raise RuntimeError("canonical BALYO primary images are not distinct")
    return {"pending_ids": sorted(PRODUCTS), "media": media}


def main() -> int:
    parser = argparse.ArgumentParser(description="Curate BALYO company 242")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    client = ResearchApiClient()
    live = client.list_robots_for_company(COMPANY_ID)
    pending_ids = {
        int(robot["id"])
        for robot in live
        if robot.get("status") == "pending_review"
    }
    expected = set(PRODUCTS) | set(REJECTS)
    if pending_ids not in (expected, set(PRODUCTS)):
        raise RuntimeError(
            f"live queue drift: missing={sorted(expected-pending_ids)} "
            f"unexpected={sorted(pending_ids-expected)}"
        )

    preview = {
        "company_id": COMPANY_ID,
        "mode": "apply" if args.apply else "dry-run",
        "keepers": sorted(PRODUCTS),
        "rejects": REJECTS,
        "stale_photos": STALE_PHOTOS,
        "products": {rid: payload(rid) for rid in PRODUCTS},
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    if not args.apply:
        REPORT.write_text(
            json.dumps(preview, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(preview, indent=2, ensure_ascii=False))
        return 0

    copy_results = {}
    import_results = {}
    for rid in PRODUCTS:
        import_results[rid] = replace_media_and_videos(client, rid)
        if import_results[rid].get("error_count"):
            raise RuntimeError(f"bulk import failed for {rid}: {import_results[rid]}")
        client._patch(f"robots/robots/{rid}/", scalar_payload(rid))
        copy_results[rid] = copy_media(rid)

    stale_video_results = prune_stale_videos(client)
    reject_results = reject_duplicates(client)
    verified = verify_company(client)
    preview.update(
        {
            "applied": True,
            "removed_stale_photo_ids": sorted(STALE_PHOTOS),
            "copy_media": copy_results,
            "import_results": import_results,
            "stale_video_results": stale_video_results,
            "reject_results": reject_results,
            "verified": verified,
            "published_legacy_duplicates": {
                372: "TUGGY; retire after canonical 2685 is approved",
                373: "REACHY; retire after canonical 2681 is approved",
            },
        }
    )
    REPORT.write_text(
        json.dumps(preview, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(preview["verified"], indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
