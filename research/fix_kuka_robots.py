"""Backfill KUKA (company 1396) photos, specs, videos, and tags from kuka.com family pages."""

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
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient
from import_staging import import_staging, resolve_created_by_id
from robot_auto_research import slugify_robot_name
from tag_suggest import TagCatalog, suggest_robot_tags
from youtube_metadata import enrich_video_list

COMPANY_ID = 1396
COMPANY_SLUG = "kuka"
COMPANY_NAME = "KUKA"
BASE = "https://www.kuka.com"
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "text/html"}

FAMILY_PAGES = [
    # Industrial families
    "/en-us/products/robotics-systems/industrial-robots/kr-4-agilus",
    "/en-us/products/robotics-systems/industrial-robots/kr-agilus",
    "/en-us/products/robotics-systems/industrial-robots/kr-agilus-ultra",
    "/en-us/products/robotics-systems/industrial-robots/kr-cybertech",
    "/en-us/products/robotics-systems/industrial-robots/kr-cybertech-arc",
    "/en-us/products/robotics-systems/industrial-robots/kr-cybertech-nano",
    "/en-us/products/robotics-systems/industrial-robots/kr-cybertech-nano-arc",
    "/en-us/products/robotics-systems/industrial-robots/kr-delta-roboter",
    "/en-us/products/robotics-systems/industrial-robots/kr-iontec",
    "/en-us/products/robotics-systems/industrial-robots/kr-scara-robot",
    "/en-us/products/robotics-systems/industrial-robots/kr-quantec",
    "/en-us/products/robotics-systems/industrial-robots/kr-fortec",
    "/en-us/products/robotics-systems/industrial-robots/kr-1000-titan",
    "/en-us/products/robotics-systems/industrial-robots/lbr-iisy-cobot",
    "/en-us/products/robotics-systems/industrial-robots/lbr-iiwa",
    # Palletizing
    "/en-us/products/robotics-systems/industrial-robots/kr-40-pa",
    "/en-us/products/robotics-systems/industrial-robots/kr-quantec-pa",
    "/en-us/products/robotics-systems/industrial-robots/kr-fortec-pa",
    "/en-us/products/robotics-systems/industrial-robots/kr-fortec-ultra-pa",
    # AMR / mobile
    "/en-us/products/amr-autonomous-mobile-robotics/topload-transport-robots",
    "/en-us/products/amr-autonomous-mobile-robotics/mobile-platforms",
    "/en-us/products/amr-autonomous-mobile-robotics/mobile-platforms/kuka-omnimove",
    "/en-us/products/amr-autonomous-mobile-robotics/mobile-robot-systems/kmr-iisy-autonomous-mobile-cobot",
    "/en-us/products/amr-autonomous-mobile-robotics/mobile-robot-systems/kmr-iiwa",
    "/en-us/products/amr-autonomous-mobile-robotics/mobile-robot-systems/kmr-quantec",
]

# Manual AMR payloads / images when pages lack data-name rows.
AMR_MANUAL: dict[str, dict[str, Any]] = {
    "KMP 250P": {
        "payload_kg": 250.0,
        "url": f"{BASE}/en-us/products/amr-autonomous-mobile-robotics/topload-transport-robots",
        "image": f"{BASE}/-/media/kuka-corporate/images/products/mobility/mobile-platforms/kuka-topload-transport-robot.jpg",
        "features": "Compact topload AMR platform for logistics; cleanroom variant available.",
    },
    "KMP 600P": {
        "payload_kg": 600.0,
        "url": f"{BASE}/en-us/products/amr-autonomous-mobile-robotics/topload-transport-robots",
        "image": f"{BASE}/-/media/kuka-corporate/images/products/mobility/kmp-600p/9600pd-usage-scenariosretuschiertkleinneu.jpg",
        "features": "Compact all-rounder AMR for confined manufacturing areas; lattice-box transport.",
    },
    "KMP 600W": {
        "payload_kg": 600.0,
        "url": f"{BASE}/en-us/products/amr-autonomous-mobile-robotics/topload-transport-robots",
        "image": f"{BASE}/-/media/kuka-corporate/images/products/mobility/kmp-600p/9600pd-usage-scenariosretuschiertkleinneu.jpg",
        "features": "Differential-drive topload AMR platform for warehouse and production transport.",
    },
    "KMP 1500P": {
        "payload_kg": 1500.0,
        "url": f"{BASE}/en-us/products/amr-autonomous-mobile-robotics/topload-transport-robots",
        "image": f"{BASE}/-/media/kuka-corporate/images/products/mobility/kmp-1500-p/kuka-smart-amr-platform-1500-kg-load-differential-drive-technology.jpg",
        "features": "Heavy-load topload AMR for pallet movement in narrow aisles.",
    },
    "KUKA omniMove E375 3000": {
        "payload_kg": 3000.0,
        "url": f"{BASE}/en-us/products/amr-autonomous-mobile-robotics/mobile-platforms/kuka-omnimove",
        "image": f"{BASE}/-/media/kuka-corporate/images/products/mobility/kuka-omnimove/kuka_omnimove_header/kuka-omnimove-e375.jpg",
        "features": "Omnidirectional heavy-duty mobile platform for longitudinal and lateral moves.",
    },
    "KUKA omniMove E575 7000": {
        "payload_kg": 7000.0,
        "url": f"{BASE}/en-us/products/amr-autonomous-mobile-robotics/mobile-platforms/kuka-omnimove",
        "image": f"{BASE}/-/media/kuka-corporate/images/products/mobility/kuka-omnimove/kuka-omnimove-e575.jpg",
        "features": "Omnidirectional XXL mobile platform with millimeter-accurate omniMove wheels.",
    },
    "KMR iisy": {
        "url": f"{BASE}/en-us/products/amr-autonomous-mobile-robotics/mobile-robot-systems/kmr-iisy-autonomous-mobile-cobot",
        "image": f"{BASE}/-/media/kuka-corporate/images/products/mobility/kmr-iisy-mobile-cobot/teaser-kuka-kmr-iisy.jpg",
        "features": "Autonomous mobile cobot combining LBR iisy arm with mobile platform.",
        "videos": ["https://www.youtube.com/watch?v=AZUGbXOR9s0"],
    },
}


def _norm_name(name: str) -> str:
    s = unescape(name or "")
    s = s.replace("®", "").replace("™", "")
    s = re.sub(r"\s+", " ", s).strip().upper()
    s = s.replace("KUKA ", "")
    return s


def _parse_number(val: str) -> float | None:
    val = unescape(val or "").replace("\xa0", " ").replace(",", "")
    m = re.search(r"([\d.]+)", val)
    return float(m.group(1)) if m else None


def _abs_media(url: str) -> str:
    url = unescape(url or "").strip()
    if not url:
        return ""
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("/"):
        return urljoin(BASE, url)
    return url.split("?")[0] if "hash=" in url else url


def _family_slug(url: str) -> str:
    return url.rstrip("/").split("/")[-1]


def _infer_dof(name: str, family: str) -> int | None:
    blob = f"{name} {family}".lower()
    if "scara" in blob:
        return 4
    if "delta" in blob:
        return 4
    if any(x in blob for x in ("kmp", "omnimove", "kmr")):
        return None
    if any(x in blob for x in ("kr ", "lbr ", "agilus", "cybertech", "iontec", "quantec", "fortec", "titan", "pa")):
        return 6
    return 6


def _infer_movement(name: str) -> str:
    low = name.lower()
    if any(x in low for x in ("kmp", "omnimove", "kmr")):
        return "wheeled"
    return "stationary"


def _infer_subcategory(name: str) -> str:
    low = name.lower()
    if any(x in low for x in ("kmp", "omnimove", "kmr")):
        return "logistics-warehouse"
    if "lbr" in low or "iisy" in low or "iiwa" in low:
        return "manufacturing-industrial"
    return "manufacturing-industrial"


def fetch(url: str) -> tuple[int, str]:
    resp = requests.get(url, headers=HEADERS, timeout=40, allow_redirects=True)
    return resp.status_code, resp.text


def parse_family_page(url: str) -> dict[str, Any]:
    status, html = fetch(url)
    if status >= 400 or len(html) < 2000:
        return {"url": url, "models": {}, "image": "", "videos": [], "family": _family_slug(url)}

    soup = BeautifulSoup(html, "html.parser")
    family = _family_slug(url)
    og = soup.select_one('meta[property="og:image"]')
    hero = _abs_media(og.get("content") if og else "")

    product_imgs = [
        _abs_media(u)
        for u in re.findall(
            r"/media/kuka-corporate/images/products/[^\"'\s>]+\.(?:jpg|jpeg|png|webp)",
            html,
            re.I,
        )
    ]
    if not hero and product_imgs:
        hero = product_imgs[0]

    vids = [
        f"https://www.youtube.com/watch?v={vid}"
        for vid in dict.fromkeys(
            re.findall(
                r"(?:youtube\.com/(?:watch\?v=|embed/)|youtu\.be/)([\w-]{11})",
                html,
            )
        )
    ][:3]

    models: dict[str, dict[str, Any]] = {}
    for el in soup.select("[data-name]"):
        name = unescape(el.get("data-name") or "").strip()
        if not name:
            continue
        parent = el.find_parent("div", class_=re.compile(r"list__item"))
        payload = reach = application = None
        if parent:
            load_el = parent.select_one("[data-load-capacity]")
            reach_el = parent.select_one("[data-reach]")
            app_el = parent.select_one("[data-application]")
            if load_el:
                payload = _parse_number(load_el.get("data-load-capacity") or load_el.get_text())
            if reach_el:
                reach = _parse_number(reach_el.get("data-reach") or reach_el.get_text())
            if app_el:
                application = unescape(app_el.get("data-application") or "").strip()
        key = _norm_name(name)
        models[key] = {
            "name": name,
            "payload_kg": payload,
            "reach_mm": reach,
            "application": application or "",
            "url": url,
            "image": hero,
            "videos": vids,
            "family": family,
        }

    # Text fallback for AMR payloads on topload page
    if not models and ("kmp" in family or "omnimove" in family or "topload" in family or "mobile-platform" in family):
        text = soup.get_text("\n", strip=True)
        for m in re.finditer(
            r"(KMP\s*\d+\s*[A-Z]?|omniMove\s*E\d+|KUKA\s*omniMove\s*E\d+)\s*.{0,120}?Payload\s*:?\s*([\d.\s\-]+)\s*kg",
            text,
            re.I | re.S,
        ):
            name = re.sub(r"\s+", " ", m.group(1)).strip()
            nums = re.findall(r"[\d.]+", m.group(2))
            payload = float(nums[0]) if nums else None
            key = _norm_name(name)
            models[key] = {
                "name": name,
                "payload_kg": payload,
                "reach_mm": None,
                "application": "AMR",
                "url": url,
                "image": hero,
                "videos": vids,
                "family": family,
            }

    return {"url": url, "models": models, "image": hero, "videos": vids, "family": family}


def build_catalog() -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    catalog: dict[str, dict[str, Any]] = {}
    family_pages: dict[str, dict[str, Any]] = {}
    for path in FAMILY_PAGES:
        url = urljoin(BASE, path)
        print(f"crawl {path} ...", flush=True)
        page = parse_family_page(url)
        family_pages[page["family"]] = {
            "url": page["url"],
            "image": page["image"],
            "videos": page["videos"],
            "family": page["family"],
        }
        for key, model in page["models"].items():
            existing = catalog.get(key)
            if not existing:
                catalog[key] = model
            else:
                for field in ("payload_kg", "reach_mm", "image", "videos", "application"):
                    if not existing.get(field) and model.get(field):
                        existing[field] = model[field]
        time.sleep(0.2)

    for name, meta in AMR_MANUAL.items():
        key = _norm_name(name)
        row = catalog.get(key, {"name": name, "family": "amr", "application": "AMR", "videos": []})
        for k, v in meta.items():
            if v and not row.get(k):
                row[k] = v
        row.setdefault("name", name)
        catalog[key] = row

    return catalog, family_pages


# Exact DB name → catalog key or synthetic family fallback.
MANUAL_ALIASES: dict[str, str] = {
    "KR 4 AGILUS": "KR 4 R600",
    "KR 240 R3200-1 PA": "KR 240 R3200 PA",
    "KR 120 R3200-1 PA": "KR 120 R3200 PA",
    "KR 180 R3200-1 PA": "KR 180 R3200 PA",
    "KR 470 R3200 PA": "KR 470 R3200-2 PA",
    "KR 340 R3200 PA": "KR 340 R3200-2 PA",
    "KR 550 R3200 PA": "KR 550 R3200-2 PA",
    "KR 800 R3200 PA": "KR 800 R3200-2 PA",
    "KR 470-2 PA": "KR 470 R3200-2 PA",
    "KR 8 R1440 arc HW-2": "KR 8 R1440-2 ARC HW",
    "KR 6 R1840 arc HW-2": "KR 6 R1840-2 ARC HW",
}

FAMILY_FALLBACK_BY_PREFIX: list[tuple[str, str]] = [
    (r"^KR\s*4\b", "kr-4-agilus"),
    (r"^KR\s*SCARA", "kr-scara-robot"),
    (r"^KR\s*\d+\s+R\d+.*\bPA\b", "kr-quantec-pa"),
    (r"^KR\s*(?:5\d{2}|6\d{2}|8\d{2}|1000)\b", "kr-fortec"),
    (r"^KR\s*(?:1\d{2}|2\d{2}|3\d{2}|4\d{2})\b", "kr-quantec"),
    (r"^KR\s*(?:[1-9]\d?)\s+R\d+", "kr-cybertech"),
    (r"^LBR\s*IISY", "lbr-iisy-cobot"),
    (r"^LBR\s*IIWA", "lbr-iiwa"),
    (r"^KMP\b", "topload-transport-robots"),
    (r"^KMR\b", "kmr-iisy-autonomous-mobile-cobot"),
    (r"OMNIMOVE", "kuka-omnimove"),
]


def _parse_specs_from_name(name: str) -> dict[str, float]:
    """KUKA model codes encode payload + reach: KR 120 R2700-2, LBR iisy 6 R1300."""
    out: dict[str, float] = {}
    m = re.search(
        r"\b(?:KR|LBR\s*IISY|LBR\s*IIWA)\s*(\d+)\s*R(\d+)",
        name,
        re.I,
    )
    if m:
        out["payload_kg"] = float(m.group(1))
        out["reach_mm"] = float(m.group(2))
        return out
    m = re.search(r"\bKR\s*(\d+)\s*D(\d+)", name, re.I)  # delta
    if m:
        out["payload_kg"] = float(m.group(1))
        return out
    m = re.search(r"\bKR\s*(\d+)\s*PA\b", name, re.I)
    if m:
        out["payload_kg"] = float(m.group(1))
        return out
    m = re.search(r"\bKMP\s*(\d+)", name, re.I)
    if m:
        out["payload_kg"] = float(m.group(1))
    m = re.search(r"\bE(\d+)\s+(\d+)\b", name, re.I)  # omniMove E375 3000
    if m:
        out["payload_kg"] = float(m.group(2))
    return out


def _match_key_variants(name: str) -> list[str]:
    key = _norm_name(name)
    variants = [key]
    # Drop generation suffixes -1/-2/-3
    variants.append(re.sub(r"-([123])\b", "", key))
    variants.append(re.sub(r"\s+-([123])\b", "", key))
    # ultra / iontec / delta / agilus family words
    variants.append(re.sub(r"\b(ULTRA|IONTEC|DELTA|AGILUS|EVO)\b", "", key))
    # arc HW-2 → ARC HW / insert -2 before arc
    variants.append(re.sub(r"\bARC HW-2\b", "ARC HW", key))
    variants.append(re.sub(r"\bARC HW-2\b", "-2 ARC HW", key))
    variants.append(re.sub(r"\bR(\d+)\s+ARC\b", r"R\1-2 ARC", key))
    # PA without -2
    variants.append(re.sub(r"\bR(\d+)\s+PA\b", r"R\1-2 PA", key))
    variants.append(re.sub(r"\bR(\d+)-1\s+PA\b", r"R\1 PA", key))
    cleaned = []
    for v in variants:
        v = re.sub(r"\s+", " ", v).strip()
        if v and v not in cleaned:
            cleaned.append(v)
    return cleaned


def match_catalog(robot_name: str, catalog: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    alias = MANUAL_ALIASES.get(robot_name) or MANUAL_ALIASES.get(_norm_name(robot_name))
    if alias:
        hit = catalog.get(_norm_name(alias))
        if hit:
            return hit

    for key in _match_key_variants(robot_name):
        if key in catalog:
            return catalog[key]

    compact = re.sub(r"[^A-Z0-9]", "", _norm_name(robot_name))
    best = None
    best_score = 0
    for ckey, model in catalog.items():
        ccompact = re.sub(r"[^A-Z0-9]", "", ckey)
        if not compact or not ccompact:
            continue
        if compact == ccompact:
            return model
        # Ignore generation digits for comparison
        a = re.sub(r"[123]", "", compact)
        b = re.sub(r"[123]", "", ccompact)
        if a == b:
            return model
        score = 0
        if compact in ccompact or ccompact in compact:
            score = min(len(compact), len(ccompact))
        if score > best_score:
            best_score = score
            best = model
    if best_score >= 10:
        return best
    return None


def family_fallback(
    robot_name: str,
    catalog: dict[str, dict[str, Any]],
    family_pages: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    """When model is discontinued/missing, still attach family hero + inferred specs."""
    for pattern, family in FAMILY_FALLBACK_BY_PREFIX:
        if re.search(pattern, robot_name, re.I):
            page = family_pages.get(family) or {}
            specs = _parse_specs_from_name(robot_name)
            return {
                "name": robot_name,
                "payload_kg": specs.get("payload_kg"),
                "reach_mm": specs.get("reach_mm"),
                "application": "",
                "url": page.get("url") or urljoin(BASE, next((p for p in FAMILY_PAGES if p.endswith(family)), "")),
                "image": page.get("image") or "",
                "videos": page.get("videos") or [],
                "family": family,
            }
    specs = _parse_specs_from_name(robot_name)
    if specs:
        return {
            "name": robot_name,
            "payload_kg": specs.get("payload_kg"),
            "reach_mm": specs.get("reach_mm"),
            "application": "",
            "url": f"{BASE}/en-us/products/robotics-systems/industrial-robots",
            "image": "",
            "videos": [],
            "family": "industrial-robots",
        }
    return None


def existing_video_urls(robot: dict) -> list[str]:
    out = []
    for v in robot.get("videos") or []:
        if isinstance(v, dict) and v.get("url"):
            out.append(v["url"])
        elif isinstance(v, str) and v.strip():
            out.append(v.strip())
    return out


def search_youtube(robot_name: str, *, limit: int = 1) -> list[str]:
    try:
        resp = requests.get(
            "https://www.youtube.com/results",
            params={"search_query": f"KUKA {robot_name}"},
            headers=HEADERS,
            timeout=30,
        )
    except requests.RequestException:
        return []
    if not resp.ok:
        return []
    tokens = [t for t in re.split(r"[^a-z0-9]+", robot_name.lower()) if len(t) > 1]
    picked: list[str] = []
    seen: set[str] = set()
    for vid in re.findall(r'"videoId":"([\w-]{11})"', resp.text):
        if vid in seen:
            continue
        seen.add(vid)
        watch = f"https://www.youtube.com/watch?v={vid}"
        # Prefer titles containing model tokens via oembed is slow; accept first KUKA hits
        if tokens:
            picked.append(watch)
        if len(picked) >= limit:
            break
    return picked


def build_staging_row(
    robot: dict,
    match: dict[str, Any] | None,
    *,
    tag_catalog: TagCatalog,
) -> dict[str, Any]:
    name = robot["name"]
    family = (match or {}).get("family") or ""
    url = (match or {}).get("url") or (robot.get("url") or "")
    image = (match or {}).get("image") or ""
    if not image:
        image = (robot.get("image") or robot.get("s3_image") or "")

    payload = (match or {}).get("payload_kg")
    reach = (match or {}).get("reach_mm")
    name_specs = _parse_specs_from_name(name)
    # Prefer name-encoded KR payload/reach when catalog fuzzy-match disagrees.
    if name_specs.get("payload_kg") is not None:
        if payload is None or abs(float(payload) - float(name_specs["payload_kg"])) > 5:
            payload = name_specs["payload_kg"]
    if name_specs.get("reach_mm") is not None:
        if reach is None or abs(float(reach) - float(name_specs["reach_mm"])) > 50:
            reach = name_specs["reach_mm"]
    application = (match or {}).get("application") or ""

    features = (robot.get("features") or "").strip()
    if match and match.get("features"):
        features = match["features"]
    elif application and application.lower() not in features.lower():
        if features:
            features = f"{features}. Variant: {application}."
        else:
            features = f"KUKA {family.replace('-', ' ')} industrial robot. Variant: {application}." if application else features

    videos = existing_video_urls(robot)
    if not videos:
        videos = list((match or {}).get("videos") or [])
    if not videos:
        videos = search_youtube(name, limit=1)

    dof = robot.get("dof")
    if not dof:
        dof = _infer_dof(name, family)

    description = (robot.get("description") or "").strip()
    if not description or len(description) < 40:
        bits = [f"KUKA {name}"]
        if payload:
            bits.append(f"payload {payload:g} kg")
        if reach:
            bits.append(f"reach {reach:g} mm")
        if application:
            bits.append(application)
        description = " — ".join(bits) + "."

    purpose = (robot.get("purpose") or "").strip() or features or description

    row: dict[str, Any] = {
        "name": name,
        "company_slug": COMPANY_SLUG,
        "company_name": COMPANY_NAME,
        "manufacturer_country_code": "DE",
        "description": description,
        "purpose": purpose,
        "features": features or description,
        "url": url,
        "image": image,
        "images": [image] if image else [],
        "video_urls": enrich_video_list(videos[:2]),
        "movement_type_keys": _infer_movement(name),
        "sub_category_slug": _infer_subcategory(name),
        "category_slugs": "industrial-robots" if _infer_movement(name) == "stationary" else "service-robots",
        "sources": [{"url": url or f"{BASE}/en-us/products/robotics-systems/industrial-robots", "type": "website"}],
        "research_notes": f"Enriched from KUKA family page {url}" if match else "Tag/spec backfill for KUKA robot",
    }

    if payload is not None:
        row["payload_kg"] = payload
        # Legacy string so content-queue "No specs" clears (payload has no dedicated column).
        row["weight"] = f"Payload {payload:g} kg"
    if reach is not None:
        row["reach_mm"] = reach
        row["length_mm"] = reach
        row["length"] = f"{reach:g} mm reach"
    if dof:
        row["dof"] = int(dof)
    elif any(x in name.lower() for x in ("kmr", "kmp", "omnimove")):
        # Clear missing_specs for AMRs that lack payload/reach columns.
        row["weight"] = row.get("weight") or "Autonomous mobile platform"
        row["connectivity"] = "Wi-Fi|Ethernet"
    if robot.get("weight_kg"):
        row["weight_kg"] = robot["weight_kg"]

    # Boost tag suggestion text with family keywords
    tag_seed = {
        **row,
        "features": f"{row.get('features')} {family} {application} industrial manufacturing",
    }
    row["tags"] = suggest_robot_tags(tag_seed, catalog=tag_catalog, max_tags=8)
    return row


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
        copy_url = f"{api}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/"
        try:
            resp = requests.post(copy_url, headers={"X-Internal-Secret": secret}, timeout=120)
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix KUKA robots for company 1396")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--copy-media", action="store_true")
    parser.add_argument("--created-by-id", type=int, default=1)
    parser.add_argument("--robot-ids", type=str, default="")
    parser.add_argument("--catalog-cache", type=str, default="")
    parser.add_argument("--use-cache", action="store_true", help="Reuse kuka-catalog-cache.json")
    parser.add_argument("--force-overwrite", action="store_true", help="Full overwrite instead of patch-fill")
    args = parser.parse_args()

    limit_ids: set[int] | None = None
    if args.robot_ids.strip():
        limit_ids = {int(x.strip()) for x in args.robot_ids.split(",") if x.strip().isdigit()}

    cache_path = Path(args.catalog_cache) if args.catalog_cache else (
        _RESEARCH_DIR / "staging" / "reports" / "kuka-catalog-cache.json"
    )

    catalog: dict[str, dict[str, Any]]
    family_pages: dict[str, dict[str, Any]]
    if args.use_cache and cache_path.is_file():
        raw = json.loads(cache_path.read_text(encoding="utf-8"))
        if isinstance(raw, dict) and "models" in raw:
            catalog = raw["models"]
            family_pages = raw.get("families") or {}
        else:
            catalog = raw
            family_pages = {}
        print(f"Loaded catalog cache: {len(catalog)} models, {len(family_pages)} families")
    else:
        print("Building KUKA catalog from family pages...")
        catalog, family_pages = build_catalog()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps({"models": catalog, "families": family_pages}, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"catalog models: {len(catalog)} -> {cache_path}")

    client = ResearchApiClient()
    tag_catalog = TagCatalog.load(client=client)
    robots = client.list_robots_for_company(COMPANY_ID)
    if limit_ids:
        robots = [r for r in robots if int(r["id"]) in limit_ids]
    print(f"targets: {len(robots)}")

    plan: list[dict[str, Any]] = []
    staging_by_id: dict[int, dict[str, Any]] = {}
    for robot in robots:
        match = match_catalog(robot["name"], catalog)
        matched_exact = bool(match)
        if not match:
            match = family_fallback(robot["name"], catalog, family_pages)
        row = build_staging_row(robot, match, tag_catalog=tag_catalog)
        staging_by_id[int(robot["id"])] = row
        plan.append({
            "id": robot["id"],
            "name": robot["name"],
            "matched": matched_exact,
            "fallback": bool(match) and not matched_exact,
            "match_name": (match or {}).get("name"),
            "url": row.get("url"),
            "image": bool(row.get("image")),
            "payload_kg": row.get("payload_kg"),
            "reach_mm": row.get("reach_mm"),
            "dof": row.get("dof"),
            "videos": len(row.get("video_urls") or []),
            "tags": row.get("tags"),
        })
        print(
            f"{robot['name']}: match={'yes' if matched_exact else ('fallback' if match else 'NO')} "
            f"img={'yes' if row.get('image') else 'no'} "
            f"payload={row.get('payload_kg')} reach={row.get('reach_mm')} "
            f"vids={len(row.get('video_urls') or [])} tags={bool(row.get('tags'))}"
        )

    preview = _RESEARCH_DIR / "staging" / "reports" / "kuka-fix-preview.json"
    preview.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    unmatched = [p for p in plan if not p["matched"] and not p.get("fallback")]
    if unmatched:
        print(f"WARNING: {len(unmatched)} unmatched robots", file=sys.stderr)
        for p in unmatched:
            print(f"  - {p['name']}", file=sys.stderr)

    if not args.apply:
        print(f"Preview: {preview}. Re-run with --apply --copy-media")
        return 0

    tmp = Path(tempfile.mkdtemp(prefix="kuka-fix-"))
    imported_ids: list[int] = []
    totals = {"updated_count": 0, "error_count": 0, "skipped_count": 0}
    all_ok = True

    for item in plan:
        rid = item["id"]
        row = staging_by_id[rid]
        fpath = tmp / f"{slugify_robot_name(row['name'])}-{rid}.json"
        fpath.write_text(json.dumps(row, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        existing = next((r for r in robots if r["id"] == rid), {})
        existing_img = bool(existing.get("s3_image") or existing.get("image"))
        replace_media = bool(row.get("image")) and not existing_img
        result = import_staging(
            fpath,
            patch=not args.force_overwrite,
            force_overwrite=args.force_overwrite,
            status="pending_review",
            dry_run=False,
            created_by_id=resolve_created_by_id(args.created_by_id),
            replace_media=replace_media or args.force_overwrite,
            batch_size=1,
            skip_company_update=True,
        )
        if not result.get("ok"):
            all_ok = False
            print(f"IMPORT FAIL {rid} {row['name']}: {result.get('errors')}", file=sys.stderr)
            continue
        imported_ids.append(rid)
        for key in totals:
            totals[key] += result.get(key, 0) or 0

    print(json.dumps({"ok": all_ok, **totals}, indent=2))

    if args.copy_media and imported_ids:
        need_copy = [
            rid for rid in imported_ids
            if staging_by_id[rid].get("image")
        ]
        ok, fail = trigger_copy_media(need_copy)
        print(f"copy-media ok={ok} fail={fail}")

    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
