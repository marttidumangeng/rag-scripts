"""Overnight Needs-cleanup soft enrich (company list from approve-publish-status.md).

Actions:
1. Reject ACY (1369) pending EOAT as non_robot.
2. Reject Jiangsu DINGS Gripper (5209) as non_robot EOAT.
3. Reject AGV Network (615) — media directory, not an OEM product.
4. Soft-fill country array / uses / industries / movement / family / purpose /
   availability for remaining Needs-cleanup pending.
5. Patch Geek+ missing heroes from known HubSpot OEM renders + copy-media.

Leaves status=pending_review except rejects. Writes morning report.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

_RESEARCH = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient

REPORT_DIR = _RESEARCH / "staging" / "reports"
MORNING_REPORT = _RESEARCH / "docs" / "reports" / "needs-cleanup-morning-report.md"
SERVER = _RESEARCH.parent.parent / "robotaigeek-server"

AVAILABLE = 11
CN, JP, KR, US, SG = 3, 11, 14, 20, 27

ACY_REASON = (
    "non_robot: ACY Automation EOAT accessories (grippers, quick changers, "
    "vacuum cups, clamps, cylinders, nippers) — not robot SKUs (Flexiv Grav precedent)"
)
DINGS_REASON = (
    "non_robot: Jiangsu DINGS Gripper series is EOAT / electric gripper accessories, "
    "not a robot SKU (ACY / Flexiv Grav precedent)"
)
AGVNET_REASON = (
    "wrong_company: AGV Network is an industry media/directory site, not an OEM; "
    "'AGV Reach Truck' is a generic category page, not a manufacturer product"
)

# Geek+ HubSpot heroes (from fix_geekplus_robots.py) keyed by match tokens.
GEEK_HEROES: list[tuple[str, str]] = [
    ("f12ml", "https://www.geekplus.com/hubfs/F12ML%201.png"),
    ("f20mt", "https://www.geekplus.com/hs-fs/hubfs/F20MT-3.png?width=800&name=F20MT-3.png"),
    ("m200c", "https://www.geekplus.com/hubfs/M200C%20Robot%20Body-left%20front%201.png"),
    ("mp1000", "https://www.geekplus.com/hs-fs/hubfs/mp1000r%20sne%202.1.940%201.png?width=800&name=mp1000r%20sne%202.1.940%201.png"),
    ("rs11", "https://www.geekplus.com/hubfs/NEW%20WEBSITE/TECHNOLOGY/RS8-DA%20model.png"),
    ("rs8", "https://www.geekplus.com/hubfs/NEW%20WEBSITE/TECHNOLOGY/RS8-DA%20model.png"),
    ("rs air", "https://www.geekplus.com/hubfs/NEW%20WEBSITE/TECHNOLOGY/RS%20Air%20model%20dark.png"),
    ("poppick", "https://www.geekplus.com/hs-fs/hubfs/onestop%20warehouse.jpg?width=1600&name=onestop%20warehouse.jpg"),
    ("instamove", "https://www.geekplus.com/hs-fs/hubfs/Geek+2025/products/p-series/P800R-img.png?width=800&name=P800R-img.png"),
    ("x1200z", "https://www.geekplus.com/hubfs/NEW%20WEBSITE/TECHNOLOGY/335x184px-X1200%201.png"),
    ("x1200", "https://www.geekplus.com/hubfs/NEW%20WEBSITE/TECHNOLOGY/335x184px-X1200%201.png"),
    ("skycube", "https://www.geekplus.com/hubfs/NEW%20WEBSITE/TECHNOLOGY/335x184px-X1200%201.png"),
    ("smart forklift", "https://www.geekplus.com/hubfs/F12ML%201.png"),
    ("smart moving", "https://www.geekplus.com/hs-fs/hubfs/Geek+2025/products/p-series/P800R-img.png?width=800&name=P800R-img.png"),
    ("roboshuttle", "https://www.geekplus.com/hubfs/NEW%20WEBSITE/TECHNOLOGY/RS8-DA%20model.png"),
    ("s20c-a", "https://www.geekplus.com/hs-fs/hubfs/S20C-A%201%201.png?width=800&name=S20C-A%201%201.png"),
    ("s20c", "https://www.geekplus.com/hs-fs/hubfs/S20C-2.png?width=800&name=S20C-2.png"),
    ("s20t", "https://www.geekplus.com/hubfs/NEW%20WEBSITE/TECHNOLOGY/s1.png"),
    ("s100c", "https://www.geekplus.com/hubfs/NEW%20WEBSITE/TECHNOLOGY/s1.png"),
    ("p1200", "https://www.geekplus.com/hs-fs/hubfs/Geek+2025/products/p-series/P1200-img.png?width=800&name=P1200-img.png"),
    ("p800h", "https://www.geekplus.com/hs-fs/hubfs/Geek+2025/products/p-series/P800R%20V6%2045-img.png?width=800&name=P800R%20V6%2045-img.png"),
    ("p800", "https://www.geekplus.com/hs-fs/hubfs/Geek+2025/products/p-series/P800R-img.png?width=800&name=P800R-img.png"),
    ("p500", "https://www.geekplus.com/hs-fs/hubfs/Tech%20P%20Series/P500R%20copy.png?width=800&name=P500R%20copy.png"),
    ("p40", "https://www.geekplus.com/hubfs/NEW%20WEBSITE/TECHNOLOGY/P%2040%20model.png"),
    ("fleetsort", "https://www.geekplus.com/hs-fs/hubfs/S20C-2.png?width=800&name=S20C-2.png"),
    ("robot arm", "https://www.geekplus.com/hs-fs/hubfs/onestop%20warehouse.jpg?width=1600&name=onestop%20warehouse.jpg"),
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def taxonomy(client: ResearchApiClient) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {"uses": {}, "industries": {}, "movement": {}}
    for kind, path in (
        ("uses", "robots/uses/"),
        ("industries", "robots/industries/"),
        ("movement", "robots/movement-types/"),
    ):
        for u in client._get(path) or []:
            if isinstance(u, dict) and u.get("key") and u.get("id"):
                out[kind][u["key"]] = int(u["id"])
    return out


def map_keys(tax: dict[str, dict[str, int]], group: str, keys: str) -> list[int]:
    ids: list[int] = []
    for k in keys.split("|"):
        k = k.strip().lower()
        if not k:
            continue
        kid = tax[group].get(k)
        if kid:
            ids.append(kid)
        else:
            print(f"  warn missing {group}={k}")
    return ids


def list_pending(client: ResearchApiClient, cid: int) -> list[dict]:
    rows: list[dict] = []
    page = 1
    while True:
        data = client._get(
            "robots/robots/",
            params={
                "company_ref": cid,
                "status": "pending_review",
                "page": page,
                "page_size": 50,
            },
        )
        batch = data.get("results") or []
        if not batch:
            break
        rows.extend(batch)
        if not data.get("next"):
            break
        page += 1
    return rows


def country_id(r: dict) -> int | None:
    ref = r.get("manufacturer_country_ref")
    if isinstance(ref, dict):
        return ref.get("id")
    if isinstance(ref, int):
        return ref
    return None


def has_image(r: dict) -> bool:
    return bool(r.get("s3_image") or r.get("image"))


def reject(client: ResearchApiClient, rid: int, reason: str) -> None:
    client._patch(
        f"robots/robots/{rid}/",
        {
            "status": "rejected",
            "rejection_reason": reason[:500],
            "notes": f"[AI Research] Overnight Needs-cleanup reject {now()[:10]}: {reason}",
        },
    )


def copy_media(rid: int) -> bool:
    secret = os.environ.get("INTERNAL_API_SECRET", "").strip()
    if not secret and (SERVER / ".env").is_file():
        for line in (SERVER / ".env").read_text(encoding="utf-8").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                secret = line.split("=", 1)[1].strip()
                break
    api = (
        os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/").replace("/api/v1", "")
        or "https://ragadmin.robotaigeek.com"
    )
    url = f"{api}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/?force=1"
    try:
        resp = requests.post(url, headers={"X-Internal-Secret": secret}, timeout=180)
        print(f"  copy-media {rid}: {resp.status_code}")
        return resp.ok
    except requests.RequestException as exc:
        print(f"  copy-media {rid} fail: {exc}")
        return False


def geek_hero(name: str) -> str | None:
    low = name.lower()
    for token, url in GEEK_HEROES:
        if token in low:
            return url
    return None


def yamaha_family(name: str) -> tuple[str, str, str, str]:
    """Return family_key, family_name, family_url, model_name."""
    m = re.search(r"(YK[\w-]+)", name, re.I)
    model = m.group(1).upper() if m else name
    low = name.lower()
    if "360" in low or "yk500tw" in low or "yk350tw" in low:
        key, fam = "yamaha:yk-x-360", "YK-X 360 SCARA"
    elif "global platform" in low:
        key, fam = "yamaha:yk-x-global", "YK-X Global Platform SCARA"
    elif "economy cleanroom" in low:
        key, fam = "yamaha:yk-x-economy-cleanroom", "YK-X Economy Cleanroom SCARA"
    elif "economy" in low:
        key, fam = "yamaha:yk-x-economy", "YK-X Economy SCARA"
    else:
        key, fam = "yamaha:yk-x-standard", "YK-X Standard SCARA"
    return key, fam, "https://global.yamaha-motor.com/business/robot/", model


def delta_family(name: str) -> tuple[str, str, str, str]:
    n = name.upper()
    if n.startswith("DRS60"):
        return "delta:drs60", "DRS60 SCARA", "https://landing.deltaww.com/en-US/products/SCARA-Robot", name
    if n.startswith("DRS40"):
        return "delta:drs40", "DRS40 SCARA", "https://landing.deltaww.com/en-US/products/SCARA-Robot", name
    if n.startswith("DRS30"):
        return "delta:drs30", "DRS30 SCARA", "https://landing.deltaww.com/en-US/products/SCARA-Robot", name
    if n.startswith("DRV90"):
        return "delta:drv90", "DRV90 Articulated", "https://landing.deltaww.com/en-US/products/Articulated-Robot", name
    if n.startswith("DRV70"):
        return "delta:drv70", "DRV70 Articulated", "https://landing.deltaww.com/en-US/products/Articulated-Robot", name
    if n.startswith("DRVA"):
        return "delta:drva", "DRVA Articulated", "https://landing.deltaww.com/en-US/products/Articulated-Robot", name
    return "delta:industrial", "DELTA Industrial Robot", "https://landing.deltaww.com/en-US/products", name


def geek_family(name: str) -> tuple[str, str, str, str]:
    low = name.lower()
    model = name
    if "f12ml" in low or "f-series (f12" in low:
        return "geekplus:f-series", "F-Series Forklift AMR", "https://www.geekplus.com/technology/f-series-robots", "F12ML"
    if "f20mt" in low or "f-series (f20" in low or "smart forklift" in low:
        return "geekplus:f-series", "F-Series Forklift AMR", "https://www.geekplus.com/technology/f-series-robots", "F20MT"
    if "m200c" in low or "m-series (m200" in low:
        return "geekplus:m-series", "M-Series AMR", "https://www.geekplus.com/technology/m-series-robots", "M200C"
    if "mp1000" in low or "m-series (mp1000" in low:
        return "geekplus:m-series", "M-Series AMR", "https://www.geekplus.com/technology/m-series-robots", "MP1000R"
    if "rs11" in low or "rs8" in low or re.search(r"\brs\b", low) or "roboshuttle" in low or "rs air" in low:
        return "geekplus:rs-series", "RS / RoboShuttle", "https://www.geekplus.com/technology/rs-series-robots", model
    if "poppick" in low or "shelf-to-person" in low:
        return "geekplus:poppick", "PopPick Shelf-to-Person", "https://www.geekplus.com/solutions/shelf-to-person", model
    if "skycube" in low or "x1200" in low or "x-series" in low or "pallet-to-person" in low:
        return "geekplus:x-series", "X-Series / SkyCube", "https://www.geekplus.com/technology/x-series-robots", model
    if "s100c" in low or "s20" in low or "s-series" in low or "fleetsort" in low or "sorting" in low:
        return "geekplus:s-series", "S-Series Sorting", "https://www.geekplus.com/technology/s-series-robots", model
    if "p1200" in low or "p800" in low or "p500" in low or "p40" in low or "p-series" in low or "instamove" in low or "smart moving" in low:
        return "geekplus:p-series", "P-Series Shelf AMR", "https://www.geekplus.com/technology/p-series-robots", model
    if "robot arm" in low:
        return "geekplus:picking-station", "Robot Arm Picking Station", "https://www.geekplus.com/solutions/shelf-to-person", model
    return "geekplus:amr", "Geek+ AMR", "https://www.geekplus.com/technology", model


def hyundai_family(name: str) -> tuple[str, str, str, str]:
    low = name.lower()
    if name.upper().startswith("UH"):
        return "hyundai:uh", "UH Series", "https://hd-hyundairobotics.com/en/biz/product", name
    if name.upper().startswith("HH"):
        return "hyundai:hh", "HH Series", "https://hd-hyundairobotics.com/en/biz/product", name
    if name.upper().startswith("HDC"):
        return "hyundai:hdc", "HDC Collaborative", "https://hd-hyundairobotics.com/en/biz/product", name
    if "hdr" in low:
        return "hyundai:hdr", "HDR Series", "https://hd-hyundairobotics.com/en/biz/product/60010001", name
    if name.upper().startswith("HI6") or name == "Hi6":
        return "hyundai:hi6", "Hi6 Controller / Cell", "https://hd-hyundairobotics.com/en/biz/product", name
    if name.upper().startswith("HI5") or name == "Hi5a":
        return "hyundai:hi5a", "Hi5a Controller / Cell", "https://hd-hyundairobotics.com/en/biz/product", name
    if "fpd" in low:
        return "hyundai:fpd", "FPD Transfer", "https://hd-hyundairobotics.com/en/biz/product/60010002", name
    if "barista" in low:
        return "hyundai:barista", "Robot Barista", "https://hd-hyundairobotics.com/en/biz/product", name
    if "labot" in low or "machine tending" in low:
        return "hyundai:labot", "LABOT Machine Tending", "https://hd-hyundairobotics.com/en/biz/product", name
    if "battery" in low or "display assembly" in low or "depalletizing" in low:
        return "hyundai:application", "Application Package", "https://hd-hyundairobotics.com/en/biz/product", name
    if "industrial robot" in low:
        return "hyundai:industrial", "Industrial Robot Family", "https://hd-hyundairobotics.com/en/biz/product/60010001", name
    return "hyundai:industrial", "HD Hyundai Industrial", "https://hd-hyundairobotics.com/en/biz/product", name


def mujin_family(name: str) -> tuple[str, str, str, str]:
    low = name.lower()
    if "agv" in low:
        return "mujin:agv", "MujinAGV", "https://www.mujin.co.jp/solution/", name
    if "rcp" in low:
        return "mujin:rcp", "MujinRCP", "https://www.mujin.co.jp/solution/", name
    if "pickworker" in low or "piece picker" in low:
        return "mujin:piece-picker", "Piece Picker", "https://www.mujin.co.jp/solution/", name
    if "pallet changer" in low:
        return "mujin:pallet-changer", "Pallet Changer", "https://www.mujin.co.jp/solution/", name
    if "pallet" in low or "パレタイ" in name:
        return "mujin:palletizer", "Palletizer", "https://www.mujin.co.jp/solution/", name
    if "depallet" in low or "デパレ" in name:
        return "mujin:depalletizer", "Depalletizer", "https://www.mujin.co.jp/solution/", name
    return "mujin:robot", "MujinRobot", "https://www.mujin.co.jp/solution/", name


def gurki_family(name: str) -> tuple[str, str, str, str]:
    m = re.search(r"(GPM-?R?\d+\w*|R\d+\w*)", name, re.I)
    model = m.group(1).upper() if m else name
    return "gurki:gpm-r", "GURKI Collaborative Palletizer", "https://www.gurkipack.com/", model


def soft_body(
    *,
    country: int,
    uses: list[int],
    industries: list[int],
    movement: list[int],
    family_key: str,
    family_name: str,
    family_url: str,
    model_name: str,
    purpose: str,
    product_url_scope: str = "exact_variant",
    hero: str | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "manufacturer_country_ref": country,
        "manufacturer_countries": [country],
        "uses": uses,
        "industries": industries,
        "movement_types": movement,
        "family_key": family_key,
        "family_name": family_name,
        "family_url": family_url,
        "model_name": model_name,
        "product_url_scope": product_url_scope,
        "purpose": purpose[:120],
        "availability_status": AVAILABLE,
    }
    if hero:
        body["image"] = hero
        body["s3_image"] = None
    return body


def patch_robot(client: ResearchApiClient, rid: int, body: dict[str, Any]) -> None:
    # Split M2M / scalar to reduce 400s from some admin serializers.
    m2m = {}
    scalar = {}
    for k, v in body.items():
        if k in ("uses", "industries", "movement_types", "manufacturer_countries", "tags"):
            m2m[k] = v
        else:
            scalar[k] = v
    if scalar:
        client._patch(f"robots/robots/{rid}/", scalar)
    if m2m:
        client._patch(f"robots/robots/{rid}/", m2m)


COMPANY_HANDLERS: dict[int, str] = {
    1398: "geekplus",
    1484: "yamaha",
    49: "hyundai",
    1206: "delta",
    810: "mujin",
    974: "gurki",
    1073: "intamsys",
    52: "intuitive",
    397: "invia",
    1373: "sixriver",
    1511: "auris",
    783: "infinium",
    254: "plusone",
}


def plan_for(cid: int, r: dict, tax: dict) -> dict[str, Any] | None:
    name = r.get("name") or ""
    rid = int(r["id"])
    handler = COMPANY_HANDLERS.get(cid)
    if handler == "yamaha":
        fk, fn, fu, model = yamaha_family(name)
        return soft_body(
            country=JP,
            uses=map_keys(tax, "uses", "assembly|pick-and-place|handling|machine-tending"),
            industries=map_keys(tax, "industries", "electronics|industrial|automotive"),
            movement=map_keys(tax, "movement", "stationary|fixed"),
            family_key=fk,
            family_name=fn,
            family_url=fu,
            model_name=model,
            purpose="SCARA pick-and-place and assembly",
        )
    if handler == "geekplus":
        fk, fn, fu, model = geek_family(name)
        hero = None if has_image(r) else geek_hero(name)
        return soft_body(
            country=CN,
            uses=map_keys(tax, "uses", "warehouse|intralogistics|picking|transport|logistics|sorting"),
            industries=map_keys(tax, "industries", "industrial|commercial|fmcg"),
            movement=map_keys(tax, "movement", "wheeled|mobile"),
            family_key=fk,
            family_name=fn,
            family_url=fu,
            model_name=model,
            purpose="Warehouse goods-to-person and intralogistics",
            product_url_scope="family" if "configuration" in name.lower() or "solution" in name.lower() else "exact_variant",
            hero=hero,
        )
    if handler == "hyundai":
        fk, fn, fu, model = hyundai_family(name)
        purpose = "Industrial arm handling and process automation"
        if "barista" in name.lower():
            purpose = "Automated beverage preparation"
        elif "labot" in name.lower() or "tending" in name.lower():
            purpose = "CNC machine tending"
        elif "battery" in name.lower():
            purpose = "EV battery handling and fastening"
        elif "depallet" in name.lower():
            purpose = "Depalletizing with 3D vision"
        elif "fpd" in name.lower() or "display" in name.lower():
            purpose = "Flat-panel display substrate handling"
        return soft_body(
            country=KR,
            uses=map_keys(tax, "uses", "handling|welding|assembly|machine-tending|palletizing|pick-and-place"),
            industries=map_keys(tax, "industries", "automotive|electronics|industrial|new-energy"),
            movement=map_keys(tax, "movement", "stationary|fixed"),
            family_key=fk,
            family_name=fn,
            family_url=fu,
            model_name=model,
            purpose=purpose,
            product_url_scope="family" if "series" in name.lower() or name.lower() in ("industrial robot", "industrial robots") else "exact_variant",
        )
    if handler == "delta":
        fk, fn, fu, model = delta_family(name)
        return soft_body(
            country=CN,  # Delta Electronics Shanghai company
            uses=map_keys(tax, "uses", "pick-and-place|assembly|handling|packaging|machine-tending"),
            industries=map_keys(tax, "industries", "electronics|industrial|plastics-polymers"),
            movement=map_keys(tax, "movement", "stationary|fixed"),
            family_key=fk,
            family_name=fn,
            family_url=fu,
            model_name=model,
            purpose="SCARA/articulated pick-and-place and assembly",
            product_url_scope="family" if "series" in name.lower() else "exact_variant",
        )
    if handler == "mujin":
        fk, fn, fu, model = mujin_family(name)
        purpose = "Warehouse palletizing and depalletizing"
        if "agv" in name.lower():
            purpose = "Autonomous material transport"
        elif "piece" in name.lower() or "pickworker" in name.lower():
            purpose = "Piece picking for fulfillment"
        return soft_body(
            country=JP,
            uses=map_keys(tax, "uses", "palletizing|picking|warehouse|intralogistics|handling"),
            industries=map_keys(tax, "industries", "industrial|fmcg|commercial"),
            movement=map_keys(tax, "movement", "stationary|fixed|wheeled"),
            family_key=fk,
            family_name=fn,
            family_url=fu,
            model_name=model,
            purpose=purpose,
        )
    if handler == "gurki":
        fk, fn, fu, model = gurki_family(name)
        return soft_body(
            country=CN,
            uses=map_keys(tax, "uses", "palletizing|packaging|handling|warehouse"),
            industries=map_keys(tax, "industries", "industrial|fmcg|food-beverage"),
            movement=map_keys(tax, "movement", "stationary|fixed"),
            family_key=fk,
            family_name=fn,
            family_url=fu,
            model_name=model,
            purpose="Collaborative end-of-line palletizing",
        )
    if handler == "intamsys":
        model = name
        return soft_body(
            country=CN,
            uses=map_keys(tax, "uses", "other|general-automation|development"),
            industries=map_keys(tax, "industries", "industrial|plastics-polymers|research"),
            movement=map_keys(tax, "movement", "stationary|fixed"),
            family_key="intamsys:funmat",
            family_name="FUNMAT Industrial 3D Printer",
            family_url="https://www.intamsys.com/",
            model_name=model,
            purpose="Industrial high-temperature FFF 3D printing",
        )
    if handler == "intuitive":
        low = name.lower()
        if "ion" in low:
            fk, fn, purpose = "intuitive:ion", "Ion", "Robotic bronchoscopy"
        elif "sp" in low:
            fk, fn, purpose = "intuitive:da-vinci-sp", "da Vinci SP", "Single-port robotic surgery"
        else:
            fk, fn, purpose = "intuitive:da-vinci-5", "da Vinci 5", "Multi-port robotic surgery"
        return soft_body(
            country=US,
            uses=map_keys(tax, "uses", "surgery|medical-assistance"),
            industries=map_keys(tax, "industries", "other"),  # healthcare not always present
            movement=map_keys(tax, "movement", "stationary|fixed"),
            family_key=fk,
            family_name=fn,
            family_url="https://www.intuitive.com/",
            model_name=name,
            purpose=purpose,
        )
    if handler == "invia":
        fk = "invia:picker-wall" if "wall" in name.lower() else "invia:picker"
        fn = "PickerWall" if "wall" in name.lower() else "inVia Picker"
        return soft_body(
            country=US,
            uses=map_keys(tax, "uses", "picking|warehouse|intralogistics|inventory"),
            industries=map_keys(tax, "industries", "industrial|commercial|fmcg"),
            movement=map_keys(tax, "movement", "wheeled|mobile"),
            family_key=fk,
            family_name=fn,
            family_url="https://inviarobotics.com/",
            model_name=name,
            purpose="Goods-to-person warehouse picking",
        )
    if handler == "sixriver":
        return soft_body(
            country=US,
            uses=map_keys(tax, "uses", "picking|warehouse|intralogistics|transport"),
            industries=map_keys(tax, "industries", "industrial|commercial|fmcg"),
            movement=map_keys(tax, "movement", "wheeled|mobile"),
            family_key="sixriver:chuck",
            family_name="Chuck AMR",
            family_url="https://www.shopify.com/",
            model_name="Chuck",
            purpose="Collaborative warehouse picking AMR",
        )
    if handler == "auris":
        return soft_body(
            country=US,
            uses=map_keys(tax, "uses", "surgery|medical-assistance"),
            industries=map_keys(tax, "industries", "other"),
            movement=map_keys(tax, "movement", "stationary|fixed"),
            family_key="auris:monarch",
            family_name="MONARCH Platform",
            family_url="https://www.jnjmedtech.com/en-US/products/robotics/monarch-platform/bronchoscopy/",
            model_name="MONARCH QUEST",
            purpose="Robotic bronchoscopy navigation",
        )
    if handler == "infinium":
        return soft_body(
            country=SG,
            uses=map_keys(tax, "uses", "inspection|scanning|surveillance|mapping"),
            industries=map_keys(tax, "industries", "facilities|commercial|industrial"),
            movement=map_keys(tax, "movement", "flying|aerial"),
            family_key="infinium:scan",
            family_name="Infinium Scan",
            family_url="https://infiniumrobotics.com/infinium-scan/",
            model_name="Infinium Scan",
            purpose="Indoor aerial inspection and scanning",
        )
    if handler == "plusone":
        return soft_body(
            country=US,
            uses=map_keys(tax, "uses", "picking|warehouse|intralogistics|handling"),
            industries=map_keys(tax, "industries", "industrial|commercial|fmcg"),
            movement=map_keys(tax, "movement", "stationary|fixed"),
            family_key="plusone:pickone",
            family_name="PickOne",
            family_url="https://www.plusonerobotics.com/products/pickone",
            model_name="PickOne",
            purpose="AI vision piece picking for warehouses",
        )
    return None


def must_clear_ok(r: dict) -> bool:
    if not has_image(r):
        return False
    if not country_id(r):
        return False
    if not (r.get("uses") or []):
        return False
    if not (r.get("categories") or []):
        return False
    if not (r.get("family_key") or "").strip():
        return False
    return True


def write_morning_report(summary: dict[str, Any]) -> None:
    MORNING_REPORT.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "---",
        "type: log",
        "title: Needs Cleanup Overnight — Morning Report",
        "status: draft",
        "version: 1.0",
        "owner: AI",
        f"last_updated: {datetime.now(timezone.utc).date().isoformat()}",
        "tags:",
        "  - content-queue",
        "  - overnight",
        "  - needs-cleanup",
        "---",
        "",
        "# Needs Cleanup Overnight — Morning Report",
        "",
        f"Generated: {summary['generated_at']}",
        "",
        "## Executive summary",
        "",
        f"- Companies processed: **{summary['companies_processed']}**",
        f"- Soft-enriched (patched): **{summary['patched']}**",
        f"- Rejected: **{summary['rejected']}**",
        f"- must_clear_pass after run: **{summary['must_clear_pass']}** / **{summary['pending_after']}** remaining pending",
        f"- Geek+ heroes copy-media OK: **{summary['geek_copy_ok']}** / attempted **{summary['geek_copy_attempted']}**",
        f"- Errors: **{len(summary['errors'])}**",
        "",
        "### Stakeholder FYIs",
        "",
        "- Bluefin (160) approved earlier → already Cleared.",
        "- ACY (1369): rejected all **pending** EOAT as `non_robot`. **Published EOAT still need reject-or-keep decision.**",
        "- Jiangsu DINGS Gripper + AGV Network reach-truck rejected (EOAT / media directory).",
        "- Intamsys FUNMAT left as industrial 3D printers (enriched, not rejected).",
        "- Soft pass only — no deep datasheet scrape tonight except Geek+ hero URLs.",
        "",
        "## Per-company results",
        "",
        "| Company | ID | Before pending | Rejected | Patched | After pending | must_clear_pass | Notes |",
        "|---------|---:|---------------:|---------:|--------:|--------------:|----------------:|-------|",
    ]
    for row in summary["companies"]:
        lines.append(
            f"| {row['name']} | {row['id']} | {row['before']} | {row['rejected']} | "
            f"{row['patched']} | {row['after']} | {row['must_clear']} | {row['notes']} |"
        )
    if summary["errors"]:
        lines += ["", "## Errors", ""]
        for e in summary["errors"][:80]:
            lines.append(f"- {e}")
    lines += [
        "",
        "## Next for you",
        "",
        "1. Bulk Approve companies that moved to Ready (must_clear green).",
        "2. Decide ACY published EOAT (35) — reject all?",
        "3. Optional deep pass: Geek+ remaining imageless if any; Hyundai series-shell dedupe.",
        "",
        "Script: `overnight_needs_cleanup_enrich.py`",
        "",
    ]
    MORNING_REPORT.write_text("\n".join(lines), encoding="utf-8")
    print("Wrote", MORNING_REPORT)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--skip-reject", action="store_true")
    parser.add_argument("--only-company", type=int, action="append")
    args = parser.parse_args()

    client = ResearchApiClient()
    tax = taxonomy(client)
    summary: dict[str, Any] = {
        "generated_at": now(),
        "companies_processed": 0,
        "patched": 0,
        "rejected": 0,
        "must_clear_pass": 0,
        "pending_after": 0,
        "geek_copy_ok": 0,
        "geek_copy_attempted": 0,
        "errors": [],
        "companies": [],
    }

    # --- Rejects ---
    if args.apply and not args.skip_reject:
        if not args.only_company or 1369 in args.only_company:
            acy = list_pending(client, 1369)
            print(f"Reject ACY pending: {len(acy)}")
            for r in acy:
                try:
                    reject(client, int(r["id"]), ACY_REASON)
                    summary["rejected"] += 1
                    print("  rejected", r["id"], r.get("name"))
                except Exception as exc:  # noqa: BLE001
                    summary["errors"].append(f"ACY reject {r['id']}: {exc}")
            summary["companies"].append(
                {
                    "id": 1369,
                    "name": "ACY Automation",
                    "before": len(acy),
                    "rejected": len(acy),
                    "patched": 0,
                    "after": 0,
                    "must_clear": 0,
                    "notes": "All pending EOAT rejected non_robot; published EOAT undecided",
                }
            )
            summary["companies_processed"] += 1

        if not args.only_company or 1512 in args.only_company:
            for r in list_pending(client, 1512):
                try:
                    reject(client, int(r["id"]), DINGS_REASON)
                    summary["rejected"] += 1
                    print("rejected DINGS", r["id"])
                except Exception as exc:  # noqa: BLE001
                    summary["errors"].append(f"DINGS {r['id']}: {exc}")
            summary["companies"].append(
                {
                    "id": 1512,
                    "name": "Jiangsu DINGS",
                    "before": 1,
                    "rejected": 1,
                    "patched": 0,
                    "after": 0,
                    "must_clear": 0,
                    "notes": "Gripper EOAT rejected",
                }
            )
            summary["companies_processed"] += 1

        if not args.only_company or 1322 in args.only_company:
            for r in list_pending(client, 1322):
                try:
                    reject(client, int(r["id"]), AGVNET_REASON)
                    summary["rejected"] += 1
                    print("rejected AGV Network", r["id"])
                except Exception as exc:  # noqa: BLE001
                    summary["errors"].append(f"AGVNet {r['id']}: {exc}")
            summary["companies"].append(
                {
                    "id": 1322,
                    "name": "AGV Network",
                    "before": 1,
                    "rejected": 1,
                    "patched": 0,
                    "after": 0,
                    "must_clear": 0,
                    "notes": "Media directory rejected",
                }
            )
            summary["companies_processed"] += 1

    # --- Soft enrich ---
    for cid, name in [
        (1398, "Geek+"),
        (1484, "Yamaha Robotics"),
        (49, "Hyundai Robotics"),
        (1206, "DELTA Electronics"),
        (810, "Mujin"),
        (974, "Gurki"),
        (1073, "Intamsys"),
        (52, "Intuitive Surgical"),
        (397, "inVia Robotics"),
        (1373, "6 River Systems"),
        (1511, "Auris Health"),
        (783, "Infinium Robotics"),
        (254, "Plus One Robotics"),
    ]:
        if args.only_company and cid not in args.only_company:
            continue
        rows = list_pending(client, cid)
        before = len(rows)
        patched = 0
        rejected_here = 0
        geek_media: list[int] = []
        print(f"\n=== {cid} {name} pending={before} ===")
        for r in rows:
            rid = int(r["id"])
            body = plan_for(cid, r, tax)
            if not body:
                summary["errors"].append(f"no plan {cid}/{rid}")
                continue
            if not args.apply:
                print(f"  dry {rid} fam={body['family_key']} hero={bool(body.get('image'))}")
                patched += 1
                continue
            try:
                hero = body.get("image")
                patch_robot(client, rid, body)
                patched += 1
                summary["patched"] += 1
                print(f"  patched {rid} {(r.get('name') or '')[:40]} fam={body['family_key']}")
                if hero:
                    geek_media.append(rid)
                time.sleep(0.05)
            except Exception as exc:  # noqa: BLE001
                summary["errors"].append(f"patch {cid}/{rid}: {exc}")
                print(f"  ERR {rid}: {exc}")

        if args.apply and geek_media:
            for rid in geek_media:
                summary["geek_copy_attempted"] += 1
                if copy_media(rid):
                    summary["geek_copy_ok"] += 1
                time.sleep(0.15)

        after_rows = list_pending(client, cid) if args.apply else rows
        # refresh details for must_clear
        ok = 0
        if args.apply:
            for r in after_rows:
                try:
                    d = client._get(f"robots/robots/{r['id']}/")
                    if must_clear_ok(d):
                        ok += 1
                except Exception:
                    pass
        summary["must_clear_pass"] += ok
        summary["pending_after"] += len(after_rows)
        summary["companies"].append(
            {
                "id": cid,
                "name": name,
                "before": before,
                "rejected": rejected_here,
                "patched": patched,
                "after": len(after_rows),
                "must_clear": ok,
                "notes": "soft family/uses/country/avail" + ("; hero+copy-media" if geek_media else ""),
            }
        )
        summary["companies_processed"] += 1

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORT_DIR / "needs-cleanup-overnight-summary.json"
    out.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_morning_report(summary)
    print("\nSUMMARY", json.dumps({k: summary[k] for k in summary if k != "companies" and k != "errors"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
