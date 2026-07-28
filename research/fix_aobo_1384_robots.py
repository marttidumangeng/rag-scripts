"""Fix Aobo Robot (company 1384) content-queue enrichment.

OEM: https://www.aoborobot.com/en/robot-en/

Issues addressed:
- 43 pending_review robots, all feat=0 / no family_key / no typed specs
- URL duplicates between 16xx AoBo-prefixed names and cleaner 19xx/20xx keepers
- Shared CDN hero hash 1df11ec2e4e6 = Service_en.jpg site banner — replace with
  distinct OEM product renders (*-r1.jpg / series ui/1.jpg)
- 1616 Daikin wrongly points at dipan.html (chassis) — reject as duplicate of 1991
- KaKa Welcome (1993) shares OEM hero bytes with KaKa Transport (1997) — imageless
- EN PDPs are sparse; specs from OEM *_parameter-pc_en / des/*.jpg sheets
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import requests

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient
from import_staging import resolve_created_by_id
from map_to_bulk_import import staging_dict_to_bulk_import_row
from robot_auto_research import slugify_robot_name
from tag_suggest import TagCatalog
from youtube_metadata import enrich_video_list

COMPANY_ID = 1384
COMPANY_SLUG = "aobo-robot"
COMPANY_NAME = "Aobo Robot"
CN = "CN"
OEM = "https://www.aoborobot.com"
EN = f"{OEM}/en/robot-en"
IMG = f"{OEM}/image/robot"
PREVIEW = _RESEARCH_DIR / "staging" / "reports" / "aobo-1384-fix-preview.json"
REPORT = _RESEARCH_DIR / "staging" / "reports" / "aobo-1384-enrichment.md"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

_AVAIL_IDS = {
    "announced": 10,
    "available": 11,
    "released": 3,
    "discontinued": 4,
    "pre_order": 12,
}

# YouTube — title-filtered AoBo OEM clips only.
YT_BENBEN = "https://www.youtube.com/watch?v=Y894EMX9pqw"
YT_BENBEN2 = "https://www.youtube.com/watch?v=fI1BIBGrTKs"
YT_BENBEN3 = "https://www.youtube.com/watch?v=y1wg44zlOmw"
YT_KAKA = "https://www.youtube.com/watch?v=IvhSiDwelaQ"
YT_YINYIN = "https://www.youtube.com/watch?v=siDkke2AdaM"
YT_XIAOAN = "https://www.youtube.com/watch?v=8JxHdGCYY1s"
YT_DISINFECT = "https://www.youtube.com/watch?v=HEImbfSw4n4"
YT_DELIVERY = "https://www.youtube.com/watch?v=Wdl83rMv9a4"
YT_TESTS = "https://www.youtube.com/watch?v=cavy5hXxr7o"
YT_PUBLIC = "https://www.youtube.com/watch?v=Pz2vhqTxO4c"

TAGS_WELCOME = "Service Robot|Reception|Reception Robot|Wheeled|AMR|Indoor|Hospitality|Customer Service"
TAGS_DELIVERY = "Service Robot|Delivery|AMR|Wheeled|Indoor|Hospitality|Indoor Delivery|food"
TAGS_PATROL = "Service Robot|Security|Security Robot|Patrol|AMR|Wheeled|Indoor|Autonomous"
TAGS_DISINFECT = "Service Robot|Cleaning|AMR|Wheeled|Indoor|Hospital|Medical"
TAGS_EDU = "Service Robot|Education|Wheeled|AMR|Indoor"
TAGS_CHASSIS = "AMR|Mobile Robot|Wheeled|Indoor|Autonomous Mobile Robot"
TAGS_RECEPTION = "Service Robot|Reception|Reception Robot|Wheeled|AMR|Indoor|Hospitality|Customer Service"

APPS_WELCOME = (
    "Bank lobby greeting\n"
    "Government hall reception\n"
    "Hospital wayfinding\n"
    "Library information desk\n"
    "Shopping center greeting\n"
    "Automotive 4S showroom reception"
)
APPS_DELIVERY = (
    "Hotel room delivery\n"
    "Hospital item transport\n"
    "Restaurant food delivery\n"
    "Banquet hall service\n"
    "Business building delivery\n"
    "Library document transport"
)
APPS_PATROL = (
    "Indoor security patrol\n"
    "Facility inspection rounds\n"
    "Public-area monitoring"
)
APPS_DISINFECT = (
    "Hospital disinfection\n"
    "Public facility UV/spray disinfection\n"
    "Indoor pathogen reduction rounds"
)
APPS_EDU = (
    "Educational programming\n"
    "STEM classroom demonstration\n"
    "Robotics training"
)
APPS_CHASSIS = (
    "Mobile robot base platform\n"
    "Custom service robot development\n"
    "Indoor autonomous navigation chassis"
)
APPS_RECEPTION_GEN3 = (
    "Science and technology museum greeting\n"
    "Showroom and exhibition hall reception\n"
    "University campus guidance\n"
    "Shopping mall greeting\n"
    "Government service center reception\n"
    "Hospital and bank lobby guidance"
)
APPS_FOOD_GEN3 = (
    "Restaurant table delivery\n"
    "Hotel food service\n"
    "Supermarket and mall delivery\n"
    "School and office catering delivery\n"
    "Hospital meal transport"
)

# Reject 16xx AoBo-prefixed URL duplicates → keep cleaner 19xx/20xx IDs.
REJECTS: dict[int, str] = {
    1613: "Duplicate of robot 2007 (DaBai Robot). Same OEM PDP dabai.html; keep the cleaner short-name record.",
    1629: "Duplicate of robot 2006 (XiaoAn Robot). Same OEM PDP xiaoan.html; keep the cleaner short-name record.",
    1621: "Duplicate of robot 2005 (LanDou Robot). Same OEM PDP landou.html; keep the cleaner short-name record.",
    1619: "Duplicate of robot 2004 (HuanHuan Robot). Same OEM PDP huanhuan.html; keep the cleaner short-name record.",
    1622: "Duplicate of robot 2003 (LeLe Robot). Same OEM PDP lele.html; keep the cleaner short-name record.",
    1615: "Duplicate of robot 2002 (DaJin Robot). Same OEM PDP dajin.html; keep the cleaner short-name record.",
    1628: "Duplicate of robot 2001 (SuanTou Robot). Same OEM PDP suantou.html; keep the cleaner short-name record.",
    1633: "Duplicate of robot 2000 (Disinfect Benben UV). Same OEM PDP ziwaixianbanxiaodubenben.html; keep the cleaner short-name record.",
    1624: "Duplicate of robot 1999 (Disinfect Benben spray). Same OEM PDP penwubanxiaodubenben.html; keep the cleaner short-name record.",
    1623: "Duplicate of robot 1998 (PeiPei Robot). Same OEM PDP peipei.html; keep the cleaner short-name record.",
    1620: "Duplicate of robot 1997 (KaKa Transport). Same OEM PDP kaka.html; keep the cleaner short-name record.",
    1630: "Duplicate of robot 1996 (XiaoAo Robot). Same OEM PDP xiaoao.html; keep the cleaner short-name record.",
    1632: "Duplicate of robot 1995 (YinYin Robot). Same OEM PDP yinyin.html; keep the cleaner short-name record.",
    1612: "Duplicate of robot 1994 (Doctor Robot). Same OEM PDP boshi.html; keep the cleaner short-name record.",
    1631: "Duplicate of robot 1993 (KaKa Welcome). Same OEM PDP yingbinbankaka.html; keep the cleaner short-name record.",
    1611: "Duplicate of robot 1992 (Ben Ben Robot). Same OEM PDP benben.html; keep the cleaner short-name record.",
    1614: "Duplicate of robot 1989 (DaBen Robot). Same OEM PDP daben.html; keep the cleaner short-name record.",
    1616: (
        "Duplicate / wrong product of robot 1991 (Robot Chassis). URL is dipan.html "
        "(OEM chassis platform with dipan-* assets). Record was misnamed 'Daikin Service "
        "Welcome Robot' (CMS H2 also wrong). Keep 1991 as the chassis SKU; do not enrich "
        "a welcome robot under this URL."
    ),
}

IMAGE_TODO_KAKA_WELCOME = (
    "[IMAGE TO-DO — no hero, deliberate]\n"
    "OEM welcome KaKa PDP (yingbinbankaka.html) reuses the same /image/robot/kaka/ "
    "product renders as KaKa Transport (kaka.html); r1–r5 content-hash collide with "
    "keeper 1997. Checked EN PDP 2026-07-29; no distinct welcome-only hero on OEM.\n"
    "Previously held shared Service_en.jpg site banner (CDN hash 1df11ec2e4e6) — removed.\n"
    "ACTION FOR TEAM: request a welcome-variant-specific licensed render from Aobo, "
    "or merge 1993 into 1997 if product is one SKU with two configs.\n"
    "Do NOT substitute a sibling render, a family banner, or marketing/diagram art.\n"
    "---\n"
)


def pdp(slug: str) -> str:
    return f"{EN}/{slug}.html"


def hero(path: str) -> str:
    return f"{IMG}/{path}"


def battery_wh_24v15() -> float:
    return 24.0 * 15.0  # OEM cites 24V15AH polymer lithium


def fix(
    *,
    name: str,
    model: str,
    series: str,
    family_name: str,
    url: str,
    image: str | None,
    description: str,
    purpose: str,
    features: str,
    tags: str,
    weight_kg: float | None = None,
    height_mm: float | None = None,
    width_mm: float | None = None,
    payload_kg: float | None = None,
    speed: float | None = None,
    runtime_minutes: int | None = None,
    battery_wh: float | None = None,
    dof: int | None = None,
    uses: str = "reception",
    industry: str = "hospitality|commercial",
    category: str = "service-robots",
    sub: str | None = None,
    videos: list[str] | None = None,
    notes_extra: str = "",
    imageless_note: str | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "name": name,
        "model_name": model,
        "variant_code": model,
        "variant_label": model,
        "family_key": f"{COMPANY_SLUG}:{series}",
        "family_name": family_name,
        "family_url": url,
        "product_url_scope": "exact_variant",
        "url": url,
        "description": description,
        "purpose": purpose,
        "features": features,
        "availability_status_key": "available",
        "movement_type_keys": "wheeled",
        "industry_keys": industry,
        "use_keys": uses,
        "category_slugs": category,
        "tags": tags,
        "manufacturer_country_code": CN,
        "videos": videos or [],
        "information_source_urls": [url],
        "notes_force": (
            f"[AI Research] OEM EN PDP {url}. Specs from OEM Function Parameter / "
            f"product datasheet images on aoborobot.com when cited. "
            f"Hero: distinct OEM product asset (replaced shared Service_en.jpg CDN collision). "
            f"{notes_extra}"
        ).strip(),
        "source_note": f"{url} — Aobo Robot OEM EN product page",
    }
    if sub:
        row["sub_category_slug"] = sub
    if image:
        row["image"] = image
    if weight_kg is not None:
        row["weight_kg"] = weight_kg
        row["weight"] = f"{weight_kg:g} kg"
    if height_mm is not None:
        row["height_mm"] = height_mm
    if width_mm is not None:
        row["width_mm"] = width_mm
    if payload_kg is not None:
        row["payload_kg"] = payload_kg
    if speed is not None:
        row["speed"] = speed
    if runtime_minutes is not None:
        row["runtime_minutes"] = runtime_minutes
    if battery_wh is not None:
        row["battery_wh"] = battery_wh
    if dof is not None:
        row["dof"] = dof
    if imageless_note:
        row["image"] = None
        row["notes_force"] = imageless_note + (row.get("notes_force") or "")
        row["imageless"] = True
    return row


COMMON_FEAT = (
    "WiFi + 4G + Bluetooth networking; automatic docking charge plus manual recharge; "
    "polymer lithium battery pack; plastic + fiberglass + steel-plate construction; "
    "touch / remote / voice operation modes where listed on OEM Function Parameter sheet."
)


ROBOT_FIXES: dict[int, dict[str, Any]] = {
    # --- Welcome series ---
    2007: fix(
        name="DaBai Robot",
        model="DaBai",
        series="welcome",
        family_name="AoBo Welcome Service Robots",
        url=pdp("dabai"),
        image=hero("dabai/dabai-r1.jpg"),
        description=(
            "DaBai is Aobo Robot's wheeled welcome service robot with a chest touchscreen, "
            "humanoid upper body, and indoor autonomous base for lobby greeting and information."
        ),
        purpose=APPS_WELCOME,
        features=(
            f"160 cm height; 45 kg weight; 24V 15Ah polymer lithium battery (~9 h runtime). "
            f"{COMMON_FEAT} Color customizable; one-year free warranty per OEM PDP."
        ),
        tags=TAGS_WELCOME,
        weight_kg=45,
        height_mm=1600,
        runtime_minutes=540,
        battery_wh=battery_wh_24v15(),
        uses="reception",
        videos=[YT_PUBLIC, YT_TESTS],
        notes_extra="Parameter sheet dabai_parameter-pc_en_01.jpg.",
    ),
    2005: fix(
        name="LanDou Robot",
        model="LanDou",
        series="welcome",
        family_name="AoBo Welcome Service Robots",
        url=pdp("landou"),
        image=hero("landou/landou-r1.jpg"),
        description=(
            "LanDou is an Aobo wheeled welcome service robot with a blue metallic finish, "
            "chest display, and articulated arms for reception and guidance in public venues."
        ),
        purpose=APPS_WELCOME,
        features=(
            f"160 cm height; 45 kg weight; 24V 15Ah polymer lithium battery (~9 h runtime). "
            f"{COMMON_FEAT}"
        ),
        tags=TAGS_WELCOME,
        weight_kg=45,
        height_mm=1600,
        runtime_minutes=540,
        battery_wh=battery_wh_24v15(),
        uses="reception",
        videos=[YT_PUBLIC, YT_TESTS],
        notes_extra="Parameter sheet landou_parameter-pc_en_01.jpg.",
    ),
    2002: fix(
        name="DaJin Robot",
        model="DaJin",
        series="welcome",
        family_name="AoBo Welcome Service Robots",
        url=pdp("dajin"),
        image=hero("dajin/dajin-r1.jpg"),
        description=(
            "DaJin is an Aobo wheeled welcome service robot with a champagne/gold finish, "
            "chest touchscreen, and indoor mobile base for lobby greeting and wayfinding."
        ),
        purpose=APPS_WELCOME,
        features=(
            f"160 cm height; 45 kg weight; 24V 15Ah polymer lithium battery (~9 h runtime). "
            f"{COMMON_FEAT}"
        ),
        tags=TAGS_WELCOME,
        weight_kg=45,
        height_mm=1600,
        runtime_minutes=540,
        battery_wh=battery_wh_24v15(),
        uses="reception",
        videos=[YT_PUBLIC, YT_TESTS],
        notes_extra="Parameter sheet dajin_parameter-sm_en_01.jpg (pc_en sheets 404).",
    ),
    2001: fix(
        name="SuanTou Robot",
        model="SuanTou",
        series="welcome",
        family_name="AoBo Welcome Service Robots",
        url=pdp("suantou"),
        image=hero("suantou/suantou-r1.jpg"),
        description=(
            "SuanTou is an Aobo wheeled welcome service robot holding a large vertical "
            "interaction display for reception, information, and indoor guidance."
        ),
        purpose=APPS_WELCOME,
        features=(
            f"160 cm height; 45 kg weight; 24V 15Ah polymer lithium battery (~9 h runtime). "
            f"{COMMON_FEAT}"
        ),
        tags=TAGS_WELCOME,
        weight_kg=45,
        height_mm=1600,
        runtime_minutes=540,
        battery_wh=battery_wh_24v15(),
        uses="reception",
        videos=[YT_PUBLIC, YT_TESTS],
        notes_extra="Parameter sheet suantou_parameter-pc_en_01.jpg.",
    ),
    1998: fix(
        name="PeiPei Robot",
        model="PeiPei",
        series="welcome",
        family_name="AoBo Welcome Service Robots",
        url=pdp("peipei"),
        image=hero("peipei/peipei-r1.jpg"),
        description=(
            "PeiPei is an Aobo wheeled welcome service robot with a handheld landscape "
            "display for guest greeting and interactive reception."
        ),
        purpose=APPS_WELCOME,
        features=(
            f"160 cm height; 45 kg weight; 24V 15Ah polymer lithium battery (~9 h runtime). "
            f"{COMMON_FEAT}"
        ),
        tags=TAGS_WELCOME,
        weight_kg=45,
        height_mm=1600,
        runtime_minutes=540,
        battery_wh=battery_wh_24v15(),
        uses="reception",
        videos=[YT_PUBLIC, YT_TESTS],
        notes_extra="Parameter sheet peipei_parameter-pc_en_01.jpg.",
    ),
    1996: fix(
        name="XiaoAo Robot",
        model="XiaoAo",
        series="welcome",
        family_name="AoBo Welcome Service Robots",
        url=pdp("xiaoao"),
        image=hero("xiaoao/xiaoao-r1.jpg"),
        description=(
            "XiaoAo is an Aobo wheeled welcome service robot with an integrated chest "
            "touchscreen, articulated arms, and indoor autonomous base for reception."
        ),
        purpose=APPS_WELCOME,
        features=(
            f"160 cm height; 45 kg weight; 24V 15Ah polymer lithium battery (~9 h runtime). "
            f"{COMMON_FEAT}"
        ),
        tags=TAGS_WELCOME,
        weight_kg=45,
        height_mm=1600,
        runtime_minutes=540,
        battery_wh=battery_wh_24v15(),
        uses="reception",
        videos=[YT_PUBLIC, YT_TESTS],
        notes_extra="Parameter sheet xiaoao_parameter-pc_en_01.jpg.",
    ),
    1995: fix(
        name="YinYin Robot",
        model="YinYin",
        series="welcome",
        family_name="AoBo Welcome Service Robots",
        url=pdp("yinyin"),
        image=hero("yinyin/yinyin-r1.jpg"),
        description=(
            "YinYin is an Aobo wheeled welcome service robot with a chest display, "
            "keypad/card-reader panel, and indoor mobile base for public-area reception."
        ),
        purpose=APPS_WELCOME,
        features=(
            f"162 cm height; 45 kg weight; 24V 15Ah polymer lithium battery (~9 h runtime). "
            f"{COMMON_FEAT}"
        ),
        tags=TAGS_WELCOME,
        weight_kg=45,
        height_mm=1620,
        runtime_minutes=540,
        battery_wh=battery_wh_24v15(),
        uses="reception",
        videos=[YT_YINYIN, YT_PUBLIC],
        notes_extra="Parameter sheet yinyin_parameter-pc_en_01.jpg.",
    ),
    1994: fix(
        name="Doctor Robot",
        model="Doctor / Boshi",
        series="welcome",
        family_name="AoBo Welcome Service Robots",
        url=pdp("boshi"),
        image=hero("boshi/boshi-r1.jpg"),
        description=(
            "Doctor (Boshi) is an Aobo wheeled welcome service robot with a large vertical "
            "torso display and articulated hands for lobby greeting and information."
        ),
        purpose=APPS_WELCOME,
        features=(
            f"160 cm height; 45 kg weight; 24V 15Ah polymer lithium battery (~9 h runtime). "
            f"{COMMON_FEAT}"
        ),
        tags=TAGS_WELCOME,
        weight_kg=45,
        height_mm=1600,
        runtime_minutes=540,
        battery_wh=battery_wh_24v15(),
        uses="reception",
        videos=[YT_PUBLIC, YT_TESTS],
        notes_extra="Parameter sheet boshi_parameter-pc_en_01.jpg. OEM EN title: Doctors service welcome robot.",
    ),
    1993: fix(
        name="KaKa Robot (Welcome version)",
        model="KaKa Welcome",
        series="welcome",
        family_name="AoBo Welcome Service Robots",
        url=pdp("yingbinbankaka"),
        image=None,
        description=(
            "KaKa Welcome is Aobo's reception-oriented KaKa configuration for indoor "
            "greeting and guest interaction (OEM welcome PDP yingbinbankaka.html)."
        ),
        purpose=APPS_WELCOME,
        features=(
            f"OEM Function Parameter sheet (shared kaka folder): 120 cm height; 30 kg weight; "
            f"24V 15Ah polymer lithium battery (~9 h runtime). {COMMON_FEAT} "
            f"Welcome-variant-specific product render not published separately from Transport KaKa."
        ),
        tags=TAGS_WELCOME,
        weight_kg=30,
        height_mm=1200,
        runtime_minutes=540,
        battery_wh=battery_wh_24v15(),
        uses="reception",
        videos=[YT_KAKA, YT_PUBLIC],
        imageless_note=IMAGE_TODO_KAKA_WELCOME,
        notes_extra="Specs from kaka_parameter-pc_en_01.jpg (shared with transport KaKa).",
    ),
    # --- Delivery / transport ---
    2004: fix(
        name="HuanHuan Robot",
        model="HuanHuan",
        series="delivery",
        family_name="AoBo Delivery Service Robots",
        url=pdp("huanhuan"),
        image=hero("huanhuan/huanhuan-r1.jpg"),
        description=(
            "HuanHuan is an Aobo wheeled food-delivery / service robot with a serving tray, "
            "chest touchscreen, and indoor autonomous base for hospitality transport."
        ),
        purpose=APPS_DELIVERY,
        features=(
            f"155 cm height; 45 kg weight; 24V 15Ah polymer lithium battery (~9 h runtime). "
            f"{COMMON_FEAT}"
        ),
        tags=TAGS_DELIVERY,
        weight_kg=45,
        height_mm=1550,
        runtime_minutes=540,
        battery_wh=battery_wh_24v15(),
        uses="food-delivery|delivery|room-service",
        videos=[YT_DELIVERY, YT_TESTS],
        notes_extra="Parameter sheet huanhuan_parameter-pc_en_01.jpg.",
    ),
    2003: fix(
        name="LeLe Robot",
        model="LeLe",
        series="delivery",
        family_name="AoBo Delivery Service Robots",
        url=pdp("lele"),
        image=hero("lele/lele-r1.jpg"),
        description=(
            "LeLe is an Aobo wheeled food-delivery service robot with a tray, expressive "
            "head display, and indoor mobile base for restaurant and hotel delivery."
        ),
        purpose=APPS_DELIVERY,
        features=(
            f"160 cm height; 30 kg weight; 24V 15Ah polymer lithium battery (~9 h runtime). "
            f"{COMMON_FEAT}"
        ),
        tags=TAGS_DELIVERY,
        weight_kg=30,
        height_mm=1600,
        runtime_minutes=540,
        battery_wh=battery_wh_24v15(),
        uses="food-delivery|delivery|room-service",
        videos=[YT_DELIVERY, YT_TESTS],
        notes_extra="Parameter sheet lele_parameter-pc_en_01.jpg.",
    ),
    1989: fix(
        name="DaBen Robot",
        model="DaBen",
        series="delivery",
        family_name="AoBo Delivery Service Robots",
        url=pdp("daben"),
        image=hero("daben/daben-r1.jpg"),
        description=(
            "DaBen is an Aobo wheeled transport/food-delivery robot with an open multi-shelf "
            "oval cabin and indoor autonomous base for hotel and restaurant delivery."
        ),
        purpose=APPS_DELIVERY,
        features=(
            f"130 cm height; 30 kg weight; 24V 15Ah polymer lithium battery (~9 h runtime); "
            f"multi-shelf open cabin with LED shelf lighting. {COMMON_FEAT}"
        ),
        tags=TAGS_DELIVERY,
        weight_kg=30,
        height_mm=1300,
        runtime_minutes=540,
        battery_wh=battery_wh_24v15(),
        uses="food-delivery|delivery|room-service",
        videos=[YT_DELIVERY, YT_BENBEN],
        notes_extra="Parameter sheet daben_parameter-pc_en_01.jpg.",
    ),
    1992: fix(
        name="Ben Ben Robot",
        model="BenBen",
        series="delivery",
        family_name="AoBo Delivery Service Robots",
        url=pdp("benben"),
        image=hero("benben/benben-r1.jpg"),
        description=(
            "BenBen is Aobo's wheeled food-delivery service robot with illuminated shelves "
            "for restaurant and hotel item transport."
        ),
        purpose=APPS_DELIVERY,
        features=(
            f"120 cm height; 30 kg weight; 24V 15Ah polymer lithium battery (~9 h runtime); "
            f"open multi-shelf delivery cabin. {COMMON_FEAT}"
        ),
        tags=TAGS_DELIVERY,
        weight_kg=30,
        height_mm=1200,
        runtime_minutes=540,
        battery_wh=battery_wh_24v15(),
        uses="food-delivery|delivery|room-service",
        videos=[YT_BENBEN, YT_BENBEN2, YT_BENBEN3],
        notes_extra="Parameter sheet benben_parameter-pc_en_01.jpg.",
    ),
    1990: fix(
        name="PaoPao Robot",
        model="PaoPao",
        series="delivery",
        family_name="AoBo Delivery Service Robots",
        url=pdp("paopao"),
        image=hero("paopao/paopao-r1.jpg"),
        description=(
            "PaoPao is an Aobo wheeled delivery/service robot with an internal shelved cabin "
            "for indoor item transport (OEM EN H2 text is wrongly labeled Doctors — assets are PaoPao)."
        ),
        purpose=APPS_DELIVERY,
        features=(
            f"126 cm height; 70 kg weight; 24V 15Ah polymer lithium battery (~9 h runtime); "
            f"shelved internal cargo cabin. {COMMON_FEAT}"
        ),
        tags=TAGS_DELIVERY,
        weight_kg=70,
        height_mm=1260,
        runtime_minutes=540,
        battery_wh=battery_wh_24v15(),
        uses="food-delivery|delivery|item-delivery",
        videos=[YT_DELIVERY, YT_TESTS],
        notes_extra="Parameter sheet paopao_parameter-pc_en_01.jpg. EN PDP H2 mislabeled Doctors.",
    ),
    1997: fix(
        name="KaKa Robot (Transport version)",
        model="KaKa Transport",
        series="delivery",
        family_name="AoBo Delivery Service Robots",
        url=pdp("kaka"),
        image=hero("kaka/kaka-r1.jpg"),
        description=(
            "KaKa Transport is Aobo's wheeled KaKa configuration for indoor hotel/item "
            "delivery and guest-facing transport tasks."
        ),
        purpose=APPS_DELIVERY,
        features=(
            f"120 cm height; 30 kg weight; 24V 15Ah polymer lithium battery (~9 h runtime). "
            f"{COMMON_FEAT}"
        ),
        tags=TAGS_DELIVERY,
        weight_kg=30,
        height_mm=1200,
        runtime_minutes=540,
        battery_wh=battery_wh_24v15(),
        uses="delivery|room-service|item-delivery",
        videos=[YT_KAKA, YT_DELIVERY],
        notes_extra="Parameter sheet kaka_parameter-pc_en_01.jpg. Hero assigned here; welcome KaKa imageless.",
    ),
    # --- Patrol ---
    2006: fix(
        name="XiaoAn Robot",
        model="XiaoAn",
        series="patrol",
        family_name="AoBo Security Patrol Robots",
        url=pdp("xiaoan"),
        image=hero("xiaoan/xiaoan-r1.jpg"),
        description=(
            "XiaoAn is an Aobo wheeled security patrol robot for indoor facility monitoring "
            "and autonomous patrol rounds."
        ),
        purpose=APPS_PATROL,
        features=(
            f"130 cm height; 50 kg weight; 24V 15Ah polymer lithium battery (~9 h runtime). "
            f"{COMMON_FEAT}"
        ),
        tags=TAGS_PATROL,
        weight_kg=50,
        height_mm=1300,
        runtime_minutes=540,
        battery_wh=battery_wh_24v15(),
        uses="patrol|security",
        industry="commercial|facilities|civil-security-emergency",
        videos=[YT_XIAOAN, YT_TESTS],
        notes_extra="Parameter sheet xiaoan_parameter-pc_en_01.jpg.",
    ),
    # --- Disinfection ---
    1999: fix(
        name="Disinfect Benben (spray version)",
        model="Benben Spray Disinfection",
        series="disinfection",
        family_name="AoBo Disinfection Robots",
        url=pdp("penwubanxiaodubenben"),
        image=hero("xiaodubenben/xiaodubenben-r1.jpg"),
        description=(
            "Disinfect Benben (spray) is Aobo's wheeled spray-disinfection service robot "
            "for indoor pathogen reduction in hospitals and public facilities."
        ),
        purpose=APPS_DISINFECT,
        features=(
            f"160 cm height; 45 kg weight; 24V 15Ah polymer lithium battery (~9 h runtime); "
            f"spray disinfection configuration. {COMMON_FEAT}"
        ),
        tags=TAGS_DISINFECT,
        weight_kg=45,
        height_mm=1600,
        runtime_minutes=540,
        battery_wh=battery_wh_24v15(),
        uses="cleaning",
        industry="commercial|hospitality",
        videos=[YT_DISINFECT, YT_TESTS],
        notes_extra="Parameter sheet pengwubanxiaodubenben_parameter-pc_en_01.jpg.",
    ),
    2000: fix(
        name="Disinfect Benben (UV version)",
        model="Benben UV Disinfection",
        series="disinfection",
        family_name="AoBo Disinfection Robots",
        url=pdp("ziwaixianbanxiaodubenben"),
        image=hero("ziwaixianbanxiaodubenben/ziwaixianbanxiaodubenben-r1.jpg"),
        description=(
            "Disinfect Benben (UV) is Aobo's wheeled ultraviolet disinfection robot with "
            "exposed UV-C lamp arrays for indoor sterilization rounds."
        ),
        purpose=APPS_DISINFECT,
        features=(
            "UV-C lamp disinfection module on a wheeled indoor service chassis; "
            "OEM EN PDP does not publish a Function Parameter table for this UV SKU "
            "(unlike the spray Benben sheet) — typed numeric specs left blank."
        ),
        tags=TAGS_DISINFECT,
        uses="cleaning",
        industry="commercial|hospitality",
        videos=[YT_DISINFECT, YT_TESTS],
        notes_extra="No OEM UV parameter sheet found; specs fail-closed blank.",
    ),
    # --- Chassis ---
    1991: fix(
        name="Robot Chassis",
        model="AoBo Robot Chassis / Dipan",
        series="chassis",
        family_name="AoBo Robot Chassis",
        url=pdp("dipan"),
        image=hero("dipan/dipan-r1.jpg"),
        description=(
            "Aobo Robot Chassis (dipan) is a compact wheeled mobile base platform with "
            "sensor ports and docking charge support for building custom service robots. "
            "OEM EN H2 text incorrectly says 'Daikin Service Welcome Robot'; product assets "
            "and dimensions are chassis/base, not a welcome humanoid."
        ),
        purpose=APPS_CHASSIS,
        features=(
            f"43 cm height; 100 kg weight; 24V 15Ah polymer lithium battery (~9 h runtime); "
            f"cylindrical two-tier mobile base with perimeter sensors. {COMMON_FEAT}"
        ),
        tags=TAGS_CHASSIS,
        weight_kg=100,
        height_mm=430,
        runtime_minutes=540,
        battery_wh=battery_wh_24v15(),
        uses="development|transport",
        industry="commercial|manufacturing",
        videos=[YT_TESTS],
        notes_extra="Parameter sheet dipan_parameter-pc_en_01.jpg. EN H2 mislabeled Daikin welcome.",
    ),
    # --- Unique 16xx SKUs (strip AoBo prefix) ---
    1627: fix(
        name="ShaQiang Educational Robot",
        model="ShaQiang",
        series="education",
        family_name="AoBo Educational Robots",
        url=pdp("shaqiang"),
        image=hero("shaqiang/shaqiang-r1.jpg"),
        description=(
            "ShaQiang is Aobo's educational programming robot for STEM classroom "
            "demonstration and robotics training."
        ),
        purpose=APPS_EDU,
        features=(
            "Educational programming service robot on a wheeled indoor platform. "
            "OEM EN PDP has no Function Parameter numeric table in this pass — typed specs blank."
        ),
        tags=TAGS_EDU,
        uses="education",
        industry="education|commercial",
        videos=[YT_TESTS],
        notes_extra="No OEM numeric parameter sheet found for ShaQiang.",
    ),
    1626: fix(
        name="QB Robot",
        model="QB",
        series="reception-gen3",
        family_name="AoBo Reception Series",
        url=pdp("qb"),
        image=hero("QB/ui/1.jpg"),
        description=(
            "QB is Aobo's Reception Series wheeled service robot with Lidar navigation, "
            "face-recognition greeting, and voice interaction for lobbies and showrooms. "
            "(Queue name said transport/food delivery; OEM datasheet is Reception Series.)"
        ),
        purpose=APPS_RECEPTION_GEN3,
        features=(
            "Height 120 cm; weight 30 kg; 10.1-inch 16:9 touch screen; Android 10; "
            "WiFi (4G/5G optional); Lidar navigation; 5 joints (head/arms); "
            "15 Ah polymer lithium battery (~6 h runtime); automatic or manual charge; "
            "six-mic array; HD face-recognition camera; ultrasonic obstacle avoidance; "
            "secondary-development SDK."
        ),
        tags=TAGS_RECEPTION,
        weight_kg=30,
        height_mm=1200,
        runtime_minutes=360,
        dof=5,
        uses="reception",
        videos=[YT_PUBLIC, YT_TESTS],
        notes_extra="Specs from OEM QB/des/QB.jpg reception datasheet. Battery Ah only (no V) — Wh blank.",
    ),
    1625: fix(
        name="PEPPA3",
        model="PEPPA3",
        series="delivery-gen3",
        family_name="AoBo Food Delivery Series",
        url=pdp("peppa3"),
        image=hero("PEPPA3/ui/1.jpg"),
        description=(
            "PEPPA3 is Aobo's Gen3 wheeled food-delivery robot with five trays, a 21.5-inch "
            "advertising display, Lidar navigation, and voice/face greeting for restaurants and hotels."
        ),
        purpose=APPS_FOOD_GEN3,
        features=(
            "Height 150 cm; chassis diameter 61 cm; weight 50 kg; load 10 kg/tray (50 kg total); "
            "10.1-inch face touchscreen + 21.5-inch ad display; Android 10; "
            "navigation speed 0.3–1.0 m/s; Lidar + ultrasonic + depth camera; "
            "15 Ah polymer lithium battery (~6 h); automatic/manual charge; five removable trays."
        ),
        tags=TAGS_DELIVERY,
        weight_kg=50,
        height_mm=1500,
        width_mm=610,
        payload_kg=50,
        speed=3.6,  # 1.0 m/s max → km/h
        runtime_minutes=360,
        uses="food-delivery|delivery",
        videos=[YT_DELIVERY, YT_TESTS],
        notes_extra="Specs from OEM PEPPA3/des/PEPPA3.jpg. Speed = max 1.0 m/s as 3.6 km/h.",
    ),
    1618: fix(
        name="GEORGE3",
        model="GEORGE3",
        series="delivery-gen3",
        family_name="AoBo Food Delivery Series",
        url=pdp("george3"),
        image=hero("GEORGE3/ui/1.jpg"),
        description=(
            "GEORGE3 is Aobo's Gen3 wheeled food-delivery robot with four trays, dual screens, "
            "and Lidar navigation for restaurant and hotel table delivery."
        ),
        purpose=APPS_FOOD_GEN3,
        features=(
            "Height 130 cm; chassis diameter 54 cm; weight 45 kg; load 10 kg/tray (40 kg total); "
            "10.1-inch + 21.5-inch displays; Android 10; speed 0.3–1.0 m/s; Lidar navigation; "
            "15 Ah polymer lithium battery (~6 h); automatic/manual charge; four open trays."
        ),
        tags=TAGS_DELIVERY,
        weight_kg=45,
        height_mm=1300,
        width_mm=540,
        payload_kg=40,
        speed=3.6,
        runtime_minutes=360,
        uses="food-delivery|delivery",
        videos=[YT_DELIVERY, YT_TESTS],
        notes_extra="Specs from OEM GEORGE3/des/GEORGE3.jpg. Speed = max 1.0 m/s as 3.6 km/h.",
    ),
    1617: fix(
        name="DOCTOR3",
        model="DOCTOR3",
        series="reception-gen3",
        family_name="AoBo Reception Series",
        url=pdp("doctor3"),
        image=hero("DOCTOR3/ui/1.jpg"),
        description=(
            "DOCTOR3 is Aobo's Reception Series wheeled service robot with a 27-inch vertical "
            "touchscreen, Lidar navigation, and proactive face-recognition greeting. "
            "(Queue name said transport/food delivery; OEM datasheet is Reception Series.)"
        ),
        purpose=APPS_RECEPTION_GEN3,
        features=(
            "Height 155 cm; weight 40 kg; 27-inch 16:9 vertical touchscreen; Android 10; "
            "WiFi (4G/5G optional); 6 joints (head/arms); Lidar + ultrasonic avoidance; "
            "20 Ah polymer lithium battery (~9 h); automatic/manual charge; "
            "four-mic array; HD face recognition; secondary-development SDK."
        ),
        tags=TAGS_RECEPTION,
        weight_kg=40,
        height_mm=1550,
        runtime_minutes=540,
        dof=6,
        uses="reception",
        videos=[YT_PUBLIC, YT_TESTS],
        notes_extra="Specs from OEM DOCTOR3/des/DOCTOR3.jpg. Battery Ah only (no V) — Wh blank.",
    ),
    1610: fix(
        name="BARRO",
        model="BARRO",
        series="reception-gen3",
        family_name="AoBo Reception Series",
        url=pdp("barro"),
        image=hero("BARRO/ui/1.jpg"),
        description=(
            "BARRO is Aobo's Reception Series wheeled service robot with a 7-inch head "
            "display, 15-inch chest touchscreen, articulated arms, and an internal storage "
            "cabinet for lobby greeting and light document/snack delivery. "
            "(Queue name said transport/food delivery; OEM datasheet is Reception Series.)"
        ),
        purpose=APPS_RECEPTION_GEN3,
        features=(
            "Height 140 cm; weight 45 kg; 7-inch head LCD + 15-inch chest touchscreen; "
            "Android 10; WiFi (4G/5G optional); 6 joints (head/arms); Lidar navigation; "
            "15 Ah polymer lithium battery (~8 h); automatic/manual charge; "
            "six-mic array; internal storage cabinet; secondary-development SDK."
        ),
        tags=TAGS_RECEPTION,
        weight_kg=45,
        height_mm=1400,
        runtime_minutes=480,
        dof=6,
        uses="reception|item-delivery",
        videos=[YT_PUBLIC, YT_TESTS],
        notes_extra="Specs from OEM BARRO/des/BARRO.jpg. Battery Ah only (no V) — Wh blank.",
    ),
}


def _admin_base() -> str:
    base = os.environ.get("IMPORT_SYNC_API_BASE_URL") or ""
    if "/api/v1" in base:
        return base.split("/api/v1")[0].rstrip("/")
    return "https://ragadmin.robotaigeek.com"


def _internal_secret() -> str:
    secret = os.environ.get("INTERNAL_API_SECRET") or ""
    env_file = _RESEARCH_DIR.parents[1] / "robotaigeek-server" / ".env"
    if not secret and env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                secret = line.split("=", 1)[1].strip()
    return secret


def reject_robot(client: ResearchApiClient, rid: int, reason: str) -> str:
    """Prefer admin reject; fall back to status=rejected PATCH (known 403 issue)."""
    url = f"{_admin_base()}/admin/robots/robot/content-queue/api/robot/{rid}/reject/"
    headers = {"Content-Type": "application/json", "X-Internal-Secret": _internal_secret()}
    try:
        resp = requests.post(
            url, headers=headers, json={"type": "robot", "reason": reason}, timeout=120
        )
        if resp.status_code < 400:
            return f"admin-reject {resp.status_code}"
        admin_msg = f"admin {resp.status_code} {(resp.text or '')[:120]}"
    except requests.RequestException as e:
        admin_msg = f"admin ERR {e}"
    try:
        client._patch(
            f"robots/robots/{rid}/",
            {"status": "rejected", "rejection_reason": reason[:500]},
        )
        return f"api-patch-rejected (fallback after {admin_msg})"
    except Exception as e:
        return f"FAIL {admin_msg} / patch {e}"


def trigger_copy_media(robot_ids: list[int]) -> tuple[int, int]:
    secret = _internal_secret()
    api = _admin_base()
    if not secret:
        print("WARN: no INTERNAL_API_SECRET for copy-media", file=sys.stderr)
        return 0, len(robot_ids)
    ok = fail = 0
    for rid in robot_ids:
        url = f"{api}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/"
        try:
            resp = requests.post(url, headers={"X-Internal-Secret": secret}, timeout=180)
            body: dict[str, Any] = {}
            try:
                body = resp.json() if resp.content else {}
            except Exception:
                body = {}
            success = bool(body.get("success")) if "success" in body else resp.ok
            if resp.ok and success:
                ok += 1
            else:
                fail += 1
                print(f"copy-media fail {rid}: HTTP {resp.status_code} body={body}", flush=True)
        except requests.RequestException as exc:
            fail += 1
            print(f"copy-media fail {rid}: {exc}", flush=True)
        time.sleep(0.2)
    return ok, fail


def resolve_tags(catalog: TagCatalog, pipe: str) -> str:
    names = [n.strip() for n in pipe.split("|") if n.strip()]
    out: list[str] = []
    missing: list[str] = []
    for n in names:
        hit = catalog._by_name.get(n.lower())
        if hit:
            out.append(str(hit.get("name") or n))
        else:
            missing.append(n)
    if missing:
        print(f"WARN unresolved tags: {missing}", file=sys.stderr)
    return "|".join(out)


def build_row(fix: dict[str, Any], *, tags: str) -> dict[str, Any]:
    row: dict[str, Any] = {
        "company_slug": COMPANY_SLUG,
        "company_name": COMPANY_NAME,
        "source_locale": "en",
    }
    skip = {"videos", "notes_force", "source_note", "images", "replace_media", "imageless"}
    for k, v in fix.items():
        if k in skip or v is None or v == "":
            continue
        row[k] = v
    row["tags"] = tags
    if fix.get("notes_force"):
        row["notes"] = fix["notes_force"]
    if fix.get("source_note"):
        row["research_notes"] = fix["source_note"]
    videos = fix.get("videos") or []
    if videos:
        row["video_urls"] = enrich_video_list(videos)
    if fix.get("image"):
        row["images"] = [fix["image"]]
    return row


def patch_typed(client: ResearchApiClient, rid: int, fix: dict[str, Any]) -> None:
    body: dict[str, Any] = {}
    for k in (
        "payload_kg",
        "reach_mm",
        "repeatability_mm",
        "weight_kg",
        "dof",
        "speed",
        "width_mm",
        "length_mm",
        "height_mm",
        "runtime_minutes",
        "battery_wh",
        "family_key",
        "family_name",
        "family_url",
        "model_name",
        "variant_code",
        "variant_label",
        "product_url_scope",
        "purpose",
        "name",
        "manufacturer_country_code",
        "url",
    ):
        if k in fix and fix[k] not in (None, ""):
            body[k] = fix[k]
    avail_key = fix.get("availability_status_key")
    if avail_key:
        body["availability_status"] = _AVAIL_IDS.get(str(avail_key), avail_key)
    # Clear media when deliberately imageless
    if fix.get("imageless"):
        body["image"] = ""
        body["s3_image"] = ""
    ok_keys: list[str] = []
    for k, v in body.items():
        try:
            client._patch(f"robots/robots/{rid}/", {k: v})
            ok_keys.append(k)
        except Exception as exc:
            print(f"  patch fail {rid}.{k}: {exc}", file=sys.stderr)
    if ok_keys:
        print(f"  patched typed {rid}: {ok_keys}")


def hash_url(url: str) -> str | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=90)
        if not resp.ok:
            return None
        return hashlib.md5(resp.content).hexdigest()
    except requests.RequestException:
        return None


def assert_distinct_heroes(fixes: dict[int, dict[str, Any]]) -> None:
    hashes: dict[str, int] = {}
    for rid, fix in fixes.items():
        if fix.get("imageless"):
            print(f"  hero hash {rid}: IMAGELESS (deliberate)")
            continue
        url = fix.get("image")
        if not url:
            raise RuntimeError(f"{rid}: missing image")
        h = hash_url(str(url))
        if not h:
            raise RuntimeError(f"{rid}: failed to hash image {url}")
        if h in hashes:
            raise RuntimeError(f"hero hash collision {rid} vs {hashes[h]} md5={h}")
        # Known-bad Service_en.jpg
        if h == "1df11ec2e4e6c8a0" or h.startswith("1df11ec2e4e6"):
            raise RuntimeError(f"{rid}: refused shared Service_en.jpg banner hash {h}")
        hashes[h] = rid
        print(f"  hero hash {rid}: {h[:12]}")


def write_report(
    *,
    imported: list[int],
    rejected: list[int],
    imageless: list[int],
    totals: dict[str, Any],
    copy_stats: dict[str, Any] | None,
) -> None:
    dedup_lines = "\n".join(
        f"- `{rid}` → keeper cited in reason: {reason.split('(')[0].strip()}"
        for rid, reason in sorted(REJECTS.items())
    )
    allow = ", ".join(str(i) for i in sorted(imported) if i not in imageless)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(
        f"""---
type: log
title: Aobo Robot 1384 enrichment
status: draft
version: 1.0
owner: AI
last_updated: 2026-07-29
tags:
  - content-queue
  - aobo-robot
---

# Aobo Robot (1384) enrichment

## Summary

- Enriched (imported): **{len(imported)}** — `{imported}`
- Rejected (URL dupes / wrong Daikin): **{len(rejected)}** — `{rejected}`
- Imageless (deliberate): **{len(imageless)}** — `{imageless}`
- Bulk-import totals: `{totals}`
- copy-media: `{copy_stats}`

## Dedup map (rejected → keeper)

{dedup_lines}

## CDN / heroes

- Replaced shared `Service_en.jpg` CDN hash `1df11ec2e4e6…` with distinct OEM `*-r1.jpg` / Gen3 `ui/1.jpg` assets.
- Pre-apply content-hash assert: no collisions among keepers with heroes.
- KaKa Welcome (1993) imageless — shares OEM `/image/robot/kaka/` bytes with KaKa Transport (1997).
- Post-apply: `python verify_cdn_images.py --company-id 1384`

## Approve allowlist

Robots with distinct verified heroes + features + family_key (pending_review):

`{allow}`

Hold: `1993` (imageless KaKa Welcome — IMAGE TO-DO note).

## Hold / blockers

- EN PDPs are sparse; numeric specs taken from OEM Function Parameter / des datasheet images (not inventable HTML tables).
- UV Benben (2000): no OEM parameter sheet — weight/battery left blank.
- ShaQiang (1627): no OEM numeric sheet — specs blank.
- Gen3 QB/BARRO/DOCTOR3 battery cited as Ah only (no voltage) — `battery_wh` blank.
- 1616 Daikin: rejected (chassis URL / wrong welcome name).
- OEM EN H2 mislabels: `dipan.html`→Daikin welcome, `paopao.html`→Doctors — corrected in catalog names/descriptions.

## Script

`scripts/research/fix_aobo_1384_robots.py`

## Related

- Staging map: `scripts/research/staging/_aobo_1384/`
""",
        encoding="utf-8",
    )
    print(f"wrote report {REPORT}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix Aobo Robot company 1384")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--copy-media", action="store_true")
    parser.add_argument("--verify-cdn", action="store_true")
    parser.add_argument("--reject-dupes", action="store_true")
    parser.add_argument("--mark-done", action="store_true")
    parser.add_argument("--created-by-id", type=int, default=1)
    parser.add_argument("--only", type=int, nargs="*")
    args = parser.parse_args()

    client = ResearchApiClient()
    catalog = TagCatalog.load(client=client)
    all_robots = {
        int(r["id"]): r
        for r in client.list_robots_for_company(COMPANY_ID)
        if str(r.get("status") or "").lower() == "pending_review"
    }

    rejected_ids: list[int] = []
    if args.reject_dupes:
        for rid, reason in REJECTS.items():
            if args.only and rid not in args.only:
                continue
            if not args.apply:
                print(f"dry-run reject {rid}: {reason[:100]}...")
                rejected_ids.append(rid)
                continue
            msg = reject_robot(client, rid, reason)
            print(f"reject {rid}: {msg}")
            rejected_ids.append(rid)

    targets = []
    for rid, fix_row in ROBOT_FIXES.items():
        if args.only and rid not in args.only:
            continue
        robot = all_robots.get(rid)
        if not robot:
            print(f"SKIP {rid}: not pending_review / not found")
            continue
        tags = resolve_tags(catalog, str(fix_row.get("tags") or ""))
        row = build_row(fix_row, tags=tags)
        if len(row.get("features") or "") < 40:
            print(f"ERROR {rid}: features too short", file=sys.stderr)
            return 1
        if not row.get("family_key"):
            print(f"ERROR {rid}: missing family_key", file=sys.stderr)
            return 1
        if not row.get("image") and not fix_row.get("imageless"):
            print(f"ERROR {rid}: missing image", file=sys.stderr)
            return 1
        targets.append({"id": rid, "name": row["name"], "row": row, "fix": fix_row})
        print(
            f"  {rid} {row['name']}: weight={row.get('weight_kg')} "
            f"payload={row.get('payload_kg')} fam={row.get('family_key')} "
            f"avail={row.get('availability_status_key')} "
            f"img={'NO' if fix_row.get('imageless') else 'yes'} "
            f"vids={len(row.get('video_urls') or [])}"
        )

    print("Hash-verifying candidate heroes...")
    try:
        assert_distinct_heroes({t["id"]: t["fix"] for t in targets})
    except RuntimeError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1

    PREVIEW.parent.mkdir(parents=True, exist_ok=True)
    PREVIEW.write_text(
        json.dumps(
            [
                {
                    "id": t["id"],
                    "name": t["name"],
                    "weight_kg": t["row"].get("weight_kg"),
                    "payload_kg": t["row"].get("payload_kg"),
                    "family_key": t["row"].get("family_key"),
                    "url": t["row"].get("url"),
                    "image": (t["row"].get("image") or "")[:140],
                    "imageless": bool(t["fix"].get("imageless")),
                    "availability": t["row"].get("availability_status_key"),
                }
                for t in targets
            ],
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    if not targets and not args.reject_dupes:
        print("ERROR: no targets", file=sys.stderr)
        return 1
    if not args.apply:
        print(
            f"Preview: {PREVIEW}. Re-run with "
            "--apply --copy-media --verify-cdn --reject-dupes --mark-done"
        )
        write_report(
            imported=[],
            rejected=rejected_ids,
            imageless=[t["id"] for t in targets if t["fix"].get("imageless")],
            totals={},
            copy_stats=None,
        )
        return 0

    tmp = Path(tempfile.mkdtemp(prefix="aobo-fix-"))
    totals = {"updated_count": 0, "error_count": 0, "skipped_count": 0, "created_count": 0}
    imported: list[int] = []
    for item in targets:
        rid = item["id"]
        fix_row = item["fix"]
        tags = resolve_tags(catalog, str(fix_row.get("tags") or ""))
        row = build_row(fix_row, tags=tags)
        # Imageless: still bulk-import metadata without replace_media images
        replace_media = not bool(fix_row.get("imageless"))
        if fix_row.get("imageless"):
            row.pop("images", None)
            row.pop("image", None)
        bulk = staging_dict_to_bulk_import_row(row)
        bulk["id"] = rid
        fpath = tmp / f"{slugify_robot_name(str(item['name']))}-{rid}.json"
        fpath.write_text(json.dumps([row], indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        try:
            result = client.bulk_import_robots(
                [bulk],
                update_existing=True,
                patch_existing=False,
                replace_media=replace_media,
                status="pending_review",
                skip_company_update=True,
                created_by_id=resolve_created_by_id(args.created_by_id),
            )
        except Exception as exc:
            print(f"IMPORT FAIL {rid}: {exc}", file=sys.stderr)
            continue
        created = int(result.get("created_count") or 0)
        if created:
            print(f"IMPORT FAIL {rid}: unexpected created_count={created} {result}", file=sys.stderr)
            continue
        err = int(result.get("error_count") or 0)
        if err:
            print(f"IMPORT FAIL {rid}: {result}", file=sys.stderr)
        else:
            imported.append(rid)
            patch_typed(client, rid, fix_row)
            notes = fix_row.get("notes_force")
            if notes:
                try:
                    client._patch(f"robots/robots/{rid}/", {"notes": notes})
                except Exception as exc:
                    print(f"  notes fail {rid}: {exc}", file=sys.stderr)
        for k in totals:
            totals[k] += int(result.get(k) or 0)
        print(f"  imported {rid}: {result.get('results')}")

    copy_stats = None
    copy_ids = [i for i in imported if not ROBOT_FIXES.get(i, {}).get("imageless")]
    if args.copy_media and copy_ids:
        ok, fail = trigger_copy_media(copy_ids)
        copy_stats = {"ok": ok, "fail": fail, "ids": copy_ids}
        print(f"copy-media ok={ok} fail={fail}")

    if args.verify_cdn and copy_ids:
        rc = subprocess.call(
            [
                sys.executable,
                str(_RESEARCH_DIR / "verify_cdn_images.py"),
                "--company-id",
                str(COMPANY_ID),
            ],
            cwd=str(_RESEARCH_DIR),
        )
        if rc != 0:
            print("CDN verify FAILED", file=sys.stderr)
            write_report(
                imported=imported,
                rejected=rejected_ids,
                imageless=[i for i in imported if ROBOT_FIXES.get(i, {}).get("imageless")],
                totals=totals,
                copy_stats=copy_stats,
            )
            return rc

    if args.mark_done and imported:
        subprocess.call(
            [
                sys.executable,
                str(_RESEARCH_DIR / "triage_content_queue.py"),
                "--mark-done",
                str(COMPANY_ID),
            ],
            cwd=str(_RESEARCH_DIR),
        )

    write_report(
        imported=imported,
        rejected=rejected_ids,
        imageless=[i for i in imported if ROBOT_FIXES.get(i, {}).get("imageless")],
        totals=totals,
        copy_stats=copy_stats,
    )
    print("totals", totals, "copy", copy_stats, "imported", imported)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
