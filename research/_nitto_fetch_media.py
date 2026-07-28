"""Fetch Nitto Seiko America product heroes and copy-media."""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

import requests

_RESEARCH = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient
from import_staging import import_staging, resolve_created_by_id
import json
import os

UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
}
SERVER = _RESEARCH.parents[1] / "robotaigeek-server"

PRODUCTS = [
    (4239, "https://nittoseikoamerica.com/Product/Detail/SR375YO", "sr375"),
    (3183, "https://nittoseikoamerica.com/Product/Detail/SR565YOZ", "sr580"),
    (3184, "https://nittoseikoamerica.com/Product/Detail/SR565YOZ-V", "sr580v"),
    (3185, "https://nittoseikoamerica.com/Product/Detail/SR765YO", "sr780"),
    (2204, "https://nittoseikoamerica.com/Product/Detail/1100", "pd400"),
]


def copy_media(rid: int) -> str:
    secret = os.environ.get("INTERNAL_API_SECRET", "").strip()
    if not secret and (SERVER / ".env").is_file():
        for line in (SERVER / ".env").read_text(encoding="utf-8").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                secret = line.split("=", 1)[1].strip()
                break
    api = "https://ragadmin.robotaigeek.com"
    url = f"{api}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/?force=1"
    resp = requests.post(url, headers={"X-Internal-Secret": secret}, timeout=180)
    return f"{resp.status_code} {(resp.text or '')[:100]}"


def main() -> int:
    client = ResearchApiClient()
    staging = _RESEARCH / "staging" / "robots" / "nitto-seiko"
    staging.mkdir(parents=True, exist_ok=True)
    for rid, url, slug in PRODUCTS:
        r = requests.get(url, headers=UA, timeout=45)
        print(rid, r.status_code, len(r.text))
        imgs = re.findall(r'src=["\']([^"\']+\.(?:jpg|jpeg|png|webp)[^"\']*)', r.text, re.I)
        # also relative /uploads/
        cand = []
        for i in imgs:
            if i.startswith("/"):
                i = "https://nittoseikoamerica.com" + i
            low = i.lower()
            if any(x in low for x in ("logo", "icon", "favicon", "sprite")):
                continue
            cand.append(i)
        print("  cands", cand[:5])
        if not cand:
            continue
        hero = cand[0]
        existing = client._get(f"robots/robots/{rid}/")
        row = {
            "id": rid,
            "name": existing.get("name"),
            "company_slug": "nitto-seiko-america",
            "image": hero,
            "images": [hero],
            "url": url,
        }
        path = staging / f"{slug}-media.json"
        path.write_text(json.dumps(row, indent=2), encoding="utf-8")
        print(
            "import",
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
        print("copy-media", copy_media(rid))
        time.sleep(0.5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
