#!/usr/bin/env python3
"""Apply verified Go2-W canyon hero (e3faa3edc876) to robot 644."""
from __future__ import annotations

import hashlib
import os
import re
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient
from import_staging import resolve_created_by_id
from map_to_bulk_import import staging_dict_to_bulk_import_row

TARGET_MD5 = "e3faa3edc876"
BAD = "e0b39e851afc"
RID = 644
UA = {"User-Agent": "Mozilla/5.0"}


def fetch(url: str) -> bytes:
    r = requests.get(url, headers=UA, timeout=60)
    r.raise_for_status()
    return r.content


def find_url() -> str:
    html = fetch("https://www.unitree.com/go2-w/").decode("utf-8", errors="ignore")
    urls = re.findall(r"https://[^\"'\s>]+\.(?:png|jpg|jpeg|webp)", html, re.I)
    for u in urls:
        if "unitree.com" not in u:
            continue
        try:
            b = fetch(u)
        except Exception:
            continue
        if hashlib.md5(b).hexdigest().startswith(TARGET_MD5):
            return u
    raise SystemExit("could not locate Go2-W hero URL")


def copy_media(rid: int) -> str:
    secret = os.environ.get("INTERNAL_API_SECRET", "").strip()
    if not secret:
        env = Path("../../robotaigeek-server/.env")
        if env.is_file():
            for line in env.read_text(encoding="utf-8").splitlines():
                if line.startswith("INTERNAL_API_SECRET="):
                    secret = line.split("=", 1)[1].strip()
    base = os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/").replace("/api/v1", "")
    url = f"{base}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/?force=1"
    r = requests.post(url, headers={"X-Internal-Secret": secret}, timeout=180)
    return "ok" if r.ok else f"HTTP {r.status_code}"


def main() -> int:
    hero = find_url()
    print("hero url", hero)
    c = ResearchApiClient()
    robot = c._get(f"robots/robots/{RID}/")
    row = staging_dict_to_bulk_import_row(
        {
            "id": RID,
            "name": robot.get("name"),
            "company_slug": "unitree-robotics",
            "image": hero,
            "images": [{"url": hero}],
            "research_notes": "Replaced A2 footed contamination with Go2-W OEM canyon wheeled hero (2026-07-19).",
            "source_locale": "en",
        }
    )
    row["id"] = RID
    print(
        "import",
        c.bulk_import_robots(
            [row],
            update_existing=True,
            patch_existing=True,
            replace_media=True,
            status="published",
            skip_company_update=True,
            created_by_id=resolve_created_by_id(1),
        ),
    )
    print("copy-media", copy_media(RID))
    time.sleep(0.5)
    d = c._get(f"robots/robots/{RID}/")
    u = (d.get("s3_image") or d.get("image") or "").strip()
    b = fetch(u)
    md5 = hashlib.md5(b).hexdigest()
    print("new", md5[:12], len(b), "ok", md5.startswith(TARGET_MD5), "not_a2", not md5.startswith(BAD))
    return 0 if md5.startswith(TARGET_MD5) else 1


if __name__ == "__main__":
    raise SystemExit(main())
