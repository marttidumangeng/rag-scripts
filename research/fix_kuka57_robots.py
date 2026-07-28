"""Enrich/fix company 57 (KUKA Robotics) family-placeholder robots.

Same OEM as company 1396 (KUKA). These 15 rows are mostly series landing
names (KR AGILUS, LBR iisy, …) plus a few AMRs — not per-variant duplicates
of 1396, but they share the brand and should merge into 1396 after QA.

Fixes:
  - English description / purpose / features (base + zh-CN translation-sync)
  - Correct OEM family URLs (not homepage / wrong SCARA / industrial hub)
  - Family series metadata, release_year, typed specs where OEM-cited
  - Taxonomy (Industrial-Robot / Mobile; uses; movement; industries)
  - Strip junk tags (Drone/UAV/Aerial/Humanoid)
  - Series videos where known
  - Price left blank (no public KUKA MSRP)

Usage:
  python fix_kuka57_robots.py            # dry-run
  python fix_kuka57_robots.py --apply
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

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
from youtube_metadata import enrich_video_list

COMPANY_ID = 57
AVAILABILITY_RELEASED = 3

# Industrial arms
CAT_INDUSTRIAL = ["Industrial-Robot"]
SUB_MFG = 9
MOVE_STATIONARY = [10]
MOVE_WHEELED = [4]
IND_MFG_AUTO = [12, 26]  # manufacturing, automotive
IND_LOGISTICS = [11, 12]  # logistics, manufacturing
USES_HANDLING = [32, 46]
USES_PALLET = [25, 32]
USES_ASSEMBLY = [21, 22]
USES_TRANSPORT = [16, 32]

TAGS_ARM = [
    "Industrial Robot",
    "Automation",
    "Manufacturing",
    "Assembly",
    "Material Handling",
]
TAGS_COBOT = [
    "Collaborative Robot",
    "Industrial Robot",
    "Automation",
    "Assembly",
    "Manufacturing",
]
TAGS_AMR = [
    "AGV",
    "AMR",
    "Autonomous Mobile Robot",
    "Logistics",
    "Material Handling",
    "Warehouse Automation",
    "Wheeled",
]
TAGS_PA = [
    "Industrial Robot",
    "Automation",
    "Palletizing",
    "Material Handling",
    "Logistics",
]

FIXES: dict[int, dict[str, Any]] = {
    62: {  # KUKA KR 6 — ambiguous series name; point at AGILUS (6 kg class)
        "family": "kr-agilus",
        "family_name": "KR AGILUS",
        "family_key": "kuka:kr-agilus",
        "url": "https://www.kuka.com/en-us/products/robotics-systems/industrial-robots/kr-agilus",
        "year": 2014,
        "description": (
            "KUKA KR 6 refers to KUKA's compact 6 kg-class industrial robot arms, "
            "today represented in the KR AGILUS family. These six-axis stationary "
            "arms are built for high-speed handling and assembly in tight cells."
        ),
        "purpose": "Compact six-axis industrial handling and assembly",
        "features": (
            "Family class: ~6 kg payload KR AGILUS variants on the live OEM table "
            "(Total load from 6 kg; Maximum reach from ~726 mm). "
            "Construction: six-axis industrial arm. Controller: KR C5 micro family. "
            "Note: record name is a class label, not a single SKU — see KR AGILUS "
            "variant rows under company KUKA (1396)."
        ),
        "categories": CAT_INDUSTRIAL,
        "sub_category": SUB_MFG,
        "movement_types": MOVE_STATIONARY,
        "industries": IND_MFG_AUTO,
        "uses": USES_HANDLING,
        "tags": TAGS_ARM,
        "video_fam": "kr-agilus",
    },
    211: {  # KMP 3000P
        "family": "kmp",
        "family_name": "KMP",
        "family_key": "kuka:kmp",
        "url": "https://www.kuka.com/en-us/products/amr-autonomous-mobile-robotics/mobile-platforms/kmp-3000p-omniMove",
        "year": 2023,
        "description": (
            "KUKA KMP 3000P is an omnidirectional autonomous mobile transport "
            "platform for intralogistics. It carries up to three tons, uses "
            "inductive charging for 24/7 operation, and navigates with laser "
            "scanners and 3D cameras."
        ),
        "purpose": "Heavy-payload autonomous intralogistics transport",
        "features": (
            "Total load: up to 3000 kg | Dimensions: 2200 x 1200 x 370 mm | "
            "Max speed: 1.2 m/s (unladen), 1.0 m/s (laden) | "
            "Operating time: 6-8 hours | Charge 10-90%: <2 hours | "
            "Protection: IP 54 | Positioning: up to +/- 10 mm (SLAM), +/- 5 mm (QR) | "
            "Lift height: 100 mm (OEM KMP 3000P product page)"
        ),
        "payload_kg": 3000.0,
        "length_mm": 2200.0,
        "width_mm": 1200.0,
        "height_mm": 370.0,
        "speed": 1.2,
        "categories": ["Service-Robots"],
        "sub_category": SUB_MFG,
        "movement_types": MOVE_WHEELED,
        "industries": IND_LOGISTICS,
        "uses": USES_TRANSPORT,
        "tags": TAGS_AMR,
        "video_fam": None,
    },
    213: {  # KUKA OmniMove — family hub
        "family": "omnimove",
        "family_name": "KUKA omniMove",
        "family_key": "kuka:omnimove",
        "url": "https://www.kuka.com/en-us/products/amr-autonomous-mobile-robotics/mobile-platforms",
        "year": None,  # long-running line; no single launch year cited
        "description": (
            "KUKA omniMove is a family of omnidirectional heavy-load transport "
            "platforms for XXL industrial payloads. OEM materials cite loads up "
            "to 90 tons and lengths up to 30 meters, with non-contact positioning "
            "accuracy of +/- 3 mm."
        ),
        "purpose": "Omnidirectional heavy-load industrial transport",
        "features": (
            "Family: KUKA omniMove heavy-load platforms | "
            "Payload class: up to 90 tons | Length: up to 30 m | "
            "Positioning accuracy: +/- 3 mm (OEM mobile-platforms / omniMove copy). "
            "Related variant rows: omniMove E375 3000 / E575 7000 under company KUKA (1396)."
        ),
        "categories": ["Service-Robots"],
        "sub_category": SUB_MFG,
        "movement_types": MOVE_WHEELED,
        "industries": IND_LOGISTICS,
        "uses": USES_TRANSPORT,
        "tags": TAGS_AMR,
        "video_fam": None,
        "notes_append": (
            "[IMAGE NOTE 2026-07-19] Prior hero reused a KMP 3000P asset. "
            "Kept owned CDN image pending a distinct omniMove render; "
            "do not treat the filename as proof of model match."
        ),
    },
    342: {  # KMP 600 — map to current KMP 600P page (600 kg)
        "family": "kmp",
        "family_name": "KMP",
        "family_key": "kuka:kmp",
        "url": "https://www.kuka.com/en-us/products/amr-autonomous-mobile-robotics/mobile-platforms/kmp-600p-diffdrive",
        "year": 2023,
        "description": (
            "KUKA KMP 600 is a compact autonomous mobile robot platform in the "
            "600 kg payload class. The current OEM page documents the KMP 600P "
            "diffDrive variant for cramped production and warehouse transport "
            "with inductive charging and VDA 5050 compatibility."
        ),
        "purpose": "Compact AMR platform for intralogistics",
        "features": (
            "Payload class: 600 kg (OEM KMP 600P page) | "
            "Drive: differential | Inductive charging for 24/7 operation | "
            "VDA 5050 compatible | Compact footprint cited as 980 x 686 x 270 mm "
            "on the KMP 600P product page. Related: KMP 600P / 600W under company 1396."
        ),
        "payload_kg": 600.0,
        "length_mm": 980.0,
        "width_mm": 686.0,
        "height_mm": 270.0,
        "categories": ["Service-Robots"],
        "sub_category": SUB_MFG,
        "movement_types": MOVE_WHEELED,
        "industries": IND_LOGISTICS,
        "uses": USES_TRANSPORT,
        "tags": TAGS_AMR,
        "video_fam": None,
    },
    2092: {
        "family": "kr-agilus",
        "family_name": "KR AGILUS",
        "family_key": "kuka:kr-agilus",
        "url": "https://www.kuka.com/en-us/products/robotics-systems/industrial-robots/kr-agilus",
        "year": 2014,
        "description": (
            "KUKA KR AGILUS is a family of compact six-axis industrial robots for "
            "high-speed handling in small cells. Live OEM table variants cover "
            "Total load from 6 kg with Maximum reach from about 726 mm to 1101 mm."
        ),
        "purpose": "Compact high-speed industrial handling",
        "features": (
            "Family: KR AGILUS | OEM table Total load range: 6–11 kg | "
            "Maximum reach range: ~726–1101 mm | Mounting: floor/ceiling/wall/angle "
            "on many variants | Controllers: KR C5 micro / KR C5 micro-2 "
            "(OEM KR AGILUS family table)."
        ),
        "categories": CAT_INDUSTRIAL,
        "sub_category": SUB_MFG,
        "movement_types": MOVE_STATIONARY,
        "industries": IND_MFG_AUTO,
        "uses": USES_HANDLING,
        "tags": TAGS_ARM,
        "video_fam": "kr-agilus",
    },
    2097: {
        "family": "kr-delta",
        "family_name": "KR DELTA",
        "family_key": "kuka:kr-delta",
        "url": "https://www.kuka.com/en-us/products/robotics-systems/industrial-robots/kr-delta",
        "year": 2018,
        "description": (
            "KUKA KR DELTA is a family of high-speed delta (parallel) robots for "
            "pick-and-place and packaging. OEM table variants list Total load from "
            "6 kg to 15 kg with Maximum reach from about 250 mm to 455 mm."
        ),
        "purpose": "High-speed delta pick-and-place",
        "features": (
            "Family: KR DELTA | OEM table Total load range: 6–15 kg | "
            "Maximum reach range: ~250–455 mm | Construction: delta/parallel kinematics "
            "(OEM KR DELTA family table)."
        ),
        "categories": CAT_INDUSTRIAL,
        "sub_category": SUB_MFG,
        "movement_types": MOVE_STATIONARY,
        "industries": IND_MFG_AUTO,
        "uses": USES_HANDLING,
        "tags": TAGS_ARM,
        "video_fam": None,
    },
    2102: {
        "family": "lbr-iisy",
        "family_name": "LBR iisy",
        "family_key": "kuka:lbr-iisy",
        "url": "https://www.kuka.com/en-us/products/robotics-systems/industrial-robots/lbr-iisy",
        "year": 2021,
        "description": (
            "KUKA LBR iisy is a collaborative robot family for light assembly and "
            "handling. OEM table variants list Total load from 3 kg to 15 kg with "
            "Maximum reach from 760 mm to 1300 mm."
        ),
        "purpose": "Collaborative light assembly and handling",
        "features": (
            "Family: LBR iisy | OEM table Total load range: 3–15 kg | "
            "Maximum reach range: 760–1300 mm | Collaborative / sensitive arm | "
            "Controller: KR C5 micro (OEM LBR iisy family table)."
        ),
        "categories": CAT_INDUSTRIAL,
        "sub_category": SUB_MFG,
        "movement_types": MOVE_STATIONARY,
        "industries": IND_MFG_AUTO,
        "uses": USES_ASSEMBLY,
        "tags": TAGS_COBOT,
        "video_fam": "lbr-iisy",
    },
    2107: {
        "family": "lbr-iiwa",
        "family_name": "LBR iiwa",
        "family_key": "kuka:lbr-iiwa",
        "url": "https://www.kuka.com/en-us/products/robotics-systems/industrial-robots/lbr-iiwa",
        "year": 2013,
        "description": (
            "KUKA LBR iiwa is a seven-axis collaborative robot family for sensitive "
            "assembly and HRC tasks. OEM table variants list Total load 7 kg or 14 kg "
            "with Maximum reach 800 mm or 820 mm."
        ),
        "purpose": "Seven-axis collaborative sensitive assembly",
        "features": (
            "Family: LBR iiwa | OEM table Total load: 7 kg or 14 kg | "
            "Maximum reach: 800 mm or 820 mm | Axes: 7 | "
            "Controller: KUKA Sunrise Cabinet (OEM LBR iiwa family table)."
        ),
        "categories": CAT_INDUSTRIAL,
        "sub_category": SUB_MFG,
        "movement_types": MOVE_STATIONARY,
        "industries": IND_MFG_AUTO,
        "uses": USES_ASSEMBLY,
        "tags": TAGS_COBOT,
        "video_fam": "lbr-iiwa",
    },
    2111: {
        "family": "kr-cybertech-nano",
        "family_name": "KR CYBERTECH nano",
        "family_key": "kuka:kr-cybertech-nano",
        "url": "https://www.kuka.com/en-us/products/robotics-systems/industrial-robots/kr-cybertech-nano",
        "year": 2020,
        "description": (
            "KUKA KR CYBERTECH nano is a compact industrial robot family for "
            "medium-reach handling. OEM table variants list Total load from 6 kg "
            "to 10 kg with Maximum reach from 1440 mm to 1840 mm."
        ),
        "purpose": "Compact industrial handling at medium reach",
        "features": (
            "Family: KR CYBERTECH nano | OEM table Total load range: 6–10 kg | "
            "Maximum reach range: 1440–1840 mm (OEM family table)."
        ),
        "categories": CAT_INDUSTRIAL,
        "sub_category": SUB_MFG,
        "movement_types": MOVE_STATIONARY,
        "industries": IND_MFG_AUTO,
        "uses": USES_HANDLING,
        "tags": TAGS_ARM,
        "video_fam": "kr-cybertech-nano",
    },
    2114: {
        "family": "kr-cybertech",
        "family_name": "KR CYBERTECH",
        "family_key": "kuka:kr-cybertech",
        "url": "https://www.kuka.com/en-us/products/robotics-systems/industrial-robots/kr-cybertech",
        "year": 2017,
        "description": (
            "KUKA KR CYBERTECH is a mid-payload industrial robot family for compact "
            "cells. OEM table variants list Total load from 8 kg to 35 kg with "
            "Maximum reach from about 1612 mm to 2013 mm."
        ),
        "purpose": "Mid-payload compact-cell industrial handling",
        "features": (
            "Family: KR CYBERTECH | OEM table Total load range: 8–35 kg | "
            "Maximum reach range: ~1612–2013 mm (OEM family table)."
        ),
        "categories": CAT_INDUSTRIAL,
        "sub_category": SUB_MFG,
        "movement_types": MOVE_STATIONARY,
        "industries": IND_MFG_AUTO,
        "uses": USES_HANDLING,
        "tags": TAGS_ARM,
        "video_fam": "kr-cybertech",
    },
    2119: {
        "family": "kr-iontec",
        "family_name": "KR IONTEC",
        "family_key": "kuka:kr-iontec",
        "url": "https://www.kuka.com/en-us/products/robotics-systems/industrial-robots/kr-iontec",
        "year": 2020,
        "description": (
            "KUKA KR IONTEC is a versatile mid-payload industrial robot family. "
            "OEM table variants list Total load from 20 kg to 70 kg with Maximum "
            "reach from about 2101 mm to 3101 mm."
        ),
        "purpose": "Versatile mid-payload industrial handling",
        "features": (
            "Family: KR IONTEC | OEM table Total load range: 20–70 kg | "
            "Maximum reach range: ~2101–3101 mm (OEM family table)."
        ),
        "categories": CAT_INDUSTRIAL,
        "sub_category": SUB_MFG,
        "movement_types": MOVE_STATIONARY,
        "industries": IND_MFG_AUTO,
        "uses": USES_HANDLING,
        "tags": TAGS_ARM,
        "video_fam": "kr-iontec",
    },
    2122: {  # KR 470 PA — align to current FORTEC PA 470 kg row
        "family": "kr-fortec-pa",
        "family_name": "KR FORTEC PA",
        "family_key": "kuka:kr-fortec-pa",
        "url": "https://www.kuka.com/en-us/products/robotics-systems/industrial-robots/kr-fortec-pa",
        "year": 2025,
        "description": (
            "KUKA KR 470 PA is a palletizing industrial robot in the KR FORTEC PA "
            "family. The current OEM table lists KR 470 R3200-2 PA at Total load "
            "470 kg and Maximum reach 3200 mm."
        ),
        "purpose": "Heavy-payload industrial palletizing",
        "features": (
            "Matched OEM row: KR 470 R3200-2 PA | Total load: 470 kg | "
            "Maximum reach: 3200 mm | Construction type: Palletizing Robots | "
            "Protection: IP 65 | Mounting: Floor | Controller: KR C5 "
            "(OEM KR FORTEC PA family table)."
        ),
        "payload_kg": 470.0,
        "reach_mm": 3200.0,
        "categories": CAT_INDUSTRIAL,
        "sub_category": SUB_MFG,
        "movement_types": MOVE_STATIONARY,
        "industries": IND_MFG_AUTO,
        "uses": USES_PALLET,
        "tags": TAGS_PA,
        "video_fam": "kr-fortec-pa",
        "variant_code": "KR 470 R3200-2 PA",
    },
    2126: {
        "family": "kr-quantec",
        "family_name": "KR QUANTEC",
        "family_key": "kuka:kr-quantec",
        "url": "https://www.kuka.com/en-us/products/robotics-systems/industrial-robots/kr-quantec",
        "year": 2010,
        "description": (
            "KUKA KR QUANTEC is a high-payload industrial robot family widely used "
            "in automotive and general industry. OEM table variants list Total load "
            "from 120 kg to 300 kg with Maximum reach from about 2671 mm to 3904 mm."
        ),
        "purpose": "High-payload industrial handling",
        "features": (
            "Family: KR QUANTEC | OEM table Total load range: 120–300 kg | "
            "Maximum reach range: ~2671–3904 mm (OEM family table)."
        ),
        "categories": CAT_INDUSTRIAL,
        "sub_category": SUB_MFG,
        "movement_types": MOVE_STATIONARY,
        "industries": IND_MFG_AUTO,
        "uses": USES_HANDLING,
        "tags": TAGS_ARM,
        "video_fam": "kr-quantec",
    },
    2129: {
        "family": "kr-fortec",
        "family_name": "KR FORTEC",
        "family_key": "kuka:kr-fortec",
        "url": "https://www.kuka.com/en-us/products/robotics-systems/industrial-robots/kr-fortec",
        "year": 2024,
        "description": (
            "KUKA KR FORTEC is a heavy-duty industrial robot family between QUANTEC "
            "and FORTEC ultra. OEM table variants list Total load from 240 kg to "
            "500 kg with Maximum reach from about 2800 mm to 3750 mm."
        ),
        "purpose": "Heavy-duty industrial handling",
        "features": (
            "Family: KR FORTEC | OEM table Total load range: 240–500 kg | "
            "Maximum reach range: ~2800–3750 mm (OEM family table)."
        ),
        "categories": CAT_INDUSTRIAL,
        "sub_category": SUB_MFG,
        "movement_types": MOVE_STATIONARY,
        "industries": IND_MFG_AUTO,
        "uses": USES_HANDLING,
        "tags": TAGS_ARM,
        "video_fam": "kr-fortec",
    },
    2132: {
        "family": "kr-1000-titan",
        "family_name": "KR 1000 titan",
        "family_key": "kuka:kr-1000-titan",
        "url": "https://www.kuka.com/en-us/products/robotics-systems/industrial-robots/kr-1000-titan",
        "year": 2007,
        "description": (
            "KUKA KR titan (KR 1000 titan family) is a ultra-heavy-payload industrial "
            "robot line. OEM table variants list Total load from 750 kg to 1300 kg "
            "with Maximum reach from about 3202 mm to 3601 mm."
        ),
        "purpose": "Ultra-heavy-payload industrial handling",
        "features": (
            "Family: KR 1000 titan | OEM table Total load range: 750–1300 kg | "
            "Maximum reach range: ~3202–3601 mm (OEM family table)."
        ),
        "categories": CAT_INDUSTRIAL,
        "sub_category": SUB_MFG,
        "movement_types": MOVE_STATIONARY,
        "industries": IND_MFG_AUTO,
        "uses": USES_HANDLING,
        "tags": TAGS_ARM,
        "video_fam": "kr-1000-titan",
    },
}

VIDEO_URLS: dict[str, list[str]] = {
    "kr-agilus": ["https://www.youtube.com/watch?v=bod5_R58V6A"],
    "kr-cybertech": ["https://www.youtube.com/watch?v=Cx-l9jogO5I"],
    "kr-cybertech-nano": ["https://www.youtube.com/watch?v=44GC57lhdtc"],
    "kr-iontec": ["https://www.youtube.com/watch?v=4fCX3M7jPJs"],
    "kr-fortec": ["https://www.youtube.com/watch?v=AFjbTD7Wc1U"],
    "kr-fortec-pa": ["https://www.youtube.com/watch?v=Sc-6A97GETY"],
    "kr-quantec": ["https://www.youtube.com/watch?v=kROzVbWpANw"],
    "kr-1000-titan": ["https://www.youtube.com/watch?v=uuIiBUvrCB4"],
    "lbr-iisy": ["https://www.youtube.com/watch?v=Bq8tTBW3R9g"],
    "lbr-iiwa": ["https://www.youtube.com/watch?v=_XU10uZbCy8"],
}

NARRATIVE = ("description", "purpose", "features")


def force_sync_zh(client: ResearchApiClient, robot_id: int, fields: dict[str, str]) -> None:
    body = {
        "updates": [
            {
                "id": robot_id,
                "locale": "zh-CN",
                "source_hash": f"kuka57-force-{robot_id}-20260719",
                "translated_fields": fields,
            }
        ]
    }
    resp = client._session.post(
        client._url("robots/robots/translation-sync/?force=1"),
        json=body,
        timeout=client.timeout,
    )
    resp.raise_for_status()


def build_body(fix: dict[str, Any], videos_by_fam: dict[str, list]) -> dict[str, Any]:
    body: dict[str, Any] = {
        "source_locale": "en",
        "url": fix["url"],
        "website_url": fix["url"],
        "description": fix["description"],
        "purpose": fix["purpose"],
        "features": fix["features"],
        "family_name": fix["family_name"],
        # Do NOT set family_key while company 57 is separate — keys are
        # company-scoped and already used by 1396 (kuka:…). Set after merge.
        "family_url": fix["url"],
        "product_url_scope": "family",
        "manufacturer_country": "Germany",
        "manufacturer_countries": [7],
        "availability_status": AVAILABILITY_RELEASED,
        "categories": fix["categories"],
        "sub_category": fix["sub_category"],
        "movement_types": fix["movement_types"],
        "industries": fix["industries"],
        "uses": fix["uses"],
        "tags": fix["tags"],
    }
    if fix.get("year"):
        body["release_year"] = int(fix["year"])
    for k in ("payload_kg", "reach_mm", "length_mm", "width_mm", "height_mm", "speed", "variant_code"):
        if fix.get(k) is not None:
            body[k] = fix[k]
    if fix.get("variant_code"):
        body["model_name"] = fix["variant_code"]
    else:
        body["variant_label"] = fix["family_name"]

    fam = fix.get("video_fam")
    if fam and videos_by_fam.get(fam):
        body["video_urls"] = videos_by_fam[fam][:2]
    return body


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--ids", type=int, nargs="*")
    args = ap.parse_args()

    targets = {
        rid: fix
        for rid, fix in FIXES.items()
        if not args.ids or rid in set(args.ids)
    }

    videos_by_fam: dict[str, list] = {}
    for fam, urls in VIDEO_URLS.items():
        videos_by_fam[fam] = enrich_video_list(urls)

    print(f"planned={len(targets)}")
    for rid, fix in sorted(targets.items()):
        print(f"  {rid} {fix['family_name']} url={fix['url'][-50:]} y={fix.get('year')}")

    if not args.apply:
        print("DRY-RUN — pass --apply to write")
        return 0

    client = ResearchApiClient()
    ok = fail = 0
    for rid, fix in sorted(targets.items()):
        body = build_body(fix, videos_by_fam)
        if fix.get("notes_append"):
            try:
                cur = client._get(f"robots/robots/{rid}/")
                notes = (cur.get("notes") or "").strip()
                note = fix["notes_append"]
                if note not in notes:
                    body["notes"] = (note + "\n---\n" + notes).strip() if notes else note
            except Exception as e:  # noqa: BLE001
                print(f"WARN notes fetch {rid}: {e}")
        try:
            patched = client._patch(f"robots/robots/{rid}/", body)
            narrative = {k: body[k] for k in NARRATIVE if body.get(k)}
            try:
                force_sync_zh(client, rid, narrative)
                sync = "zh-synced"
            except Exception as e:  # noqa: BLE001
                sync = f"zh-fail:{e}"
            print(
                f"ok {rid} fam={patched.get('family_key')} "
                f"y={patched.get('release_year')} p={patched.get('payload_kg')} "
                f"feat={len(patched.get('features') or '')} {sync}"
            )
            ok += 1
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL {rid}: {exc}")
            fail += 1
        time.sleep(0.12)

    print(f"DONE ok={ok} fail={fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
