"""Curated full enrichment for Yamaha Robotics company 1484.

Only operates on the five Yamaha records that remained ``pending_review`` when
the curated pass began. The other 34 YK-X records had already been published by
another process and are deliberately never touched.

Sources are Yamaha Motor global product pages, exact-model PDFs, launch releases,
and Yamaha Robotics Group (YRG) family tables. Family-table values are stored per
explicit model key; this script never selects a positional "first" value.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import fitz
import requests
from PIL import Image

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from api_client import ResearchApiClient
from load_env import load_research_env

load_research_env()

COMPANY_ID = 1484
COMPANY_SLUG = "yamaha-motor-co-ltd-robotics-division"
AVAILABLE = 11
TARGET_IDS = {3520, 4757, 4758, 4759, 4784}
REPORT = _HERE / "staging" / "reports" / "yamaha-1484-curated-full.json"
MEDIA_DIR = _HERE / "staging" / "yamaha_1484_media"

XEC_FAMILY = "https://global.yamaha-motor.com/business/robot/lineup/clean/ykxec/"
XEC_SPEC = f"{XEC_FAMILY}spec/"
XEC_CATALOG = (
    "https://global.yamaha-motor.com/business/robot/download/catalog/pdf/"
    "YK-XE_catalog_202412-FE.pdf"
)
XEC_RELEASE = "https://global.yamaha-motor.com/news/2023/1127/yk-xec.html"
YRG_XEC = "https://www.yrginc.com/products/details/?product=economy-cleanroom-scara"
LARGE_FAMILY = "https://global.yamaha-motor.com/business/robot/lineup/ykxg/large/"
YK1200_PDF = (
    "https://global.yamaha-motor.com/business/robot/lineup/ykxg/large/pdf/index/"
    "YK1200XG_202505-CE_WEB.pdf"
)
YK1200_RELEASE = "https://global.yamaha-motor.com/news/2024/0910/scara.html"
YK1200_IMAGE = (
    "https://news.yamaha-motor.co.jp/news/assets_c/2024/09/"
    "94545_0001-thumb-1000x618-256300.jpg"
)
YRG_STANDARD = "https://www.yrginc.com/products/details/?product=standard-scara"

XEC_FAMILY_VIDEOS = [
    {
        "url": "https://www.youtube.com/watch?v=spCY10jRA3g",
        "title": "【YK-X series】 Product Lineup and Application Introduction",
        "description": (
            "Official Yamaha Motor family overview covering the YK-X SCARA lineup; "
            "retained as family-level media because no exact-token YK-XEC video was found."
        ),
    }
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}


def xec_pdf(model: str) -> str:
    return f"{XEC_FAMILY}pdf/{model}.pdf"


COMMON_XEC_PURPOSE = (
    "Semiconductor production automation\n"
    "Hard disk drive production automation\n"
    "Food production automation\n"
    "Medical equipment production automation\n"
    "Precision instrument assembly"
)


def xec_features(
    *,
    model: str,
    arm_x: int,
    arm_y: int,
    rotation_x: float,
    rotation_y: float,
    z_stroke: int,
    motors: tuple[int, int, int, int],
    xy_speed: float,
    z_speed: float,
    r_speed: int,
    payload: int,
    cycle: float,
    inertia: float,
    weight: int,
    intake: int,
) -> str:
    return (
        f"Exact-model Yamaha datasheet specifications for {model}:\n"
        f"• Four-axis cleanroom SCARA; total arm length {arm_x + arm_y} mm "
        f"(X arm {arm_x} mm, Y arm {arm_y} mm); Z stroke {z_stroke} mm.\n"
        f"• Rotation ranges: X ±{rotation_x:g}°, Y ±{rotation_y:g}°, R ±360°.\n"
        f"• AC servo outputs (X/Y/Z/R): {motors[0]}/{motors[1]}/{motors[2]}/{motors[3]} W.\n"
        f"• Maximum speeds: X-Y synthesis {xy_speed:g} m/s; Z {z_speed:g} m/s; "
        f"R {r_speed:,}°/s.\n"
        "• Repeatability at constant ambient temperature: X-Y ±0.01 mm, "
        "Z ±0.01 mm, R ±0.01°.\n"
        f"• Maximum payload {payload} kg; standard cycle time {cycle:g} s with "
        f"2 kg payload; R-axis tolerable moment of inertia {inertia:g} kg·m².\n"
        f"• Robot weight {weight} kg; ISO Class 4 cleanliness (ISO 14644-1); "
        f"intake air {intake} Nℓ/min.\n"
        "• RCX340 controller; soft limits plus mechanical stoppers on X/Y/Z; "
        "standard 3.5 m robot cable with 5 m and 10 m options.\n"
        "• Family features: compact clean design, vibration-reduced high-speed "
        "operation, RCXiVY2+ vision integration, and support for CC-Link, "
        "EtherNet/IP, DeviceNet, PROFIBUS, PROFINET, and EtherCAT."
    )


PRODUCTS: dict[int, dict[str, Any]] = {
    4757: {
        "model": "YK400XEC",
        "official_name": "YK400XEC-4",
        "payload_kg": 4.0,
        "reach_mm": 400.0,
        "weight_kg": 18.0,
        "repeatability_mm": 0.01,
        "cycle_s": 0.45,
        "z_stroke_mm": 150,
        "features": xec_features(
            model="YK400XEC-4",
            arm_x=225,
            arm_y=175,
            rotation_x=132,
            rotation_y=145,
            z_stroke=150,
            motors=(200, 100, 100, 100),
            xy_speed=6.0,
            z_speed=1.1,
            r_speed=2600,
            payload=4,
            cycle=0.45,
            inertia=0.05,
            weight=18,
            intake=55,
        ),
    },
    4758: {
        "model": "YK510XEC",
        "official_name": "YK510XEC-10",
        "payload_kg": 10.0,
        "reach_mm": 510.0,
        "weight_kg": 27.0,
        "repeatability_mm": 0.01,
        "cycle_s": 0.42,
        "z_stroke_mm": 200,
        "features": xec_features(
            model="YK510XEC-10",
            arm_x=235,
            arm_y=275,
            rotation_x=134,
            rotation_y=147.5,
            z_stroke=200,
            motors=(400, 200, 200, 200),
            xy_speed=7.8,
            z_speed=2.0,
            r_speed=2600,
            payload=10,
            cycle=0.42,
            inertia=0.3,
            weight=27,
            intake=60,
        ),
    },
    3520: {
        "model": "YK610XEC",
        "official_name": "YK610XEC-10",
        "payload_kg": 10.0,
        "reach_mm": 610.0,
        "weight_kg": 27.0,
        "repeatability_mm": 0.01,
        "cycle_s": 0.44,
        "z_stroke_mm": 200,
        "features": xec_features(
            model="YK610XEC-10",
            arm_x=335,
            arm_y=275,
            rotation_x=134,
            rotation_y=147.5,
            z_stroke=200,
            motors=(400, 200, 200, 200),
            xy_speed=8.6,
            z_speed=2.0,
            r_speed=2600,
            payload=10,
            cycle=0.44,
            inertia=0.3,
            weight=27,
            intake=60,
        ),
    },
    4759: {
        "model": "YK710XEC",
        "official_name": "YK710XEC-10",
        "payload_kg": 10.0,
        "reach_mm": 710.0,
        "weight_kg": 28.0,
        "repeatability_mm": 0.01,
        "cycle_s": 0.49,
        "z_stroke_mm": 200,
        "features": xec_features(
            model="YK710XEC-10",
            arm_x=435,
            arm_y=275,
            rotation_x=134,
            rotation_y=147.5,
            z_stroke=200,
            motors=(400, 200, 200, 200),
            xy_speed=9.5,
            z_speed=2.0,
            r_speed=2600,
            payload=10,
            cycle=0.49,
            inertia=0.3,
            weight=28,
            intake=60,
        ),
    },
    4784: {
        "model": "YK1200XG",
        "official_name": "YK1200XG",
        "payload_kg": 50.0,
        "reach_mm": 1200.0,
        "weight_kg": 96.0,
        # Singular typed field uses the least favorable linear-axis value.
        "repeatability_mm": 0.05,
        "cycle_s": 0.61,
        "z_stroke_mm": 400,
        "features": (
            "Exact-model Yamaha YK1200XG datasheet specifications:\n"
            "• Four-axis, completely beltless large SCARA; total arm length 1,200 mm "
            "(X arm 600 mm, Y arm 600 mm); Z stroke 400 mm.\n"
            "• Standard working-envelope rotations: X ±125°, Y ±150°, R ±360°.\n"
            "• AC servo outputs (X/Y/Z/R): 950/400/750/400 W.\n"
            "• Maximum speeds: X-Y synthesis 7.7 m/s; Z 1.6 m/s; R 660°/s.\n"
            "• Repeatability: X-Y ±0.05 mm, Z ±0.02 mm, R ±0.005°.\n"
            "• Maximum payload 50 kg (48 kg with tool flange); standard cycle times "
            "0.55 s at 2 kg, 0.61 s at 5 kg, and 0.92 s at 40 kg.\n"
            "• R-axis tolerable moment of inertia 2.45 kg·m²; robot weight 96 kg.\n"
            "• User wiring: 0.2 sq × 12 wires plus RJ45 Cat5e PoE; three φ6 user tubes; "
            "standard 3.5 m cable with 5 m and 10 m options.\n"
            "• Dedicated RCX341 controller; high-rigidity extruded arm, two linear "
            "shafts to reduce vibration, built-in user wiring/piping, and optional tool flange."
        ),
    },
}


def is_image(body: bytes) -> bool:
    return (
        body.startswith(b"\xff\xd8")
        or body.startswith(b"\x89PNG\r\n\x1a\n")
        or (body.startswith(b"RIFF") and body[8:12] == b"WEBP")
    )


def get_bytes(url: str) -> bytes:
    response = requests.get(url, headers=HEADERS, timeout=90, allow_redirects=True)
    response.raise_for_status()
    return response.content


def upscale_product_render(body: bytes, target_long_side: int = 1_200) -> bytes:
    """Upscale a small exact-model transparent render for content-card use."""
    source = Image.open(io.BytesIO(body)).convert("RGBA")
    long_side = max(source.size)
    if long_side < target_long_side:
        scale = target_long_side / long_side
        target = (
            max(1, round(source.width * scale)),
            max(1, round(source.height * scale)),
        )
        source = source.resize(target, Image.Resampling.LANCZOS)
    output = io.BytesIO()
    source.save(output, format="PNG", optimize=True)
    return output.getvalue()


def exact_model_render(product: dict[str, Any]) -> tuple[Path, str, int]:
    """Extract the largest raster render from that model's exact Yamaha PDF."""
    model = product["model"]
    pdf_url = xec_pdf(model)
    pdf = fitz.open(stream=get_bytes(pdf_url), filetype="pdf")
    images = pdf[0].get_images(full=True)
    if not images:
        raise RuntimeError(f"{model}: exact datasheet has no raster product render")
    xref = max(images, key=lambda row: int(row[2]) * int(row[3]))[0]
    extracted = pdf.extract_image(xref)
    body = upscale_product_render(extracted["image"])
    if not is_image(body) or len(body) < 10_000:
        raise RuntimeError(f"{model}: extracted render failed magic/size gate ({len(body)} bytes)")
    path = MEDIA_DIR / f"{model.lower()}-exact-datasheet-render-1200.png"
    path.write_bytes(body)
    return path, hashlib.sha256(body).hexdigest(), len(body)


def remote_exact_image(url: str, filename: str) -> tuple[Path, str, int]:
    body = get_bytes(url)
    if not is_image(body) or len(body) < 10_000:
        raise RuntimeError(f"{url}: failed image magic/size gate ({len(body)} bytes)")
    path = MEDIA_DIR / filename
    path.write_bytes(body)
    return path, hashlib.sha256(body).hexdigest(), len(body)


def upload_image(client: ResearchApiClient, rid: int, path: Path, title: str) -> str:
    headers = {
        key: value
        for key, value in client._session.headers.items()
        if key.lower() != "content-type"
    }
    with path.open("rb") as handle:
        response = requests.post(
            client._url(f"robots/robots/{rid}/images/"),
            headers=headers,
            files={"images": (path.name, handle, "image/png")},
            data={"title": title, "description": "Exact-model render extracted from Yamaha datasheet."},
            timeout=120,
        )
    response.raise_for_status()
    data = response.json()
    photos = data.get("photos") or [data.get("photo") or {}]
    url = str((photos[0] or {}).get("url") or "")
    if not url:
        raise RuntimeError(f"{rid}: upload returned no CDN URL")
    return url


def copy_media(rid: int) -> dict[str, Any]:
    secret = os.environ.get("INTERNAL_API_SECRET", "").strip()
    if not secret:
        raise RuntimeError("INTERNAL_API_SECRET missing")
    base = os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/").replace("/api/v1", "")
    response = requests.post(
        f"{base}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/?force=1",
        headers={"X-Internal-Secret": secret},
        timeout=240,
    )
    response.raise_for_status()
    return response.json()


def verify_cdn(url: str) -> dict[str, Any]:
    response = requests.get(url, headers=HEADERS, timeout=60)
    body = response.content
    return {
        "url": url,
        "status": response.status_code,
        "bytes": len(body),
        "magic_ok": is_image(body),
        "sha256": hashlib.sha256(body).hexdigest() if response.status_code == 200 else "",
    }


def source_list(rid: int) -> list[str]:
    if rid == 4784:
        return [YK1200_PDF, LARGE_FAMILY, YK1200_RELEASE, YRG_STANDARD]
    model = PRODUCTS[rid]["model"]
    return [xec_pdf(model), XEC_FAMILY, XEC_SPEC, XEC_CATALOG, XEC_RELEASE, YRG_XEC]


def description_for(rid: int) -> str:
    product = PRODUCTS[rid]
    if rid == 4784:
        return (
            "YK1200XG is Yamaha Motor's 1,200 mm, 50 kg-payload large SCARA robot "
            "for assembly and transfer of large or heavy objects. Introduced in 2024 "
            "with the dedicated RCX341 controller, its completely beltless YK-XG "
            "architecture combines a high-rigidity arm with fast heavy-load motion."
        )
    return (
        f"{product['official_name']} is Yamaha Motor's ISO Class 4 cleanroom SCARA "
        f"with a {int(product['reach_mm'])} mm arm, {int(product['payload_kg'])} kg "
        f"maximum payload, and {product['cycle_s']:.2f} s standard cycle time. It is "
        "the clean version of the cost-performance YK-XE platform and is intended for "
        "clean manufacturing environments."
    )


def purpose_for(rid: int) -> str:
    if rid == 4784:
        return (
            "Assembly of large and heavy objects\n"
            "Transfer of large and heavy objects\n"
            "Large-workpiece palletizing\n"
            "In-vehicle battery handling"
        )
    return COMMON_XEC_PURPOSE


def notes_for(rid: int, media_origin: str) -> str:
    product = PRODUCTS[rid]
    if rid == 4784:
        dead = (
            "Dead searches: no public Yamaha list price or complete external L×W×H "
            "envelope found after the exact PDF, family PDP, YRG table, and launch release. "
            "Axis synthesis speed is retained in Features and not mapped to Robot.speed "
            "(km/h), because this is a stationary arm rather than locomotion speed."
        )
    else:
        dead = (
            "Dead searches: no public Yamaha list price or safely defined overall L×W×H "
            "typed dimensions found after exact-model PDF, YK-XEC PDP/spec table, YK-XE "
            "catalog, YRG table, and launch release. Axis synthesis/Z/R speeds and Z stroke "
            "are retained in Features and not mis-mapped to Robot.speed or overall height."
        )
    return (
        "[AI Research — curated Yamaha full enrichment]\n"
        f"Exact model: {product['official_name']}. release_year=2024. "
        f"Model-column source: {source_list(rid)[0]}. "
        f"Hero provenance: {media_origin}. Image bytes passed magic, size, and SHA-256 gates. "
        f"{dead}"
    )


def patch_payload(rid: int, media_url: str, media_origin: str) -> dict[str, Any]:
    product = PRODUCTS[rid]
    clean = rid != 4784
    payload: dict[str, Any] = {
        "name": product["official_name"],
        "model_name": product["official_name"],
        "variant_code": product["official_name"],
        "variant_label": (
            f"{int(product['reach_mm'])} mm arm / {int(product['payload_kg'])} kg payload"
        ),
        "description": description_for(rid),
        "purpose": purpose_for(rid),
        "features": product["features"],
        "url": source_list(rid)[0],
        "family_key": "yamaha:yk-xec" if clean else "yamaha:yk-xg-large",
        "family_name": "YK-XEC Clean SCARA" if clean else "YK-XG Large SCARA",
        "family_url": XEC_FAMILY if clean else LARGE_FAMILY,
        "product_url_scope": "exact_variant",
        "availability_status": AVAILABLE,
        "release_year": 2024,
        "payload_kg": product["payload_kg"],
        "reach_mm": product["reach_mm"],
        "weight_kg": product["weight_kg"],
        "weight": f"{product['weight_kg']:g} kg",
        "repeatability_mm": product["repeatability_mm"],
        "dof": 4,
        "images": [media_url],
        "image": media_url,
        "s3_image": None,
        "information_source_urls": source_list(rid),
        "notes": notes_for(rid, media_origin),
        "tags": (
            ["Assembly", "Automation", "Cleanroom", "Industrial", "Industrial Automation",
             "Manufacturing", "Precision", "scara"]
            if clean
            else ["Assembly", "Automation", "Handling", "Industrial", "Industrial Automation",
                  "Manufacturing", "Palletizing", "scara"]
        ),
        # Explicit invariant: the script never approves or publishes.
        "status": "pending_review",
    }
    if rid == 4784:
        payload["video_urls"] = [
            {
                "url": "https://www.youtube.com/watch?v=RI_y0bqdh8g",
                "title": '【50kg】High payload, High speed! Large type SCARA robots "YK1200XG"',
            },
            {
                "url": "https://www.youtube.com/watch?v=FlX1gOUCLpk",
                "title": "Boost Logistics Efficiency with a Large SCARA Robot (Up to 50 kg Payload)",
                "description": "Official Yamaha video description explicitly identifies YK1200XG.",
            },
        ]
    else:
        payload["video_urls"] = XEC_FAMILY_VIDEOS
    return payload


def replace_robot_videos(
    client: ResearchApiClient, payload: dict[str, Any]
) -> dict[str, Any]:
    """Replace all active videos while preserving the moderation status."""
    result = client.bulk_import_robots(
        [
            {
                "name": payload["name"],
                "company_slug": COMPANY_SLUG,
                "video_urls": payload["video_urls"],
            }
        ],
        update_existing=True,
        patch_existing=True,
        status="pending_review",
        skip_company_update=True,
        replace_videos=True,
    )
    if result.get("error_count"):
        raise RuntimeError(f"video replacement failed: {result}")
    return result


def video_dead_search(robot: dict[str, Any]) -> dict[str, Any]:
    videos = robot.get("videos") or []
    return {
        "id": int(robot["id"]),
        "model": PRODUCTS[int(robot["id"])]["official_name"],
        "reason": (
            "No official video with the exact XEC model token was found by Yamaha/YRG "
            "PDP, launch-release, and YouTube exact-token searches. All previous sibling "
            "and off-product clips were replaced through bulk import with the official "
            "Yamaha YK-X family overview only."
        ),
        "replacement_video_urls": XEC_FAMILY_VIDEOS,
        "existing_video_ids": [v.get("id") for v in videos],
        "existing_titles": [v.get("title") for v in videos],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Curated Yamaha 1484 pending-review enrichment")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    client = ResearchApiClient()
    all_robots = client.list_robots_for_company(COMPANY_ID)
    status_counts: dict[str, int] = {}
    for robot in all_robots:
        status = str(robot.get("status") or "")
        status_counts[status] = status_counts.get(status, 0) + 1

    pending = {
        int(robot["id"]): robot
        for robot in all_robots
        if int(robot["id"]) in TARGET_IDS and robot.get("status") == "pending_review"
    }
    excluded_published = [
        int(robot["id"])
        for robot in all_robots
        if int(robot["id"]) not in TARGET_IDS and robot.get("status") == "published"
    ]
    missing_or_moved = sorted(TARGET_IDS - set(pending))

    candidates: dict[int, dict[str, Any]] = {}
    seen_hashes: dict[str, int] = {}
    for rid in sorted(pending):
        product = PRODUCTS[rid]
        if rid in (4757, 3520, 4759):
            path, digest, size = exact_model_render(product)
            origin = f"largest raster product render embedded in {xec_pdf(product['model'])}"
            upload_required = True
        elif rid == 4758:
            release_image = (
                "https://news.yamaha-motor.co.jp/news/assets_c/2023/11/"
                "79741_0001-thumb-1000x1016-251318.jpg"
            )
            path, digest, size = remote_exact_image(
                release_image, "yk510xec-exact-launch-photo.jpg"
            )
            origin = f"{release_image} (Yamaha release caption: photograph shows YK510XEC)"
            upload_required = False
        else:
            path, digest, size = remote_exact_image(
                YK1200_IMAGE, "yk1200xg-exact-release-photo.jpg"
            )
            origin = (
                f"{YK1200_IMAGE} "
                "(Yamaha launch-release image captioned SCARA Robot YK1200XG)"
            )
            upload_required = False
        if digest in seen_hashes:
            raise RuntimeError(
                f"cross-model image hash collision: {rid} and {seen_hashes[digest]} ({digest})"
            )
        seen_hashes[digest] = rid
        candidates[rid] = {
            "path": str(path),
            "sha256": digest,
            "bytes": size,
            "origin": origin,
            "upload_required": upload_required,
        }

    report: dict[str, Any] = {
        "company_id": COMPANY_ID,
        "mode": "apply" if args.apply else "dry-run",
        "production_status_counts_at_start": status_counts,
        "target_pending_ids": sorted(pending),
        "excluded_already_published_count": len(excluded_published),
        "excluded_already_published_ids": sorted(excluded_published),
        "target_ids_missing_or_status_moved": missing_or_moved,
        "candidates": candidates,
        "applied": [],
        "errors": [],
        "rejected_ids": [],
        "held_ids": [],
        "video_dead_searches": [
            video_dead_search(pending[rid]) for rid in sorted(pending) if rid != 4784
        ],
    }
    if not args.apply:
        REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0

    for rid in sorted(pending):
        try:
            current = client._get(f"robots/robots/{rid}/")
            if current.get("status") != "pending_review":
                report["errors"].append(
                    {"id": rid, "error": f"status moved to {current.get('status')} before write"}
                )
                continue

            candidate = candidates[rid]
            if candidate["upload_required"]:
                media_url = upload_image(
                    client,
                    rid,
                    Path(candidate["path"]),
                    f"{PRODUCTS[rid]['official_name']} exact Yamaha datasheet render",
                )
            elif rid == 4758:
                media_url = (
                    "https://news.yamaha-motor.co.jp/news/assets_c/2023/11/"
                    "79741_0001-thumb-1000x1016-251318.jpg"
                )
            else:
                media_url = YK1200_IMAGE

            payload = patch_payload(rid, media_url, candidate["origin"])
            client._patch(
                f"robots/robots/{rid}/",
                payload,
            )
            video_result = replace_robot_videos(client, payload)
            copy_result = copy_media(rid)
            refreshed = client._get(f"robots/robots/{rid}/")
            if refreshed.get("status") != "pending_review":
                raise RuntimeError(
                    f"status invariant violated after patch: {refreshed.get('status')}"
                )
            cdn_url = str(refreshed.get("s3_image") or refreshed.get("image") or "")
            cdn = verify_cdn(cdn_url)
            if cdn["status"] != 200 or not cdn["magic_ok"]:
                raise RuntimeError(f"CDN verification failed: {cdn}")
            photo_hashes = []
            for photo in refreshed.get("photos") or []:
                url = photo.get("s3_image") or photo.get("url")
                if not url:
                    continue
                checked = verify_cdn(url)
                if checked["status"] != 200 or not checked["magic_ok"]:
                    raise RuntimeError(f"gallery CDN verification failed: {checked}")
                photo_hashes.append(checked["sha256"])
            if len(photo_hashes) != len(set(photo_hashes)):
                raise RuntimeError(f"duplicate gallery byte hash after copy: {photo_hashes}")

            report["applied"].append(
                {
                    "id": rid,
                    "name": refreshed.get("name"),
                    "status": refreshed.get("status"),
                    "typed": {
                        field: refreshed.get(field)
                        for field in (
                            "payload_kg",
                            "reach_mm",
                            "weight_kg",
                            "repeatability_mm",
                            "dof",
                        )
                    },
                    "family_key": refreshed.get("family_key"),
                    "availability_status": refreshed.get("availability_status"),
                    "cdn": cdn,
                    "gallery_count": len(refreshed.get("photos") or []),
                    "gallery_hashes": photo_hashes,
                    "videos": [
                        {"id": v.get("id"), "url": v.get("url"), "title": v.get("title")}
                        for v in refreshed.get("videos") or []
                    ],
                    "video_replacement": video_result,
                    "copy_media": copy_result,
                }
            )
            print(f"applied {rid} {refreshed.get('name')} — CDN {cdn['status']}")
        except Exception as exc:
            report["errors"].append({"id": rid, "error": str(exc)})
            print(f"ERROR {rid}: {exc}", file=sys.stderr)
        time.sleep(0.2)

    # Exact-token XEC videos were unavailable, but the official Yamaha family
    # overview is relevant and replace_videos removes every prior sibling clip.
    report["held_ids"] = []
    report["production_status_counts_at_end"] = {}
    final = client.list_robots_for_company(COMPANY_ID)
    for robot in final:
        status = str(robot.get("status") or "")
        report["production_status_counts_at_end"][status] = (
            report["production_status_counts_at_end"].get(status, 0) + 1
        )
    report["status_invariant_ok"] = all(
        robot.get("status") == "pending_review"
        for robot in final
        if int(robot["id"]) in {item["id"] for item in report["applied"]}
    )
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"report: {REPORT}")
    return 0 if not report["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
