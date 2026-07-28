#!/usr/bin/env python3
"""Audit Unitree A2 vs A2-W heroes; fix A2 if it wrongly has wheeled render."""
from __future__ import annotations

import hashlib
import sys
import time
from pathlib import Path
from urllib.parse import quote

import requests

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient
from import_staging import resolve_created_by_id
from map_to_bulk_import import staging_dict_to_bulk_import_row

QA = Path("staging/unitree_pending_qa")


def main() -> int:
    apply = "--apply" in sys.argv
    c = ResearchApiClient()
    for rid in (5354, 5353):
        r = c._get(f"robots/robots/{rid}/")
        hero = (r.get("s3_image") or r.get("image") or "").strip()
        b = requests.get(hero, timeout=60).content
        md5 = hashlib.md5(b).hexdigest()
        QA.mkdir(parents=True, exist_ok=True)
        ext = "jpg" if b.startswith(b"\xff\xd8") else "png"
        (QA / f"a2_cmp_{rid}_{md5[:12]}.{ext}").write_bytes(b)
        print(rid, r.get("name"), r.get("url"), md5[:12], len(b))

    # OEM candidates for footed A2
    candidates = [
        "https://www.unitree.com/images/A2.png",
        "https://www.unitree.com/images/a2.png",
        "https://oss-global-cdn.unitree.com/static/a2/a2.png",
    ]
    # scrape A2 page for og:image / product imgs
    page = requests.get("https://www.unitree.com/A2", timeout=60, headers={"User-Agent": "Mozilla/5.0"})
    print("A2 page", page.status_code, len(page.text))
    import re

    imgs = re.findall(r"https://[^\"'\s>]+\.(?:png|jpg|jpeg|webp)", page.text, re.I)
    imgs = list(dict.fromkeys(imgs))[:30]
    print("page imgs", len(imgs))
    for u in imgs[:15]:
        print(" ", u[:100])

    # Also try known CDN patterns from prior unitree work
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
