#!/usr/bin/env python3
"""Quick Realman OEM probe: gallery count, price/year mentions on sample PDPs."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient

SESS = requests.Session()
SESS.headers["User-Agent"] = "Mozilla/5.0 (compatible; RobotAIGeek-ResearchAgent/1.0)"


def main() -> int:
    client = ResearchApiClient()
    data = client._get(
        "robots/robots/",
        params={"company_ref": 882, "status": "pending_review", "page_size": 50},
    )
    samples = []
    for r in (data.get("results") or [])[:8]:
        url = (r.get("url") or "").strip()
        if not url:
            continue
        try:
            html = SESS.get(url, timeout=40).text
        except Exception as e:
            samples.append({"id": r["id"], "url": url, "error": str(e)})
            continue
        imgs = re.findall(
            r'(?:src|data-src|href)=["\']([^"\']+\.(?:png|jpe?g|webp))["\']',
            html,
            re.I,
        )
        oem_imgs = [
            u
            for u in imgs
            if "realman" in u.lower()
            or "/prop/" in u.lower()
            or "upload" in u.lower()
            or u.startswith("http")
        ]
        # unique basenames
        bases = []
        for u in oem_imgs:
            b = u.split("?")[0].rsplit("/", 1)[-1]
            if b not in bases and len(b) > 4:
                bases.append(b)
        price_hits = re.findall(
            r"(?i)(\$|USD|EUR|RMB|¥|price|MSRP|报价|售价)[^\n]{0,40}", html
        )[:8]
        year_hits = re.findall(
            r"(?i)(20(?:1[5-9]|2[0-6])|release|launch|debut|发布|上市)[^\n]{0,30}",
            html,
        )[:10]
        samples.append(
            {
                "id": r["id"],
                "name": r.get("name"),
                "url": url,
                "unique_img_basenames": len(bases),
                "sample_imgs": bases[:8],
                "price_hits": price_hits,
                "year_hits": year_hits,
            }
        )
        print(
            f"{r['id']} {r.get('name')}: imgs~{len(bases)} "
            f"price_hits={len(price_hits)} year_hits={len(year_hits)}"
        )

    Path("staging/reports/_realman_oem_softwarn_probe.json").write_text(
        json.dumps(samples, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
