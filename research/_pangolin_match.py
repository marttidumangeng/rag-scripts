"""Map Pangolin pending robots → catalog product thumbs by Chinese name tokens."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_RESEARCH_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH_DIR))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient

CAT = json.loads(
    (_RESEARCH_DIR / "staging" / "reports" / "pangolin-list-thumbs.json").read_text(
        encoding="utf-8"
    )
)

# Prefer primary product name tokens
TOKEN_MAP = [
    # (robot name substrings / regex, preferred catalog url substrings, preferred name tokens)
    ("金刚G1", ["productjg"], ["金刚G1"]),
    ("特种兵", ["producttzb"], ["特种兵"]),
    ("黑猫警长", ["producthmjz"], ["黑猫警长"]),
    ("飞毛腿Max", ["productspeedybot", "product/102"], ["飞毛腿Max", "飞毛腿"]),
    ("飞毛腿 Pro", ["productspeedybot"], ["飞毛腿 Pro", "飞毛腿"]),
    ("飞毛腿", ["productspeedybot", "product/102"], ["飞毛腿"]),
    ("牛魔王", ["productnmw"], ["牛魔王"]),
    ("任我行", ["productrwx"], ["任我行"]),
    ("熊猫消杀", ["productjb"], ["熊猫消杀"]),
    ("熊猫医疗", ["product/145"], ["熊猫医疗"]),
    ("熊猫", ["productxm", "product/133"], ["熊猫"]),
    ("爱丽丝", ["productalsjj"], ["爱丽丝"]),
    ("艾米送餐", ["productamsc"], ["艾米送餐"]),
    ("艾米", ["productamjj"], ["艾米"]),
    ("小雪", ["productxx"], ["小雪"]),
    ("小鱼", ["productxy"], ["小鱼"]),
    ("精灵", ["productjl"], ["精灵"]),
]


def match_product(name: str) -> dict | None:
    for token, url_parts, name_tokens in TOKEN_MAP:
        if token not in name:
            continue
        # find products matching
        cands = []
        for p in CAT["products"]:
            if not any(part in p["url"] for part in url_parts):
                continue
            names = " ".join(p["names"])
            if any(t in names for t in name_tokens):
                uniq = [m for m in (p.get("thumb_meta") or []) if m.get("n_products") == 1]
                cands.append((p, uniq))
        if cands:
            # prefer ones with unique thumbs
            cands.sort(key=lambda x: -len(x[1]))
            return {"token": token, "product": cands[0][0], "uniq": cands[0][1]}
    return None


def main() -> None:
    client = ResearchApiClient()
    robots = [
        r
        for r in client.list_robots_for_company(1413)
        if str(r.get("status") or "").lower() == "pending_review"
    ]
    rows = []
    for r in sorted(robots, key=lambda x: int(x["id"])):
        rid = int(r["id"])
        full = client._get(f"robots/robots/{rid}/")
        name = full.get("name") or ""
        m = match_product(name)
        row = {
            "id": rid,
            "name": name,
            "url": full.get("url"),
            "has_img": bool((full.get("image") or full.get("s3_image") or "").strip()),
            "country": full.get("manufacturer_country"),
            "categories": full.get("categories"),
            "uses": [u.get("key") if isinstance(u, dict) else u for u in (full.get("uses") or [])],
            "feat_len": len(full.get("features") or ""),
            "match_token": (m or {}).get("token"),
            "catalog_url": ((m or {}).get("product") or {}).get("url"),
            "uniq_thumbs": [
                {"url": t["url"], "md5": t["md5"], "file": t["file"]}
                for t in ((m or {}).get("uniq") or [])
            ],
        }
        rows.append(row)
        flag = "OK" if row["uniq_thumbs"] else ("MAP" if m else "NO")
        print(
            f"{flag} {rid} {(name[:42]):42s} token={row['match_token']!s:8s} "
            f"thumbs={len(row['uniq_thumbs'])} img={row['has_img']}"
        )

    out = _RESEARCH_DIR / "staging" / "reports" / "pangolin-match.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    with_thumb = sum(1 for r in rows if r["uniq_thumbs"])
    print(f"wrote {out} matched_with_unique_thumb={with_thumb}/{len(rows)}")


if __name__ == "__main__":
    main()
