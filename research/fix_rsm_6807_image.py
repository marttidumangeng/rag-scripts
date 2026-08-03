"""Restore SC6-1460 (#6807) hero wiped by quality-flag restamp."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import requests

_RESEARCH_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH_DIR))
from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient
from import_staging import resolve_created_by_id
from map_to_bulk_import import staging_dict_to_bulk_import_row

RID = 6807
CN = 3
HERO = "https://rsm-machinery.com/wp-content/uploads/2025/12/SC-Series-cobot-welding-robot.png"
GALLERY = [
    HERO,
    "https://rsm-machinery.com/wp-content/uploads/2025/12/SC-Series-cobot-welding-robot.png.webp",
]
TAGS = "6-Axis|Collaborative|Industrial|Material Handling|Welding"
PURPOSE = "Collaborative arc welding"


def _admin_base() -> str:
    return (os.environ.get("ADMIN_BASE") or "https://ragadmin.robotaigeek.com").rstrip("/")


def _internal_secret() -> str:
    secret = (
        os.environ.get("INTERNAL_API_SECRET")
        or os.environ.get("CONTENT_QUEUE_INTERNAL_SECRET")
        or ""
    ).strip()
    if secret:
        return secret
    for candidate in (
        _RESEARCH_DIR.parent.parent / "robotaigeek-server" / ".env",
        _RESEARCH_DIR.parent.parent / "robotaigeek-server" / ".env.local",
    ):
        if not candidate.exists():
            continue
        for line in candidate.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def copy_media(rid: int) -> bool:
    url = f"{_admin_base()}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/"
    resp = requests.post(url, headers={"X-Internal-Secret": _internal_secret()}, timeout=120)
    print(f"copy-media {rid}: HTTP {resp.status_code} {resp.text[:200]}")
    return resp.status_code < 300


def main() -> int:
    client = ResearchApiClient()
    r = client._get(f"robots/robots/{RID}/")
    row = {
        "company_slug": "rsm-machinery",
        "company_name": "RSM Machinery",
        "source_locale": "en",
        "name": r.get("name") or "SC6-1460",
        "model_name": r.get("model_name") or "SC6-1460",
        "url": r.get("url")
        or "https://rsm-machinery.com/product/sc6-1460-cobot-welding-robot/",
        "description": r.get("description") or "ERSM SC-series collaborative welding robot.",
        "purpose": PURPOSE,
        "features": r.get("features") or "ERSM SC-series collaborative welding robot.",
        "image": HERO,
        "images": GALLERY,
        "information_source_urls": [
            r.get("url")
            or "https://rsm-machinery.com/product/sc6-1460-cobot-welding-robot/"
        ],
        "notes": (r.get("notes") or "")
        + "\n[AI Research] Restored SC6-1460 OEM studio hero after quality restamp wiped media.",
        "manufacturer_country_code": "CN",
        "availability_status_key": "available",
        "payload_kg": r.get("payload_kg") or 6.0,
        "reach_mm": r.get("reach_mm") or 1460.7,
        "dof": r.get("dof") or 6,
        "repeatability_mm": r.get("repeatability_mm") or 0.05,
        "weight_kg": r.get("weight_kg") or 22.0,
        "family_key": "rsm-machinery:sc-cobot-welding",
        "family_name": "SC Cobot Welding",
        "family_url": r.get("url")
        or "https://rsm-machinery.com/product/sc6-1460-cobot-welding-robot/",
        "product_url_scope": "family",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "manufacturing-industrial",
        "movement_type_keys": "stationary|fixed",
        "industry_keys": "manufacturing|industrial|metalworking",
        "use_keys": "welding|material-handling|machine-tending",
        "tags": TAGS,
    }
    bulk = staging_dict_to_bulk_import_row(row)
    bulk["id"] = RID
    bulk["status"] = "pending_review"
    result = client.bulk_import_robots(
        [bulk],
        update_existing=True,
        patch_existing=False,
        replace_media=True,
        replace_videos=False,
        status="pending_review",
        skip_company_update=True,
        created_by_id=resolve_created_by_id(1),
    )
    print(
        json.dumps(
            {
                "updated": result.get("updated_count"),
                "errors": result.get("error_count"),
                "error_details": result.get("errors"),
            },
            ensure_ascii=False,
        )
    )
    if int(result.get("error_count") or 0) or not int(result.get("updated_count") or 0):
        return 1

    client._patch(
        f"robots/robots/{RID}/",
        {
            "status": "pending_review",
            "purpose": PURPOSE,
            "tags": [t.strip() for t in TAGS.split("|")],
            "manufacturer_countries": [CN],
            "manufacturer_country_ref": CN,
            "availability_status": 11,
            "payload_kg": row["payload_kg"],
            "reach_mm": row["reach_mm"],
            "dof": row["dof"],
            "repeatability_mm": row["repeatability_mm"],
            "weight_kg": row["weight_kg"],
            "product_url_scope": "family",
            "family_key": "rsm-machinery:sc-cobot-welding",
            "family_name": "SC Cobot Welding",
            "family_url": row["family_url"],
        },
    )

    if not copy_media(RID):
        time.sleep(2)
        if not copy_media(RID):
            print("copy-media failed", file=sys.stderr)
            return 1

    subprocess.check_call(
        [sys.executable, str(_RESEARCH_DIR / "verify_cdn_images.py"), "--ids", str(RID)],
        cwd=str(_RESEARCH_DIR),
    )

    r2 = client._get(f"robots/robots/{RID}/")
    flags = r2.get("quality_flags") or []
    print(
        json.dumps(
            {
                "id": RID,
                "name": r2.get("name"),
                "image": r2.get("image"),
                "s3_image": r2.get("s3_image"),
                "photos_n": len(r2.get("photos") or []),
                "errors": [
                    f.get("flag")
                    for f in flags
                    if isinstance(f, dict) and f.get("severity") == "error"
                ],
                "warns": [
                    f.get("flag")
                    for f in flags
                    if isinstance(f, dict) and f.get("severity") == "warn"
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if not (r2.get("s3_image") or r2.get("image")):
        print("ERROR still no image", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
