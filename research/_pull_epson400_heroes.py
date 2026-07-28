#!/usr/bin/env python3
"""Pull Epson 400 heroes for suspicious shared clusters + unique samples."""
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

QA = Path("staging/fleet_media_qa/400")
QA.mkdir(parents=True, exist_ok=True)

# One per shared cluster + a few uniques
IDS = [
    5111, 5139, 5144,  # C XL/LC cluster
    5115, 5136, 5137, 5140,  # C*B cluster (C4/C8/C12)
    3059, 5121,  # LS10-B
    5130, 5134,  # GX8
    3076, 5123,  # C8 / C8L
    5112, 5129,  # GX20 / GX10
]


def main() -> int:
    c = ResearchApiClient()
    for rid in IDS:
        r = c._get(f"robots/robots/{rid}/")
        u = (r.get("s3_image") or r.get("image") or "").strip()
        b = requests.get(u, timeout=60).content
        md5 = hashlib.md5(b).hexdigest()
        ext = (
            "png"
            if b.startswith(b"\x89PNG")
            else ("jpg" if b.startswith(b"\xff\xd8") else ("webp" if b[:4] == b"RIFF" else "bin"))
        )
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in (r.get("name") or "")[:36])
        (QA / f"{rid}_{md5[:12]}_{safe}.{ext}").write_bytes(b)
        print(f"{rid} {r.get('name')} md5={md5[:12]} bytes={len(b)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
