"""Clear Pangolin (1413) WARN flags where OEM/YouTube evidence exists.

- Specs: only OEM PDP / family-table column values (no invention).
- Videos: brand-gated CSJBOT/Alpha/Speedybot/Panda clips only.
- Photos: few_photos stays — OEM list cards give 1 distinct render per model;
  PDP galleries are shared site chrome or sibling variants (fail closed).
- Price / release_year: none published on checked OEM pages — leave blank.

Usage:
  python fix_pangolin_warns.py
  python fix_pangolin_warns.py --apply --copy-media
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from typing import Any

_RESEARCH_DIR = __import__("pathlib").Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient
from fix_pangolin_robots import HERO, copy_media, _internal_secret
from youtube_metadata import enrich_video_list

COMPANY_ID = 1413

# OEM-cited specs only. Niumowang F300 from multi-column table (F150|F300|F600).
# Speedybot outdoor dims/weight applied to Pro only (shared PDP; Max form factor differs).
SPECS: dict[int, dict[str, Any]] = {
    2172: {  # Xiaoyu
        "weight_kg": 19.0,
        "weight": "19 kg",
        "runtime": "≥10 h",
        "connectivity": "Laser autonomous navigation (OEM PDP)",
        "notes_append": "Screen: 13.3 inch (alpha-robot.com.cn/productxy)",
    },
    2176: {  # Aimi
        "weight_kg": 49.0,
        "weight": "49 kg",
        "runtime": "≥10 h",
        "connectivity": "Laser autonomous navigation (OEM PDP)",
        "battery_capacity": "Lithium battery",
        "notes_append": "Screen: 21.5 inch (alpha-robot.com.cn/productamjj)",
    },
    2515: {  # Alice
        "weight_kg": 45.0,
        "weight": "45 kg",
        "runtime": "≥10 h",
        "connectivity": "Laser autonomous navigation (OEM PDP)",
        "notes_append": "Screen: 13.3 inch (alpha-robot.com.cn/productalsjj)",
    },
    3497: {  # Xiaoxue
        "weight_kg": 30.0,
        "weight": "approx. 30 kg",
        "runtime": "≥10 h",
        "connectivity": "Laser autonomous navigation (OEM PDP)",
        "notes_append": "Screen: 13.3 inch (alpha-robot.com.cn/productxx)",
    },
    3197: {  # Jingling
        "weight_kg": 40.0,
        "weight": "40 kg",
        "runtime": "≥10 h",
        "connectivity": "SLAM LiDAR navigation (OEM PDP)",
        "battery_capacity": "Lithium battery",
        "notes_append": "Screen: 21.5 inch (alpha-robot.com.cn/productjl)",
    },
    2179: {  # Speedybot Pro — outdoor PDP numbers (Pro-scale body)
        "length_mm": 710.0,
        "width_mm": 560.0,
        "height_mm": 715.0,
        "dimensions_mm": "710 x 560 x 715",
        "weight_kg": 65.0,
        "weight": "approx. 65 kg",
        "battery_capacity": "48V 20Ah",
        "voltage": "48 V",
        "speed": 7.2,  # km/h OEM 最大速度
        "notes_append": (
            "OEM outdoor Speedybot PDP: range 40 km, battery 48V20Ah, "
            "max speed 7.2 km/h (alpha-robot.com.cn/productspeedybot)"
        ),
    },
    2189: {  # Panda food
        "weight_kg": 43.0,
        "weight": "43 kg",
        "runtime": "≥8 h",
        "notes_append": "Screen: 10.1 inch (alpha-robot.com.cn/productxm)",
    },
    2193: {  # Aimi food
        "weight_kg": 45.0,
        "weight": "45 kg",
        "runtime": "≥8 h",
        "connectivity": "LiDAR navigation (OEM PDP)",
        "notes_append": "Screen: 13 inch (alpha-robot.com.cn/productamsc)",
    },
    2195: {  # Niumowang F300 — column F300 of Oxbot family table
        "length_mm": 885.0,
        "width_mm": 500.0,
        "height_mm": 1350.0,
        "dimensions_mm": "885 x 500 x 1350",
        "weight_kg": 90.0,
        "weight": "90 kg",
        "payload_kg": 300.0,
        "battery_capacity": "48V 20Ah",
        "voltage": "48 V",
        "notes_append": (
            "Oxbot family table F300 column: payload 300 kg, net weight 90 kg, "
            "dims 885*500*1350 mm, battery 48V20Ah (alpha-robot.com.cn/productnmw)"
        ),
    },
    2203: {  # Renwoxing
        "length_mm": 2275.0,
        "width_mm": 1070.0,
        "height_mm": 1820.0,
        "dimensions_mm": "2275 x 1070 x 1820",
        "speed": 10.0,  # km/h
        "notes_append": "Cargo volume 1108 L (alpha-robot.com.cn/productrwx)",
    },
    2208: {  # Panda disinfection
        "weight_kg": 55.0,
        "weight": "55 kg",
        "runtime": "≤10 h",
        "battery_capacity": "20 Ah",
        "notes_append": "Screen: 10.1 inch (alpha-robot.com.cn/productjb)",
    },
    3201: {  # Panda hotel
        "weight_kg": 59.0,
        "weight": "59 kg",
        "runtime": "≥8 h",
    },
    3502: {  # indoor Speedybot
        "weight_kg": 59.0,
        "weight": "59 kg",
        "runtime": "≥8 h",
    },
    3503: {  # Panda medical
        "weight_kg": 59.0,
        "weight": "59 kg",
        "runtime": "≥8 h",
    },
    3505: {  # Black Cat Sheriff
        "charging_time": "4 h",
        "notes_append": "OEM max flat speed 1.0 m/s; charge time 4 h (producthmjz)",
    },
    3506: {  # Special Forces T1
        "length_mm": 850.0,
        "width_mm": 580.0,
        "height_mm": 1350.0,  # range 1350–1750; store min
        "dimensions_mm": "850 x 580 x 1350-1750",
        "weight_kg": 85.0,
        "weight": "85 kg",
        "runtime": "≥10 h",
        "notes_append": "Speed 0–1.5 m/s; gradeability 10% (producttzb)",
    },
}

# Brand-gated YouTube only (CSJBOT / Alpha Robotics / Speedybot / named model).
VIDEOS: dict[int, list[str]] = {
    2172: ["https://www.youtube.com/watch?v=NL4xgiJmYdE"],  # Alpha robotics-TImo (readable title)
    2176: [
        "https://www.youtube.com/watch?v=n4eIGkAT2RY",
        "https://www.youtube.com/watch?v=zdg490P35fQ",
    ],
    2515: [
        "https://www.youtube.com/watch?v=3Ox7xvI8oqk",
        "https://www.youtube.com/watch?v=Qj4EsHmNRRY",
    ],
    2179: [
        "https://www.youtube.com/watch?v=evU9OjSYX_U",
        "https://www.youtube.com/watch?v=GHy-99QExcA",
        "https://www.youtube.com/watch?v=BiVPOLBGvX0",
    ],
    # Max variants: no Max-titled clip found — family Speedybot demos (same OEM line)
    2185: [
        "https://www.youtube.com/watch?v=evU9OjSYX_U",
        "https://www.youtube.com/watch?v=BiVPOLBGvX0",
    ],
    3499: [
        "https://www.youtube.com/watch?v=evU9OjSYX_U",
        "https://www.youtube.com/watch?v=BiVPOLBGvX0",
    ],
    3502: [
        "https://www.youtube.com/watch?v=phYYaq0J6F0",
        "https://www.youtube.com/watch?v=evU9OjSYX_U",
    ],
    2189: [
        "https://www.youtube.com/watch?v=RXMbIW4CagU",
        "https://www.youtube.com/watch?v=-zRpoVdNK-k",
        # dropped b9QASN1S90o — title is hashtag-only junk
    ],
    3201: [
        "https://www.youtube.com/watch?v=RXMbIW4CagU",
        "https://www.youtube.com/watch?v=phYYaq0J6F0",
    ],
    3503: ["https://www.youtube.com/watch?v=RXMbIW4CagU"],
    2208: ["https://www.youtube.com/watch?v=HYWN5dn3ggk"],
    2193: [
        "https://www.youtube.com/watch?v=n4eIGkAT2RY",
        "https://www.youtube.com/watch?v=LaoD-apU3Z0",
    ],
}


def parse_speed_note(notes: str) -> None:
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--copy-media", action="store_true")
    ap.add_argument("--ids", type=int, nargs="*")
    args = ap.parse_args()

    client = ResearchApiClient()
    robots = [
        r
        for r in client.list_robots_for_company(COMPANY_ID)
        if str(r.get("status") or "").lower() == "pending_review"
    ]

    plan = []
    for r in sorted(robots, key=lambda x: int(x["id"])):
        rid = int(r["id"])
        if args.ids and rid not in set(args.ids):
            continue
        if rid not in HERO:
            continue
        full = client._get(f"robots/robots/{rid}/")
        body: dict[str, Any] = {}
        spec = dict(SPECS.get(rid) or {})
        notes_append = spec.pop("notes_append", None)
        body.update(spec)

        vids = VIDEOS.get(rid) or []
        if vids:
            body["video_urls"] = enrich_video_list(vids)

        if notes_append:
            existing = (full.get("notes") or "").strip()
            if notes_append not in existing:
                body["notes"] = (
                    (existing + "\n" + notes_append).strip()
                    if existing
                    else notes_append
                )

        plan.append(
            {
                "id": rid,
                "name": full.get("name"),
                "specs": bool(spec),
                "videos": len(vids),
                "body": body,
            }
        )
        print(
            f"{rid} specs={'Y' if spec else 'n'} videos={len(vids)} "
            f"{(full.get('name') or '')[:40]}"
        )

    if not args.apply:
        print("DRY-RUN — pass --apply to write")
        print(
            "NOTE: few_photos / missing_price / missing_release_year stay — "
            "no 4th OEM photo, no MSRP, no launch year on checked pages."
        )
        return 0

    secret = _internal_secret() if args.copy_media else ""
    ok = fail = 0
    for p in plan:
        try:
            body = {k: v for k, v in p["body"].items() if v not in (None, "", [])}
            patched = client._patch(f"robots/robots/{p['id']}/", body)
            print(
                f"ok {p['id']} weight={patched.get('weight_kg')} "
                f"payload={patched.get('payload_kg')} "
                f"vids={len(patched.get('videos') or [])}"
            )
            ok += 1
        except Exception as e:  # noqa: BLE001
            print(f"FAIL {p['id']}: {e}")
            fail += 1
        time.sleep(0.12)

    print(f"DONE ok={ok} fail={fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
