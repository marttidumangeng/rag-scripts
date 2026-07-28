"""Download Universal Robots hero candidates for visual QA."""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import requests

_RESEARCH_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH_DIR))

from load_env import load_research_env

load_research_env()

from api_client import ResearchApiClient
from fix_universal_robots import HERO_OVERRIDE

OUT = _RESEARCH_DIR / "staging" / "ur_heroes"
OUT.mkdir(parents=True, exist_ok=True)

KEEP_IDS = {2524, 2525, 2534, 2535, 3302, 3303, 3542}


def main() -> None:
    for model, url in HERO_OVERRIDE.items():
        r = requests.get(url, timeout=90)
        data = r.content
        h = hashlib.md5(data).hexdigest()
        ext = "png" if data[:8] == b"\x89PNG\r\n\x1a\n" else "jpg"
        name = model.replace(" ", "_")
        p = OUT / f"{name}.{ext}"
        p.write_bytes(data)
        print(f"OVERRIDE {model}: HTTP {r.status_code} bytes={len(data)} md5={h} -> {p.name}")

    client = ResearchApiClient()
    robots = client.list_robots_for_company(192)
    for r in robots:
        rid = int(r["id"])
        if rid not in KEEP_IDS:
            continue
        img = (r.get("image") or r.get("s3_image") or "").strip()
        print(f"KEEP {rid} {r.get('name')!r} img={(img[:90] if img else None)}")
        if not img:
            continue
        try:
            resp = requests.get(img, timeout=90)
            data = resp.content
            h = hashlib.md5(data).hexdigest()
            ext = "webp" if data[:4] == b"RIFF" else ("png" if data[:8] == b"\x89PNG\r\n\x1a\n" else "bin")
            p = OUT / f"keep_{rid}.{ext}"
            p.write_bytes(data)
            print(f"  saved {p.name} HTTP {resp.status_code} bytes={len(data)} md5={h}")
        except Exception as e:  # noqa: BLE001
            print(f"  FAIL download: {e}")


if __name__ == "__main__":
    main()
