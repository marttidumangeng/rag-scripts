#!/usr/bin/env python3
"""Inspect Go2-W (644) gallery for a correct wheeled hero candidate."""
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


def main() -> int:
    c = ResearchApiClient()
    r = c._get("robots/robots/644/")
    print("hero", (r.get("s3_image") or r.get("image") or "")[:100])
    print("url", r.get("url"))
    for p in r.get("photos") or []:
        u = (p.get("s3_image") or p.get("url") or "").strip()
        if not u:
            continue
        try:
            b = requests.get(u, timeout=60).content
        except Exception as e:
            print("fail", p.get("id"), e)
            continue
        md5 = hashlib.md5(b).hexdigest()
        ext = "png" if b.startswith(b"\x89PNG") else (
            "jpg" if b.startswith(b"\xff\xd8") else ("webp" if b[:4] == b"RIFF" else "bin")
        )
        path = QA / f"go2w_photo_{p.get('id')}_{md5[:12]}.{ext}"
        path.write_bytes(b)
        print(
            f"photo {p.get('id')} status={p.get('status')} primary={p.get('is_primary')} "
            f"md5={md5[:12]} bytes={len(b)} -> {path.name}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
