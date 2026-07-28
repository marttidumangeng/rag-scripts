"""Backfill Epson Robots (company 1445) pending_review records.

Resolves official epson.com PDPs (Serper), scrapes product heroes from
mediaserver.goepson.com adaptivemedia (reject shared ImConvServlet placeholder),
and fills features/tags/videos/specs from PDP + 2023 Epson robot catalog facts.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
from html import unescape
from pathlib import Path
from typing import Any

import requests

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient
from import_staging import import_staging, resolve_created_by_id
from robot_auto_research import slugify_robot_name
from youtube_metadata import enrich_video_list

COMPANY_ID = 1445
COMPANY_SLUG = "epson-robots"
COMPANY_NAME = "Epson Robots"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}
SHARED_OG_TOKEN = "5cab161d26aaacc0c4aa817a842cd31bb583070d"

# Exact TagCatalog names (pipe-separated).
SCARA_TAGS = (
    "scara|Industrial|Manufacturing|Assembly|Pick-and-Place|"
    "Factory Automation|Industrial Arm|4-axis"
)
AXIS6_TAGS = (
    "6-Axis|Industrial|Manufacturing|Assembly|Factory Automation|"
    "Industrial Arm|Industrial Robot"
)

# Exact DB robot name -> official PDP (unique product hero verified).
ROBOT_URLS: dict[str, str] = {
    "Epson LS20-B SCARA Robot - 800mm": (
        "https://epson.com/For-Work/Robots/SCARA/Epson-LS20-B-SCARA-Robot---800mm/p/RLS20B804ST9B3"
    ),
    "C12XL 6-Axis Robot": (
        "https://epson.com/For-Work/Robots/6-Axis/C12XL-6-Axis-Robot/p/RC12XL-A1401ST73SS"
    ),
    "Epson C12XL 6-Axis Robot": (
        "https://epson.com/For-Work/Robots/6-Axis/C12XL-6-Axis-Robot/p/RC12XL-A1401ST73SS"
    ),
    "Flexion N6 Compact 6-Axis Robots - 850mm": (
        "https://epson.com/For-Work/Robots/6-Axis/Flexion-N6-Compact-6-Axis-Robots---850mm/p/RN6-A85SR73SS"
    ),
    "Epson LS3-B SCARA Robot": (
        "https://epson.com/For-Work/Robots/SCARA/Epson-LS3-B-SCARA-Robot---400mm/p/RLS3B401ST9B3"
    ),
    "Epson LS6-B SCARA Robot": (
        "https://epson.com/For-Work/Robots/SCARA/Epson-LS6-B-SCARA-Robot---600mm/p/RLS6B602ST9B5"
    ),
    "Epson LS10-B SCARA Robot": (
        "https://epson.com/For-Work/Robots/SCARA/Epson-LS10-B-SCARA-Robot---800mm/p/RLS10B802ST9B3"
    ),
    "Epson LS20-B SCARA Robot": (
        "https://epson.com/For-Work/Robots/SCARA/Epson-LS20-B-SCARA-Robot---1000mm/p/RLS20BA04ST9B3"
    ),
    "Epson RS3 SCARA Robot": (
        "https://epson.com/For-Work/Robots/SCARA/Epson-RS3-SCARA-Robots---350mm/p/RRS-351SSR13"
    ),
    "Epson RS4 SCARA Robot": (
        "https://epson.com/For-Work/Robots/SCARA/Epson-RS4-SCARA-Robots---550mm/p/RRS-551SSR13"
    ),
    "Epson GX4 SCARA Robot": (
        "https://epson.com/For-Work/Robots/SCARA/GX4-SCARA-Robot---300mm/p/RGX4-A301SSTSD"
    ),
    "Epson GX8 SCARA Robot": (
        "https://epson.com/For-Work/Robots/SCARA/Epson-GX8-SCARA-Robot---650mm/p/RGX8-A652SSTD"
    ),
    "Epson G1 Mini SCARA Robot": (
        "https://epson.com/For-Work/Robots/SCARA/Epson-G1-Mini-SCARA-Robots---175mm/p/RG1-171ST13"
    ),
    "Epson G3 SCARA Robot": (
        "https://epson.com/For-Work/Robots/SCARA/Epson-G3-SCARA-Robots---350mm/p/RG3-351SST13"
    ),
    "Epson G6 SCARA Robot": (
        "https://epson.com/For-Work/Robots/SCARA/Epson-G6-SCARA-Robots---650mm/p/RG6-653ST13"
    ),
    "Epson G10 SCARA Robot": (
        "https://epson.com/For-Work/Robots/SCARA/Epson-G10-SCARA-Robots---650mm/p/RG10-651ST13"
    ),
    "Epson G20 SCARA Robot": (
        "https://epson.com/For-Work/Robots/SCARA/Epson-G20-SCARA-Robots---1000mm/p/RG20-A01ST13"
    ),
    "Epson T3-B SCARA Robot": (
        "https://epson.com/For-Work/Robots/SCARA/Epson-T3-B-All-in-One-SCARA-Robot/p/RT3B-401SS"
    ),
    "Epson T6-B SCARA Robot": (
        "https://epson.com/For-Work/Robots/SCARA/T6-B-All-in-One-SCARA-Robot/p/RT6B-602SS"
    ),
    "Epson VT6L All-in-One 6-Axis Robot": (
        "https://epson.com/For-Work/Robots/6-Axis/Epson-VT6L-All-in-One-6-Axis-Robot/p/RVT6L-A901SS"
    ),
    "Epson N2 6-Axis Robot": (
        "https://epson.com/For-Work/Robots/6-Axis/Epson-Flexion-N2-Compact-6-Axis-Robots/p/RN2-A45SS73SS"
    ),
    "Epson N6 6-Axis Robot": (
        "https://epson.com/For-Work/Robots/6-Axis/Flexion-N6-Compact-6-Axis-Robots---1000mm/p/RN6-A10SS73SS"
    ),
    "Epson C4 6-Axis Robot": (
        "https://epson.com/For-Work/Robots/6-Axis/Epson-C4-Compact-6-Axis-Robots/p/RC4-A601ST75"
    ),
    "Epson C8 6-Axis Robot": (
        "https://epson.com/For-Work/Robots/6-Axis/Epson-C8-Compact-6-Axis-Robots/p/RC8-A701ST75SS"
    ),
    # No distinct live C12 PDP — C-series top model is C12XL; map with note.
    "Epson C12 6-Axis Robot": (
        "https://epson.com/For-Work/Robots/6-Axis/C12XL-6-Axis-Robot/p/RC12XL-A1401ST73SS"
    ),
}

# Catalog-backed facts (Epson Robot Spec Catalog 2023 / PDP core specs).
ROBOT_FACTS: dict[str, dict[str, Any]] = {
    "Epson LS3-B SCARA Robot": {
        "payload_kg": 3.0,
        "reach_mm": 400,
        "weight_kg": 14.0,
        "dof": 4,
        "cycle_s": 0.42,
        "kind": "scara",
        "blurb": (
            "LS-B value SCARA for high-precision small-parts assembly with Residual Vibration "
            "Technology and Epson RC+ software; ISO 4 Clean option; RC90-B controller."
        ),
    },
    "Epson LS6-B SCARA Robot": {
        "payload_kg": 6.0,
        "reach_mm": 600,
        "weight_kg": 17.0,
        "dof": 4,
        "cycle_s": 0.40,
        "kind": "scara",
        "blurb": (
            "Compact LS-B SCARA with up to 6 kg payload and ~600 mm reach class; fast cycle times "
            "and ISO 4 Clean option for budget-conscious factory cells."
        ),
    },
    "Epson LS10-B SCARA Robot": {
        "payload_kg": 10.0,
        "reach_mm": 800,
        "dof": 4,
        "cycle_s": 0.44,
        "kind": "scara",
        "blurb": (
            "LS-B SCARA with powerful arm design, up to 10 kg payload and reaches through 800 mm; "
            "multi-tool capable; RC90-B controller; ISO 4 Clean option."
        ),
    },
    "Epson LS20-B SCARA Robot": {
        "payload_kg": 20.0,
        "reach_mm": 1000,
        "weight_kg": 51.0,
        "dof": 4,
        "cycle_s": 0.43,
        "kind": "scara",
        "blurb": (
            "Heavy-payload LS-B SCARA for high-inertia applications; reaches 800/1000 mm; max payload "
            "20 kg; Residual Vibration Technology; ISO 4 Clean option."
        ),
    },
    "Epson LS20-B SCARA Robot - 800mm": {
        "payload_kg": 20.0,
        "reach_mm": 800,
        "weight_kg": 48.0,
        "dof": 4,
        "cycle_s": 0.39,
        "kind": "scara",
        "blurb": (
            "LS20-B 800 mm reach SKU for heavy payloads up to 20 kg; tabletop mount; RC90-B; "
            "Residual Vibration Technology and Epson RC+ development software."
        ),
    },
    "Epson RS3 SCARA Robot": {
        "payload_kg": 3.0,
        "reach_mm": 350,
        "dof": 4,
        "kind": "scara",
        "blurb": (
            "RS-Series zero-footprint ceiling-mount SCARA that can work beneath its own arm; "
            "maximizes workspace for compact cells."
        ),
    },
    "Epson RS4 SCARA Robot": {
        "payload_kg": 4.0,
        "reach_mm": 550,
        "dof": 4,
        "kind": "scara",
        "blurb": (
            "RS-Series zero-footprint SCARA with longer reach; ceiling mount uses the full cylinder "
            "under the arm for flexible layouts."
        ),
    },
    "Epson GX4 SCARA Robot": {
        "payload_kg": 4.0,
        "reach_mm": 300,
        "dof": 4,
        "kind": "scara",
        "blurb": (
            "GX-Series high-power-density SCARA with GYROPLUS vibration reduction; compact footprint "
            "for fast precision assembly and handling."
        ),
    },
    "Epson GX8 SCARA Robot": {
        "payload_kg": 8.0,
        "reach_mm": 650,
        "dof": 4,
        "cycle_s": 0.33,
        "kind": "scara",
        "blurb": (
            "GX8 high-power-density SCARA; up to 8 kg payload and 450–650 mm reach options; "
            "GYROPLUS technology; battery-less encoders; Cleanroom/ESD/washdown configurations."
        ),
    },
    "Epson G1 Mini SCARA Robot": {
        "payload_kg": 1.0,
        "reach_mm": 175,
        "dof": 4,
        "kind": "scara",
        "blurb": (
            "G-Series mini SCARA for micro-assembly and tight footprints; short reach class around 175 mm."
        ),
    },
    "Epson G3 SCARA Robot": {
        "payload_kg": 3.0,
        "reach_mm": 350,
        "dof": 4,
        "kind": "scara",
        "blurb": "G-Series SCARA for precision assembly and pick-and-place in mid-small work envelopes.",
    },
    "Epson G6 SCARA Robot": {
        "payload_kg": 6.0,
        "reach_mm": 650,
        "dof": 4,
        "kind": "scara",
        "blurb": "G-Series SCARA balancing payload and reach for general factory automation cells.",
    },
    "Epson G10 SCARA Robot": {
        "payload_kg": 10.0,
        "reach_mm": 650,
        "dof": 4,
        "kind": "scara",
        "blurb": "G-Series higher-payload SCARA for assembly and material handling.",
    },
    "Epson G20 SCARA Robot": {
        "payload_kg": 20.0,
        "reach_mm": 1000,
        "dof": 4,
        "kind": "scara",
        "blurb": "G-Series long-reach heavy-payload SCARA for larger work envelopes.",
    },
    "Epson T3-B SCARA Robot": {
        "payload_kg": 3.0,
        "reach_mm": 400,
        "dof": 4,
        "kind": "scara",
        "blurb": (
            "T-Series all-in-one SCARA with built-in controller — simple slide alternative for "
            "easy setup and compact cells."
        ),
    },
    "Epson T6-B SCARA Robot": {
        "payload_kg": 6.0,
        "reach_mm": 600,
        "dof": 4,
        "kind": "scara",
        "blurb": (
            "T6-B all-in-one SCARA with integrated controller; compact design aimed at replacing "
            "complex linear-slide systems."
        ),
    },
    "Epson VT6L All-in-One 6-Axis Robot": {
        "payload_kg": 6.0,
        "reach_mm": 900,
        "dof": 6,
        "kind": "6axis",
        "blurb": (
            "VT-Series all-in-one 6-axis with built-in controller; ~900 mm reach and up to 6 kg payload "
            "for machine load/unload, packaging, and simple assembly."
        ),
    },
    "Epson N2 6-Axis Robot": {
        "payload_kg": 2.5,
        "reach_mm": 450,
        "dof": 6,
        "kind": "6axis",
        "blurb": (
            "Flexion N2 compact 6-axis with Epson folding-arm design for confined workspaces; "
            "payloads up to ~2.5 kg and ~450 mm reach class."
        ),
    },
    "Epson N6 6-Axis Robot": {
        "payload_kg": 6.0,
        "reach_mm": 1000,
        "dof": 6,
        "kind": "6axis",
        "blurb": (
            "Flexion N6 folding-arm 6-axis for load/unload and assembly; longer reach options "
            "(850/1000 mm) and payloads up to 6 kg."
        ),
    },
    "Flexion N6 Compact 6-Axis Robots - 850mm": {
        "payload_kg": 6.0,
        "reach_mm": 850,
        "dof": 6,
        "kind": "6axis",
        "blurb": (
            "Flexion N6 850 mm reach SKU — folding-arm compact 6-axis for space-constrained cells "
            "with Epson RC+ software."
        ),
    },
    "Epson C4 6-Axis Robot": {
        "payload_kg": 4.0,
        "reach_mm": 600,
        "dof": 6,
        "kind": "6axis",
        "blurb": "C-Series compact 6-axis for precision assembly and handling in mid-size envelopes.",
    },
    "Epson C8 6-Axis Robot": {
        "payload_kg": 8.0,
        "reach_mm": 900,
        "dof": 6,
        "kind": "6axis",
        "blurb": "C-Series compact 6-axis with higher payload for machine tending and assembly.",
    },
    "Epson C12 6-Axis Robot": {
        "payload_kg": 12.0,
        "reach_mm": 1400,
        "dof": 6,
        "kind": "6axis",
        "blurb": (
            "C-Series 12 kg-class 6-axis; live US catalog lists C12XL as the current long-reach "
            "C12 family product page used for media/specs."
        ),
    },
    "C12XL 6-Axis Robot": {
        "payload_kg": 12.0,
        "reach_mm": 1400,
        "dof": 6,
        "kind": "6axis",
        "blurb": (
            "C12XL long-reach compact 6-axis; up to 12 kg payload and ~1400 mm reach for machine "
            "tending and material handling."
        ),
    },
    "Epson C12XL 6-Axis Robot": {
        "payload_kg": 12.0,
        "reach_mm": 1400,
        "dof": 6,
        "kind": "6axis",
        "blurb": (
            "C12XL long-reach compact 6-axis; up to 12 kg payload and ~1400 mm reach for machine "
            "tending and material handling."
        ),
    },
}

_YT_CACHE: dict[str, list[str]] = {}


def verify_image(url: str) -> bool:
    if not url or SHARED_OG_TOKEN in url:
        return False
    try:
        resp = requests.head(url, headers=HEADERS, timeout=20, allow_redirects=True)
        if resp.status_code == 405 or "image" not in (resp.headers.get("content-type") or "").lower():
            resp = requests.get(url, headers=HEADERS, timeout=30, stream=True)
            resp.close()
        if resp.status_code != 200:
            return False
        ctype = (resp.headers.get("content-type") or "").lower()
        return "image" in ctype or "adaptivemedia" in url
    except requests.RequestException:
        return False


def scrape_pdp(url: str) -> dict[str, Any]:
    resp = requests.get(url, headers=HEADERS, timeout=45, allow_redirects=True)
    html = resp.text
    og_m = re.search(r'property=["\']og:image["\']\s+content=["\']([^"\']+)["\']', html, re.I)
    og = unescape(og_m.group(1)) if og_m else ""
    desc_m = re.search(
        r'property=["\']og:description["\']\s+content=["\']([^"\']+)["\']', html, re.I
    )
    og_desc = unescape(desc_m.group(1)) if desc_m else ""
    adapt = re.findall(
        r"https://mediaserver\.goepson\.com/adaptivemedia/rendition\?id=[a-f0-9]+[^\"'\s]*",
        html,
        re.I,
    )
    adapt = [unescape(u) for u in dict.fromkeys(adapt)]
    bullets = re.findall(r"<li[^>]*>\s*(.*?)\s*</li>", html, re.I | re.S)
    clean_bullets = []
    for b in bullets:
        text = re.sub(r"<[^>]+>", " ", b)
        text = re.sub(r"\s+", " ", unescape(text)).strip()
        if 40 <= len(text) <= 220 and not text.lower().startswith("http"):
            clean_bullets.append(text)
    clean_bullets = list(dict.fromkeys(clean_bullets))[:8]
    h1_m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.I | re.S)
    h1 = re.sub(r"<[^>]+>", "", h1_m.group(1)).strip() if h1_m else ""
    hero = ""
    for cand in adapt:
        if verify_image(cand):
            hero = cand
            break
    if not hero and og and SHARED_OG_TOKEN not in og and verify_image(og):
        hero = og
    return {
        "status": resp.status_code,
        "final_url": resp.url,
        "h1": h1,
        "og_description": og_desc,
        "hero": hero,
        "images": [u for u in adapt if verify_image(u)][:4],
        "bullets": clean_bullets,
    }


def youtube_search_ids(query: str, limit: int = 3) -> list[str]:
    try:
        resp = requests.get(
            "https://www.youtube.com/results",
            params={"search_query": query},
            headers=HEADERS,
            timeout=30,
        )
    except requests.RequestException:
        return []
    ids = re.findall(r'"videoId":"([a-zA-Z0-9_-]{11})"', resp.text)
    out: list[str] = []
    for vid in ids:
        if vid not in out:
            out.append(vid)
        if len(out) >= limit:
            break
    return [f"https://www.youtube.com/watch?v={v}" for v in out]


def build_features(name: str, facts: dict[str, Any], pdp: dict[str, Any]) -> str:
    parts: list[str] = []
    if facts.get("blurb"):
        parts.append(str(facts["blurb"]))
    bits = []
    if facts.get("payload_kg") is not None:
        bits.append(f"Max payload ~{facts['payload_kg']} kg")
    if facts.get("reach_mm") is not None:
        bits.append(f"reach class ~{facts['reach_mm']} mm")
    if facts.get("cycle_s") is not None:
        bits.append(f"catalog cycle time ~{facts['cycle_s']} s")
    if facts.get("dof") is not None:
        bits.append(f"{facts['dof']}-axis / DOF class")
    if bits:
        parts.append("Cited specs: " + "; ".join(bits) + ".")
    for b in pdp.get("bullets") or []:
        low = b.lower()
        if any(k in low for k in ("payload", "reach", "cycle", "rc+", "gyroplus", "residual", "clean")):
            parts.append(b)
        elif len(parts) < 5:
            parts.append(b)
        if len(parts) >= 7:
            break
    if pdp.get("og_description") and len(parts) < 4:
        parts.append(pdp["og_description"])
    text = " ".join(parts)
    return text[:1800]


def trigger_copy_media(robot_ids: list[int]) -> tuple[int, int]:
    secret = os.environ.get("INTERNAL_API_SECRET", "").strip()
    env_file = _RESEARCH_DIR.parents[1] / "robotaigeek-server" / ".env"
    if not secret and env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                secret = line.split("=", 1)[1].strip()
    api = os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/").replace("/api/v1", "")
    if not secret or not api:
        return 0, len(robot_ids)
    ok = fail = 0
    for rid in robot_ids:
        url = f"{api}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/"
        try:
            resp = requests.post(url, headers={"X-Internal-Secret": secret}, timeout=120)
            if resp.ok:
                ok += 1
            else:
                fail += 1
                print(f"copy-media fail {rid}: HTTP {resp.status_code}")
        except requests.RequestException as exc:
            fail += 1
            print(f"copy-media fail {rid}: {exc}")
        time.sleep(0.1)
    return ok, fail


def build_row(robot: dict[str, Any], url: str, facts: dict[str, Any], pdp: dict[str, Any]) -> dict[str, Any]:
    name = robot["name"]
    kind = facts.get("kind") or ("scara" if "scara" in name.lower() else "6axis")
    images = list(pdp.get("images") or [])
    hero = pdp.get("hero") or ""
    if hero and hero not in images:
        images = [hero, *images]
    features = build_features(name, facts, pdp)
    description = (
        pdp.get("og_description")
        or facts.get("blurb")
        or f"{name} industrial robot from Epson Robots."
    )
    # Cache YouTube HTML search by series to avoid 25× slow page fetches.
    series_key = kind
    if "LS" in name.upper():
        series_key = "ls"
    elif "GX" in name.upper():
        series_key = "gx"
    elif re.search(r"\bG\d", name, re.I):
        series_key = "g"
    elif "RS" in name.upper():
        series_key = "rs"
    elif re.search(r"\bT\d", name, re.I):
        series_key = "t"
    elif "VT" in name.upper():
        series_key = "vt"
    elif re.search(r"\bN\d", name, re.I) or "Flexion" in name:
        series_key = "n"
    elif re.search(r"\bC\d", name, re.I):
        series_key = "c"
    if series_key not in _YT_CACHE:
        token = re.sub(r"[^A-Za-z0-9]+", " ", name)
        vids = youtube_search_ids(f"Epson {token} robot", limit=3)
        if not vids:
            vids = youtube_search_ids(
                f"Epson {'SCARA' if kind == 'scara' else '6-Axis'} robot",
                limit=2,
            )
        _YT_CACHE[series_key] = enrich_video_list(vids)
    videos = list(_YT_CACHE[series_key])
    tags = SCARA_TAGS if kind == "scara" else AXIS6_TAGS
    row: dict[str, Any] = {
        "name": name,
        "company_slug": COMPANY_SLUG,
        "company_name": COMPANY_NAME,
        "manufacturer_country_code": "JP",
        "description": description[:1200],
        "purpose": description[:1200],
        "features": features,
        "url": url,
        "image": hero,
        "images": images[:4],
        "video_urls": videos,
        "movement_type_keys": "stationary",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "manufacturing-industrial",
        "tags": tags,
        "dof": facts.get("dof"),
        "sources": [{"url": url, "type": "website", "title": name}],
        "research_notes": (
            f"Epson content-queue backfill from {url}. "
            "Specs from Epson US PDP / Robot Spec Catalog 2023. "
            + (
                "Note: C12 mapped to live C12XL PDP (no distinct C12 SKU page)."
                if name == "Epson C12 6-Axis Robot"
                else ""
            )
        ),
    }
    if facts.get("payload_kg") is not None:
        row["payload_kg"] = facts["payload_kg"]
    if facts.get("weight_kg") is not None:
        row["weight_kg"] = facts["weight_kg"]
        row["weight"] = f"{facts['weight_kg']} kg"
    if facts.get("reach_mm") is not None:
        row["notes"] = f"Reach class ~{facts['reach_mm']} mm (catalog/PDP)."
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix Epson Robots company 1445")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--copy-media", action="store_true")
    parser.add_argument("--created-by-id", type=int, default=1)
    parser.add_argument("--only", nargs="*", help="Optional robot name substrings")
    args = parser.parse_args()

    client = ResearchApiClient()
    robots = [
        r for r in client.list_robots_for_company(COMPANY_ID)
        if (r.get("status") or "") == "pending_review"
    ]
    if args.only:
        robots = [r for r in robots if any(s.lower() in r["name"].lower() for s in args.only)]

    plan = []
    staging: dict[int, dict] = {}
    for robot in robots:
        name = robot["name"]
        url = ROBOT_URLS.get(name)
        facts = ROBOT_FACTS.get(name)
        if not url or not facts:
            print(f"SKIP {robot['id']} {name}: missing url/facts map")
            continue
        print(f"scrape {name} …")
        pdp = scrape_pdp(url)
        row = build_row(robot, url, facts, pdp)
        staging[int(robot["id"])] = row
        item = {
            "id": robot["id"],
            "name": name,
            "url": row["url"],
            "image": bool(row.get("image")),
            "image_url": row.get("image"),
            "features_len": len(row.get("features") or ""),
            "videos": len(row.get("video_urls") or []),
            "tags": row.get("tags"),
            "pdp_status": pdp.get("status"),
            "h1": pdp.get("h1"),
        }
        plan.append(item)
        print(
            f"  img={'yes' if item['image'] else 'no'} feat={item['features_len']} "
            f"vids={item['videos']} h1={item['h1']!r}"
        )

    preview = _RESEARCH_DIR / "staging" / "reports" / "epson-fix-preview.json"
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if not plan:
        print("ERROR: nothing to import", file=sys.stderr)
        return 1
    bad = [p for p in plan if not p["image"] or p["features_len"] < 40 or not p["videos"] or not p["tags"]]
    if bad:
        print(f"ERROR: incomplete enrichment for {len(bad)} robots:", file=sys.stderr)
        for p in bad:
            print(f"  {p['name']}: img={p['image']} feat={p['features_len']} vids={p['videos']}", file=sys.stderr)
        return 1
    if not args.apply:
        print(f"Preview: {preview}. Re-run with --apply --copy-media")
        return 0

    tmp = Path(tempfile.mkdtemp(prefix="epson-fix-"))
    imported: list[int] = []
    totals = {"updated_count": 0, "error_count": 0, "skipped_count": 0}
    all_ok = True
    for item in plan:
        rid = item["id"]
        row = staging[rid]
        fpath = tmp / f"{slugify_robot_name(row['name'])}-{rid}.json"
        fpath.write_text(json.dumps(row, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        result = import_staging(
            fpath,
            patch=False,
            force_overwrite=True,
            status="pending_review",
            dry_run=False,
            created_by_id=resolve_created_by_id(args.created_by_id),
            replace_media=True,
            batch_size=1,
            skip_company_update=True,
        )
        if not result.get("ok"):
            all_ok = False
            print(f"IMPORT FAIL {rid}: {result.get('errors')}", file=sys.stderr)
            continue
        imported.append(rid)
        for k in totals:
            totals[k] += result.get(k, 0) or 0
        print(f"imported {rid} {row['name']}")

    print(json.dumps({"ok": all_ok, **totals, "imported": imported}, indent=2))
    if args.copy_media and imported:
        ok, fail = trigger_copy_media(imported)
        print(f"copy-media ok={ok} fail={fail}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
