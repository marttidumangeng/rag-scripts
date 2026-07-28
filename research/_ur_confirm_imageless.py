"""Confirm notes + CDN for previously imageless UR rows."""
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

OUT = _RESEARCH_DIR / "staging" / "ur_heroes" / "chase" / "cdn_after"
OUT.mkdir(parents=True, exist_ok=True)
IDS = (2535, 3543, 3544, 4882, 4883)


def main() -> None:
    client = ResearchApiClient()
    for rid in IDS:
        r = client._get(f"robots/robots/{rid}/")
        img = (r.get("image") or r.get("s3_image") or "").strip()
        notes = r.get("notes") or ""
        print(
            f"{rid} {r.get('name')!r} todo={'IMAGE TO-DO' in notes} "
            f"img={img[:90]}"
        )
        if not img:
            continue
        data = requests.get(img, timeout=90).content
        print(f"  bytes={len(data)} md5={hashlib.md5(data).hexdigest()}")
        Image.open(BytesIO(data)).convert("RGB").save(OUT / f"{rid}.png")


if __name__ == "__main__":
    main()
