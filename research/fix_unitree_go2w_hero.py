#!/usr/bin/env python3
"""Fix Unitree Go2-W (644) hero: was A2 footed studio (e0b39e851afc)."""
from __future__ import annotations

import hashlib
import json
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

QA = Path("staging/unitree_fleet_qa")
UA = {"User-Agent": "Mozilla/5.0 (compatible; RobotAIGeekResearch/1.0)"}
BAD = "e0b39e851afc"  # A2 footed studio — must not stay on Go2-W
RID = 644
REPORT = Path("staging/reports/unitree-109-go2w-fix.json")


def fetch(url: str) -> bytes:
    r = requests.get(url, headers=UA, timeout=60)
    r.raise_for_status()
    return r.content


def page_images(url: str) -> list[str]:
    html = fetch(url).decode("utf-8", errors="ignore")
    found = re.findall(r"https://[^\"'\s>]+\.(?:png|jpg|jpeg|webp)", html, re.I)
    out, seen = [], set()
    for u in found:
        if u in seen:
            continue
        seen.add(u)
        out.append(u)
    return out


def sniff_ok(body: bytes) -> bool:
    return body.startswith((b"\x89PNG", b"\xff\xd8")) or (
        body[:4] == b"RIFF" and body[8:12] == b"WEBP"
    )


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
    apply = "--apply" in sys.argv
    QA.mkdir(parents=True, exist_ok=True)
    c = ResearchApiClient()

    imgs = page_images("https://www.unitree.com/go2-w/")
    imgs += page_images("https://www.unitree.com/mobile/go2-w/")
    print(f"page imgs={len(imgs)}")

    vetted = []
    for u in imgs:
        if "unitree.com" not in u:
            continue
        try:
            body = fetch(u)
        except Exception:
            continue
        if not sniff_ok(body) or len(body) < 25000:
            continue
        md5 = hashlib.md5(body).hexdigest()
        if md5.startswith(BAD):
            continue
        ext = "png" if body.startswith(b"\x89PNG") else (
            "jpg" if body.startswith(b"\xff\xd8") else "webp"
        )
        path = QA / f"go2w_cand_{md5[:12]}.{ext}"
        path.write_bytes(body)
        vetted.append({"url": u, "md5": md5, "bytes": len(body), "path": str(path)})
        print(f"cand {md5[:12]} {len(body)} {u[:100]}")
        if len(vetted) >= 15:
            break

    # Prefer wheeled studio/product shots: larger files often better; exclude tiny icons
    vetted.sort(key=lambda x: -x["bytes"])
    chosen = vetted[0] if vetted else None
    print("chosen", chosen["url"] if chosen else None, (chosen or {}).get("md5", "")[:12])

    REPORT.write_text(
        json.dumps({"candidates": vetted[:10], "chosen": chosen}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    if not apply:
        print("dry-run; visually pick then --apply")
        return 0
    if not chosen:
        print("ERROR: no Go2-W candidate")
        return 1

    robot = c._get(f"robots/robots/{RID}/")
    row = staging_dict_to_bulk_import_row(
        {
            "id": RID,
            "name": robot.get("name"),
            "company_slug": "unitree-robotics",
            "image": chosen["url"],
            "images": [{"url": chosen["url"]}],
            "research_notes": "Replaced A2 footed studio contamination with Go2-W OEM hero (2026-07-19).",
            "source_locale": "en",
        }
    )
    row["id"] = RID
    res = c.bulk_import_robots(
        [row],
        update_existing=True,
        patch_existing=True,
        replace_media=True,
        status="published",
        skip_company_update=True,
        created_by_id=resolve_created_by_id(1),
    )
    print("import", res)
    print("copy-media", copy_media(RID))
    time.sleep(0.5)
    d = c._get(f"robots/robots/{RID}/")
    u = (d.get("s3_image") or d.get("image") or "").strip()
    body = fetch(u)
    md5 = hashlib.md5(body).hexdigest()
    print("new hero", md5[:12], len(body), "still_a2", md5.startswith(BAD))
    return 0 if not md5.startswith(BAD) else 1


if __name__ == "__main__":
    raise SystemExit(main())
