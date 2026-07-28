"""Re-import Nitto rows with OEM heroes + copy-media."""
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
    4239: "https://nittoseikoamerica.com/img/products/product-SR375YO.jpg",
    3183: "https://nittoseikoamerica.com/img/products/product-SR565YO.jpg",
    3184: "https://nittoseikoamerica.com/img/products/SR580_SD600T.jpg",
    3185: "https://nittoseikoamerica.com/img/products/SR765YO.jpg",
    2204: "https://nittoseikoamerica.com/img/products/1_PD400UR.800.jpg",
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
    return f"{resp.status_code} {(resp.text or '')[:140]}"


def main() -> int:
    c = ResearchApiClient()
    staging = _RESEARCH / "staging" / "robots" / "nitto-seiko"
    staging.mkdir(parents=True, exist_ok=True)
    for rid, hero in HEROES.items():
        ex = c._get(f"robots/robots/{rid}/")
        row = {
            "id": rid,
            "name": ex.get("name"),
            "company_slug": "nitto-seiko-america",
            "company_name": "Nitto Seiko America",
            "manufacturer_country_code": "US",
            "description": ex.get("description") or "Nitto Seiko America screw driving system.",
            "purpose": ex.get("purpose") or "Automated screw fastening",
            "features": ex.get("features") or "OEM Nitto Seiko America fastening robot.",
            "url": ex.get("url"),
            "image": hero,
            "images": [hero],
            "sources": [{"url": ex.get("url") or hero, "type": "website", "title": "OEM"}],
            "information_source_urls": [ex.get("url") or hero],
            "family_key": ex.get("family_key"),
            "family_name": ex.get("family_name"),
            "family_url": ex.get("family_url"),
        }
        path = staging / f"media-{rid}.json"
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
        print("  copy-media", copy_media(rid))
        after = c._get(f"robots/robots/{rid}/")
        print("  img", (after.get("image") or after.get("s3_image") or "")[:100])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
