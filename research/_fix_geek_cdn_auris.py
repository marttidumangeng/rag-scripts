"""Fix Geek+ imageless heroes via content-queue copy-media + fix Auris 5197."""
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
from overnight_needs_cleanup_enrich import geek_hero, list_pending, soft_body, map_keys, taxonomy, patch_robot, US

SERVER = _RESEARCH.parent.parent / "robotaigeek-server"


def copy_media(rid: int) -> tuple[int, str]:
    secret = os.environ.get("INTERNAL_API_SECRET", "").strip()
    if not secret and (SERVER / ".env").is_file():
        for line in (SERVER / ".env").read_text(encoding="utf-8").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                secret = line.split("=", 1)[1].strip()
                break
    api = os.environ.get("RESEARCH_API_BASE") or "https://ragadmin.robotaigeek.com"
    # strip /api/v1 if present
    base = api.replace("/api/v1", "").rstrip("/")
    url = f"{base}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/?force=1"
    resp = requests.post(
        url,
        headers={"X-Internal-Secret": secret},
        timeout=120,
    )
    return resp.status_code, (resp.text or "")[:200]


def main() -> int:
    c = ResearchApiClient()
    tax = taxonomy(c)
    rows = list_pending(c, 1398)
    need = []
    for r in rows:
        detail = c._get(f"robots/robots/{r['id']}/")
        img = detail.get("s3_image") or detail.get("image") or ""
        owned = "cdn.robotaigeek.com" in str(img) or "robotaigeek" in str(img).lower() and "geekplus" not in str(img).lower()
        # treat hubspot / geekplus.com as not owned
        if "geekplus.com" in str(img) or "hubfs" in str(img) or not img:
            need.append(detail)
    print(f"Geek+ need CDN hero: {len(need)}")
    ok = 0
    for d in need:
        rid = int(d["id"])
        name = d.get("name") or ""
        hero = geek_hero(name)
        if not hero:
            print(f"  no hero map {rid} {name}")
            continue
        print(f"  set image {rid} {name[:40]}")
        c._patch(f"robots/robots/{rid}/", {"image": hero, "s3_image": None})
        code, text = copy_media(rid)
        print(f"  copy-media {rid}: {code} {text}")
        if code == 200:
            ok += 1
        time.sleep(0.2)
    print(f"copy-media ok {ok}/{len(need)}")

    # Auris 5197 — try minimal patch
    print("\nAuris 5197")
    try:
        body = soft_body(
            country=US,
            uses=map_keys(tax, "uses", "surgery|medical-assistance"),
            industries=map_keys(tax, "industries", "other"),
            movement=map_keys(tax, "movement", "stationary|fixed"),
            family_key="auris:monarch",
            family_name="MONARCH Platform",
            family_url="https://www.jnjmedtech.com/en-US/products/robotics/monarch-platform/bronchoscopy/",
            model_name="MONARCH QUEST",
            purpose="Robotic bronchoscopy navigation",
        )
        # try scalar only first
        scalar = {k: v for k, v in body.items() if k not in ("uses", "industries", "movement_types", "manufacturer_countries")}
        c._patch("robots/robots/5197/", scalar)
        print("  scalar ok")
        c._patch(
            "robots/robots/5197/",
            {
                "uses": body["uses"],
                "industries": body["industries"],
                "movement_types": body["movement_types"],
                "manufacturer_countries": body["manufacturer_countries"],
            },
        )
        print("  m2m ok")
        d = c._get("robots/robots/5197/")
        print("  fam", d.get("family_key"), "uses", len(d.get("uses") or []), "country", d.get("manufacturer_country_ref"))
    except Exception as exc:
        print("  fail", exc)
        # dump current
        d = c._get("robots/robots/5197/")
        print("  current keys sample", {k: d.get(k) for k in ("name", "family_key", "purpose", "availability_status", "manufacturer_country_ref")})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
