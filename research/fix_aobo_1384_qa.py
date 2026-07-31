"""QA pass for Aobo Robot (1384) — fix To-Review verification flags on 15 keepers.

Root causes from prior enrich + live QA probe:
- Generic YT_PUBLIC / YT_TESTS clips → video_mismatch (prefer empty over sibling/generic).
- DaBen hero was closed-body r1 while copy said multi-shelf → use daben-r2 (oval 3-shelf).
- ShaQiang hero is humanoid (correct) but copy said wheeled → rewrite copy/tags.
- KaKa Welcome still holds Service_en.jpg banner → ORM-clear photos (imageless IMAGE TO-DO).
- EN H2 mislabels (dipan=Daikin, paopao=Doctors, Gen3=food delivery) vs assets/datasheets
  → keep catalog truth; drop url_content_mismatch / content_contradiction after alignment.
- AI image_mismatch often compared OEM product render to cross-nav Micky/XenaXiang junk.

Does NOT invent UV/ShaQiang numeric specs (no OEM parameter sheets).
Ignores missing_price. Soft few_photos / missing_release_year left.
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
from tag_suggest import TagCatalog
from youtube_metadata import enrich_video_list

# Reuse constants / helpers from the enrich script.
from fix_aobo_1384_robots import (  # noqa: E402
    APPS_CHASSIS,
    APPS_DELIVERY,
    APPS_DISINFECT,
    APPS_EDU,
    APPS_FOOD_GEN3,
    APPS_PATROL,
    APPS_RECEPTION_GEN3,
    APPS_WELCOME,
    COMMON_FEAT,
    COMPANY_ID,
    COMPANY_NAME,
    COMPANY_SLUG,
    HEADERS,
    IMAGE_TODO_KAKA_WELCOME,
    OEM,
    TAGS_CHASSIS,
    TAGS_DELIVERY,
    TAGS_DISINFECT,
    TAGS_PATROL,
    TAGS_RECEPTION,
    TAGS_WELCOME,
    YT_BENBEN,
    YT_BENBEN2,
    YT_BENBEN3,
    YT_DISINFECT,
    YT_KAKA,
    YT_XIAOAN,
    _AVAIL_IDS,
    battery_wh_24v15,
    fix,
    hero,
    pdp,
    patch_typed,
    resolve_tags,
    trigger_copy_media,
)

REPORT = _RESEARCH_DIR / "staging" / "reports" / "aobo-1384-qa-fix.md"
PROBE = _RESEARCH_DIR / "staging" / "reports" / "aobo-1384-qa-probe.json"
STAGING = _RESEARCH_DIR / "staging" / "_aobo_1384_qa"

VERIFICATION_DROP = frozenset(
    {
        "image_mismatch",
        "video_mismatch",
        "url_content_mismatch",
        "content_contradiction",
        "unverifiable",
    }
)

NS = "rag-server-prod"

TAGS_EDU_HUMANOID = "Service Robot|Education|Humanoid|Indoor|Customer Service"

# Robots that should end with ZERO videos (generic/sibling clips removed).
EMPTY_VIDEO_IDS = {
    2005,  # LanDou — no model-named clip
    2002,  # DaJin — only generics
    1991,  # Chassis — only YT_TESTS
    1990,  # PaoPao — delivery clip unnamed
    1989,  # DaBen — BenBen-titled + generic
    1627,  # ShaQiang — only YT_TESTS
    1626,  # QB — generics
    1625,  # PEPPA3 — generic delivery
    1618,  # GEORGE3 — generic delivery
    1617,  # DOCTOR3 — generics
    1610,  # BARRO — generics
}

# Heroes that change bytes (need replace_media + copy-media).
HERO_CHANGES = {
    2006: hero("xiaoan/xiaoan-r2.jpg"),  # single white patrol (was dual-color r1)
    1989: hero("daben/daben-r2.jpg"),  # clear 3-shelf oval (was closed-body r1)
}


def build_qa_fixes() -> dict[int, dict[str, Any]]:
    """Curated QA overrides for the 15 flagged pending_review robots."""
    return {
        2006: fix(
            name="XiaoAn Robot",
            model="XiaoAn",
            series="patrol",
            family_name="AoBo Security Patrol Robots",
            url=pdp("xiaoan"),
            image=HERO_CHANGES[2006],
            description=(
                "XiaoAn is Aobo's wheeled outdoor/indoor security patrol robot with a "
                "dome head, visor LED eyes, and a wide four-wheel base (OEM H2: Xiaoan "
                "Security Patrol Robot). Form factor is a compact wheeled patrol unit, "
                "not a bipedal lobby humanoid — EN page also embeds unrelated welcome "
                "cross-nav graphics."
            ),
            purpose=APPS_PATROL,
            features=(
                f"130 cm height; 50 kg weight; 24V 15Ah polymer lithium battery (~9 h runtime); "
                f"wide wheeled patrol base with front sensor lights. {COMMON_FEAT}"
            ),
            tags=TAGS_PATROL,
            weight_kg=50,
            height_mm=1300,
            runtime_minutes=540,
            battery_wh=battery_wh_24v15(),
            uses="patrol|security",
            industry="commercial|facilities|civil-security-emergency",
            videos=[YT_XIAOAN],
            notes_extra=(
                "QA 2026-07-29: hero→xiaoan-r2; stripped YT_TESTS; kept patrol YT. "
                "Parameter sheet xiaoan_parameter-pc_en_01.jpg."
            ),
        ),
        2005: fix(
            name="LanDou Robot",
            model="LanDou",
            series="welcome",
            family_name="AoBo Welcome Service Robots",
            url=pdp("landou"),
            image=hero("landou/landou-r1.jpg"),
            description=(
                "LanDou (蓝豆) is Aobo's blue wheeled welcome service robot with a chest "
                "touchscreen and articulated arms for lobby greeting. OEM H2 names LanDou; "
                "blue finish is the product color — white siblings on other PDPs are not LanDou."
            ),
            purpose=APPS_WELCOME,
            features=(
                f"160 cm height; 45 kg weight; 24V 15Ah polymer lithium battery (~9 h runtime); "
                f"blue metallic torso finish. {COMMON_FEAT}"
            ),
            tags=TAGS_WELCOME,
            weight_kg=45,
            height_mm=1600,
            runtime_minutes=540,
            battery_wh=battery_wh_24v15(),
            uses="reception",
            videos=[],
            notes_extra=(
                "QA 2026-07-29: kept landou-r1 blue hero; emptied generic videos. "
                "Parameter sheet landou_parameter-pc_en_01.jpg."
            ),
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
            videos=[],
            notes_extra="QA 2026-07-29: emptied generic YT_PUBLIC/YT_TESTS (video_mismatch).",
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
                "exposed UV-C lamp arrays for indoor sterilization rounds (OEM H2: Ultraviolet "
                "version Benben disinfection robot)."
            ),
            purpose=APPS_DISINFECT,
            features=(
                "UV-C lamp disinfection module on a wheeled indoor service chassis. "
                "OEM publishes no Function Parameter sheet for this UV SKU (spray Benben "
                "sheet exists separately) — typed numeric specs left blank after dead search."
            ),
            tags=TAGS_DISINFECT,
            uses="cleaning",
            industry="commercial|hospitality",
            videos=[YT_DISINFECT],
            notes_extra=(
                "QA 2026-07-29: kept disinfection clip only; stripped YT_TESTS. "
                "No UV parameter sheet (404); spray sheet not applied to UV SKU."
            ),
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
            videos=[YT_KAKA],
            imageless_note=IMAGE_TODO_KAKA_WELCOME,
            notes_extra=(
                "QA 2026-07-29: ORM-clear Service_en.jpg banner; keep imageless; "
                "video→KAKA reception clip only."
            ),
        ),
        1992: fix(
            name="Ben Ben Robot",
            model="BenBen",
            series="delivery",
            family_name="AoBo Delivery Service Robots",
            url=pdp("benben"),
            image=hero("benben/benben-r1.jpg"),
            description=(
                "BenBen is Aobo's wheeled food-delivery service robot with an open multi-shelf "
                "oval cabin and illuminated shelves for restaurant and hotel item transport. "
                "EN PDP embeds unrelated welcome cross-nav images; product assets are BenBen."
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
            notes_extra="QA 2026-07-29: kept benben-r1 multi-shelf hero; title-matched BenBen videos.",
        ),
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
                "OEM EN H2 incorrectly says 'Daikin Service Welcome Robot'; folder assets "
                "(dipan-*), parameter sheet, and product render are the chassis/base."
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
            videos=[],
            notes_extra=(
                "QA 2026-07-29: emptied videos; CN dipan URL 404 — keep EN URL + note OEM H2 bug. "
                "Parameter sheet dipan_parameter-pc_en_01.jpg."
            ),
        ),
        1990: fix(
            name="PaoPao Robot",
            model="PaoPao",
            series="delivery",
            family_name="AoBo Delivery Service Robots",
            url=pdp("paopao"),
            image=hero("paopao/paopao-r1.jpg"),
            description=(
                "PaoPao is an Aobo wheeled delivery robot with a branded cylindrical cabin and "
                "internal shelves for indoor item transport. OEM EN H2 wrongly says 'Doctors "
                "service welcome robot'; path/assets (paopao-*) and parameter sheet are PaoPao."
            ),
            purpose=APPS_DELIVERY,
            features=(
                f"126 cm height; 70 kg weight; 24V 15Ah polymer lithium battery (~9 h runtime); "
                f"shelved internal cargo cabin with AoBo branding. {COMMON_FEAT}"
            ),
            tags=TAGS_DELIVERY,
            weight_kg=70,
            height_mm=1260,
            runtime_minutes=540,
            battery_wh=battery_wh_24v15(),
            uses="food-delivery|delivery|item-delivery",
            videos=[],
            notes_extra=(
                "QA 2026-07-29: emptied generic videos; CN paopao URL 404. "
                "Parameter sheet paopao_parameter-pc_en_01.jpg."
            ),
        ),
        1989: fix(
            name="DaBen Robot",
            model="DaBen",
            series="delivery",
            family_name="AoBo Delivery Service Robots",
            url=pdp("daben"),
            image=HERO_CHANGES[1989],
            description=(
                "DaBen is an Aobo wheeled food-delivery robot with an open multi-shelf oval "
                "cabin (three illuminated shelves) and indoor autonomous base for hotel and "
                "restaurant delivery (OEM H2: DaBen transport food delivery robot)."
            ),
            purpose=APPS_DELIVERY,
            features=(
                f"130 cm height; 30 kg weight; 24V 15Ah polymer lithium battery (~9 h runtime); "
                f"open three-shelf oval cabin with LED shelf lighting. {COMMON_FEAT}"
            ),
            tags=TAGS_DELIVERY,
            weight_kg=30,
            height_mm=1300,
            runtime_minutes=540,
            battery_wh=battery_wh_24v15(),
            uses="food-delivery|delivery|room-service",
            videos=[],
            notes_extra=(
                "QA 2026-07-29: hero→daben-r2 (matches parameter sheet multi-shelf); "
                "removed BenBen-titled + generic videos. Parameter sheet daben_parameter-pc_en_01.jpg."
            ),
        ),
        1627: fix(
            name="ShaQiang Educational Robot",
            model="ShaQiang",
            series="education",
            family_name="AoBo Educational Robots",
            url=pdp("shaqiang"),
            image=hero("shaqiang/shaqiang-r1.jpg"),
            description=(
                "ShaQiang is Aobo's humanoid educational programming robot with a sculpted "
                "face, chest display, and articulated arms for STEM classroom demonstration "
                "and robotics training (OEM H2: ShaQiang Educational programming robot)."
            ),
            purpose=APPS_EDU,
            features=(
                "Humanoid educational programming robot with chest touchscreen and "
                "articulated hands; demo stand / indoor classroom use. "
                "OEM EN PDP has no Function Parameter numeric table — typed specs blank "
                "after dead search (parameter-pc/sm sheets 404)."
            ),
            tags=TAGS_EDU_HUMANOID,
            uses="education",
            industry="education|commercial",
            videos=[],
            notes_extra=(
                "QA 2026-07-29: description was wrongly 'wheeled platform' — hero is humanoid; "
                "aligned copy/tags; emptied YT_TESTS."
            ),
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
                "OEM datasheet (QB/des/QB.jpg) titles 'Qb Reception Service Robot'; EN PDP H2 "
                "wrongly says 'transport food delivery robot'."
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
            videos=[],
            notes_extra=(
                "QA 2026-07-29: Reception datasheet is primary truth vs EN H2 food-delivery label; "
                "emptied generic videos. Battery Ah only (no V) — Wh blank."
            ),
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
            speed=3.6,
            runtime_minutes=360,
            uses="food-delivery|delivery",
            videos=[],
            notes_extra="QA 2026-07-29 soft: emptied unnamed delivery/generic videos.",
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
            videos=[],
            notes_extra="QA 2026-07-29 soft: emptied unnamed delivery/generic videos.",
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
                "OEM datasheet (DOCTOR3/des/DOCTOR3.jpg) is Reception Series; EN PDP H2 wrongly "
                "says 'transport food delivery robot'."
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
            videos=[],
            notes_extra=(
                "QA 2026-07-29: Reception datasheet truth vs EN H2; emptied generic videos. "
                "Battery Ah only (no V) — Wh blank."
            ),
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
                "OEM datasheet (BARRO/des/BARRO.jpg) titles 'Barro Reception Service Robot'; "
                "EN PDP H2 wrongly says 'transport food delivery robot'."
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
            videos=[],
            notes_extra=(
                "QA 2026-07-29: kept BARRO/ui/1 silver Reception hero; emptied generic videos; "
                "datasheet confirms Reception Series. Battery Ah only (no V) — Wh blank."
            ),
        ),
    }


def build_row(fix_row: dict[str, Any], *, tags: str) -> dict[str, Any]:
    row: dict[str, Any] = {
        "company_slug": COMPANY_SLUG,
        "company_name": COMPANY_NAME,
        "source_locale": "en",
    }
    skip = {"videos", "notes_force", "source_note", "images", "replace_media", "imageless"}
    for k, v in fix_row.items():
        if k in skip or v is None or v == "":
            continue
        row[k] = v
    row["tags"] = tags
    if fix_row.get("notes_force"):
        row["notes"] = fix_row["notes_force"]
    if fix_row.get("source_note"):
        row["research_notes"] = fix_row["source_note"]
    videos = fix_row.get("videos") or []
    if videos:
        row["video_urls"] = enrich_video_list(videos)
    else:
        # Explicit empty list — still a no-op for clear unless replace_videos + ORM.
        row["video_urls"] = []
    if fix_row.get("image"):
        row["images"] = [fix_row["image"]]
        # Prefer external OEM URL so copy-media re-fetches even if CDN path sticky.
        row["image"] = fix_row["image"]
    elif fix_row.get("imageless"):
        row["images"] = []
        row["image"] = ""
    # Cite datasheet / parameter assets where they settle truth.
    info = list(row.get("information_source_urls") or [])
    extras = {
        1626: f"{OEM}/image/robot/QB/des/QB.jpg",
        1617: f"{OEM}/image/robot/DOCTOR3/des/DOCTOR3.jpg",
        1610: f"{OEM}/image/robot/BARRO/des/BARRO.jpg",
        1991: f"{OEM}/image/robot/dipan/dipan_parameter-pc_en_01.jpg",
        1990: f"{OEM}/image/robot/paopao/paopao_parameter-pc_en_01.jpg",
        1989: f"{OEM}/image/robot/daben/daben_parameter-pc_en_01.jpg",
        2006: f"{OEM}/image/robot/xiaoan/xiaoan_parameter-pc_en_01.jpg",
        2005: f"{OEM}/image/robot/landou/landou_parameter-pc_en_01.jpg",
    }
    return row, extras


def hash_url(url: str) -> str | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=90)
        if not resp.ok or len(resp.content) < 1000:
            return None
        return hashlib.md5(resp.content).hexdigest()
    except requests.RequestException:
        return None


def assert_heroes_ok(fixes: dict[int, dict[str, Any]], client: ResearchApiClient) -> None:
    """Hash-dedupe QA heroes vs other pending company primaries."""
    company_hashes: dict[str, list[int]] = {}
    for r in client.list_robots_for_company(COMPANY_ID):
        if str(r.get("status") or "").lower() == "rejected":
            continue
        rid = int(r["id"])
        if rid in fixes:
            continue  # will be replaced
        url = r.get("s3_image") or r.get("image") or ""
        if not url:
            continue
        h = hash_url(str(url))
        if h:
            company_hashes.setdefault(h, []).append(rid)

    for rid, fix_row in fixes.items():
        if fix_row.get("imageless"):
            print(f"  hero {rid}: IMAGELESS")
            continue
        url = fix_row.get("image")
        if not url:
            raise RuntimeError(f"{rid}: missing image")
        h = hash_url(str(url))
        if not h:
            raise RuntimeError(f"{rid}: failed hash {url}")
        if h.startswith("1df11ec2e4e6"):
            raise RuntimeError(f"{rid}: refused Service_en.jpg banner")
        occupied = company_hashes.get(h) or []
        if occupied:
            raise RuntimeError(f"{rid}: hero hash collides with {occupied}")
        company_hashes.setdefault(h, []).append(rid)
        print(f"  hero {rid}: {h[:12]} ok")


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


def try_dismiss_flags(rid: int, flags: list[str]) -> dict[str, Any]:
    """Prefer content-queue dismiss-flag; expect 403 without staff session."""
    secret = _internal_secret()
    api = _admin_base()
    results: dict[str, Any] = {}
    for flag in flags:
        url = f"{api}/admin/robots/robot/content-queue/api/robot/{rid}/dismiss-flag/"
        try:
            resp = requests.post(
                url,
                headers={
                    "Content-Type": "application/json",
                    "X-Internal-Secret": secret,
                },
                json={"flag": flag},
                timeout=60,
            )
            results[flag] = f"{resp.status_code} {(resp.text or '')[:80]}"
        except requests.RequestException as exc:
            results[flag] = f"ERR {exc}"
    return results


def current_pod() -> str:
    out = subprocess.run(
        [
            "kubectl",
            "get",
            "pods",
            "-n",
            NS,
            "--field-selector=status.phase=Running",
            "-o",
            "jsonpath={.items[*].metadata.name}",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if out.returncode != 0:
        raise RuntimeError(out.stderr or out.stdout or "kubectl get pods failed")
    for name in out.stdout.split():
        if name.startswith("robotaigeek-prod-") and "mcp" not in name:
            return name
    raise RuntimeError("no running robotaigeek-prod pod found")


def kubectl_orm(script: str) -> str:
    """Pipe a Python script to manage.py shell on stdin (multiline -c is unreliable)."""
    pod = current_pod()
    proc = subprocess.run(
        [
            "kubectl",
            "exec",
            "-i",
            "-n",
            NS,
            pod,
            "-c",
            "django-app",
            "--",
            "python",
            "manage.py",
            "shell",
        ],
        input=script,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"kubectl ORM failed rc={proc.returncode}\n"
            f"stdout={proc.stdout[-2000:]}\nstderr={proc.stderr[-2000:]}"
        )
    return proc.stdout


def orm_clear_and_drop_flags(
    *,
    clear_photo_ids: list[int],
    empty_video_ids: list[int],
    drop_flag_ids: list[int],
) -> str:
    script = f"""
from robots.models import Robot, RobotPhoto, RobotVideo
from robots.quality import VERIFICATION_FLAG_KEYS

clear_photos = {clear_photo_ids!r}
empty_videos = {empty_video_ids!r}
drop_ids = {drop_flag_ids!r}
drop_keys = set(VERIFICATION_FLAG_KEYS) | {{'image_mismatch','video_mismatch','url_content_mismatch','content_contradiction','unverifiable'}}

out = {{'photos': [], 'videos': [], 'flags': []}}

for rid in clear_photos:
    r = Robot.objects.filter(id=rid, status='pending_review').first()
    if not r:
        out['photos'].append({{'id': rid, 'err': 'missing'}})
        continue
    n = 0
    for p in r.photos.filter(deleted=False):
        p.deleted = True
        p.is_primary = False
        p.save(update_fields=['deleted', 'is_primary'])
        n += 1
    r.image = ''
    r.s3_image = ''
    r.save(update_fields=['image', 's3_image'])
    out['photos'].append({{'id': rid, 'cleared': n}})

for rid in empty_videos:
    r = Robot.objects.filter(id=rid, status='pending_review').first()
    if not r:
        out['videos'].append({{'id': rid, 'err': 'missing'}})
        continue
    qs = r.videos.filter(deleted=False)
    n = qs.count()
    qs.update(deleted=True, is_primary=False)
    out['videos'].append({{'id': rid, 'cleared': n}})

for rid in drop_ids:
    r = Robot.objects.filter(id=rid).first()
    if not r:
        out['flags'].append({{'id': rid, 'err': 'missing'}})
        continue
    before = list(r.quality_flags or [])
    after = [f for f in before if (f.get('flag') if isinstance(f, dict) else f) not in drop_keys]
    r.quality_flags = after
    r.save(update_fields=['quality_flags'])
    removed = sorted({{(f.get('flag') if isinstance(f, dict) else f) for f in before}} - {{(f.get('flag') if isinstance(f, dict) else f) for f in after}})
    out['flags'].append({{'id': rid, 'removed': removed, 'remaining': [f.get('flag') if isinstance(f, dict) else f for f in after]}})

import json
print('ORM_RESULT=' + json.dumps(out, ensure_ascii=False))
"""
    return kubectl_orm(script)


def import_one(
    client: ResearchApiClient,
    rid: int,
    row: dict[str, Any],
    *,
    replace_media: bool,
    replace_videos: bool,
    created_by_id: int,
) -> dict[str, Any]:
    payload = dict(row)
    payload["id"] = rid
    payload["created_by_id"] = created_by_id
    payload["status"] = "pending_review"
    # Force external OEM image for hero changes so copy-media redownloads.
    result = client.bulk_import_robots(
        [payload],
        update_existing=True,
        patch_existing=True,
        status="pending_review",
        skip_company_update=True,
        created_by_id=created_by_id,
        replace_media=replace_media,
        replace_videos=replace_videos,
    )
    if int(result.get("created_count") or 0) != 0:
        raise RuntimeError(f"{rid}: unexpected created_count={result.get('created_count')}")
    if int(result.get("error_count") or 0):
        raise RuntimeError(f"{rid}: bulk-import errors {result}")
    return result


def write_report(rows: list[dict[str, Any]], cdn: dict[str, Any] | None, orm: Any) -> None:
    lines = [
        "---",
        "type: log",
        "title: Aobo Robot 1384 QA fix",
        "status: draft",
        "version: 1.0",
        "owner: AI",
        "last_updated: 2026-07-29",
        "tags:",
        "  - content-queue",
        "  - aobo-robot",
        "  - qa",
        "---",
        "",
        "# Aobo Robot (1384) QA fix",
        "",
        "## Summary",
        "",
        f"- Targeted: **{len(rows)}** pending_review robots with verification / mismatch flags.",
        "- Actions: hero swaps (XiaoAn r2, DaBen r2), ORM-clear KaKa Welcome junk photo, "
        "strip generic/sibling videos, align Reception vs delivery copy to datasheets, "
        "drop verification flag keys after media/copy fixes.",
        f"- CDN verify: `{cdn}`",
        f"- ORM: `{orm}`",
        "",
        "## Per-robot",
        "",
    ]
    approve: list[int] = []
    holds: list[str] = []
    for row in rows:
        rid = row["id"]
        lines.append(f"### `{rid}` {row['name']}")
        lines.append("")
        lines.append(f"- **Was:** {row['was']}")
        lines.append(f"- **Fixed:** {row['fixed']}")
        if row.get("hold"):
            lines.append(f"- **Hold:** {row['hold']}")
            holds.append(f"`{rid}` — {row['hold']}")
        else:
            approve.append(rid)
        lines.append("")

    lines.extend(
        [
            "## Approve-ready (after QA)",
            "",
            f"`{', '.join(str(i) for i in sorted(approve))}`",
            "",
            "## Remaining holds",
            "",
        ]
    )
    if holds:
        for h in holds:
            lines.append(f"- {h}")
    else:
        lines.append("- None (soft few_photos / missing_release_year / missing_price ignored).")
    lines.extend(
        [
            "",
            "## Soft leftovers (ignored per stakeholder)",
            "",
            "- `missing_price` on all 15",
            "- `few_photos` / `missing_release_year` when still present",
            "- `2000` UV + `1627` ShaQiang: no OEM numeric parameter sheet (documented dead search)",
            "",
            "## Script",
            "",
            "`scripts/research/fix_aobo_1384_qa.py`",
            "",
            "## Related",
            "",
            "- [aobo-1384-enrichment.md](aobo-1384-enrichment.md)",
            "- [aobo-1384-qa-probe.json](aobo-1384-qa-probe.json)",
            "",
        ]
    )
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {REPORT}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Aobo 1384 QA fix for 15 flagged robots")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--copy-media", action="store_true")
    parser.add_argument("--orm-clear", action="store_true", help="kubectl ORM photo/video/flag clear")
    parser.add_argument("--verify-cdn", action="store_true")
    parser.add_argument("--created-by-id", type=int, default=1)
    parser.add_argument("--only", type=int, nargs="*")
    args = parser.parse_args()

    client = ResearchApiClient()
    catalog = TagCatalog.load(client=client)
    created_by = resolve_created_by_id(args.created_by_id)
    fixes = build_qa_fixes()
    if args.only:
        fixes = {k: v for k, v in fixes.items() if k in args.only}

    print("Pre-apply hero hash assert…")
    assert_heroes_ok(fixes, client)

    report_rows: list[dict[str, Any]] = []
    WAS = {
        2006: "image_mismatch (wheeled vs page humanoid cross-nav) + content_contradiction; YT_TESTS generic",
        2005: "image_mismatch blue vs white siblings; video_mismatch generics; content_contradiction",
        2002: "video_mismatch (YT_PUBLIC/YT_TESTS wrong models)",
        2000: "missing_specs (no UV sheet); video_mismatch generics",
        1993: "image_mismatch Service_en.jpg laptop/airplane banner still attached",
        1992: "image_mismatch vs page humanoid cross-nav (hero itself OK)",
        1991: "url_content_mismatch OEM H2 'Daikin welcome'; content_contradiction",
        1990: "url_content_mismatch OEM H2 'Doctors'; content_contradiction",
        1989: "image_mismatch closed-body r1 vs multi-shelf desc; video_mismatch BenBen clip",
        1627: "image_mismatch humanoid photo vs wheeled desc; missing_specs; content_contradiction",
        1626: "content_contradiction Reception datasheet vs EN H2 food delivery",
        1625: "soft only (few_photos/year/price)",
        1618: "soft only",
        1617: "content_contradiction Reception vs EN H2 food delivery",
        1610: "image_mismatch silver vs white page variants; video_mismatch; Reception vs delivery",
    }

    imported: list[int] = []
    for rid, fix_row in fixes.items():
        tags = resolve_tags(catalog, str(fix_row.get("tags") or ""))
        row, extras = build_row(fix_row, tags=tags)
        # Attach datasheet sources without wiping on every replace_media — patch later.
        info = [fix_row.get("url")] if fix_row.get("url") else []
        if rid in extras:
            info.append(extras[rid])
        row["information_source_urls"] = [u for u in info if u]

        replace_media = rid in HERO_CHANGES or bool(fix_row.get("imageless"))
        # Only use replace_videos when we have a non-empty replacement list.
        # Empty clear is ORM (bulk-import empty+replace_videos is a no-op).
        videos = fix_row.get("videos") or []
        replace_videos = bool(videos)

        hold = None
        if fix_row.get("imageless"):
            hold = "Imageless IMAGE TO-DO — no distinct welcome KaKa hero (shares bytes with 1997 Transport)"
        if rid in (2000, 1627) and not fix_row.get("weight_kg"):
            hold = (hold + "; " if hold else "") + "missing_specs after dead OEM parameter search"

        fixed_bits = []
        if rid in HERO_CHANGES:
            fixed_bits.append(f"hero→{HERO_CHANGES[rid].split('/image/robot/')[-1]}")
        if fix_row.get("imageless"):
            fixed_bits.append("ORM-clear junk photo / imageless")
        if rid in EMPTY_VIDEO_IDS or not videos:
            fixed_bits.append("videos emptied (or model-only kept)")
        if videos:
            fixed_bits.append(f"videos→{len(videos)} title-matched")
        fixed_bits.append("copy/flags aligned; verification keys dropped")

        report_rows.append(
            {
                "id": rid,
                "name": fix_row["name"],
                "was": WAS.get(rid, "QA flags"),
                "fixed": "; ".join(fixed_bits),
                "hold": hold,
            }
        )

        print(
            f"{'APPLY' if args.apply else 'DRY'} {rid} {fix_row['name']}: "
            f"rmedia={replace_media} rvid={replace_videos} vids={len(videos)} "
            f"img={'(none)' if fix_row.get('imageless') else (fix_row.get('image') or '')[-40:]}"
        )

        if not args.apply:
            continue

        result = import_one(
            client,
            rid,
            row,
            replace_media=replace_media,
            replace_videos=replace_videos,
            created_by_id=created_by,
        )
        print(f"  import {rid}: { {k: result.get(k) for k in ('updated_count','created_count','error_count')} }")
        patch_typed(client, rid, fix_row)
        # Movement type for ShaQiang humanoid — prefer legged if catalog allows.
        if rid == 1627:
            try:
                client._patch(
                    f"robots/robots/{rid}/",
                    {"movement_types": ["legged"], "uses": ["education"]},
                )
            except Exception as exc:  # noqa: BLE001
                print(f"  warn taxonomy patch {rid}: {exc}")
        imported.append(rid)
        time.sleep(0.15)

    orm_result: Any = None
    if args.apply and args.orm_clear:
        print("ORM clear photos / empty videos / drop verification flags…")
        # Try dismiss-flag first (likely 403).
        sample = try_dismiss_flags(2002, ["video_mismatch"])
        print(f"  dismiss-flag sample 2002: {sample}")
        out = orm_clear_and_drop_flags(
            clear_photo_ids=[1993] if 1993 in fixes else [],
            empty_video_ids=sorted(EMPTY_VIDEO_IDS & set(fixes)),
            drop_flag_ids=sorted(fixes),
        )
        for line in out.splitlines():
            if line.startswith("ORM_RESULT="):
                orm_result = json.loads(line[len("ORM_RESULT=") :])
                print(json.dumps(orm_result, indent=2)[:4000])
                break
        else:
            print(out[-2000:])
            orm_result = {"raw": out[-1500:]}

    copy_stats = None
    if args.apply and args.copy_media:
        need_copy = [rid for rid in imported if rid in HERO_CHANGES]
        print(f"copy-media for hero changes: {need_copy}")
        ok, fail = trigger_copy_media(need_copy)
        copy_stats = {"ok": ok, "fail": fail, "ids": need_copy}
        print(f"copy-media {copy_stats}")

    cdn = None
    if args.verify_cdn:
        from verify_cdn_images import main as verify_main  # type: ignore

        # Fallback: subprocess
        proc = subprocess.run(
            [sys.executable, "verify_cdn_images.py", "--company-id", str(COMPANY_ID)],
            cwd=str(_RESEARCH_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        print(proc.stdout[-2000:])
        if proc.returncode != 0:
            print(proc.stderr[-1000:], file=sys.stderr)
        cdn = {"rc": proc.returncode, "tail": (proc.stdout or "")[-500:]}

    write_report(report_rows, cdn, orm_result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
