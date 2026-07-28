"""PATCH Nitto image URLs then copy-media."""
from __future__ import annotations

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
    return f"{resp.status_code} {(resp.text or '')[:120]}"


def main() -> int:
    c = ResearchApiClient()
    for rid, hero in HEROES.items():
        # set image via import staging with full required fields from existing
        existing = c._get(f"robots/robots/{rid}/")
        # try direct photo endpoint or patch image field if supported
        try:
            c._patch(f"robots/robots/{rid}/", {"image": hero, "images": [hero]})
            print("patch image", rid, "ok")
        except Exception as e:
            print("patch image", rid, e)
        print("copy-media", rid, copy_media(rid))
        after = c._get(f"robots/robots/{rid}/")
        print("  now", (after.get("image") or after.get("s3_image") or "")[:90])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
