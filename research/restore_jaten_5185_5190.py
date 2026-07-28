"""Restore Jaten 5185 + 5190: hero-swap 5190, soft-fill, publish.

Keep *-335-MG0 phantoms rejected (2912, 5186-5189).
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import requests

_RESEARCH = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from api_client import ResearchApiClient
from load_env import load_research_env
from moderate_robots import apply_publish

load_research_env()

COMPANY_ID = 1461
RID_5185 = 5185  # SDM300-339-MGD — CDN hero OK
RID_5190 = 5190  # MN30-164 — promote gallery photo
# Good gallery photo (black-bg product render ~1MB)
HERO_5190 = "https://cdn.robotaigeek.com/robots/photos/photo-5190-16991-v1784010193.png"
GALLERY_5190 = [
    HERO_5190,
    "https://cdn.robotaigeek.com/robots/photos/photo-5190-16990-v1784010192.jpg",
]
REPORT = _RESEARCH / "staging" / "reports" / "jaten-restore-5185-5190.json"
SERVER = _RESEARCH.parents[1] / "robotaigeek-server"


def _internal_secret() -> str:
    secret = os.environ.get("INTERNAL_API_SECRET", "").strip()
    if secret:
        return secret
    env = SERVER / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                return line.split("=", 1)[1].strip()
    return ""


def copy_media(rid: int) -> dict:
    secret = _internal_secret()
    api = (
        os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/").replace("/api/v1", "")
        or "https://ragadmin.robotaigeek.com"
    )
    url = f"{api}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/?force=1"
    resp = requests.post(url, headers={"X-Internal-Secret": secret}, timeout=180)
    return {"status": resp.status_code, "body": (resp.text or "")[:200]}


def main() -> int:
    apply = "--apply" in sys.argv
    c = ResearchApiClient()

    d5185 = c._get(f"robots/robots/{RID_5185}/")
    d5190 = c._get(f"robots/robots/{RID_5190}/")
    sib = c._get("robots/robots/2914/")  # published MN100-164

    china_id = 3
    # Prefer sibling country list if present
    countries = sib.get("manufacturer_countries") or [china_id]
    if isinstance(countries, list) and countries and isinstance(countries[0], dict):
        countries = [x.get("id") or china_id for x in countries]

    plan = {
        "5185": {
            "id": RID_5185,
            "name": d5185.get("name"),
            "status": d5185.get("status"),
            "image": (d5185.get("s3_image") or d5185.get("image") or "")[:100],
            "countries": bool(d5185.get("manufacturer_countries")),
            "family_key": d5185.get("family_key"),
            "purpose": (d5185.get("purpose") or "")[:100],
        },
        "5190": {
            "id": RID_5190,
            "name": d5190.get("name"),
            "status": d5190.get("status"),
            "image": (d5190.get("s3_image") or d5190.get("image") or "")[:100],
            "new_hero": HERO_5190,
            "countries": bool(d5190.get("manufacturer_countries")),
            "family_key": d5190.get("family_key"),
            "purpose": (d5190.get("purpose") or "")[:100],
        },
    }
    print(json.dumps(plan, indent=2, ensure_ascii=False))

    if not apply:
        print("dry-run; pass --apply")
        REPORT.write_text(json.dumps({"dry_run": True, "plan": plan}, indent=2), encoding="utf-8")
        return 0

    # --- 5190 hero swap + soft fill ---
    print("PATCH 5190 hero + soft…")
    c._patch(
        f"robots/robots/{RID_5190}/",
        {
            "image": HERO_5190,
            "images": GALLERY_5190,
            "manufacturer_country_ref": china_id,
            "manufacturer_countries": countries,
            "availability_status": 11,  # Available
            "family_key": "jaten:mn",
            "family_name": "MN series",
            "family_url": "https://jaten-robotics.com/",
            "model_name": "MN30-164",
            "variant_code": "MN30-164",
            "product_url_scope": "exact_variant",
            "purpose": "Light indoor material transport",
            "notes": (
                "[AI Research] Jaten restore 2026-07-20: promoted gallery product "
                "render to primary (tiny 6.7KB hero was insufficient); China; "
                "family jaten:mn; Available; restored from soft reject."
            ),
        },
    )
    # Prefer replace_media via bulk so photo rows refresh
    print("bulk_import replace_media 5190…")
    c.bulk_import_robots(
        [
            {
                "id": RID_5190,
                "name": d5190.get("name") or "MN30-164",
                "company_id": COMPANY_ID,
                "image": HERO_5190,
                "images": GALLERY_5190,
            }
        ],
        patch_existing=True,
        replace_media=True,
    )
    cm5190 = copy_media(RID_5190)
    print("copy-media 5190", cm5190)

    # --- 5185 soft fill (hero already good) ---
    print("PATCH 5185 soft…")
    c._patch(
        f"robots/robots/{RID_5185}/",
        {
            "manufacturer_country_ref": china_id,
            "manufacturer_countries": countries,
            "availability_status": 11,
            "family_key": "jaten:sdm300",
            "family_name": "SDM300",
            "family_url": "https://jaten-robotics.com/",
            "model_name": "SDM300-339-MGD",
            "variant_code": "SDM300-339-MGD",
            "product_url_scope": "exact_variant",
            "purpose": "Automated material lifting and transport",
            "notes": (
                "[AI Research] Jaten restore 2026-07-20: CDN hero OK; China; "
                "family jaten:sdm300; Available; restored from soft reject "
                "(Purpose not relevant)."
            ),
        },
    )

    # Verify heroes before publish
    for rid in (RID_5190, RID_5185):
        d = c._get(f"robots/robots/{rid}/")
        img = d.get("s3_image") or d.get("image") or ""
        code = size = None
        if img:
            r = requests.get(img, timeout=30)
            code, size = r.status_code, len(r.content)
        print(f"verify {rid}: status={d.get('status')} http={code} bytes={size} img={img[:90]}")

    print("publish…")
    results = apply_publish([RID_5185, RID_5190])
    time.sleep(1)
    final = {}
    for rid in (RID_5185, RID_5190):
        d = c._get(f"robots/robots/{rid}/")
        final[rid] = {
            "status": d.get("status"),
            "rejection_reason": d.get("rejection_reason"),
            "image": (d.get("s3_image") or d.get("image") or "")[:110],
            "countries": bool(d.get("manufacturer_countries")),
            "family_key": d.get("family_key"),
            "purpose": d.get("purpose"),
        }
        print(f"final {rid}: {final[rid]['status']} fam={final[rid]['family_key']}")

    out = {
        "copy_media_5190": cm5190,
        "publish": results,
        "final": final,
    }
    REPORT.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print("wrote", REPORT)
    return 0 if all(x.get("ok") for x in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
