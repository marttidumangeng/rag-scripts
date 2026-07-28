#!/usr/bin/env python3
"""Map OEM list-card labels → thumb hashes; compare to Pangolin HERO assignments."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests
import urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings()
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from fix_pangolin_robots import HERO

SESS = requests.Session()
SESS.verify = False
SESS.headers["User-Agent"] = "Mozilla/5.0"
BASE = "https://www.alpha-robot.com.cn"

# Prefer category lists that are more specific; all-products pages also useful.
LISTS = [
    f"{BASE}/product/102.html",
    f"{BASE}/product/103.html",
    f"{BASE}/product/133.html",
    f"{BASE}/product/138.html",
    f"{BASE}/product/139.html",
    f"{BASE}/product/141.html",
    f"{BASE}/product/142.html",
    f"{BASE}/product/145.html",
    f"{BASE}/product/146.html",
]

# Expected Chinese name tokens for each published robot id
EXPECT = {
    2172: ["小鱼"],
    2176: ["艾米"],  # welcome Aimi — not 艾米送餐
    2515: ["爱丽丝"],
    3497: ["小雪"],
    3197: ["精灵"],
    2179: ["飞毛腿 Pro", "飞毛腿Pro"],
    2185: ["飞毛腿Max标准"],
    3499: ["飞毛腿Max快递"],
    3502: ["飞毛腿"],  # indoor food — careful not Max/Pro
    2189: ["熊猫"],  # food — not hotel/medical/disinfect
    3201: ["熊猫酒店"],
    3503: ["熊猫医疗"],
    2208: ["熊猫消杀"],
    2193: ["艾米送餐"],
    2195: ["牛魔王F300", "牛魔王 F300"],
    2203: ["任我行"],
    3505: ["黑猫警长"],
    3506: ["特种兵"],
}


def card_pairs(list_url: str) -> list[dict]:
    html = SESS.get(list_url, timeout=45).text
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for a in soup.find_all("a", href=True):
        href = urljoin(list_url, a["href"]).split("?")[0]
        if "/detail/" not in href:
            continue
        text = " ".join(a.get_text(" ", strip=True).split())
        if not text or text == "了解更多":
            continue
        img = a.find("img")
        parent = a
        for _ in range(5):
            if img:
                break
            parent = parent.parent if parent else None
            if parent is None:
                break
            img = parent.find("img")
        if not img:
            continue
        src = img.get("src") or img.get("data-src") or ""
        if not src or "eee172ad" in src or "footerLinks" in src or "more-jt" in src:
            continue
        src = urljoin(list_url, src).split("?")[0]
        try:
            data = SESS.get(src, timeout=30).content
        except Exception:
            continue
        if len(data) < 5000:
            continue
        out.append(
            {
                "text": text,
                "href": href,
                "src": src,
                "md5": hashlib.md5(data).hexdigest(),
            }
        )
    return out


def pick_for(tokens: list[str], cards: list[dict], *, exclude: list[str] | None = None) -> dict | None:
    exclude = exclude or []
    hits = []
    for c in cards:
        t = c["text"]
        if any(ex in t for ex in exclude):
            continue
        if any(tok in t for tok in tokens):
            hits.append(c)
    # Prefer longest token match specificity: exact-ish first
    if not hits:
        return None
    # Deduplicate by md5 keeping first
    seen = set()
    uniq = []
    for h in hits:
        if h["md5"] in seen:
            continue
        seen.add(h["md5"])
        uniq.append(h)
    return uniq[0] if uniq else None


def main() -> int:
    all_cards: list[dict] = []
    for u in LISTS:
        try:
            pairs = card_pairs(u)
            print(f"{u}: {len(pairs)} cards")
            all_cards.extend(pairs)
        except Exception as e:
            print(f"FAIL {u}: {e}")

    # de-dupe cards by (text, md5)
    keyed = {}
    for c in all_cards:
        keyed[(c["text"], c["md5"])] = c
    cards = list(keyed.values())

    mismatches = []
    ok = []
    for rid, tokens in EXPECT.items():
        cfg = HERO[rid]
        hero_url = cfg["hero"]
        hero_md5 = hashlib.md5(SESS.get(hero_url, timeout=30).content).hexdigest()
        exclude = []
        if rid == 2176:
            exclude = ["送餐"]
        if rid == 2189:
            exclude = ["酒店", "医疗", "消杀"]
        if rid == 3502:
            exclude = ["Pro", "Max", "飞毛腿Max", "飞毛腿 Pro"]
        if rid == 2195:
            exclude = ["医疗", "F150", "F600"]
        pick = pick_for(tokens, cards, exclude=exclude)
        row = {
            "id": rid,
            "model": cfg["model"],
            "hero_url": hero_url,
            "hero_md5": hero_md5,
            "list_pick": pick,
            "match": bool(pick and pick["md5"] == hero_md5),
        }
        if row["match"]:
            ok.append(row)
            print(f"OK  {rid} {cfg['model']}")
        else:
            mismatches.append(row)
            print(
                f"MISMATCH {rid} {cfg['model']}\n"
                f"  have {hero_md5[:12]} {hero_url.rsplit('/',1)[-1]}\n"
                f"  list {(pick or {}).get('md5','')[:12]} {(pick or {}).get('text','NONE')!r} "
                f"{(pick or {}).get('src','')}"
            )

    Path("staging/reports/_pangolin_hero_label_check.json").write_text(
        json.dumps({"ok": ok, "mismatches": mismatches}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    print(f"\nok={len(ok)} mismatch={len(mismatches)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
