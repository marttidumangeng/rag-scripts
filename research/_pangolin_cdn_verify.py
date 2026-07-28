"""Retry copy-media for Pangolin hero targets; verify CDN."""
from __future__ import annotations

import hashlib
import sys
import time
from collections import defaultdict
from pathlib import Path

import requests

_RESEARCH_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH_DIR))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient
from fix_pangolin_robots import HERO, _admin_base, _internal_secret, copy_media

HERO_IDS = sorted(HERO.keys())


def main() -> None:
    client = ResearchApiClient()
    secret = _internal_secret()
    need_copy = []
    for rid in HERO_IDS:
        r = client._get(f"robots/robots/{rid}/")
        img = (r.get("image") or r.get("s3_image") or "").strip()
        on_cdn = "cdn.robotaigeek.com" in img or "cloudfront" in img.lower()
        print(f"{rid} cdn={on_cdn} img={img[:80]}")
        if not on_cdn:
            need_copy.append(rid)

    for rid in need_copy:
        cm = copy_media(rid, secret)
        print(f"retry copy {rid}: {cm}")
        time.sleep(0.3)

    # hash CDN heroes
    hashes: dict[str, list[int]] = defaultdict(list)
    bad = []
    for rid in HERO_IDS:
        r = client._get(f"robots/robots/{rid}/")
        img = (r.get("image") or r.get("s3_image") or "").strip()
        if not img:
            bad.append((rid, "empty"))
            continue
        try:
            data = requests.get(img, timeout=60).content
        except Exception as e:
            bad.append((rid, f"fetch {e}"))
            continue
        if len(data) < 5000 or (
            data[:3] != b"\xff\xd8\xff"
            and data[:8] != b"\x89PNG\r\n\x1a\n"
            and data[:4] != b"RIFF"
        ):
            # webp ok
            if data[:4] != b"RIFF" and data[8:12] != b"WEBP" and data[:4] != b"\x00\x00\x00":
                if not (data[:2] == b"\xff\xd8" or data[:8] == b"\x89PNG\r\n\x1a\n" or data[:4] == b"RIFF"):
                    bad.append((rid, f"not image bytes={len(data)}"))
                    continue
        md5 = hashlib.md5(data).hexdigest()
        hashes[md5].append(rid)
        print(f"OK {rid} bytes={len(data)} md5={md5[:12]} {img[:70]}")

    shared = {h: ids for h, ids in hashes.items() if len(ids) > 1}
    print(f"bad={bad}")
    print(f"shared_hashes={shared}")
    print(f"unique_ok={len(hashes)} robots={len(HERO_IDS)}")


if __name__ == "__main__":
    main()
