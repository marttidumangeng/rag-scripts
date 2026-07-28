"""Download one post-apply CDN hero for visual QA."""
from __future__ import annotations

import hashlib
import sys
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image

_RESEARCH_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH_DIR))

from load_env import load_research_env

load_research_env()

from api_client import ResearchApiClient

OUT = _RESEARCH_DIR / "staging" / "ur_heroes"
OUT.mkdir(parents=True, exist_ok=True)


def main() -> None:
    client = ResearchApiClient()
    for rid in (2524, 2534, 3302):
        full = client._get(f"robots/robots/{rid}/")
        url = (full.get("image") or full.get("s3_image") or "").strip()
        print(f"{rid} {full.get('name')!r} {url}")
        if not url:
            continue
        r = requests.get(url, timeout=90)
        data = r.content
        h = hashlib.md5(data).hexdigest()
        im = Image.open(BytesIO(data))
        dest = OUT / f"cdn_{rid}_after.png"
        im.convert("RGB").save(dest)
        print(f"  HTTP {r.status_code} bytes={len(data)} md5={h} size={im.size} -> {dest.name}")


if __name__ == "__main__":
    main()
