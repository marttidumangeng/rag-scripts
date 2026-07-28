#!/usr/bin/env python3
"""Replace wrong Niumowang F300 (2195) hero — was Medical list-card thumb."""

from __future__ import annotations

import hashlib
import sys
import time
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings()
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient
from fix_pangolin_robots import _internal_secret, copy_media

RID = 2195
HERO = (
    "https://www.alpha-robot.com.cn/public/uploads/images/20250815/"
    "9ddbecba5684601d2f8419b9066ae4d2.png"
)
EXPECT_MD5 = "6ce9fce4cd87"


def main() -> int:
    apply = "--apply" in sys.argv
    client = ResearchApiClient()
    print(f"set robot {RID} hero -> {HERO}")
    if not apply:
        print("dry-run; pass --apply")
        return 0

    client._patch(f"robots/robots/{RID}/", {"image": HERO, "images": [HERO]})
    print("ok patch")
    secret = _internal_secret()
    cm = copy_media(RID, secret)
    print("copy-media", cm)
    time.sleep(1.5)
    r = client._get(f"robots/robots/{RID}/")
    s3 = r.get("s3_image") or r.get("image") or ""
    print("s3_image", s3)
    if s3:
        body = requests.get(s3, timeout=30).content
        md5 = hashlib.md5(body).hexdigest()
        print("cdn_md5", md5[:12], "expect", EXPECT_MD5, "OK" if md5.startswith(EXPECT_MD5) else "MISS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
