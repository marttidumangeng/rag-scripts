"""Copy the 14 FlexQube AGV drafts' gallery photos into our own storage.

The import attaches photos by source URL; `gallery_not_uploaded` stays flagged
until the content-queue copy-media endpoint localizes them to the CDN.
"""
import os
import sys
import time
from pathlib import Path

import requests

from api_client import ResearchApiClient

SERVER = Path(__file__).resolve().parents[2] / "robotaigeek-server"
IDS = [7276, 7277, 7278, 7279, 7280, 7281, 7282, 7283, 7284, 7285, 7286, 7287, 7288, 7289]


def secret() -> str:
    s = os.environ.get("INTERNAL_API_SECRET", "").strip()
    if not s and (SERVER / ".env").is_file():
        for line in (SERVER / ".env").read_text(encoding="utf-8").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                s = line.split("=", 1)[1].strip()
                break
    return s


def copy_media(rid: int, sec: str) -> tuple[int, str]:
    url = (f"https://ragadmin.robotaigeek.com/admin/robots/robot/"
           f"content-queue/api/robot/{rid}/copy-media/?force=1")
    r = requests.post(url, headers={"X-Internal-Secret": sec}, timeout=300)
    return r.status_code, (r.text or "")[:200]


def main() -> int:
    sec = secret()
    if not sec:
        print("no INTERNAL_API_SECRET")
        return 1
    c = ResearchApiClient()
    for rid in IDS:
        code, body = copy_media(rid, sec)
        print(f"copy-media {rid}: {code} {body}", flush=True)
        time.sleep(2)

    print("\n-- landed check --", flush=True)
    for rid in IDS:
        for a in range(6):
            try:
                r = c._get(f"robots/robots/{rid}/")
                break
            except Exception:
                time.sleep(3 * (a + 1))
        photos = r.get("photos") or []
        localized = sum(1 for p in photos if (p.get("s3_image") or p.get("image_url", "")).startswith("https://cdn.robotaigeek.com"))
        flags = [f["flag"] for f in (r.get("quality_flags") or [])]
        print(f"  {rid} {r.get('name'):32s} photos={len(photos):2d} onCDN={localized:2d} "
              f"hero={'yes' if r.get('image_url') else 'NO'} flags={flags}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
