"""Parse Pangolin PDP HTML for label→value specs; hash-dedupe gallery candidates."""
from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import requests
import urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_RESEARCH_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH_DIR))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from fix_pangolin_robots import HERO

SESS = requests.Session()
SESS.verify = False
SESS.headers["User-Agent"] = "Mozilla/5.0"
OUT = _RESEARCH_DIR / "staging" / "reports" / "pangolin-specs-gallery.json"

LABEL_MAP = {
    "外观尺寸": "dimensions",
    "整机重量": "weight",
    "重量": "weight",
    "移动速度": "speed",
    "速度": "speed",
    "最快速度": "speed",
    "最大平底速度": "speed",
    "续航时间": "runtime",
    "续航里程": "range",
    "充电时间": "charging",
    "最大载重": "payload",
    "最大载重（kg）": "payload",
    "货箱容量": "cargo_volume",
    "屏幕尺寸": "screen",
    "爬坡能力": "gradeability",
    "最大爬坡角度": "gradeability",
    "最大越障高度": "obstacle",
    "电池": "battery",
    "导航方式": "navigation",
}


def abs_url(u: str) -> str:
    if u.startswith("http"):
        return u
    return "https://www.alpha-robot.com.cn" + u


def parse_pairs(soup: BeautifulSoup) -> dict[str, str]:
    pairs: dict[str, str] = {}
    # table rows
    for tr in soup.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        cells = [c for c in cells if c]
        if len(cells) >= 2:
            lab, val = cells[0], cells[1]
            if any(k in lab for k in LABEL_MAP):
                pairs[lab] = val
    # dl
    for dl in soup.find_all("dl"):
        dts = dl.find_all("dt")
        dds = dl.find_all("dd")
        for dt, dd in zip(dts, dds):
            lab, val = dt.get_text(" ", strip=True), dd.get_text(" ", strip=True)
            if any(k in lab for k in LABEL_MAP):
                pairs[lab] = val
    # adjacent sibling pattern: label in one div, value in next
    text_blocks = []
    for el in soup.find_all(["li", "p", "div", "span"]):
        t = el.get_text(" ", strip=True)
        if t and len(t) < 60:
            text_blocks.append(t)
    for i, t in enumerate(text_blocks):
        for lab in LABEL_MAP:
            if t == lab or t.startswith(lab):
                # value may be same string "外观尺寸：xxx" or next block
                m = re.search(rf"{re.escape(lab)}\s*[:：]?\s*(.+)", t)
                if m and m.group(1).strip() and m.group(1).strip() != lab:
                    pairs[lab] = m.group(1).strip()
                elif i + 1 < len(text_blocks):
                    nxt = text_blocks[i + 1]
                    if nxt not in LABEL_MAP and len(nxt) < 40:
                        pairs.setdefault(lab, nxt)
    return pairs


def main() -> None:
    deep = json.loads(
        (_RESEARCH_DIR / "staging" / "reports" / "pangolin-pdp-deep.json").read_text(
            encoding="utf-8"
        )
    )
    # count md5 across robots' extras
    md5_owners: dict[str, list[int]] = defaultdict(list)
    for rid_s, row in deep.items():
        rid = int(rid_s)
        for ex in row.get("extras") or []:
            md5_owners[ex["md5"]].append(rid)

    report = {}
    for rid, cfg in sorted(HERO.items()):
        html = SESS.get(cfg["url"], timeout=45).text
        soup = BeautifulSoup(html, "html.parser")
        pairs = parse_pairs(soup)
        mapped = {}
        for lab, val in pairs.items():
            for k, field in LABEL_MAP.items():
                if k in lab:
                    mapped[field] = val
                    break

        extras = deep.get(str(rid), {}).get("extras") or []
        unique = [
            ex
            for ex in extras
            if len(set(md5_owners.get(ex["md5"], []))) == 1
        ]
        # also allow images that appear on this page's URL cluster only
        shared_ok = [
            ex
            for ex in extras
            if len(set(md5_owners.get(ex["md5"], []))) <= 3
            and rid in md5_owners.get(ex["md5"], [])
        ]

        report[str(rid)] = {
            "model": cfg["model"],
            "url": cfg["url"],
            "raw_pairs": pairs,
            "mapped": mapped,
            "unique_extras": unique,
            "low_share_extras": shared_ok,
        }
        print(f"\n{rid} {cfg['model']}")
        print(f"  mapped={mapped}")
        print(f"  unique_extras={len(unique)} low_share={len(shared_ok)}")

    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
