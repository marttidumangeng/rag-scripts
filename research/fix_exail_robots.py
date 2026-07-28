"""Fix Exail (428) contaminated UGV heroes + wrong A6K (UlyX) hero.

Apply:
  Cameleon LG (2753)  -> OEM catalog cameleon-lg_800x600 (distinct)
  Cameleon MK3 (2754) -> OEM catalog cameleon-e_800x600 (distinct; site names MK3 as Cameleon E art)
  Iguana (2755)       -> OEM catalog iguana_800x600 (distinct)
  A6K (2756)          -> labeled A6K produit PNG (replace UlyX header)
  Seascan (2758)      -> high-res seascan product (optional upgrade)
  K-Ster C (2757)     -> already correct K-STER underwater photo — keep

Ban hash: c00717f139eb… (shared UGV family outdoor banner)
"""
from __future__ import annotations

import argparse
import hashlib
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

from api_client import ResearchApiClient
from import_staging import import_staging, resolve_created_by_id
from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

COMPANY_ID = 428
COMPANY_SLUG = "exail-robotics"
COMPANY_NAME = "Exail Robotics"
FR = 5
REPORT = _RESEARCH / "staging" / "reports" / "exail-media-fix.json"
UA = {"User-Agent": "Mozilla/5.0 (compatible; RobotAIGeekResearch/1.0)"}
BAN = {"c00717f139ebc8605dd9c4563a89456b", "0c6bf486ed291ac7dd6f2416d127544a"}  # UGV banner, UlyX header

FIXES: list[dict[str, Any]] = [
    {
        "id": 2753,
        "name": "Cameleon LG",
        "url": "https://www.exail.com/product-range/unmanned-ground-vehicles",
        "description": (
            "Cameleon LG is Exail's lightweight compact UGV for rapid EOD/IEDD intervention."
        ),
        "purpose": "Rapid-intervention lightweight demining and EOD UGV",
        "features": (
            "Lightweight portable UGV with 20 cm obstacle clearance, about 14 kg base weight, "
            "5-axis manipulator arm, 0.9 m x 0.9 m reach (OEM UGV range comparison table)."
        ),
        "category_slugs": "",
        "use_keys": "",
        "movement_type_keys": "",
        "images": [
            "https://www.exail.com/media/9277/exail-cameleon-lg_800x600.png",
            "https://www.exail.com/media/9277/exail-cameleon-lg_400x280.png",
        ],
    },
    {
        "id": 2754,
        "name": "Cameleon MK3",
        "url": "https://www.exail.com/product-range/unmanned-ground-vehicles#cameleon-mk3",
        "description": (
            "Cameleon MK3 is Exail's multi-mission lightweight UGV for specialized intervention."
        ),
        "purpose": "Multi-mission lightweight EOD/intervention UGV",
        "features": (
            "Multi-mission UGV with 25 cm obstacle clearance, about 28 kg base weight, "
            "6-axis manipulator, 1.5 m x 1.2 m reach (OEM UGV range comparison table)."
        ),
        "category_slugs": "",
        "use_keys": "",
        "movement_type_keys": "",
        "images": [
            "https://www.exail.com/media/9278/exail-cameleon-e_800x600.png",
            "https://www.exail.com/media/9278/exail-cameleon-e_400x280.png",
        ],
    },
    {
        "id": 2755,
        "name": "Iguana",
        "url": "https://www.exail.com/product-range/unmanned-ground-vehicles#iguana",
        "description": (
            "Iguana is Exail's two-person-portable UGV for specialized intervention in confined spaces."
        ),
        "purpose": "Two-person-portable EOD/intervention UGV for confined spaces",
        "features": (
            "Two-men portable UGV with 60 cm obstacle clearance, about 52 kg base weight, "
            "6-axis arm, 2.2 m x 1.2 m reach (OEM UGV range comparison table)."
        ),
        "category_slugs": "",
        "use_keys": "",
        "movement_type_keys": "",
        "images": [
            "https://www.exail.com/media/9276/exail-iguana_800x600.png",
            "https://www.exail.com/media/9276/exail-iguana_400x280.png",
        ],
    },
    {
        "id": 2756,
        "name": "A6K Ultra-deep Autonomous Underwater Vehicle",
        "url": "https://www.exail.com/product/a6k-ultra-deep-autonomous-underwater-vehicles",
        "description": (
            "A6K is Exail's ultra-deep AUV for survey and inspection missions down to 6,000 m."
        ),
        "purpose": "Ultra-deep survey and inspection AUV",
        "features": (
            "Dual-mode survey & inspection to 6,000 m; long endurance up to about 30-hour missions; "
            "hovering capability (OEM A6K product page)."
        ),
        "category_slugs": "",
        "use_keys": "",
        "movement_type_keys": "",
        "images": [
            "https://www.exail.com/media/10850/exail-produit-a6k_804x498.png",
            "https://www.exail.com/media/10718/exail-a6k-ultra-deep-auv_1090x685.jpg",
        ],
    },
    {
        "id": 2758,
        "name": "Seascan Mine Identification System",
        "url": "https://www.exail.com/product/seascan-mine-identification-system",
        "description": (
            "Seascan is Exail's self-propelled mine identification ROV/system for naval MCM."
        ),
        "purpose": "Naval mine identification ROV",
        "features": (
            "Lightweight self-propelled hovering mine ID system with high-resolution video "
            "(OEM Seascan product page)."
        ),
        "category_slugs": "",
        "use_keys": "",
        "movement_type_keys": "",
        "images": [
            "https://www.exail.com/media/10517/exail-produit-seascan_3840x2160.png",
            "https://www.exail.com/media/10956/seascan-m_804x503.jpg",
        ],
    },
]


def download_ok(url: str) -> tuple[bool, str, int]:
    try:
        r = requests.get(url, timeout=60, headers=UA)
        data = r.content
        if r.status_code != 200 or len(data) < 5000:
            return False, "", len(data)
        if not (
            data[:3] == b"\xff\xd8\xff"
            or data[:8].startswith(b"\x89PNG")
            or data[:4] == b"RIFF"
        ):
            return False, "", len(data)
        md5 = hashlib.md5(data).hexdigest()
        if md5 in BAN:
            return False, md5, len(data)
        return True, md5, len(data)
    except requests.RequestException:
        return False, "", 0


def copy_media(rid: int) -> str:
    secret = os.environ.get("INTERNAL_API_SECRET", "").strip()
    env_file = _RESEARCH.parents[1] / "robotaigeek-server" / ".env"
    if not secret and env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                secret = line.split("=", 1)[1].strip()
    api = os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/").replace("/api/v1", "")
    if not secret or not api:
        return "no-secret"
    url = f"{api}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/?force=1"
    for attempt in range(5):
        try:
            resp = requests.post(url, headers={"X-Internal-Secret": secret}, timeout=180)
            if resp.ok:
                return "ok"
            if resp.status_code not in (502, 503, 504):
                return f"HTTP {resp.status_code}"
        except requests.RequestException as e:
            last = f"ERR {e}"
        time.sleep(2**attempt)
    return "fail"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--copy-media", action="store_true")
    ap.add_argument("--created-by-id", type=int, default=1)
    args = ap.parse_args()

    client = ResearchApiClient()
    staging = _RESEARCH / "staging" / "robots" / COMPANY_SLUG
    staging.mkdir(parents=True, exist_ok=True)
    plan: dict[str, Any] = {"robots": []}

    # Also ensure FR country on all pending
    for rid in (2753, 2754, 2755, 2756, 2757, 2758):
        if args.apply:
            client._patch(
                f"robots/robots/{rid}/",
                {"manufacturer_countries": [FR], "manufacturer_country_ref": FR},
            )

    for spec in FIXES:
        images: list[str] = []
        seen: set[str] = set()
        for u in spec["images"]:
            ok, md5, n = download_ok(u)
            print(f"{spec['name']}: {'OK' if ok else 'FAIL'} {n} {md5[:12] if md5 else '-'} {u[-50:]}")
            if ok and md5 not in seen:
                seen.add(md5)
                images.append(u)
        plan["robots"].append({"id": spec["id"], "name": spec["name"], "images_n": len(images), "images": images})
        if not images:
            print(f"  !! no images for {spec['name']}")
            continue
        if not args.apply:
            continue
        row = {
            "id": spec["id"],
            "name": spec["name"],
            "company_slug": COMPANY_SLUG,
            "company_name": COMPANY_NAME,
            "manufacturer_country_code": "FR",
            "manufacturer_country_codes": "FR",
            "description": spec["description"],
            "purpose": spec["purpose"],
            "features": spec["features"],
            "category_slugs": spec.get("category_slugs") or "",
            "use_keys": spec.get("use_keys") or "",
            "movement_type_keys": spec.get("movement_type_keys") or "",
            "url": spec["url"],
            "image": images[0],
            "images": images,
            "source_locale": "en",
            "notes": (
                "[AI Research] Exail media fix 2026-07-19: replaced shared UGV family banner / "
                "wrong UlyX header with model-named OEM assets. FR country set."
            ),
            "sources": [{"url": spec["url"], "type": "website", "title": spec["name"]}],
            "information_source_urls": [spec["url"]],
        }
        path = staging / f"{spec['id']}-{spec['name'].lower().replace(' ', '-')[:40]}.json"
        path.write_text(json.dumps(row, indent=2), encoding="utf-8")
        result = import_staging(
            path,
            dry_run=False,
            patch=True,
            force_overwrite=True,
            replace_media=True,
            status="pending_review",
            created_by_id=resolve_created_by_id(args.created_by_id),
            skip_company_update=True,
        )
        print("import", spec["name"], result)
        if args.copy_media:
            print("copy-media", spec["id"], copy_media(int(spec["id"])))

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    print("Report", REPORT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
