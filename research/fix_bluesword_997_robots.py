"""Curate BlueSword company 997 into nine named robot products."""

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

COMPANY_ID = 997
COMPANY_SLUG = "bluesword-intelligent-technology-coltd"
COMPANY_NAME = "Bluesword Intelligent Technology Co., Ltd"
REPORT = _HERE / "staging" / "reports" / "bluesword-997-curated-report.json"
AVAILABLE = 11
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
    )
}

STACKER_URL = "https://www.bluesword.com/solutions/products/stacker-crane"
PALLET_URL = "https://www.bluesword.com/solutions/products/pallet-shuttle"
PALLET_BROCHURE = (
    "https://www.bluesword.com/resources/downloads/product-brochures/pallet-shuttle"
)
LOADING_URL = "https://www.bluesword.com/solutions/products/loading-unloading"
KANGAROO_URL = "https://www.bluesword.com/solutions/products/kangaroo"
SPIDER_URL = "https://www.bluesword.com/solutions/products/spider"
GECKO_URL = (
    "https://www.bluesword.com/solutions/products/"
    "gecko-sky-miniload-autonomous-case-handling-robot"
)
AGV_URL = "https://www.bluesword.com/solutions/products/agv-amr"
LAUNCH_2024 = "https://www.bluesword.com/resources/news/newslist/154"
MODEX_2024 = "https://www.bluesword.com/resources/news/activities/110"

STACKER_VIDEO = (
    "https://www.bluesword.com/Public/Uploads/uploadfile/files/"
    "20250717/chanpinduiduojibanner.mp4"
)

COMMON_TAGS = [
    "AGV",
    "AMR",
    "AS/RS",
    "Automation",
    "Industrial",
    "Intralogistics",
    "Logistics",
    "Material Handling",
    "Warehouse Automation",
]
USES = [74, 62, 32, 54, 78]
INDUSTRIES = [11, 12]

PRODUCTS: dict[int, dict[str, Any]] = {
    5051: {
        "name": "Jaguar Full-Servo Stacker Crane",
        "model": "Jaguar",
        "url": STACKER_URL,
        "image": (
            "https://www.bluesword.com/Public/Uploads/uploadfile/images/"
            "20250723/sifuduiduoji-598.png"
        ),
        "description": (
            "BlueSword Jaguar is a lightweight distributed full-servo stacker "
            "crane for automated pallet storage and retrieval across 6–22 m systems."
        ),
        "features": (
            "Official Jaguar specifications: maximum load 1,000 kg; stacker-crane "
            "height 6–22 m; horizontal speed 120–160 m/min; horizontal acceleration "
            "0.5–0.9 m/s²; vertical speed 30 m/min; fork speed 30 m/min; vertical "
            "and fork acceleration 0.5 m/s². Full-servo drive supports smooth, "
            "quiet response; lightweight construction reduces energy use and "
            "simplifies maintenance and deployment."
        ),
        "purpose": (
            "Automated pallet storage and retrieval\n"
            "High-bay warehouse handling\n"
            "Rail-guided pallet transfer"
        ),
        "typed": {"payload_kg": 1000, "speed": 9.6, "release_year": 2024},
        "movement": [10],
        "videos": [
            {
                "url": STACKER_VIDEO,
                "title": "BlueSword stacker-crane portfolio",
                "description": (
                    "Official BlueSword stacker-crane page overview; no "
                    "Jaguar-only public video was found."
                ),
            }
        ],
        "sources": [LAUNCH_2024],
        "dead": "fixed robot dimensions, body mass, battery/runtime, and Jaguar-only video",
    },
    5050: {
        "name": "Four-Way Pallet Shuttle",
        "model": "Four-Way Pallet Shuttle",
        "url": PALLET_BROCHURE,
        "image": (
            "https://www.bluesword.com/Public/Uploads/uploadfile/images/"
            "20250729/weimingmingdesheji2.jpg"
        ),
        "description": (
            "BlueSword Four-Way Pallet Shuttle is a rail-guided omnidirectional "
            "robot for dense pallet AS/RS storage, retrieval, and aisle switching."
        ),
        "features": (
            "Official indexed PDP and live BlueSword brochure: 1,150 × 980 × "
            "135 mm body; 350 kg body weight; speed 1.5 m/s; acceleration "
            "0.3 m/s²; ±2 mm positioning accuracy; 2.5 s lifting and direction "
            "change; LFP battery; over 8 h runtime; under 2 h charging; 2,000+ "
            "battery cycles. Current OEM material conflicts on standard payload "
            "(1.5 t versus 1.6 t), while both cite customization up to 3 t, so "
            "payload is deliberately not mapped to a typed field. Features "
            "16-wheel four-way drive, opportunity charging, sealed modular "
            "construction, and low-temperature/explosion-proof options."
        ),
        "purpose": (
            "High-density pallet storage and retrieval\n"
            "Four-way rail movement within AS/RS racks\n"
            "Automated pallet lane transfer"
        ),
        "typed": {
            "weight_kg": 350,
            "weight": "350 kg",
            "speed": 5.4,
            "length_mm": 1150,
            "width_mm": 980,
            "height_mm": 135,
        },
        "movement": [4],
        "videos": [],
        "sources": [PALLET_URL],
        "dead": "unambiguous standard payload, exact public demo, and release year",
    },
    5048: {
        "name": "Asian Elephant Robot",
        "model": "Asian Elephant",
        "url": LOADING_URL,
        "image": (
            "https://www.bluesword.com/Public/Uploads/uploadfile/images/"
            "20251103/yazhouxiang.png"
        ),
        "description": (
            "BlueSword Asian Elephant is an autonomous truck-loading and unloading "
            "robot for cartons, bags, and totes across multiple warehouse docks."
        ),
        "features": (
            "Official specifications: 35 kg rated load; 0.8 m/s maximum travel "
            "speed; 1 m/s conveyor speed; 500–600 pieces/h with single grip or "
            "800–1,000 pieces/h with dual grip. Supports multiple docks and truck "
            "types, Laser-SLAM navigation, 360° obstacle avoidance, dual-grip "
            "handling, and integration with manual or automated palletizing."
        ),
        "purpose": (
            "Truck and container loading/unloading\n"
            "Dock-to-warehouse case transfer\n"
            "Carton, bag, and tote handling"
        ),
        "typed": {"payload_kg": 35, "speed": 2.88, "release_year": 2023},
        "movement": [4],
        "videos": [],
        "sources": [
            "https://www.bluesword.com/resources/news/media-press/132",
            MODEX_2024,
        ],
        "dead": "body mass, dimensions, runtime/battery, and exact public video",
    },
    5047: {
        "name": "Kangaroo Case Stack Access Robot",
        "model": "Kangaroo",
        "url": KANGAROO_URL,
        "image": (
            "https://www.bluesword.com/Public/Uploads/uploadfile/images/"
            "20250719/39.png"
        ),
        "description": (
            "BlueSword Kangaroo is a rack-free case stack access robot that "
            "directly stacks and retrieves totes for dense, flexible warehousing."
        ),
        "features": (
            "Official configurable platform specifications: automated-guided mode "
            "3 m/s, ±3 mm, ±0.5°, 1,000 mm aisle; rail-guided mode 1.5 m/s, "
            "±5 mm, ±1°, 1,200 mm aisle. Configuration maxima are 200/250/300 kg "
            "total load, 1/0.6/0.8 m/s fork-lift speed, and 6/8/11 internal tote "
            "positions. Full charge ≤2 h; endurance ≥6 h. Standard tote "
            "600×400×280 mm at 30 kg. Uses 2D vision, direct rack-free stacking, "
            "non-sequential access, and up to 50% claimed density improvement."
        ),
        "purpose": (
            "Rack-free tote stacking and retrieval\n"
            "Goods-to-person case fulfillment\n"
            "Dense storage in irregular or low-ceiling warehouses"
        ),
        "typed": {"payload_kg": 300, "speed": 10.8, "release_year": 2024},
        "movement": [4],
        "videos": [
            {
                "url": (
                    "https://www.bluesword.com/Public/Uploads/uploadfile/files/"
                    "20250729/daishuxiaoshipinjingyin.mp4"
                ),
                "title": "BlueSword Kangaroo demonstration",
                "description": "Official exact-product Kangaroo demonstration.",
            }
        ],
        "sources": [LAUNCH_2024],
        "dead": "body dimensions, body mass, battery capacity, and named configuration mapping",
    },
    5046: {
        "name": "Spider Sky-Shuttle",
        "model": "Spider Sky-Shuttle",
        "url": SPIDER_URL,
        "image": (
            "https://www.bluesword.com/Public/Uploads/uploadfile/images/"
            "20260716/blueswordmaterialhandlingautomation-168.png"
        ),
        "description": (
            "BlueSword Spider Sky-Shuttle is a case-handling robot family for "
            "two-way or four-way travel and lift-free access across flexible "
            "three-dimensional rack layouts."
        ),
        "features": (
            "Official Standard and Four-Way variants both specify a customizable "
            "600×400×300 mm case, 1,000 mm minimum aisle, 50 kg load, 4 m/s "
            "horizontal speed, 3 m/s lifting speed, and 2 m/s² acceleration. "
            "Movement differs by two-way versus four-way configuration. Flexible "
            "winch lift supports up to 20 m reach, automatic leveling, N/L/T-shaped "
            "layouts, LiDAR/3D vision, automatic aisle switching, and WMS/ERP APIs."
        ),
        "purpose": (
            "High-bay case storage and retrieval\n"
            "Goods-to-person order fulfillment\n"
            "Flexible irregular-layout AS/RS handling"
        ),
        "typed": {"payload_kg": 50, "speed": 14.4, "release_year": 2024},
        "movement": [4],
        "videos": [
            {
                "url": (
                    "https://www.bluesword.com/Public/Uploads/uploadfile/files/"
                    "20250917/liangxiangzhizhu.mp4"
                ),
                "title": "BlueSword Standard Spider Sky-Shuttle",
                "description": "Official exact-product Standard Spider demonstration.",
            }
        ],
        "sources": [LAUNCH_2024],
        "dead": "robot body dimensions, mass, runtime/battery, and variant launch dates",
    },
    2807: {
        "name": "UnitLoad-Libra",
        "model": "UnitLoad-Libra",
        "url": STACKER_URL,
        "image": (
            "https://www.bluesword.com/Public/Uploads/uploadfile/images/"
            "20250723/tianping.png"
        ),
        "description": (
            "BlueSword UnitLoad-Libra is a standard-pallet stacker crane for "
            "cost-focused automated storage and retrieval systems up to 24 m."
        ),
        "features": (
            "Official specifications: maximum load 1,500 kg; stacker-crane height "
            "up to 24 m; horizontal speed 340 m/min; acceleration 0.6 m/s²; "
            "vertical speed 60 m/min. Supports single- or double-deep layouts, "
            "single/double/multiple positions, and single- or double-mast "
            "configurations. BlueSword positions Libra for broad operating "
            "conditions, cost efficiency, short lead time, and stable performance."
        ),
        "purpose": (
            "Automated standard-pallet storage and retrieval\n"
            "High-bay AS/RS pallet transfer\n"
            "Single- and double-deep warehouse handling"
        ),
        "typed": {"payload_kg": 1500, "speed": 20.4},
        "movement": [10],
        "videos": [
            {
                "url": STACKER_VIDEO,
                "title": "BlueSword stacker-crane portfolio",
                "description": (
                    "Official BlueSword stacker-crane page overview; no "
                    "UnitLoad-Libra-only public video was found."
                ),
            }
        ],
        "dead": "fixed robot dimensions, body mass, battery/runtime, release year, and exact video",
    },
    2806: {
        "name": "Gecko Sky-MiniLoad",
        "model": "Gecko Sky-MiniLoad",
        "url": GECKO_URL,
        "image": (
            "https://www.bluesword.com/Public/Uploads/uploadfile/images/"
            "20260311/bihuSTUshebei011.jpg"
        ),
        "description": (
            "BlueSword Gecko Sky-MiniLoad is a rail-guided case-handling robot "
            "for mixed cartons and totes on existing 6, 9, or 12 m racks."
        ),
        "features": (
            "Official current specifications: 30 kg load; customizable "
            "600×400×300 mm cartons/totes; 3 m/s operating speed; 3 m/s lifting "
            "speed; conductor-rail power. Installs on existing racks without floor "
            "modification, supports mixed case sizes, integrates with conveyors, "
            "AGVs/AMRs and lifts, and uses modular track installation for relocation "
            "and typical three-day deployment."
        ),
        "purpose": (
            "Mixed-size carton and tote storage/retrieval\n"
            "Existing-rack mini-load AS/RS automation\n"
            "Case transfer to conveyors and mobile robots"
        ),
        "typed": {"payload_kg": 30, "speed": 10.8, "release_year": 2024},
        "movement": [4],
        "videos": [
            {
                "url": (
                    "https://www.bluesword.com/Public/Uploads/uploadfile/files/"
                    "20250729/bihuxiaoshipinjingyin.mp4"
                ),
                "title": "BlueSword Gecko Sky-MiniLoad demonstration",
                "description": "Official exact-product Gecko demonstration.",
            }
        ],
        "sources": [MODEX_2024],
        "dead": "robot body dimensions, body mass, battery/runtime, and exact current launch date",
    },
    1233: {
        "name": "Transfer FMR",
        "model": "Transfer FMR",
        "url": AGV_URL,
        "image": (
            "https://www.bluesword.com/Public/Uploads/uploadfile/images/"
            "20251023/FT2002B1banyunxingchaqujiqiren.184.png"
        ),
        "description": (
            "BlueSword Transfer Forklift Mobile Robot (FMR) is a heavy-duty "
            "autonomous platform for shelves, large loads, and low-lift transfer."
        ),
        "features": (
            "Official configuration specifications: rated load 2,000 or 3,000 kg; "
            "body weight 650 or 720 kg; lifting height up to 205 mm; gradability "
            "3% at full load or 5% unloaded; ±10 mm positioning accuracy; charging "
            "time ≤3 h. Uses multi-technology navigation, LiDAR/3D safety, "
            "collision sensors, emergency stop, and audio-visual alarms."
        ),
        "purpose": (
            "Heavy shelf and large-load transfer\n"
            "Low-lift autonomous forklift handling\n"
            "Factory and warehouse material movement"
        ),
        "typed": {"payload_kg": 3000},
        "movement": [4],
        "videos": [],
        "dead": "configuration-specific dimensions/speed/runtime, battery capacity, release year, and exact video",
    },
    1231: {
        "name": "Latent Mobile Robot (LMR)",
        "model": "Latent Mobile Robot",
        "url": AGV_URL,
        "image": (
            "https://www.bluesword.com/Public/Uploads/uploadfile/images/"
            "20251023/AMRqianfushijiqiren1-94.png"
        ),
        "description": (
            "BlueSword Latent Mobile Robot (LMR) is a compact under-load lifting "
            "AMR family for flat warehouses and production-line delivery."
        ),
        "features": (
            "Official family specifications: rated load 400–2,000 kg; lift "
            "60–100 mm; no-load speed 1–2.5 m/s; climbing capacity 3% at full "
            "load or 5% unloaded; positioning accuracy ±10 mm and ±1°; "
            "differential drive; QR-code, VSLAM, or LSLAM navigation. Standard "
            "safety includes LiDAR/3D perception, collision sensors, emergency "
            "stop, and audio-visual alarms."
        ),
        "purpose": (
            "Under-load rack and pallet transport\n"
            "Production-line material delivery\n"
            "Flexible flat-warehouse intralogistics"
        ),
        "typed": {"payload_kg": 2000, "speed": 9.0},
        "movement": [4],
        "videos": [],
        "dead": "configuration-specific dimensions/mass/runtime, battery capacity, release year, and exact video",
    },
}

REJECTS: dict[int, str] = {
    5052: "non_robot: fixed conveyor/diverter infrastructure family",
    5049: "family_or_category: Case Shuttle page contains multiple distinct shuttle products and support equipment",
    5045: "solution_or_category: loading/unloading umbrella contains Asian Elephant, Hammerhead, FMR and pallet systems",
    3609: "category: AGV & AMR portfolio shell covering multiple LMR/FMR/CMR products",
    1234: "phantom_non_robot: no official Bin Conveyor Robot; current item is conveyor infrastructure",
    1232: "generic_category_duplicate: BlueSword AMR is the AGV/AMR fleet, not one product",
    1230: "family: Forklift Robot/FMR covers Transfer, Reach, Stacker and Counterbalance products",
    1229: "category_or_solution: Picking & Sorting page contains multiple stations, arms and sorters",
}


def payload(rid: int) -> dict[str, Any]:
    data = PRODUCTS[rid]
    sources = [data["url"], *(data.get("sources") or [])]
    body: dict[str, Any] = {
        "name": data["name"],
        "model_name": data["model"],
        "variant_code": data["model"].replace(" ", "-"),
        "description": data["description"],
        "features": data["features"],
        "purpose": data["purpose"],
        "url": data["url"],
        "family_key": f"bluesword:{data['model'].lower().replace(' ', '-')}",
        "family_name": data["model"],
        "family_url": data["url"],
        "product_url_scope": "exact_variant",
        "availability_status": AVAILABLE,
        "manufacturer_country_ref": 3,
        "manufacturer_countries": [3],
        "uses": USES,
        "industries": INDUSTRIES,
        "movement_types": data["movement"],
        "tags": COMMON_TAGS,
        "information_source_urls": sources,
        "image": data["image"],
        "images": [data["image"]],
        "s3_image": None,
        "notes": (
            "[AI Research — BlueSword curated catalog pass 2026-07-21] "
            f"Exact official product identity/media verified. Dead searches: "
            f"{data['dead']}. Typed values use exact current OEM claims; ranges "
            "are represented as maximum configuration only when explicitly stated."
        ),
        "status": "pending_review",
    }
    body.update(data["typed"])
    return body


def scalar_payload(rid: int) -> dict[str, Any]:
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


def replace_media_and_videos(
    client: ResearchApiClient, rid: int
) -> dict[str, Any]:
    data = PRODUCTS[rid]
    row = payload(rid)
    row.update(
        {
            "id": rid,
            "company_slug": COMPANY_SLUG,
            "company_name": COMPANY_NAME,
            "manufacturer_country_code": "CN",
            "manufacturer_country_codes": "CN",
            "video_urls": enrich_video_list(data["videos"]),
        }
    )
    return client.bulk_import_robots(
        [row],
        update_existing=True,
        patch_existing=True,
        status="pending_review",
        skip_company_update=True,
        replace_media=True,
        replace_videos=True,
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


def reject_invalid_rows(client: ResearchApiClient) -> list[dict[str, Any]]:
    results = []
    for rid, reason in REJECTS.items():
        client._patch(
            f"robots/robots/{rid}/",
            {
                "status": "rejected",
                "rejection_reason": reason,
                "notes": f"[CURATED FULL 2026-07-21] {reason}",
            },
        )
        results.append({"id": rid, "reason": reason})
    return results


def desired_video_urls(rid: int) -> set[str]:
    return {
        str(item.get("url") if isinstance(item, dict) else item)
        for item in PRODUCTS[rid]["videos"]
    }


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
        if image.width < 600 or image.height < 600:
            raise RuntimeError(f"undersized hero for {rid}: {image.size}")
        photos = robot.get("photos") or []
        if len(photos) != 1:
            raise RuntimeError(
                f"media replacement invariant failed for {rid}: "
                f"{[photo.get('id') for photo in photos]}"
            )
        actual_videos = {video.get("url") for video in robot.get("videos") or []}
        if actual_videos != desired_video_urls(rid):
            raise RuntimeError(
                f"video replacement invariant failed for {rid}: {actual_videos}"
            )
        if robot.get("family_key") != payload(rid)["family_key"]:
            raise RuntimeError(f"family invariant failed for {rid}")
        media.append(
            {
                "id": rid,
                "url": url,
                "size": list(image.size),
                "bytes": len(response.content),
                "sha256": digest,
            }
        )
    if len(hashes) != len(PRODUCTS):
        raise RuntimeError("BlueSword keeper primary images are not distinct")
    return {"pending_ids": sorted(PRODUCTS), "media": media}


def main() -> int:
    parser = argparse.ArgumentParser(description="Curate BlueSword company 997")
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

    report: dict[str, Any] = {
        "company_id": COMPANY_ID,
        "mode": "apply" if args.apply else "dry-run",
        "keepers": sorted(PRODUCTS),
        "rejects": REJECTS,
        "products": {rid: payload(rid) for rid in PRODUCTS},
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    if not args.apply:
        REPORT.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0

    import_results = {}
    copy_results = {}
    for rid in PRODUCTS:
        import_results[rid] = replace_media_and_videos(client, rid)
        if import_results[rid].get("error_count"):
            raise RuntimeError(
                f"bulk import failed for {rid}: {import_results[rid]}"
            )
        client._patch(f"robots/robots/{rid}/", scalar_payload(rid))
        copy_results[rid] = copy_media(rid)

    reject_results = reject_invalid_rows(client)
    verified = verify_company(client)
    report.update(
        {
            "applied": True,
            "import_results": import_results,
            "copy_media": copy_results,
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
