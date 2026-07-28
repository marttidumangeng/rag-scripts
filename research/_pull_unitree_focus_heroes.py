#!/usr/bin/env python3
"""Pull Unitree heroes that share suspicious hashes for visual QA."""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import requests

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient

QA = Path("staging/unitree_fleet_qa")
QA.mkdir(parents=True, exist_ok=True)

# Focus on contamination clusters from fleet audit
FOCUS_NAMES = (
    "Go2-W",
    "A2",
    "A2-W",
    "As2 EDU",
    "Go2 EDU",
    "Aliengo",
    "R1-A7",
    "R1-A5",
)


def main() -> int:
    c = ResearchApiClient()
    robots = c.list_robots_for_company(109)
    for r in robots:
        name = r.get("name") or ""
        if not any(x.lower() in name.lower() for x in FOCUS_NAMES):
            continue
        rid = int(r["id"])
        d = c._get(f"robots/robots/{rid}/")
        u = (d.get("s3_image") or d.get("image") or "").strip()
        if not u:
            print(rid, name, "NO HERO")
            continue
        b = requests.get(u, timeout=60).content
        md5 = hashlib.md5(b).hexdigest()
        if b.startswith(b"\x89PNG"):
            ext = "png"
        elif b.startswith(b"\xff\xd8"):
            ext = "jpg"
        elif b[:4] == b"RIFF":
            ext = "webp"
        else:
            ext = "bin"
        path = QA / f"{rid}_{md5[:12]}.{ext}"
        path.write_bytes(b)
        print(f"{rid} {name} md5={md5[:12]} bytes={len(b)} -> {path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
