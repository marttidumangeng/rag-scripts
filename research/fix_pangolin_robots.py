"""Enrich Pangolin Robotics / CSJBOT / Alpha (company 1413) — easy must-clear first.

OEM site: csjbot.com redirects to alpha-robot.com.cn (use verify=False; skip expired csjbot TLS).
PDP pages share a site-wide banner (eee172ad…) and a footer gallery — never use those.
Heroes come from **category list-page product-card thumbs** (unique by content hash).

Usage:
  python fix_pangolin_robots.py
  python fix_pangolin_robots.py --apply --copy-media
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

import requests

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient

COMPANY_ID = 1413
BASE = "https://www.alpha-robot.com.cn"
U = f"{BASE}/public/uploads/images"

# Curated 1:1 heroes — list-card thumbs, visually QA'd, unique md5 across targets.
# Do NOT reuse any hash across two different models.
HERO: dict[int, dict[str, Any]] = {
    # Reception / welcome
    2172: {  # 小鱼 Xiaoyu
        "hero": f"{U}/20250115/380e1d385395f86bfcdff8d8c23c81d9.png",
        "url": f"{BASE}/productxy/3/detail/9.html",
        "model": "Xiaoyu",
        "role": "reception/welcome service robot",
        "categories": ["Service-Robots", "Mobile-Robots"],
        "uses": [9],  # monitoring / guidance-adjacent already on fleet
        "tags": "Service Robot|Mobile Robot|Wheeled|AMR|Hospitality|Reception",
        "purpose": "Indoor reception and welcome guidance",
    },
    2176: {  # 艾米 Aimi
        "hero": f"{U}/20250116/d4edb398654fe67c069d3269c71803bb.png",
        "url": f"{BASE}/productamjj/3/detail/6.html",
        "model": "Aimi",
        "role": "reception/welcome service robot with torso display",
        "categories": ["Service-Robots", "Mobile-Robots"],
        "uses": [9],
        "tags": "Service Robot|Mobile Robot|Wheeled|AMR|Hospitality|Reception",
        "purpose": "Indoor reception and interactive guidance",
    },
    2515: {  # 爱丽丝 Alice
        "hero": f"{U}/20250115/92aae68e1b6a72c3d03ef87d4d22eb49.png",
        "url": f"{BASE}/productalsjj/3/detail/6.html",
        "model": "Alice",
        "role": "reception/welcome humanoid-style service robot",
        "categories": ["Service-Robots", "Mobile-Robots"],
        "uses": [9],
        "tags": "Service Robot|Mobile Robot|Wheeled|AMR|Hospitality|Reception",
        "purpose": "Indoor reception and customer interaction",
    },
    3497: {  # 小雪 Xiaoxue
        "hero": f"{U}/20250116/41a82df868bb34f5dc995a375e6845d5.png",
        "url": f"{BASE}/productxx/3/detail/9.html",
        "model": "Xiaoxue",
        "role": "reception/welcome service robot",
        "categories": ["Service-Robots", "Mobile-Robots"],
        "uses": [9],
        "tags": "Service Robot|Mobile Robot|Wheeled|AMR|Hospitality|Reception",
        "purpose": "Indoor reception and welcome guidance",
    },
    3197: {  # 精灵 Jingling (primary; 3498 is duplicate)
        "hero": f"{U}/20250506/6519c08da7c3ea6d61353da70eb99768.png",
        "url": f"{BASE}/productjl/3/detail/8.html",
        "model": "Jingling",
        "role": "reception service robot with tablet head display",
        "categories": ["Service-Robots", "Mobile-Robots"],
        "uses": [9],
        "tags": "Service Robot|Mobile Robot|Wheeled|AMR|Hospitality|Reception",
        "purpose": "Indoor reception and interactive guidance",
    },
    # Outdoor / last-mile Speedybot family (distinct renders)
    2179: {  # 飞毛腿 Pro — 4-wheel outdoor box (side text 飞毛腿)
        "hero": f"{U}/20260410/43ab60436d7c6ea671efd13e2f7ba259.png",
        "url": f"{BASE}/productspeedybot/138/detail/13.html",
        "model": "Speedybot Pro",
        "role": "outdoor indoor-outdoor delivery AMR (Speedybot Pro)",
        "categories": ["Mobile-Robots", "Service-Robots"],
        "uses": [4],  # delivery
        "tags": "AMR|Autonomous Mobile Robot|Delivery|Mobile Robot|Wheeled|Logistics",
        "purpose": "Indoor/outdoor autonomous delivery",
    },
    2185: {  # 飞毛腿Max标准版 — Max 4-locker
        "hero": f"{U}/20260408/3adc4122df5b6446d648e7f6791cfa5a.png",
        "url": f"{BASE}/productspeedybot/138/detail/13.html",
        "model": "Speedybot Max Standard",
        "role": "outdoor delivery AMR (Speedybot Max, 4 compartments)",
        "categories": ["Mobile-Robots", "Service-Robots"],
        "uses": [4],
        "tags": "AMR|Autonomous Mobile Robot|Delivery|Mobile Robot|Wheeled|Logistics",
        "purpose": "Indoor/outdoor autonomous delivery",
    },
    3499: {  # 飞毛腿Max快递版 — Max 8-locker
        "hero": f"{U}/20260408/f74b373474dedf300706064bb619b2f8.png",
        "url": f"{BASE}/productspeedybot/138/detail/13.html",
        "model": "Speedybot Max Express",
        "role": "outdoor delivery AMR (Speedybot Max, 8 compartments)",
        "categories": ["Mobile-Robots", "Service-Robots"],
        "uses": [4],
        "tags": "AMR|Autonomous Mobile Robot|Delivery|Mobile Robot|Wheeled|Logistics",
        "purpose": "Indoor/outdoor parcel delivery",
    },
    3502: {  # 飞毛腿 indoor food-delivery pillar (product/102 card)
        "hero": f"{U}/20250523/2f5de98406abc9cbaf742555320c029c.png",
        "url": f"{BASE}/product/102/detail/2.html",
        "model": "Speedybot",
        "role": "indoor multi-compartment food-delivery robot",
        "categories": ["Service-Robots", "Mobile-Robots"],
        "uses": [4],
        "tags": "AMR|Delivery|Mobile Robot|Wheeled|Hospitality|Service Robot",
        "purpose": "Indoor food and item delivery",
    },
    # Panda family
    2189: {  # 熊猫 food service with trays + panda face
        "hero": f"{U}/20250523/0352364895494fec01d640c1160bd41b.png",
        "url": f"{BASE}/productxm/2/detail/1.html",
        "model": "Panda",
        "role": "indoor multi-tray food-service robot",
        "categories": ["Service-Robots", "Mobile-Robots"],
        "uses": [4],
        "tags": "AMR|Delivery|Mobile Robot|Wheeled|Hospitality|Service Robot",
        "purpose": "Indoor food service and delivery",
    },
    3201: {  # 熊猫酒店配送 — 4-door hotel locker
        "hero": f"{U}/20250523/c678e4ed24ce0fb4008902feb2bd2bcf.png",
        "url": f"{BASE}/product/133/detail/11.html",
        "model": "Panda Hotel Delivery",
        "role": "hotel multi-compartment delivery robot",
        "categories": ["Service-Robots", "Mobile-Robots"],
        "uses": [4],
        "tags": "AMR|Delivery|Mobile Robot|Wheeled|Hospitality|Service Robot",
        "purpose": "Hotel room and lobby delivery",
    },
    3503: {  # 熊猫医疗款 — note: OEM moved file from 20260408/ → 20260428/
        "hero": f"{U}/20260428/59fe804059ec2754826bd941b4776660.png",
        "url": f"{BASE}/product/145/detail/33.html",
        "model": "Panda Medical",
        "role": "medical multi-compartment delivery robot",
        "categories": ["Service-Robots", "Mobile-Robots"],
        "uses": [4],
        "tags": "AMR|Delivery|Mobile Robot|Wheeled|Medical|Service Robot",
        "purpose": "Hospital/clinic item delivery",
    },
    2208: {  # 熊猫消杀 (primary; 3508 duplicate)
        "hero": f"{U}/20260428/12418c72f9e9e96f3df648bc02334e9f.png",
        "url": f"{BASE}/productjb/4/detail/3.html",
        "model": "Panda Disinfection",
        "role": "disinfection / sanitization service robot",
        "categories": ["Service-Robots", "Mobile-Robots"],
        "uses": [9],  # monitoring/service (no dedicated disinfection use id)
        "tags": "AMR|Mobile Robot|Wheeled|Cleaning|Service Robot|Medical",
        "purpose": "Indoor disinfection and sanitation",
    },
    # Aimi food delivery (tray arms — distinct from reception Aimi)
    2193: {
        "hero": f"{U}/20250523/25f745e221e781764bee5f1e4ae6ca9f.png",
        "url": f"{BASE}/productamsc/2/detail/5.html",
        "model": "Aimi Food Delivery",
        "role": "indoor tray-carrying food-delivery robot",
        "categories": ["Service-Robots", "Mobile-Robots"],
        "uses": [4],
        "tags": "AMR|Delivery|Mobile Robot|Wheeled|Hospitality|Service Robot",
        "purpose": "Indoor food delivery",
    },
    # Factory handling — only F300 Hot gets a hero (sibling variants share PDP; fail closed)
    2195: {
        "hero": f"{U}/20250815/9ddbecba5684601d2f8419b9066ae4d2.png",  # list-card 牛魔王F300 (was wrongly medical)
        "url": f"{BASE}/productnmw/141/detail/15.html",
        "model": "Niumowang F300",
        "role": "factory/hospitality open-shelf mobile handling robot (F300)",
        "categories": ["Mobile-Robots", "Service-Robots"],
        "uses": [4],  # delivery / transport
        "tags": "AMR|Autonomous Mobile Robot|Material Handling|Mobile Robot|Wheeled|Logistics",
        "purpose": "Indoor material handling and transport",
    },
    # Retail / security
    2203: {
        "hero": f"{U}/20250429/55658c77ec2dfdfc33e077803ada114e.png",
        "url": f"{BASE}/productrwx/139/detail/14.html",
        "model": "Renwoxing",
        "role": "unmanned retail / mobile vending vehicle",
        "categories": ["Mobile-Robots", "Service-Robots"],
        "uses": [11],
        "tags": "AMR|Autonomous Mobile Robot|Mobile Robot|Wheeled|Retail|Logistics",
        "purpose": "Autonomous mobile retail / vending",
    },
    3505: {  # 黑猫警长
        "hero": f"{U}/20251118/b4fa5d8de4a5186c1ab66e2e3c98fba1.png",
        "url": f"{BASE}/producthmjz/142/detail/20.html",
        "model": "Black Cat Sheriff",
        "role": "security / patrol inspection robot",
        "categories": ["Mobile-Robots", "Service-Robots"],
        "uses": [7],
        "tags": "AMR|Mobile Robot|Wheeled|Security|Inspection|Autonomous",
        "purpose": "Indoor security patrol and inspection",
    },
    3506: {  # 特种兵T1
        "hero": f"{U}/20260408/03e203c3acf6ec5d4ac939ee33ba8da0.png",
        "url": f"{BASE}/producttzb/142/detail/27.html",
        "model": "Special Forces T1",
        "role": "outdoor security / patrol robot",
        "categories": ["Mobile-Robots", "Service-Robots"],
        "uses": [7],
        "tags": "AMR|Mobile Robot|Wheeled|Security|Inspection|Outdoor|Autonomous",
        "purpose": "Outdoor security patrol and surveillance",
    },
}

# Duplicate / variant shells: clear contaminated keep-image, leave IMAGE TO-DO / merge note.
# Maps id → note reason (no hero assigned — would duplicate a primary's hash).
LEFTOVER_NOTES: dict[int, str] = {
    2199: (
        "Niumowang F600 shares productnmw PDP with F150/F300/medical. "
        "Only F300 received a distinct list-card hero; no labeled F600 render found."
    ),
    3198: (
        "Speedybot Max Medical shares speedybot PDP. "
        "Distinct renders assigned to Pro / Max Standard / Max Express only."
    ),
    3199: (
        "Niumowang F150 shares productnmw PDP; no labeled F150-only list-card thumb."
    ),
    3200: (
        "Niumowang Medical shares productnmw PDP; no labeled medical-only list-card thumb "
        "(open-shelf hero reserved for F300 Hot)."
    ),
    3471: "Generic category shell (室内外配送机器人) — merge into named Speedybot rows or reject.",
    3472: "Generic category shell (迎宾接待机器人) — merge into Xiaoyu/Aimi/Alice/Xiaoxue/Jingling or reject.",
    3473: "Generic category shell (酒店配送机器人) — merge into Panda Hotel Delivery (3201) or reject.",
    3474: "Generic category shell (工厂搬运机器人) — merge into Niumowang rows or reject.",
    3475: "Generic category shell (安防巡检机器人) — merge into Black Cat Sheriff / T1 or reject.",
    3476: "Duplicate of Xiaoyu (2172) under Chinese reception title — merge into 2172.",
    3477: "Duplicate of Aimi (2176) under Chinese reception title — merge into 2176.",
    3478: "Duplicate of Alice (2515) under Chinese reception title — merge into 2515.",
    3479: "Duplicate of Panda Medical (3503) — merge into 3503.",
    3480: "Duplicate of Niumowang Medical (3200/3507) — merge after medical hero is sourced.",
    3481: "Duplicate of Panda Disinfection (2208) — merge into 2208.",
    3482: "Duplicate of Aimi Food Delivery (2193) — merge into 2193.",
    3483: "Duplicate of Speedybot food-delivery (3502) — merge into 3502.",
    3484: "Duplicate of Panda Hotel Delivery (3201) — merge into 3201.",
    3485: "Duplicate of Black Cat Sheriff (3505) — merge into 3505.",
    3486: (
        "外卖机器人 shell previously shared Xiaoyu keep-hash. "
        "No model-specific list-card thumb; merge into Speedybot Max Food Delivery or reject."
    ),
    3498: "Duplicate of Jingling (3197) — merge into 3197.",
    3500: (
        "Speedybot Max Food Delivery shares speedybot PDP; "
        "no distinct food-edition render (Max Standard/Express already assigned)."
    ),
    3501: (
        "Speedybot Max Medical shares speedybot PDP; no distinct medical-edition render."
    ),
    3504: "Duplicate Niumowang F150 row — same gap as 3199.",
    3507: "Duplicate Niumowang Medical row — same gap as 3200.",
    3508: "Duplicate of Panda Disinfection (2208) — merge into 2208.",
}


def _admin_base() -> str:
    import os

    return (os.environ.get("RESEARCH_ADMIN_BASE") or "https://ragadmin.robotaigeek.com").rstrip(
        "/"
    )


def _internal_secret() -> str:
    env = _RESEARCH_DIR.parents[1] / "robotaigeek-server" / ".env"
    if env.is_file():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                return line.split("=", 1)[1].strip()
    return ""


def copy_media(rid: int, secret: str) -> str:
    url = f"{_admin_base()}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/?force=1"
    try:
        r = requests.post(url, headers={"X-Internal-Secret": secret}, timeout=180)
        return "ok" if r.ok else f"HTTP {r.status_code}"
    except requests.RequestException as e:
        return f"ERR {e}"


def image_todo_note(why: str) -> str:
    return (
        "[IMAGE TO-DO — no hero, deliberate]\n"
        f"{why}\n"
        "Checked: alpha-robot.com.cn category list cards + PDP (shared banner eee172ad rejected).\n"
        "ACTION FOR TEAM: source a model-specific OEM render, or merge/reject duplicate shell.\n"
        "Do NOT substitute a sibling render, family banner, or site footer gallery image.\n"
        "---"
    )


def build_features(cfg: dict[str, Any]) -> str:
    text = (
        f"Pangolin Robotics (CSJBOT / Alpha) {cfg['model']} — {cfg['role']}. "
        f"Manufacturer: Suzhou Pangolin Robot Co., Ltd. (China)."
    )
    if "http://" in text or "https://" in text:
        raise ValueError("features must not contain URLs — use information_source_urls")
    return text


def build_description(cfg: dict[str, Any]) -> str:
    text = (
        f"{cfg['model']} is a {cfg['role']} from Pangolin Robotics "
        f"(Suzhou Pangolin Robot Co., Ltd. / Alpha Robot, China)."
    )
    if "http://" in text or "https://" in text:
        raise ValueError("description must not contain URLs — use information_source_urls")
    return text


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--copy-media", action="store_true")
    ap.add_argument("--ids", type=int, nargs="*")
    args = ap.parse_args()

    # Assert no hero hash reused across two targets (URL path uniqueness ≈ content uniqueness here)
    heroes = [c["hero"] for c in HERO.values()]
    if len(heroes) != len(set(heroes)):
        raise SystemExit("BUG: duplicate hero URL in HERO map")

    client = ResearchApiClient()
    robots = None
    for a in range(12):
        try:
            robots = client.list_robots_for_company(COMPANY_ID)
            break
        except Exception as e:  # noqa: BLE001
            print(f"retry {a}: {e}")
            time.sleep(5)
    if robots is None:
        return 1

    plan: list[dict[str, Any]] = []
    for r in sorted(robots, key=lambda x: int(x["id"])):
        if str(r.get("status") or "").lower() != "pending_review":
            continue
        rid = int(r["id"])
        if args.ids and rid not in set(args.ids):
            continue

        has_img = bool((r.get("image") or r.get("s3_image") or "").strip())
        cfg = HERO.get(rid)
        leftover = LEFTOVER_NOTES.get(rid)

        body: dict[str, Any] = {
            "source_locale": "en",
            "manufacturer_country": "China",
        }

        if cfg:
            body.update(
                {
                    "url": cfg["url"],
                    "website_url": cfg["url"],
                    "model_name": cfg["model"],
                    "categories": cfg["categories"],
                    "uses": cfg.get("uses") or [],
                    "tags": cfg["tags"],
                    "purpose": cfg["purpose"],
                    "description": build_description(cfg),
                    "features": build_features(cfg),
                    "images": [cfg["hero"]],
                    "image": cfg["hero"],
                    "movement_types": [4],  # wheeled
                    "information_source_urls": [
                        {
                            "url": cfg["url"],
                            "title": f"{cfg['model']} product page",
                            "source_type": "website",
                        }
                    ],
                }
            )
            plan.append(
                {
                    "id": rid,
                    "name": r.get("name"),
                    "action": "SET_HERO",
                    "hero": cfg["hero"],
                    "body": body,
                    "clear_image": False,
                }
            )
        elif leftover:
            notes = (r.get("notes") or "").strip()
            note = image_todo_note(leftover)
            if "[IMAGE TO-DO" not in notes:
                body["notes"] = (note + "\n" + notes).strip() if notes else note
            # Always clear contaminated / placeholder keep images on leftovers
            plan.append(
                {
                    "id": rid,
                    "name": r.get("name"),
                    "action": "CLEAR+TODO" if has_img else "TODO",
                    "hero": None,
                    "body": body,
                    "clear_image": True,
                }
            )
        else:
            print(f"SKIP {rid} {(r.get('name') or '')[:40]} — not in HERO/LEFTOVER")

    print(f"planned={len(plan)}")
    for p in plan:
        print(f"  {p['action']:10s} {p['id']} {(p['name'] or '')[:48]}")

    if not args.apply:
        print("DRY-RUN — pass --apply to write")
        return 0

    secret = _internal_secret() if args.copy_media else ""
    ok = fail = 0
    for p in plan:
        try:
            body = dict(p["body"])
            if p.get("clear_image"):
                body["image"] = None
                body["s3_image"] = None
                body["images"] = []
            else:
                body = {k: v for k, v in body.items() if v is not None}
            patched = client._patch(f"robots/robots/{p['id']}/", body)
            cm = ""
            if (
                args.copy_media
                and p.get("hero")
                and secret
                and not p.get("clear_image")
            ):
                cm = copy_media(p["id"], secret)
            print(
                f"ok {p['id']} {p['action']} "
                f"img={(patched.get('image') or patched.get('s3_image') or '')[:60]} "
                f"copy={cm or '-'}"
            )
            ok += 1
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL {p['id']}: {exc}")
            fail += 1
        time.sleep(0.15)

    print(f"DONE ok={ok} fail={fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
