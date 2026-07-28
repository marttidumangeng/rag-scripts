"""Probe Piaggio company fields + Storyblok product images."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import requests

_RESEARCH = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient

UA = {"User-Agent": "Mozilla/5.0"}


def main() -> int:
    client = ResearchApiClient()
    r = client._get("robots/robots/3767/")
    print("company keys sample:")
    for k in sorted(r.keys()):
        if "compan" in k.lower() or "slug" in k.lower():
            print(" ", k, ":", json.dumps(r.get(k), ensure_ascii=False)[:200])

    # published sibling search via moderate report pattern — list by status
    # Try company filter variants
    for params in (
        {"company_id": 236, "page_size": 30},
        {"company": 236, "page_size": 30},
        {"search": "gita", "page_size": 30},
    ):
        data = client._get("robots/robots/", params=params)
        rows = data.get("results") if isinstance(data, dict) else data
        print("params", params, "n", len(rows or []))
        for row in (rows or [])[:15]:
            if "gita" in (row.get("name") or "").lower() or row.get("id") in (3767, 3765):
                print(
                    " ",
                    row.get("id"),
                    row.get("name"),
                    row.get("status"),
                    (row.get("company") or {}),
                )

    home = requests.get("https://piaggiofastforward.com/", headers=UA, timeout=40).text
    imgs = sorted(
        set(
            re.findall(
                r"https://a\.storyblok\.com/f/\d+/[^\"'\s>]+\.(?:jpg|jpeg|png|webp)",
                home,
                flags=re.I,
            )
        )
    )
    print("storyblok home", len(imgs))
    for u in imgs:
        print(u)

    # Try Shopify CDN from page JSON
    for pat in (
        r"cdn\.shopify\.com[^\"'\s]+",
        r"https://[^\"'\s]+gita[^\"'\s]+\.(?:jpg|jpeg|png|webp)",
    ):
        hits = sorted(set(re.findall(pat, home, flags=re.I)))
        print("pat", pat, len(hits))
        for h in hits[:20]:
            print(" ", h[:160])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
