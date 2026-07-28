#!/usr/bin/env python3
"""Download heroes for visual QA: Noblelift shared clusters + RobCo fleet."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient

c = ResearchApiClient()
SESSION = requests.Session()


def save(company: int, rid: int, name: str, url: str, sub: str = "") -> str:
    b = SESSION.get(url, timeout=60).content
    md5 = hashlib.md5(b).hexdigest()
    ext = (
        "png"
        if b.startswith(b"\x89PNG")
        else ("jpg" if b.startswith(b"\xff\xd8") else ("webp" if b[:4] == b"RIFF" else "bin"))
    )
    d = Path(f"staging/fleet_media_qa/{company}")
    d.mkdir(parents=True, exist_ok=True)
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in (name or "")[:40])
    path = d / f"{rid}_{md5[:12]}_{safe}.{ext}"
    path.write_bytes(b)
    print(f"{company}/{rid} {name[:40]} md5={md5[:12]} bytes={len(b)} {sub}")
    return md5


# Noblelift: one representative per shared cluster + suspicious siblings
nl_ids = [
    3354, 3358, 3362, 3369, 3365, 3336, 2210, 3335, 2214, 3332, 3368, 3352, 3353,
    3378, 3379, 3187, 3372, 3377,  # previously wrong-hero / repaired set
]
print("=== Noblelift sample ===")
for rid in nl_ids:
    r = c._get(f"robots/robots/{rid}/")
    u = (r.get("s3_image") or r.get("image") or "").strip()
    save(1028, rid, r.get("name") or "", u)

# RobCo: all published
print("=== RobCo all ===")
robots = c.list_robots_for_company(239)
for lite in robots:
    if str(lite.get("status") or "").lower() not in ("published", "approved"):
        continue
    rid = int(lite["id"])
    r = c._get(f"robots/robots/{rid}/")
    u = (r.get("s3_image") or r.get("image") or "").strip()
    save(239, rid, r.get("name") or "", u, sub=(r.get("url") or "")[:50])

print("done")
