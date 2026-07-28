"""Debug Auris 5197 PATCH 400 + retry Geek+ 4869/4865 heroes."""
from __future__ import annotations

import os
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

SERVER = _RESEARCH.parent.parent / "robotaigeek-server"
AVAILABLE = 11
US = 20


def copy_media(rid: int) -> tuple[int, str]:
    secret = os.environ.get("INTERNAL_API_SECRET", "").strip()
    if not secret and (SERVER / ".env").is_file():
        for line in (SERVER / ".env").read_text(encoding="utf-8").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                secret = line.split("=", 1)[1].strip()
                break
    url = f"https://ragadmin.robotaigeek.com/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/?force=1"
    resp = requests.post(url, headers={"X-Internal-Secret": secret}, timeout=120)
    return resp.status_code, (resp.text or "")[:300]


def try_patch(c: ResearchApiClient, rid: int, body: dict) -> None:
    url = c._url(f"robots/robots/{rid}/")
    resp = c._session.patch(url, json=body, timeout=60)
    print(f"  {list(body.keys())} -> {resp.status_code} {(resp.text or '')[:300]}")


def main() -> int:
    c = ResearchApiClient()
    print("Auris field probes")
    try_patch(c, 5197, {"purpose": "Robotic bronchoscopy navigation"})
    try_patch(c, 5197, {"availability_status": AVAILABLE})
    try_patch(c, 5197, {"family_key": "auris-health:monarch-quest", "family_name": "MONARCH QUEST", "family_url": "https://www.jnjmedtech.com/en-US/products/robotics/monarch-platform/bronchoscopy/", "model_name": "MONARCH QUEST", "product_url_scope": "exact_variant"})
    try_patch(c, 5197, {"manufacturer_countries": [US]})
    try_patch(c, 5197, {"uses": [23, 26]})  # surgery, medical-assistance
    try_patch(c, 5197, {"industries": [23]})  # other
    try_patch(c, 5197, {"movement_types": [19, 10]})  # fixed, stationary

    d = c._get("robots/robots/5197/")
    print("after", d.get("family_key"), "uses", d.get("uses"), "purpose", (d.get("purpose") or "")[:80])

    # Geek+ stubborn heroes — clear gallery junk then set primary
    for rid, hero in [
        (4869, "https://www.geekplus.com/hubfs/NEW%20WEBSITE/TECHNOLOGY/335x184px-X1200%201.png"),
        (4865, "https://www.geekplus.com/hs-fs/hubfs/Geek+2025/products/p-series/P800R%20V6%2045-img.png?width=800&name=P800R%20V6%2045-img.png"),
    ]:
        print("retry", rid)
        c._patch(f"robots/robots/{rid}/", {"image": hero, "s3_image": None})
        code, text = copy_media(rid)
        print(code, text)
        d = c._get(f"robots/robots/{rid}/")
        print("  img", (d.get("s3_image") or d.get("image") or "")[:100])
        time.sleep(0.3)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
