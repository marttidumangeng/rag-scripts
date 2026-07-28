"""Fix Nitto 3184/3185 heroes with working OEM product-*.jpg paths."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests

_RESEARCH = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient
from import_staging import import_staging, resolve_created_by_id

SERVER = _RESEARCH.parents[1] / "robotaigeek-server"
HEROES = {
    3184: "https://nittoseikoamerica.com/img/products/product-SR565YO.jpg",  # vision sibling share
    3185: "https://nittoseikoamerica.com/img/products/product-SR765YO.jpg",
}


def copy_media(rid: int) -> str:
    secret = os.environ.get("INTERNAL_API_SECRET", "").strip()
    if not secret and (SERVER / ".env").is_file():
        for line in (SERVER / ".env").read_text(encoding="utf-8").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                secret = line.split("=", 1)[1].strip()
                break
    url = f"https://ragadmin.robotaigeek.com/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/?force=1"
    resp = requests.post(url, headers={"X-Internal-Secret": secret}, timeout=180)
    return f"{resp.status_code} {(resp.text or '')[:120]}"


def main() -> int:
    c = ResearchApiClient()
    staging = _RESEARCH / "staging" / "robots" / "nitto-seiko"
    staging.mkdir(parents=True, exist_ok=True)
    for rid, hero in HEROES.items():
        ex = c._get(f"robots/robots/{rid}/")
        notes = (ex.get("notes") or "").replace("[IMAGE TO-DO]", "").replace("IMAGE TO-DO", "").strip()
        row = {
            "id": rid,
            "name": ex.get("name"),
            "company_slug": "nitto-seiko-america",
            "company_name": "Nitto Seiko America",
            "manufacturer_country_code": "US",
            "description": ex.get("description") or "Nitto Seiko screw driving robot.",
            "purpose": ex.get("purpose") or "Automated screw fastening",
            "features": ex.get("features") or "OEM Nitto Seiko America fastening robot.",
            "url": ex.get("url"),
            "image": hero,
            "images": [hero],
            "notes": notes or "[AI Research] Nitto hero restored 2026-07-20",
            "sources": [{"url": ex.get("url") or hero, "type": "website", "title": "OEM"}],
            "information_source_urls": [ex.get("url") or hero],
            "family_key": ex.get("family_key"),
            "family_name": ex.get("family_name"),
            "family_url": ex.get("family_url"),
        }
        path = staging / f"fix-hero-{rid}.json"
        path.write_text(json.dumps(row, indent=2, ensure_ascii=False), encoding="utf-8")
        print(
            rid,
            import_staging(
                path,
                dry_run=False,
                patch=True,
                force_overwrite=True,
                replace_media=True,
                status="pending_review",
                created_by_id=resolve_created_by_id(1),
                skip_company_update=True,
            ),
        )
        c._patch(f"robots/robots/{rid}/", {"notes": row["notes"]})
        print("  copy-media", copy_media(rid))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
