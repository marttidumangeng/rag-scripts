"""Fix LimX Dynamics (company 68) content-queue enrichment.

OEM: https://www.limxdynamics.com/en
Current catalog PDPs: /en/products/{luna,oli,tron1,tron2}
Legacy: W1 / P1 / CL-1 (news + about timeline); CL-3 = Oli codename.

Issues addressed:
- Off-domain URLs (pr.ai, Facebook) → OEM product/news pages
- Reject 4856 TRON 1 duplicate of 158; 2170 company shell; 4855 CL-3 (= Oli)
- Clear fabricated payload_kg=10 on non-TRON1 keepers
- Distinct OEM heroes for Luna / Oli / TRON 2; keep verified CDN for TRON 1
- Fail-closed IMAGE TO-DO for W1 / CL-1 / P1 (no distinct OEM product hero)
- family_* / purpose apps / CN manufacturer / Available or Discontinued / Announced
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

COMPANY_ID = 68
COMPANY_SLUG = "limx-dynamics-2"  # existing odd slug; do not invent a rename
COMPANY_NAME = "LimX Dynamics"
COMPANY_WEBSITE = "https://www.limxdynamics.com/en"
FAMILY_PREFIX = "limx-dynamics"  # stakeholder family_key format
CN = "CN"
CN_COUNTRY_ID = 3

URL_LUNA = f"{COMPANY_WEBSITE}/products/luna"
URL_LUNA_SPEC = f"{URL_LUNA}/spec"
URL_OLI = f"{COMPANY_WEBSITE}/products/oli"
URL_OLI_SPEC = f"{URL_OLI}/spec"
URL_TRON1 = f"{COMPANY_WEBSITE}/products/tron1"
URL_TRON1_SPEC = f"{URL_TRON1}/spec"
URL_TRON2 = f"{COMPANY_WEBSITE}/products/tron2"
URL_TRON2_SPEC = f"{URL_TRON2}/spec"
URL_W1_NEWS = f"{COMPANY_WEBSITE}/news/BK000034"
URL_CL1_NEWS = f"{COMPANY_WEBSITE}/news/BK000049"
URL_P1_NEWS = f"{COMPANY_WEBSITE}/news/BK000032"
URL_ABOUT = f"{COMPANY_WEBSITE}/about"
URL_OLI_LAUNCH = f"{COMPANY_WEBSITE}/news/BK000043"
URL_LUNA_LAUNCH = f"{COMPANY_WEBSITE}/news/BK000062"
URL_TRON1_LAUNCH = f"{COMPANY_WEBSITE}/news/BK000040"

IMG = {
    "tron2": (
        "https://limx-video.oss-cn-beijing.aliyuncs.com/"
        "limx-website/products/tron2/torso-front.webp"
    ),
    "oli": (
        "https://limx-video.oss-cn-beijing.aliyuncs.com/"
        "limx-website/products/oli/img-1.webp"
    ),
    "luna": (
        "https://limx-video.oss-cn-beijing.aliyuncs.com/"
        "limx-website/products/luna/luna-3-1.png"
    ),
}
EXPECTED_MD5 = {
    "tron2": "1f8b8d278f00d01d3547fd8eb2faf19a",
    "oli": "1238c9a8fdb6ac3b533b2aee3c604fde",
    "luna": "79753d051badfa37c9ce8227208c45c4",
}

YT_TRON1 = [
    "https://www.youtube.com/watch?v=9Lypkwll6tM",  # Launches Multi-Modal Biped Robot TRON 1
    "https://www.youtube.com/watch?v=4cxC0qjm82k",  # TRON 1 Stability and Recovery
    "https://www.youtube.com/watch?v=kAOkQZ2-yBg",  # TRON 1 Point-foot
]
YT_TRON2 = [
    "https://www.youtube.com/watch?v=Ut3QFPr7hyo",  # TRON 2 Officially Launched
    "https://www.youtube.com/watch?v=0-wvQSfi3W8",  # TRON 2 retail
    "https://www.youtube.com/watch?v=chYwj78OuWk",  # TRON 2 Light Up the Future
]
YT_OLI = [
    "https://www.youtube.com/watch?v=uyHDkx9X3fc",  # Meet LimX Oli
    "https://www.youtube.com/watch?v=NDCt3xwXl8o",  # Tennis ball picks up & tosses
    "https://www.youtube.com/watch?v=AGKWOrBViu0",  # Walks Like a Human
]
YT_LUNA = [
    "https://www.youtube.com/watch?v=-lgo5xqgVko",  # Meet LimX Luna
    "https://www.youtube.com/watch?v=16LyEh0LTME",  # officially launched LimX Luna
    "https://www.youtube.com/watch?v=bHEX7ESdZXk",  # Debuts Like a Star
]
YT_W1 = [
    "https://www.youtube.com/watch?v=tEYLccxFuns",  # Launches First Wheeled Quadruped W1
    "https://www.youtube.com/watch?v=p1g5kk2qD4E",  # W1 Evolves into a Biped
]
YT_CL1 = [
    "https://www.youtube.com/watch?v=11Iz8x27jS4",  # Continuous Heavy Objects Loading
    "https://www.youtube.com/watch?v=sihIDeJ4Hmk",  # Dynamic Testing CL-1
    "https://www.youtube.com/watch?v=hbYia3Wbd2k",  # Steps to the Next Level
]
YT_P1 = [
    "https://www.youtube.com/watch?v=HYFCGPPjJnk",  # Rigorous Testing P1
    "https://www.youtube.com/watch?v=UpNid_rWDnI",  # Conquers the Wild
    "https://www.youtube.com/watch?v=XmVVVW_34is",  # Introducing Biped Robot P1
]

TAGS_HUMANOID = "Humanoid|Bipedal|Legged|Research|Autonomous|Electric|Embodied AI|Education"
TAGS_TRON = (
    "Bipedal|Legged|Wheeled|Research|Autonomous|Electric|"
    "Research Platform|Mobile Robot"
)
TAGS_W1 = "Quadruped|Wheeled|Legged|Research|Autonomous|Electric|Outdoor"
TAGS_P1 = "Bipedal|Legged|Research|Autonomous|Electric|Locomotion Research|Research Platform"

PURPOSE_LUNA = (
    "Interactive entertainment and stage performance\n"
    "Human-robot interaction demos\n"
    "Multimodal voice and gesture interaction\n"
    "Embodied AI research and choreography"
)
PURPOSE_OLI = (
    "Full-size humanoid research and education\n"
    "Embodied AI algorithm development\n"
    "Mobile manipulation and dexterous tasks\n"
    "Indoor service and guidance pilots"
)
PURPOSE_TRON1 = (
    "Multi-modal biped locomotion research\n"
    "Reinforcement learning and sim-to-real\n"
    "Point-foot, sole, and wheeled foot-end experiments\n"
    "University and lab platform development"
)
PURPOSE_TRON2 = (
    "Multi-form embodied locomotion and manipulation\n"
    "Dual-arm desktop and retail tasks\n"
    "Sole and wheeled biped operations\n"
    "Embodied AI data collection and teleoperation"
)
PURPOSE_W1 = (
    "All-terrain wheeled-quadruped mobility research\n"
    "Stair and slope traversal experiments\n"
    "Perception-based gait switching\n"
    "Early LimX locomotion platform development"
)
PURPOSE_CL1 = (
    "Full-size humanoid locomotion research\n"
    "Stair climbing and dynamic balance\n"
    "Heavy-object loading demos\n"
    "Humanoid motion-control development"
)
PURPOSE_P1 = (
    "Outdoor biped locomotion research\n"
    "Reinforcement-learning gait experiments\n"
    "Rough-terrain walking demos\n"
    "Early biped platform development"
)

IMAGE_TODO_W1 = (
    "[IMAGE TO-DO — no hero, deliberate]\n"
    "Checked limxdynamics.com/en/products (no W1 PDP), news BK000034, about timeline, "
    "and support download center references. No distinct W1 product still on OEM CDN; "
    "prior gallery wrongly used TRON 2 wheeled-45deg.png (sibling). Official YouTube "
    "launch thumbs are text-heavy promo banners (not is_primary).\n"
    "ACTION FOR TEAM: source a licensed W1 product render from LimX press kit or "
    "request from OEM.\n"
    "Do NOT substitute TRON/Oli/Luna renders.\n"
    "---\n"
)
IMAGE_TODO_CL1 = (
    "[IMAGE TO-DO — no hero, deliberate]\n"
    "OEM news BK000049 names CL-1 but page HTML has no extractable model still; no CL-1 "
    "PDP on current EN catalog (Luna/Oli/TRON only).\n"
    "ACTION FOR TEAM: pull a still from official LimX CL-1 YouTube (e.g. "
    "11Iz8x27jS4 / sihIDeJ4Hmk) with republication rights, or request OEM press asset.\n"
    "Do NOT substitute Oli/Luna heroes.\n"
    "---\n"
)
IMAGE_TODO_P1 = (
    "[IMAGE TO-DO — no hero, deliberate]\n"
    "OEM news BK000032 names P1; current CDN hero visually matches TRON-series biped "
    "(blue LED torso + red joint rings) and is treated as sibling contamination — "
    "cleared fail-closed. No distinct P1 still on current product CDN.\n"
    "ACTION FOR TEAM: source P1-specific OEM/press still (e.g. Tanglang Mountain / "
    "IROS era) with rights.\n"
    "Do NOT reuse TRON 1/2 heroes.\n"
    "---\n"
)

REJECTS: dict[int, str] = {
    4856: (
        "Duplicate of robot 158 (TRON 1). Same multi-modal biped SKU; OEM PDP is "
        f"{URL_TRON1}. 4856 had no hero and an off-domain pr.ai URL. Keep 158 as the "
        "canonical TRON 1 record."
    ),
    2170: (
        "Not a robot product — company/technology shell named 'LimX Dynamics Technology' "
        f"with homepage URL {COMPANY_WEBSITE} and a COSA/chip marketing graphic, not a "
        "model PDP. Reject as non_robot / junk; enrich real SKUs instead."
    ),
    4855: (
        "Duplicate of robot 670 (Oli). LimX full-size humanoid launched as LimX Oli "
        f"({URL_OLI_LAUNCH}; PDP {URL_OLI}). CL-3 was the pre-release / press codename "
        "for the same platform (no OEM CL-3 PDP; Facebook URL off-domain). Keep 670."
    ),
}

_AVAIL_IDS = {
    "announced": 10,
    "available": 11,
    "released": 3,
    "discontinued": 4,
    "pre_order": 12,
    "prototype": 2,
    "research": 9,
}


def _headers() -> dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }


def verify_hero(name: str, url: str) -> str:
    resp = requests.get(url, timeout=60, headers=_headers())
    resp.raise_for_status()
    data = resp.content
    magic_ok = (
        data[:8] == b"\x89PNG\r\n\x1a\n"
        or data[:3] == b"\xff\xd8\xff"
        or data[:4] == b"RIFF"
    )
    if not magic_ok:
        raise RuntimeError(f"{name}: not an image magic={data[:8]!r}")
    md5 = hashlib.md5(data).hexdigest()
    expected = EXPECTED_MD5.get(name)
    if expected and md5 != expected:
        raise RuntimeError(f"{name}: md5 mismatch got={md5} expected={expected}")
    if len(data) < 8_000:
        raise RuntimeError(f"{name}: image too small ({len(data)} bytes)")
    return md5


def _admin_base() -> str:
    api = (os.environ.get("IMPORT_SYNC_API_BASE_URL") or "").rstrip("/")
    if api.endswith("/api/v1"):
        return api[: -len("/api/v1")]
    return api.rsplit("/api/", 1)[0] if "/api/" in api else api


def _internal_secret() -> str:
    secret = (
        os.environ.get("INTERNAL_API_SECRET")
        or os.environ.get("CONTENT_QUEUE_INTERNAL_SECRET")
        or ""
    )
    if secret:
        return secret
    for candidate in (
        _RESEARCH_DIR.parent.parent / "robotaigeek-server" / ".env",
        _RESEARCH_DIR.parent.parent / "robotaigeek-server" / ".env.local",
    ):
        if not candidate.exists():
            continue
        for line in candidate.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def reject_robot(client: ResearchApiClient, rid: int, reason: str) -> str:
    url = f"{_admin_base()}/admin/robots/robot/content-queue/api/robot/{rid}/reject/"
    headers = {
        "Content-Type": "application/json",
        "X-Internal-Secret": _internal_secret(),
    }
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
    skip = {
        "videos",
        "notes_force",
        "source_note",
        "images",
        "replace_media",
        "clear_payload",
        "clear_height",
        "clear_dof",
        "availability_status_key",
        "imageless",
        "keep_existing_image",
        "dof",
    }
    for k, v in fix.items():
        if k in skip or v is None or v == "":
            continue
        row[k] = v
    if fix.get("dof") is not None:
        row["dof"] = fix["dof"]
    row["tags"] = tags
    if fix.get("notes_force"):
        row["notes"] = fix["notes_force"]
    if fix.get("source_note"):
        row["research_notes"] = fix["source_note"]
    videos = fix.get("videos") or []
    if videos:
        row["video_urls"] = enrich_video_list(videos)
    if fix.get("image") and not fix.get("imageless") and not fix.get("keep_existing_image"):
        row["images"] = [fix["image"]]
        row["image"] = fix["image"]
    row["availability_status_key"] = fix.get("availability_status_key") or "available"
    return row


def patch_typed(client: ResearchApiClient, rid: int, fix: dict[str, Any]) -> None:
    body: dict[str, Any] = {}
    for k in (
        "payload_kg",
        "weight_kg",
        "speed",
        "length_mm",
        "width_mm",
        "height_mm",
        "runtime_minutes",
        "dof",
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
        "release_year",
        "programming_interface",
        "deployment_context",
        "ecosystem_compatibility",
        "safety_fencing",
        "mounting_options",
    ):
        if k in fix and fix[k] not in (None, ""):
            body[k] = fix[k]
    if fix.get("clear_payload"):
        body["payload_kg"] = None
    if fix.get("clear_height"):
        body["height_mm"] = None
    if fix.get("clear_dof"):
        body["dof"] = None
    avail_key = fix.get("availability_status_key")
    if avail_key:
        body["availability_status"] = _AVAIL_IDS.get(str(avail_key), avail_key)
    if fix.get("imageless"):
        body["image"] = ""
        body["s3_image"] = None
    ok_keys: list[str] = []
    for k, v in body.items():
        try:
            client._patch(f"robots/robots/{rid}/", {k: v})
            ok_keys.append(k)
        except Exception as exc:
            print(f"  patch fail {rid}.{k}: {exc}", file=sys.stderr)
    try:
        client._patch(
            f"robots/robots/{rid}/",
            {
                "manufacturer_countries": [CN_COUNTRY_ID],
                "manufacturer_country_ref": CN_COUNTRY_ID,
            },
        )
        ok_keys.append("manufacturer_countries")
    except Exception as exc:
        print(f"  patch fail {rid}.manufacturer_countries: {exc}", file=sys.stderr)
    if ok_keys:
        print(f"  patched typed {rid}: {ok_keys}")


def drop_stale_media_flags(client: ResearchApiClient, robot_ids: list[int]) -> None:
    drop = {
        "duplicate_images",
        "image_mismatch",
        "video_mismatch",
        "url_content_mismatch",
        "url_domain_mismatch",
        "content_contradiction",
        "unverifiable",
        "non_english_content",
    }
    for rid in robot_ids:
        try:
            r = client._get(f"robots/robots/{rid}/")
        except Exception as exc:
            print(f"  flag-read fail {rid}: {exc}", file=sys.stderr)
            continue
        flags = r.get("quality_flags") or r.get("error_flags") or []
        if not isinstance(flags, list) or not flags:
            continue
        before = [(f.get("flag") if isinstance(f, dict) else f) for f in flags]
        after = [
            f
            for f in flags
            if (f.get("flag") if isinstance(f, dict) else f) not in drop
        ]
        removed = sorted(set(before) - {(f.get("flag") if isinstance(f, dict) else f) for f in after})
        if not removed:
            continue
        try:
            client._patch(f"robots/robots/{rid}/", {"quality_flags": after})
            print(f"  dropped flags {rid}: {removed}")
        except Exception as exc:
            print(f"  flag-drop fail {rid}: {exc} (may need ORM)", file=sys.stderr)


ROBOT_FIXES: dict[int, dict[str, Any]] = {
    4857: {
        "name": "Luna",
        "model_name": "Luna",
        "variant_code": "Luna",
        "variant_label": "Full-Size Interactive Humanoid",
        "url": URL_LUNA,
        "family_key": f"{FAMILY_PREFIX}:luna",
        "family_name": "Luna",
        "family_url": URL_LUNA,
        "product_url_scope": "exact_variant",
        "image": IMG["luna"],
        "description": (
            "LimX Luna is a full-size interactive humanoid robot for entertainment, "
            "stage performance, and multimodal human-robot interaction. At 160 cm with "
            "27 active degrees of freedom, slide-out batteries, and LimX motion/"
            "interaction software, it targets embodied demos and interactive venues."
        ),
        "purpose": PURPOSE_LUNA,
        "features": (
            "Height 160 cm; weight with battery 56 kg; active DoF 27 "
            "(leg 6 / arm 5 / waist 3 / neck 2 per OEM spec). "
            "Max arm payload 3 kg; max walking speed 5 km/h. "
            "Optional 5-finger hand (6 DoF); slide-out dual battery modules "
            "(10,000 mAh; ≈4 h life; ≈1 h recharge). "
            "RGB camera perception; WiFi 6 + Bluetooth; motion-control compute "
            "RK3588 / 16G / 256G. Active fall mitigation, force sensing, hardware "
            "E-stop, and safe action override on OEM PDP."
        ),
        "payload_kg": 3.0,
        "weight_kg": 56.0,
        "height_mm": 1600,
        "speed": 5.0,  # OEM Max Walking Speed 5 km/h
        "dof": 27,
        "runtime_minutes": 240,
        "availability_status_key": "available",
        "movement_type_keys": "legged|bipedal",
        "industry_keys": "research|education|entertainment",
        "use_keys": "research|education|entertainment|service",
        "category_slugs": "Humanoid|Legged-Robots",
        "sub_category_slug": "service-hospitality",
        "tags": TAGS_HUMANOID,
        "manufacturer_country_code": CN,
        "release_year": 2026,
        "programming_interface": "LimX COSA / embodied interaction stack; video-to-motion and kinesthetic teaching (OEM)",
        "deployment_context": "Interactive venues, stage demos, and humanoid HRI research",
        "ecosystem_compatibility": "LimX software stack; RGB perception; WiFi 6 / Bluetooth",
        "safety_fencing": "Active fall mitigation; external force sensing; hardware E-stop; safe action override",
        "mounting_options": "Free-standing biped humanoid",
        "videos": YT_LUNA,
        "information_source_urls": [URL_LUNA, URL_LUNA_SPEC, URL_LUNA_LAUNCH],
        "notes_force": (
            "[AI Research] EN PDP + /spec: height 160 cm, 56 kg w/ battery, 27 DoF, "
            "arm payload 3 kg, walk 5 km/h, ~4 h battery. Hero: OEM luna-3-1.png "
            "(close-up with LIMX DYNAMICS chest mark; md5-verified). URL fixed from "
            "news#Luna anchor to /en/products/luna. Cleared missing payload; status stays "
            "pending_review."
        ),
        "source_note": f"{URL_LUNA}; {URL_LUNA_SPEC}; {URL_LUNA_LAUNCH}",
    },
    670: {
        "name": "Oli",
        "model_name": "Oli EDU",
        "variant_code": "Oli EDU",
        "variant_label": "Oli EDU",
        "url": URL_OLI,
        "family_key": f"{FAMILY_PREFIX}:oli",
        "family_name": "Oli",
        "family_url": URL_OLI,
        "product_url_scope": "family",
        "image": IMG["oli"],
        "description": (
            "LimX Oli is a full-size general-purpose humanoid for research, education, "
            "and embodied AI. The Oli family (Lite / EDU / Super) shares a biped "
            "platform with multi-DoF arms, swappable batteries, and open interfaces; "
            "this record tracks the EDU column on the official spec table."
        ),
        "purpose": PURPOSE_OLI,
        "features": (
            "OEM family table (Lite | EDU | Super): EDU height 165 cm; weight ≤55 kg "
            "with battery; active DoF 33 (Lite 31 / Super 43); single-arm DoF 7; "
            "waist 3; neck 2; single-leg DoF 6. "
            "EDU/Lite max single-arm load 3 kg (Super 5 kg); max moving speed 5 km/h. "
            "Battery ~9,500 mAh; life about 2 h (Lite/EDU) / 1.5 h (Super). "
            "Multiple end-effectors (2-finger / 3-finger / 5-finger options). "
            "Head + chest depth cameras; self-developed IMU; dual compute paths on "
            "higher SKUs. Formerly press-codenamed CL-3 before Oli branding."
        ),
        "payload_kg": 3.0,  # EDU column max single-arm load
        "weight_kg": 55.0,
        "height_mm": 1650,
        "speed": 5.0,
        "dof": 33,
        "runtime_minutes": 120,
        "availability_status_key": "available",
        "movement_type_keys": "legged|bipedal",
        "industry_keys": "research|education|manufacturing",
        "use_keys": "research|education|service|material-handling",
        "category_slugs": "Humanoid|Legged-Robots",
        "sub_category_slug": "service-hospitality",
        "tags": TAGS_HUMANOID,
        "manufacturer_country_code": CN,
        "release_year": 2025,
        "programming_interface": "LimX SDK / COSA; ROS-compatible research workflows (OEM positioning)",
        "deployment_context": "Labs, education, and indoor humanoid pilots",
        "ecosystem_compatibility": "Depth cameras, IMU, Ethernet/USB/power interfaces; optional LiDAR",
        "safety_fencing": "Handheld emergency stop option on OEM table; research deploy with site E-stops",
        "mounting_options": "Free-standing biped humanoid; slide-out battery modules",
        "videos": YT_OLI,
        "information_source_urls": [URL_OLI, URL_OLI_SPEC, URL_OLI_LAUNCH],
        "notes_force": (
            "[AI Research] Specs from /en/products/oli/spec family table — EDU column "
            "(middle): 165 cm, ≤55 kg, 33 DoF, 3 kg arm load, 5 km/h. Super differs "
            "(175 cm / ≤60 kg / 43 DoF / 5 kg). Replaced prior chip/COSA graphic hero "
            "with OEM oli/img-1.webp (humanoid upper body; md5-verified). Cleared "
            "fabricated payload_kg=10. CL-3 queue row 4855 rejected as same SKU."
        ),
        "source_note": f"{URL_OLI}; {URL_OLI_SPEC}; {URL_OLI_LAUNCH}",
    },
    676: {
        "name": "TRON 2",
        "model_name": "TRON 2",
        "variant_code": "TRON 2",
        "variant_label": "Multi-Form Embodied Robot",
        "url": URL_TRON2,
        "family_key": f"{FAMILY_PREFIX}:tron",
        "family_name": "TRON",
        "family_url": URL_TRON2,
        "product_url_scope": "exact_variant",
        "image": IMG["tron2"],
        "description": (
            "LimX TRON 2 is a multi-form embodied robot with swappable sole/wheeled "
            "legs and optional dual-arm manipulation. It extends the TRON platform for "
            "loco-manipulation research, teleoperation, and embodied data collection."
        ),
        "purpose": PURPOSE_TRON2,
        "features": (
            "Single-arm DoF 7; single-leg DoF 5; active vision head DoF 2. "
            "Max end-effector load 5 kg/arm (extended 3 kg/arm); marketing dual-arm "
            "payload 10 kg (= 5+5). Max end-effector speed 5 m/s; repeatability ±0.5 mm. "
            "Locomotion: sole 2–3 m/s, wheeled 3–5 m/s; climbing sole 15° / wheeled 30°; "
            "step height 20 cm. Platform load capacity 30 kg flat walking / 20 kg stairs. "
            "Battery 46.8 V ternary lithium 9 Ah; max battery power 2,800 W; hot-swap "
            "supported. Gripper options (20 N, 85 mm width) or dexterous hand."
        ),
        "payload_kg": 5.0,  # OEM max per arm — NOT fabricated dual-arm marketing 10
        "clear_dof": True,  # prior dof=7 was single-arm only; total DoF not one OEM number
        "speed": 18.0,  # wheeled max 5 m/s → 18 km/h
        "availability_status_key": "available",
        "movement_type_keys": "legged|bipedal|wheeled",
        "industry_keys": "research|education|retail",
        "use_keys": "research|education|material-handling|service",
        "category_slugs": "Legged-Robots|Mobile-Robots",
        "sub_category_slug": "service-hospitality",
        "tags": TAGS_TRON,
        "manufacturer_country_code": CN,
        "release_year": 2025,
        "programming_interface": "VR teleoperation; LimX data collection / dual-arm safety boundary tools",
        "deployment_context": "Lab, retail pilots, and embodied AI data collection",
        "ecosystem_compatibility": "Waist/head/wrist RGBD (arms config); Ethernet; Intel Core Ultra compute options",
        "safety_fencing": "Dual-arm safety boundary protection; remote E-stop; fall/stand-up behaviors",
        "mounting_options": "Modular sole or wheeled legs; optional dual-arm torso",
        "videos": YT_TRON2,
        "information_source_urls": [URL_TRON2, URL_TRON2_SPEC],
        "notes_force": (
            "[AI Research] Specs from /en/products/tron2/spec. Cleared fabricated "
            "payload_kg=10 → typed 5 kg/arm (OEM Maximum End Effector Load). Wheeled "
            "top speed 5 m/s stored as speed=18 km/h. Replaced multi-config banner hero "
            "with OEM torso-front.webp (single TRON 2 biped; md5-verified). Prior dof=7 "
            "cleared (arm-only)."
        ),
        "source_note": f"{URL_TRON2}; {URL_TRON2_SPEC}",
    },
    158: {
        "name": "TRON 1",
        "model_name": "TRON 1",
        "variant_code": "TRON 1",
        "variant_label": "Multi-Modal Biped Robot",
        "url": URL_TRON1,
        "family_key": f"{FAMILY_PREFIX}:tron",
        "family_name": "TRON",
        "family_url": URL_TRON1,
        "product_url_scope": "exact_variant",
        "keep_existing_image": True,
        "description": (
            "LimX TRON 1 is a multi-modal biped research platform with interchangeable "
            "point-foot, sole, and wheeled foot-ends. It is sold as Educational and "
            "Standard editions and positioned as a gateway to humanoid reinforcement-"
            "learning research."
        ),
        "purpose": PURPOSE_TRON1,
        "features": (
            "Dimensions ≤ 392 × 420 × 845 mm; net weight ≤ 20 kg; load capacity ≤ 10 kg. "
            "Motion speed: point-foot <1 m/s; sole <1 m/s; wheeled ≤ 3 m/s. "
            "Max climbing angle ≤30°; max obstacle height ≤20 cm (wheeled-state notes). "
            "Battery 46.8 V ternary lithium 4.5 Ah; max power 1,000 W; range ≤2 h; "
            "charge <1 h (20–80%) with swap dock. Aluminum alloy + industrial plastic. "
            "Handheld remote up to 50 m; E-stop; optional roll cage / spare battery. "
            "Extension kits: arm, perception (LiDAR + depth), voice interaction."
        ),
        "payload_kg": 10.0,  # OEM Load Capacity ≤10 kg
        "weight_kg": 20.0,
        "length_mm": 392,
        "width_mm": 420,
        "height_mm": 845,
        "speed": 10.8,  # wheeled ≤3 m/s → 10.8 km/h
        "runtime_minutes": 120,
        "availability_status_key": "available",
        "movement_type_keys": "legged|bipedal|wheeled",
        "industry_keys": "research|education",
        "use_keys": "research|education",
        "category_slugs": "Legged-Robots|Mobile-Robots",
        "sub_category_slug": "service-hospitality",
        "tags": TAGS_TRON,
        "manufacturer_country_code": CN,
        "release_year": 2024,
        "programming_interface": "LimX TRON software + simulation; joint control / data recording tools",
        "deployment_context": "University labs and RL / loco-manipulation research",
        "ecosystem_compatibility": "Foot-end kits; optional arm / LiDAR / voice expansion kits",
        "safety_fencing": "Remote E-stop; stand-up-after-fall behaviors; optional roll cage",
        "mounting_options": "Swappable point-foot, sole, or wheeled foot-ends",
        "videos": YT_TRON1,
        "information_source_urls": [URL_TRON1, URL_TRON1_SPEC, URL_TRON1_LAUNCH],
        "notes_force": (
            "[AI Research] Specs from /en/products/tron1/spec. URL fixed from homepage "
            "to OEM PDP. Cleared absurd height_mm=100 → 845 mm from OEM dimensions. "
            "payload_kg=10 kept as OEM Load Capacity (not the fabricated default). "
            "speed from wheeled ≤3 m/s (=10.8 km/h). Hero: kept existing verified "
            "CDN wheeled-TRON1 product shot (OEM case/scene assets were people/logos/"
            "foot crops only). Duplicate 4856 rejected."
        ),
        "source_note": f"{URL_TRON1}; {URL_TRON1_SPEC}; {URL_TRON1_LAUNCH}",
    },
    4858: {
        "name": "W1",
        "model_name": "W1",
        "variant_code": "W1",
        "variant_label": "Wheeled Quadruped",
        "url": URL_W1_NEWS,
        "family_key": f"{FAMILY_PREFIX}:w1",
        "family_name": "W1",
        "family_url": URL_W1_NEWS,
        "product_url_scope": "exact_variant",
        "imageless": True,
        "description": (
            "LimX W1 was the company's first wheeled-quadruped robot, combining wheeled "
            "efficiency with legged terrain negotiation for stairs, slopes, and mixed "
            "surfaces. Later demos evolved W1 toward biped behaviors; it is no longer "
            "listed on the current EN product catalog."
        ),
        "purpose": PURPOSE_W1,
        "features": (
            "Wheeled-quadruped morphology with proprietary high-performance actuators. "
            "OEM launch video and news document stair climbing, slope ascent/descent, "
            "curb negotiation, ground-clearance adjustment, one-sided bridge traversal, "
            "and rough grass/gravel mobility. Perception-based motion control with "
            "gaited and wheeled modes. No OEM numeric payload/weight/DoF table remains "
            "on the current public EN site — typed columns left blank."
        ),
        "clear_payload": True,
        "availability_status_key": "discontinued",
        "movement_type_keys": "legged|wheeled",
        "industry_keys": "research",
        "use_keys": "research",
        "category_slugs": "Legged-Robots|Mobile-Robots",
        "sub_category_slug": "service-hospitality",
        "tags": TAGS_W1,
        "manufacturer_country_code": CN,
        "release_year": 2023,
        "programming_interface": "LimX W1 software (legacy support downloads still list W1 packages)",
        "deployment_context": "Historical LimX locomotion R&D platform (not on current catalog)",
        "ecosystem_compatibility": "Legacy LimX W1 firmware/support channel",
        "safety_fencing": "Research platform — site E-stops and supervised operation",
        "mounting_options": "Wheeled-quadruped chassis",
        "videos": YT_W1,
        "information_source_urls": [URL_W1_NEWS, URL_ABOUT],
        "notes_force": IMAGE_TODO_W1
        + (
            "[AI Research] URL fixed from pr.ai forum to OEM news BK000034. Removed "
            "wrong TRON 2 wheeled sibling gallery asset. No citeable typed specs on "
            "current OEM pages — left blank. availability=Discontinued (absent from "
            "current EN product nav)."
        ),
        "source_note": f"{URL_W1_NEWS}; {URL_ABOUT}",
    },
    4854: {
        "name": "CL-1",
        "model_name": "CL-1",
        "variant_code": "CL-1",
        "variant_label": "Humanoid",
        "url": URL_CL1_NEWS,
        "family_key": f"{FAMILY_PREFIX}:cl",
        "family_name": "CL",
        "family_url": URL_CL1_NEWS,
        "product_url_scope": "exact_variant",
        "imageless": True,
        "description": (
            "LimX CL-1 is an early full-size humanoid research platform documented for "
            "stair climbing, continuous running, and heavy-object loading. It appears "
            "on the OEM about timeline and product news but is not sold on the current "
            "EN catalog (superseded by Oli / Luna lines)."
        ),
        "purpose": PURPOSE_CL1,
        "features": (
            "OEM news BK000049: continuous heavy-objects loading demonstration. "
            "About timeline: validated stair climbing, continuous running, and "
            "heavy-load handling; multi-scenario dynamic testing. No public EN PDP "
            "spec table with citeable weight/height/DoF remains — typed columns blank."
        ),
        "clear_payload": True,
        "availability_status_key": "discontinued",
        "movement_type_keys": "legged|bipedal",
        "industry_keys": "research",
        "use_keys": "research|material-handling",
        "category_slugs": "Humanoid|Legged-Robots",
        "sub_category_slug": "service-hospitality",
        "tags": TAGS_HUMANOID,
        "manufacturer_country_code": CN,
        "release_year": 2024,
        "programming_interface": "LimX humanoid control stack (legacy CL-1 demos)",
        "deployment_context": "Historical humanoid R&D demonstrator",
        "ecosystem_compatibility": "LimX research tooling of the CL-1 era",
        "safety_fencing": "Research demonstrator — supervised operation",
        "mounting_options": "Free-standing biped humanoid",
        "videos": YT_CL1,
        "information_source_urls": [URL_CL1_NEWS, URL_ABOUT],
        "notes_force": IMAGE_TODO_CL1
        + (
            "[AI Research] Kept OEM news URL BK000049. No citeable typed specs on "
            "current EN pages. availability=Discontinued (not in current product nav)."
        ),
        "source_note": f"{URL_CL1_NEWS}; {URL_ABOUT}",
    },
    3539: {
        "name": "P1",
        "model_name": "P1",
        "variant_code": "P1",
        "variant_label": "Biped",
        "url": URL_P1_NEWS,
        "family_key": f"{FAMILY_PREFIX}:p1",
        "family_name": "P1",
        "family_url": URL_P1_NEWS,
        "product_url_scope": "exact_variant",
        "imageless": True,
        "description": (
            "LimX P1 is an early biped research robot showcased for outdoor rough-"
            "terrain walking using reinforcement learning (OEM news BK000032; about "
            "timeline notes IROS unveiling). It is not listed on the current EN "
            "product catalog."
        ),
        "purpose": PURPOSE_P1,
        "features": (
            "OEM news: biped P1 conquers wild terrain based on reinforcement learning. "
            "About timeline: unveiled at IROS; outdoor RL locomotion milestone. "
            "No remaining public EN PDP with citeable numeric weight/height/DoF — "
            "typed columns left blank. Cleared fabricated payload_kg=10."
        ),
        "clear_payload": True,
        "availability_status_key": "discontinued",
        "movement_type_keys": "legged|bipedal",
        "industry_keys": "research",
        "use_keys": "research",
        "category_slugs": "Legged-Robots",
        "sub_category_slug": "service-hospitality",
        "tags": TAGS_P1,
        "manufacturer_country_code": CN,
        "release_year": 2023,
        "programming_interface": "Reinforcement-learning locomotion stack (OEM P1 demos)",
        "deployment_context": "Historical outdoor biped R&D platform",
        "ecosystem_compatibility": "LimX early biped research tooling",
        "safety_fencing": "Research demonstrator — supervised outdoor trials",
        "mounting_options": "Free-standing biped",
        "videos": YT_P1,
        "information_source_urls": [URL_P1_NEWS, URL_ABOUT],
        "notes_force": IMAGE_TODO_P1
        + (
            "[AI Research] URL kept as OEM news BK000032. Cleared payload_kg=10 "
            "(uncited). Cleared CDN hero suspected TRON sibling contamination. "
            "availability=Discontinued."
        ),
        "source_note": f"{URL_P1_NEWS}; {URL_ABOUT}",
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix LimX Dynamics company 68")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--copy-media", action="store_true")
    parser.add_argument("--verify-cdn", action="store_true")
    parser.add_argument("--reject-dupes", action="store_true")
    parser.add_argument("--mark-done", action="store_true")
    parser.add_argument("--skip-hero-check", action="store_true")
    parser.add_argument("--drop-flags", action="store_true")
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

    if not args.skip_hero_check:
        print("Verifying OEM hero hashes…")
        seen_hashes: dict[str, str] = {}
        for name, url in IMG.items():
            md5 = verify_hero(name, url)
            if md5 in seen_hashes:
                raise RuntimeError(f"hash collision {name} vs {seen_hashes[md5]}")
            seen_hashes[md5] = name
            print(f"  OK {name} md5={md5}")

    targets = []
    imageless_ids: list[int] = []
    for rid, fix in ROBOT_FIXES.items():
        if args.only and rid not in args.only:
            continue
        robot = all_robots.get(rid)
        if not robot:
            print(f"SKIP {rid}: not pending_review / not found")
            continue
        tags = resolve_tags(catalog, str(fix.get("tags") or ""))
        row = build_row(fix, tags=tags)
        if len(row.get("features") or "") < 40:
            print(f"ERROR {rid}: features too short", file=sys.stderr)
            return 1
        if not row.get("family_key"):
            print(f"ERROR {rid}: missing family_key", file=sys.stderr)
            return 1
        if fix.get("imageless"):
            imageless_ids.append(rid)
        elif not fix.get("keep_existing_image") and not row.get("image"):
            print(f"ERROR {rid}: missing image", file=sys.stderr)
            return 1
        purpose = str(row.get("purpose") or "")
        desc = str(row.get("description") or "")
        if purpose and desc and purpose.strip().rstrip(".") == desc.strip().split(".")[0].strip():
            print(f"ERROR {rid}: purpose duplicates description", file=sys.stderr)
            return 1
        targets.append({"id": rid, "name": row["name"], "row": row, "fix": fix})
        print(
            f"  {rid} {row['name']}: weight={row.get('weight_kg')} "
            f"payload={row.get('payload_kg')} speed={row.get('speed')} "
            f"fam={row.get('family_key')} avail={row.get('availability_status_key')} "
            f"img={'KEEP' if fix.get('keep_existing_image') else ('NONE' if fix.get('imageless') else 'OEM')} "
            f"vids={len(row.get('video_urls') or [])} tags={tags}"
        )

    preview = _RESEARCH_DIR / "staging" / "reports" / "limx-68-fix-preview.json"
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_text(
        json.dumps(
            [
                {
                    "id": t["id"],
                    "name": t["name"],
                    "weight_kg": t["row"].get("weight_kg"),
                    "payload_kg": t["row"].get("payload_kg"),
                    "speed": t["row"].get("speed"),
                    "family_key": t["row"].get("family_key"),
                    "image": (t["row"].get("image") or "")[:120],
                    "imageless": bool(t["fix"].get("imageless")),
                    "keep_existing_image": bool(t["fix"].get("keep_existing_image")),
                    "availability": t["row"].get("availability_status_key"),
                    "url": t["row"].get("url"),
                }
                for t in targets
            ]
            + [{"rejects": REJECTS}, {"imageless": imageless_ids}],
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    if not targets and not (args.reject_dupes and REJECTS):
        print("ERROR: no targets", file=sys.stderr)
        return 1
    if not args.apply:
        print(
            f"Preview: {preview}. Re-run with "
            "--apply --copy-media --verify-cdn --reject-dupes --drop-flags --mark-done"
        )
        return 0

    rejected: list[dict[str, Any]] = []
    if args.reject_dupes:
        for rid, reason in REJECTS.items():
            if args.only and rid not in args.only:
                continue
            msg = reject_robot(client, rid, reason)
            print(f"REJECT {rid}: {msg}")
            rejected.append({"id": rid, "reason": reason, "result": msg})

    tmp = Path(tempfile.mkdtemp(prefix="limx-fix-"))
    totals = {"updated_count": 0, "error_count": 0, "skipped_count": 0, "created_count": 0}
    imported: list[int] = []
    copy_ids: list[int] = []
    for item in targets:
        rid = item["id"]
        row = item["row"]
        fix = item["fix"]
        bulk = staging_dict_to_bulk_import_row(row)
        bulk["id"] = rid
        replace_media = bool(
            fix.get("image") and not fix.get("keep_existing_image") and not fix.get("imageless")
        ) or bool(fix.get("imageless"))
        fpath = tmp / f"{slugify_robot_name(str(item['name']))}-{rid}.json"
        fpath.write_text(json.dumps([row], indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        try:
            result = client.bulk_import_robots(
                [bulk],
                update_existing=True,
                patch_existing=False,
                replace_media=replace_media,
                replace_videos=True,
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
            if replace_media and not fix.get("imageless"):
                copy_ids.append(rid)
            patch_typed(client, rid, fix)
            notes = fix.get("notes_force")
            if notes:
                try:
                    client._patch(f"robots/robots/{rid}/", {"notes": notes})
                except Exception as exc:
                    print(f"  notes fail {rid}: {exc}", file=sys.stderr)
        for k in totals:
            totals[k] += int(result.get(k) or 0)
        print(f"  imported {rid}: {result.get('results')}")

    copy_stats = None
    if args.copy_media and copy_ids:
        ok, fail = trigger_copy_media(copy_ids)
        copy_stats = {"ok": ok, "fail": fail, "ids": copy_ids}
        print(f"copy-media ok={ok} fail={fail}")
        for item in targets:
            if item["id"] in imported:
                patch_typed(client, item["id"], item["fix"])

    cdn_rc = None
    if args.verify_cdn:
        cdn_rc = subprocess.call(
            [
                sys.executable,
                str(_RESEARCH_DIR / "verify_cdn_images.py"),
                "--company-id",
                str(COMPANY_ID),
            ],
            cwd=str(_RESEARCH_DIR),
        )
        print(f"verify_cdn exit={cdn_rc}")

    if args.drop_flags and imported:
        drop_stale_media_flags(client, imported)

    if args.mark_done:
        subprocess.call(
            [
                sys.executable,
                str(_RESEARCH_DIR / "triage_content_queue.py"),
                "--mark-done",
                str(COMPANY_ID),
            ],
            cwd=str(_RESEARCH_DIR),
        )

    report = {
        "company_id": COMPANY_ID,
        "imported": imported,
        "imageless": imageless_ids,
        "rejected": rejected,
        "totals": totals,
        "copy_media": copy_stats,
        "verify_cdn_rc": cdn_rc,
        "preview": str(preview),
        "slug_note": (
            "Company slug remains limx-dynamics-2 (odd duplicate-style slug); "
            "family_key uses limx-dynamics:{series} per stakeholder format."
        ),
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if not totals.get("error_count") else 1


if __name__ == "__main__":
    raise SystemExit(main())
