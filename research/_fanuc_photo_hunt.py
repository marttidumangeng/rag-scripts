#!/usr/bin/env python3
"""Hunt OEM stills for FANUC CRX-30iA/L, CRX-20iA/L, M-800iA/60W, M-810iA/45."""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OUT = Path(__file__).resolve().parent / "staging" / "media" / "fanuc-photo-fix" / "candidates"
OUT.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (compatible; RobotAIGeekResearch/1.0)"}

PAGES = {
    "crx30": "https://crx.fanucamerica.com/crx-30ia",
    "crx30l": "https://crx.fanucamerica.com/crx-30ial",
    "crx20l": "https://crx.fanucamerica.com/crx-20ial",
    "crx20": "https://crx.fanucamerica.com/crx-20ia",
    "crx_series": "https://www.fanucamerica.com/products/robots/series/crx",
    "m800_60": "https://www.fanucamerica.com/products/robots/series/m-800-series/m-800ia-60",
    "m800": "https://www.fanucamerica.com/products/robots/series/m-800-series",
    "m800_eu": "https://www.fanuc.eu/eu-en/m-800-series",
    "m800_eu_prod": "https://www.fanuc.eu/eu-en/product/robot/m-800ia60",
    "m810": "https://www.fanucamerica.com/products/robots/series/m-810",
    "m810_prod": "https://www.fanucamerica.com/products/robot/m-810ia-45",
    "m810_eu": "https://www.fanuc.eu/eu-en/product/robot/m-810ia45",
    "eu_crx30": "https://www.fanuc.eu/eu-en/product/robot/crx-30ial",
    "eu_crx20": "https://www.fanuc.eu/eu-en/product/robot/crx-20ial",
}

SKIP = ("logo", "icon", "sprite", "favicon", "wistia", "youtube", "avatar", "flag", "cookie")
KEEP = ("crx", "m-800", "m800", "m-810", "m810", "robot", "cobot", "product", "assets", "craft")


def ext_for(data: bytes) -> str:
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:4] == b"RIFF":
        return ".webp"
    return ".bin"


def collect_urls(html: str) -> list[str]:
    found: list[str] = []
    for m in re.finditer(r"https?://[^\s\"'<>]+\.(?:jpg|jpeg|png|webp)", html, re.I):
        u = m.group(0).rstrip(").,;\"'").split("?")[0]
        if u not in found:
            found.append(u)
    return found


def main() -> None:
    for key, url in PAGES.items():
        try:
            r = requests.get(url, timeout=40, headers=UA)
        except requests.RequestException as e:
            print(key, "ERR", e)
            continue
        print(f"==== {key} {r.status_code} {r.url[:90]}")
        if r.status_code != 200:
            continue
        urls = collect_urls(r.text)
        keep = []
        for u in urls:
            ul = u.lower()
            if any(s in ul for s in SKIP):
                continue
            if any(k in ul for k in KEEP):
                keep.append(u)
        print(f"  candidates {len(keep)}")
        for i, u in enumerate(keep[:15]):
            print(f"  {i} {u[:130]}")
            try:
                ir = requests.get(u, timeout=30, headers=UA)
            except requests.RequestException as e:
                print("    fail", e)
                continue
            if ir.status_code != 200 or len(ir.content) < 5000:
                continue
            h = hashlib.md5(ir.content).hexdigest()[:8]
            fn = OUT / f"{key}_{i}_{h}{ext_for(ir.content)}"
            fn.write_bytes(ir.content)
            print(f"    saved {fn.name} {len(ir.content)}")


if __name__ == "__main__":
    main()
