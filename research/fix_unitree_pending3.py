#!/usr/bin/env python3
"""Fix Unitree pending 3: fill manufacturer_countries, spot-check, approve."""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path

import requests

_RESEARCH_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH_DIR))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient

IDS = [5362, 5355, 5353]
CHINA_ID = 3
QA = _RESEARCH_DIR / "staging" / "unitree_pending_qa"
REPORT = _RESEARCH_DIR / "staging" / "reports" / "unitree-109-pending3-fix.json"


def _admin_base() -> str:
    return (
        os.environ.get("IMPORT_SYNC_API_BASE_URL", "")
        .rstrip("/")
        .replace("/api/v1", "")
    )


def _session_headers() -> dict[str, str] | None:
    sid = os.environ.get("ADMIN_SESSION_ID", "").strip()
    if not sid:
        return None
    return {"Cookie": f"sessionid={sid}", "Content-Type": "application/json"}


def approve(rid: int) -> dict:
    headers = _session_headers()
    if not headers:
        return {"ok": False, "error": "no ADMIN_SESSION_ID"}
    url = f"{_admin_base()}/admin/robots/robot/content-queue/api/robot/{rid}/approve/"
    r = requests.post(url, headers=headers, json={"type": "robot"}, timeout=120)
    try:
        body = r.json()
    except Exception:
        body = {"raw": r.text[:200]}
    return {"http": r.status_code, **(body if isinstance(body, dict) else {"body": body})}


def save_hero(rid: int, url: str) -> dict:
    QA.mkdir(parents=True, exist_ok=True)
    b = requests.get(url, timeout=60).content
    md5 = hashlib.md5(b).hexdigest()
    if b.startswith(b"\x89PNG"):
        ext = "png"
    elif b.startswith(b"\xff\xd8"):
        ext = "jpg"
    elif b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        ext = "webp"
    else:
        ext = "bin"
    path = QA / f"{rid}_{md5[:12]}.{ext}"
    path.write_bytes(b)
    return {"md5": md5, "bytes": len(b), "ext": ext, "path": str(path)}


def main() -> int:
    apply = "--apply" in sys.argv
    client = ResearchApiClient()
    plan = []
    for rid in IDS:
        r = client._get(f"robots/robots/{rid}/")
        hero = (r.get("s3_image") or r.get("image") or "").strip()
        hero_meta = save_hero(rid, hero) if hero else {}
        entry = {
            "id": rid,
            "name": r.get("name"),
            "status": r.get("status"),
            "url": r.get("url"),
            "mc_ref": r.get("manufacturer_country_ref"),
            "mcs": r.get("manufacturer_countries"),
            "features_len": len(r.get("features") or ""),
            "n_photos": len(r.get("photos") or []),
            "n_videos": len(r.get("videos") or []),
            "hero": hero_meta,
            "patch": {"manufacturer_countries": [CHINA_ID]},
        }
        plan.append(entry)
        print(
            f"{rid} {r.get('name')}: mcs={entry['mcs']} hero={hero_meta.get('ext')}/"
            f"{hero_meta.get('bytes')} vids={entry['n_videos']}"
        )

    REPORT.write_text(json.dumps({"plan": plan}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not apply:
        print("dry-run; pass --apply to patch countries + approve")
        return 0

    for entry in plan:
        rid = entry["id"]
        if str(entry.get("status") or "").lower() != "pending_review":
            print(f"SKIP {rid}: status={entry.get('status')}")
            continue
        client._patch(f"robots/robots/{rid}/", entry["patch"])
        print(f"patched countries {rid}")
        time.sleep(0.2)

    # Approve
    results = []
    for entry in plan:
        rid = entry["id"]
        res = approve(rid)
        print(f"approve {rid}: {res}")
        results.append({"id": rid, **res})
        time.sleep(0.3)

    # Verify status
    for rid in IDS:
        r = client._get(f"robots/robots/{rid}/")
        print(f"verify {rid}: status={r.get('status')} mcs={r.get('manufacturer_countries')}")

    REPORT.write_text(
        json.dumps({"plan": plan, "approve": results}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    fail = sum(1 for x in results if x.get("http") not in (200, 201) and not x.get("success"))
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
