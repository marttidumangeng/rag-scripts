"""Backfill Noblelift (company 1028) pending_review robots via noblelift.com ASPX PDPs.

Many CRM itemids are wrong (shifted bulk import). Prefer name-matched URLs from
list-page crawl (`staging/reports/noblelift-url-map.json`) plus curated overrides.
Heroes come from `figure.Ispic` background-image (not footer flag uploadfiles).
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import tempfile
import time
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urljoin, urlparse

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

COMPANY_ID = 1028
COMPANY_SLUG = "noblefit-intelligent-equipment-co-ltd"  # CRM slug typo — keep as stored
COMPANY_NAME = "Noblelift Intelligent Equipment Co., Ltd."
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

TAGS_AGV = (
    "AMR|AGV|Warehouse Automation|Logistics|Pallet Handling|Forklift|"
    "Autonomous Mobile Robot|Intralogistics|Industrial"
)
TAGS_FORK = (
    "Forklift|Warehouse Automation|Logistics|Pallet Handling|Industrial|"
    "Intralogistics|Material Handling"
)
TAGS_STACKER = (
    "Warehouse Automation|Logistics|Pallet Handling|Industrial|"
    "Intralogistics|Material Handling|Forklift"
)
TAGS_PALLET = (
    "Warehouse Automation|Logistics|Pallet Handling|Industrial|"
    "Intralogistics|Material Handling"
)
TAGS_REACH = (
    "Forklift|Warehouse Automation|Logistics|Industrial|Intralogistics|"
    "Material Handling|Pallet Handling"
)
TAGS_TOW = "Warehouse Automation|Logistics|Industrial|Intralogistics|Material Handling"
TAGS_PICKER = "Warehouse Automation|Logistics|Industrial|Intralogistics|Material Handling"
TAGS_CLEAN = "Warehouse Automation|Industrial|Intralogistics|Material Handling|Logistics"

# Explicit URL fixes when CRM itemid is wrong / dead and list-map needs a nudge.
URL_OVERRIDES: dict[str, str] = {
    "PS20/35CB": "https://www.noblelift.com/AGV/info.aspx?itemid=649&lcid=55",
    "PS10/15CB": "https://www.noblelift.com/AGV/info.aspx?itemid=653&lcid=55",
    "FEP-30/35/38P": "https://www.noblelift.com/wlbysb/info.aspx?itemid=809&lcid=50",
    "FE4P16/18/20/25/30/35N": "https://www.noblelift.com/wlbysb/info.aspx?itemid=695&lcid=50",
    "PSE12N": "https://www.noblelift.com/wlbysb/info.aspx?itemid=721&lcid=47",
    "PSE12N PRO": "https://www.noblelift.com/wlbysb/info.aspx?itemid=729&lcid=47",
    "PS12/16/20N": "https://www.noblelift.com/wlbysb/info.aspx?itemid=691&lcid=47",
    "PS12/16/20N PRO": "https://www.noblelift.com/wlbysb/info.aspx?itemid=691&lcid=47",
    "PS12/16/20L": "https://www.noblelift.com/wlbysb/info.aspx?itemid=715&lcid=47",
    "PS12/16/20C": "https://www.noblelift.com/wlbysb/info.aspx?itemid=715&lcid=47",
    "PS12/16/20D": "https://www.noblelift.com/wlbysb/info.aspx?itemid=715&lcid=47",
    "PS12/16/20R": "https://www.noblelift.com/wlbysb/info.aspx?itemid=716&lcid=47",
    "PS15/20": "https://www.noblelift.com/AGV/info.aspx?itemid=650&lcid=51",
    "PS14/16RP": "https://www.noblelift.com/wlbysb/info.aspx?itemid=691&lcid=47",
    "PS15CB": "https://www.noblelift.com/wlbysb/info.aspx?itemid=719&lcid=47",
    "PTE15/20N": "https://www.noblelift.com/wlbysb/info.aspx?itemid=707&lcid=48",
    "PTE15/20N PRO": "https://www.noblelift.com/wlbysb/info.aspx?itemid=708&lcid=48",
    "PTE20N PLUS": "https://www.noblelift.com/wlbysb/info.aspx?itemid=708&lcid=48",
    "PT15/20/25/30/36": "https://www.noblelift.com/wlbysb/info.aspx?itemid=709&lcid=48",
    "PT20/25/30PLUS": "https://www.noblelift.com/wlbysb/info.aspx?itemid=709&lcid=48",
    "PT20/25/30PRO": "https://www.noblelift.com/wlbysb/info.aspx?itemid=709&lcid=48",
    "PT20/25/30L": "https://www.noblelift.com/wlbysb/info.aspx?itemid=709&lcid=48",
    "PT20/25/30C": "https://www.noblelift.com/wlbysb/info.aspx?itemid=709&lcid=48",
    "PT20/25/30R": "https://www.noblelift.com/wlbysb/info.aspx?itemid=709&lcid=48",
    "T20/30/40/50": "https://www.noblelift.com/wlbysb/info.aspx?itemid=751&lcid=45",
    "T60": "https://www.noblelift.com/wlbysb/info.aspx?itemid=506&lcid=45",
    "OPL10": "https://www.noblelift.com/wlbysb/info.aspx?itemid=753&lcid=43",
    "AC20/25/30": "https://www.noblelift.com/wlbysb/info.aspx?itemid=516&lcid=46",
    "AC20/25/30L": "https://www.noblelift.com/wlbysb/info.aspx?itemid=515&lcid=46",
    "AC20/25/30G": "https://www.noblelift.com/wlbysb/info.aspx?itemid=756&lcid=46",
    "NR530": "https://www.noblelift.com/wlbysb/info.aspx?itemid=731&lcid=44",
    "ES15": "https://www.noblelift.com/wlbysb/info.aspx?itemid=749&lcid=63",
    "Counterbalanced Forklift": "https://www.noblelift.com/wlbysb/info.aspx?itemid=746&lcid=63",
    "Reach Truck": "https://www.noblelift.com/wlbysb/info.aspx?itemid=747&lcid=63",
    "Pallet Truck": "https://www.noblelift.com/wlbysb/info.aspx?itemid=748&lcid=63",
}

FLAG_HINTS = (
    "usa", "canada", "france", "germany", "malaysia", "australia", "brazil",
    "mexico", "korea", "japan", "china", "spain", "italy", "ru.png", "eu.png",
    "uk.png", "in.png", "ytb.png", "facebook", "linkedin", "twitter", "instagram",
)

_YT_CACHE: dict[str, list[str]] = {}
_PAGE_CACHE: dict[str, dict[str, Any]] = {}
_URL_MAP: dict[str, str] | None = None


def load_url_map() -> dict[str, str]:
    global _URL_MAP
    if _URL_MAP is not None:
        return _URL_MAP
    path = _RESEARCH_DIR / "staging" / "reports" / "noblelift-url-map.json"
    _URL_MAP = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    return _URL_MAP


def model_key(name: str) -> str:
    n = re.sub(r"^Noblelift\s+", "", name, flags=re.I).strip()
    # Prefer full model token including PRO / PLUS suffix when present early
    m = re.match(
        r"^((?:Counterbalanced Forklift|Reach Truck|Pallet Truck)|"
        r"[A-Za-z0-9][A-Za-z0-9./\-]*(?:\s+PRO|\s+PLUS)?)",
        n,
        re.I,
    )
    return (m.group(1) if m else n).strip()


def is_junk_image(url: str) -> bool:
    low = url.lower()
    if any(x in low for x in ("logo", "favicon", "icon", "banner", "wx", "qr")):
        return True
    if any(x in low for x in FLAG_HINTS):
        return True
    if "?" in url:
        q = unquote(url.split("?", 1)[1])
        try:
            pad = "=" * (-len(q) % 4)
            decoded = base64.b64decode(q + pad).decode("utf-8", errors="ignore").lower()
            if any(x in decoded for x in FLAG_HINTS):
                return True
        except Exception:
            pass
    # social / tiny chrome assets often lack dated path
    path = urlparse(url).path.lower()
    if re.search(r"/(in|ytb|fb|linkedin)\.png$", path):
        return True
    return False


def abs_url(base: str, u: str) -> str:
    u = unescape((u or "").strip().strip("'\""))
    if not u:
        return ""
    if u.startswith("//"):
        return "https:" + u
    return urljoin(base, u)


def verify_image(url: str) -> bool:
    if not url or is_junk_image(url):
        return False
    try:
        resp = requests.head(url, headers=HEADERS, timeout=20, allow_redirects=True)
        if resp.status_code == 405 or "image" not in (resp.headers.get("content-type") or "").lower():
            resp = requests.get(url, headers=HEADERS, timeout=40, stream=True)
            resp.close()
        if resp.status_code != 200:
            return False
        ctype = (resp.headers.get("content-type") or "").lower()
        return "image" in ctype or bool(re.search(r"\.(png|jpe?g|webp)(\?|$)", url, re.I))
    except requests.RequestException:
        return False


def classify(name: str, url: str, subtit: str = "") -> str:
    blob = f"{name} {subtit} {url}".upper()
    tok = model_key(name).upper()
    if "AGV" in blob or "/AGV/" in url.upper():
        return "agv"
    if any(x in blob for x in ("SCRUBBER", "CLEANING", "NR530", "NB380", "NB460")):
        return "clean"
    if any(x in blob for x in ("ORDER PICKER", "OPL", "OPH", "OLE", "OVS")):
        return "picker"
    # Tow models are T## / TE## — do not match T30 inside PT20/25/30*
    if re.search(r"(?:^|[^A-Z0-9])(?:TOW|TRACTOR|T\d{2}|TE\d{2})", f"{tok} {subtit}".upper()):
        if not tok.startswith("PT") and not tok.startswith("PTE") and not tok.startswith("PS"):
            return "tow"
    if any(x in blob for x in ("REACH", "RT15", "RT16", "RT20", "RRS")):
        return "reach"
    if any(x in blob for x in ("FORKLIFT", "FE3", "FE4", "FEP", "CBT", "COUNTERBALANCE")):
        return "fork"
    if any(x in blob for x in ("STACKER", "PSE", "PS12", "PS15", "PS14", "SWB", "ES15")):
        return "stacker"
    if any(x in blob for x in ("PALLET", "PTE", "PWB", "EPT", "PT15", "PT20", "AC20", "AG SERIES")):
        return "pallet"
    return "fork"


def tags_for(kind: str) -> str:
    return {
        "agv": TAGS_AGV,
        "fork": TAGS_FORK,
        "stacker": TAGS_STACKER,
        "pallet": TAGS_PALLET,
        "reach": TAGS_REACH,
        "tow": TAGS_TOW,
        "picker": TAGS_PICKER,
        "clean": TAGS_CLEAN,
    }.get(kind, TAGS_FORK)


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


def score_map_key(token: str, map_key: str) -> int:
    tok = token.upper().strip()
    mk = map_key.upper()
    mk_model = mk.split()[0]
    if tok == mk_model:
        return 100
    # Prefer exact non-PRO when token has no PRO
    if tok + " PRO" == " ".join(mk.split()[:2]) and "PRO" not in tok:
        return 40
    if mk_model.startswith(tok) or tok.startswith(mk_model):
        return 85
    # slash variants: PSE12N inside PSE12B/12N/12BD
    parts = re.split(r"[/\s\-]+", mk_model)
    tok_parts = re.split(r"[/\s\-]+", tok)
    if tok in mk_model and len(tok) >= 5:
        return 80
    if any(p and p in parts for p in tok_parts if len(p) >= 4):
        return 60
    root = re.sub(r"[/\-].*", "", tok)
    if root and root in mk_model and len(root) >= 4:
        return 55
    return 0


def resolve_url(name: str, crm_url: str) -> tuple[str, str]:
    """Return (url, resolution_note)."""
    key = model_key(name)
    key_compact = key.upper()
    # Exact override first; longer keys win (PSE12N PRO before PSE12N).
    for ov_key, ov_url in sorted(URL_OVERRIDES.items(), key=lambda kv: -len(kv[0])):
        if key_compact == ov_key.upper():
            return ov_url, f"override:{ov_key}"

    url_map = load_url_map()
    scored = sorted(
        ((score_map_key(key, mk), mk, u) for mk, u in url_map.items()),
        reverse=True,
    )
    if scored and scored[0][0] >= 80:
        return scored[0][2], f"map:{scored[0][1]}"
    if scored and scored[0][0] >= 55 and "Cold Storage" not in scored[0][1]:
        return scored[0][2], f"map-fuzzy:{scored[0][1]}"

    if crm_url and "noblelift.com" in crm_url:
        return crm_url, "crm"

    if scored and scored[0][0] > 0:
        return scored[0][2], f"map-weak:{scored[0][1]}"
    return crm_url or "", "none"


def scrape_pdp(url: str) -> dict[str, Any]:
    if url in _PAGE_CACHE:
        return _PAGE_CACHE[url]
    resp = requests.get(url, headers=HEADERS, timeout=45, allow_redirects=True)
    html = resp.text
    base = f"{urlparse(resp.url).scheme}://{urlparse(resp.url).netloc}"

    name_m = re.search(r"var\s+name\s*=\s*'([^']+)'", html)
    page_name = name_m.group(1).strip() if name_m else ""
    tit_m = re.search(r'class="tit"[^>]*>(.*?)</div>', html, re.I | re.S)
    tit = re.sub(r"<[^>]+>", " ", tit_m.group(1)).strip() if tit_m else ""
    tit = re.sub(r"\s+", " ", unescape(tit))
    if tit.lower() == "social media":
        tit = ""
    sub_m = re.search(r'class="subtit"[^>]*>(.*?)</div>', html, re.I | re.S)
    subtit = re.sub(r"<[^>]+>", " ", sub_m.group(1)).strip() if sub_m else ""
    subtit = re.sub(r"\s+", " ", unescape(subtit))

    # Ispic heroes (dated uploadfiles preferred)
    bgs = [
        abs_url(base, b)
        for b in re.findall(r"background-image\s*:\s*url\(([^)]+)\)", html, re.I)
    ]
    heroes = []
    for u in bgs:
        if not u or is_junk_image(u):
            continue
        if "/uploadfiles/" not in u:
            continue
        # Prefer product shots with year folders
        if re.search(r"/uploadfiles/\d{4}/", u):
            heroes.append(u.split("?")[0])
    heroes = list(dict.fromkeys(heroes))

    # Description / gallery imgs
    gallery = []
    for m in re.findall(r'(?:src|data-src)=["\']([^"\']+)["\']', html, re.I):
        u = abs_url(base, m)
        if "/uploadfiles/" not in u:
            continue
        if not re.search(r"\.(png|jpe?g|webp)", u, re.I):
            continue
        if is_junk_image(u):
            continue
        if not re.search(r"/uploadfiles/\d{4}/", u):
            continue
        gallery.append(u.split("?")[0])
    gallery = list(dict.fromkeys(gallery))

    # Spec table cells
    cells = [
        re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", unescape(c))).strip()
        for c in re.findall(r"<td[^>]*>(.*?)</td>", html, re.I | re.S)
    ]
    cells = [c for c in cells if c and len(c) < 80]

    payload_kg = None
    weight_kg = None
    lift_mm = None
    for i, c in enumerate(cells):
        cl = c.lower()
        if "load capacity" in cl or "rated load" in cl:
            # next numeric cell(s); unit may be t or kg
            unit_t = False
            for j in range(i + 1, min(i + 6, len(cells))):
                if cells[j].lower() in ("t", "ton", "tons"):
                    unit_t = True
                    continue
                if cells[j].lower() == "kg":
                    unit_t = False
                    continue
                m = re.match(r"^(\d+(?:\.\d+)?)$", cells[j])
                if m:
                    val = float(m.group(1))
                    payload_kg = val * 1000.0 if unit_t or val <= 5 else val
                    break
        if cl.startswith("service weight"):
            for j in range(i + 1, min(i + 5, len(cells))):
                if cells[j].lower() == "kg":
                    continue
                m = re.match(r"^(\d+(?:\.\d+)?)$", cells[j])
                if m:
                    weight_kg = float(m.group(1))
                    break
        if "lift height" in cl:
            for j in range(i + 1, min(i + 5, len(cells))):
                if cells[j].lower() == "mm":
                    continue
                m = re.match(r"^(\d+(?:\.\d+)?)$", cells[j])
                if m:
                    lift_mm = float(m.group(1))
                    break

    # Subtitle payload fallback e.g. "1500KG Pallet handling AGV"
    if payload_kg is None and subtit:
        m = re.search(r"(\d+(?:\.\d+)?)\s*(?:—|-|/)?\s*(?:\d+(?:\.\d+)?)?\s*kg", subtit, re.I)
        if not m:
            m = re.search(r"(\d+(?:\.\d+)?)\s*KG", subtit, re.I)
        if m:
            payload_kg = float(m.group(1))

    # OEM hosted mp4 (kept as note; YouTube used for video_urls)
    mp4s = [
        abs_url(base, m)
        for m in re.findall(r'(?:rel|src|href)=["\']([^"\']+\.mp4[^"\']*)["\']', html, re.I)
    ]

    # Feature-ish lines from description boxes (rare on AGV pages)
    text = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "\n", text)
    text = unescape(re.sub(r"[ \t]+", " ", text))
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    paras = [
        ln for ln in lines
        if 40 <= len(ln) <= 280
        and "leading manufacturer" not in ln.lower()
        and "cookie" not in ln.lower()
        and "copyright" not in ln.lower()
        and not ln.startswith("$")
        and "function" not in ln.lower()
    ]

    hero = ""
    for cand in [*heroes, *gallery]:
        if verify_image(cand):
            hero = cand
            break

    out = {
        "page_name": page_name or tit,
        "tit": tit,
        "subtit": subtit,
        "hero": hero,
        "images": [u for u in [*heroes, *gallery] if u != hero][:4],
        "payload_kg": payload_kg,
        "weight_kg": weight_kg,
        "lift_mm": lift_mm,
        "paras": paras[:6],
        "mp4s": mp4s[:2],
        "cells_sample": cells[:20],
    }
    _PAGE_CACHE[url] = out
    return out


def parse_name_payload(name: str) -> float | None:
    m = re.search(r"(\d{3,5})\s*kg", name, re.I)
    if m:
        return float(m.group(1))
    # PS20/35CB → first number * 100 if looks like tonnage shorthand? No — 20 means 2000kg in model codes
    return None


def build_features(name: str, kind: str, pdp: dict[str, Any], resolution: str) -> str:
    parts: list[str] = []
    tit = pdp.get("tit") or pdp.get("page_name") or model_key(name)
    sub = pdp.get("subtit") or ""
    if tit and sub:
        parts.append(f"{tit} — {sub} (Noblelift product page).")
    elif sub:
        parts.append(f"{name}: {sub} (Noblelift product page).")
    else:
        parts.append(f"{name} material handling equipment from Noblelift.")

    if pdp.get("payload_kg") is not None:
        parts.append(f"Cited load capacity: {pdp['payload_kg']:g} kg.")
    if pdp.get("weight_kg") is not None:
        parts.append(f"Cited service weight: {pdp['weight_kg']:g} kg.")
    if pdp.get("lift_mm") is not None:
        parts.append(f"Cited lift height: {pdp['lift_mm']:g} mm.")

    for p in pdp.get("paras") or []:
        if p not in parts and len(p) > 40:
            parts.append(p)
            if len(parts) >= 5:
                break

    kind_line = {
        "agv": "Autonomous guided vehicle for warehouse pallet / load handling.",
        "fork": "Electric forklift for warehouse and factory material handling.",
        "stacker": "Electric stacker for pallet lifting and short-distance transport.",
        "pallet": "Pallet truck for warehouse floor transport.",
        "reach": "Reach truck for narrow-aisle racking operations.",
        "tow": "Tow tractor for warehouse trailer / cart movement.",
        "picker": "Order picker for warehouse picking operations.",
        "clean": "Industrial floor scrubber for facility cleaning.",
    }.get(kind)
    if kind_line:
        parts.append(kind_line)

    if resolution.startswith("override") or resolution.startswith("map-fuzzy") or resolution.startswith("map-weak"):
        parts.append(f"URL resolved via {resolution} (CRM itemid may have been incorrect).")

    return " ".join(parts)[:1800]


def build_row(robot: dict[str, Any], pdp: dict[str, Any], url: str, resolution: str) -> dict[str, Any]:
    name = robot["name"]
    kind = classify(name, url, pdp.get("subtit") or "")
    features = build_features(name, kind, pdp, resolution)
    description = (
        (f"{pdp.get('tit') or model_key(name)} — {pdp.get('subtit')}".strip(" —")
         if pdp.get("subtit") else None)
        or (pdp.get("paras") or [None])[0]
        or f"{name} from Noblelift."
    )
    hero = pdp.get("hero") or ""
    # Seed from existing CDN when scrape hero missing
    if not hero:
        hero = (robot.get("s3_image") or robot.get("image") or "").strip()
    images = list(pdp.get("images") or [])
    if hero and hero not in images:
        images = [hero, *images]

    if kind not in _YT_CACHE:
        qmap = {
            "agv": "Noblelift AGV pallet handling",
            "fork": "Noblelift electric forklift",
            "stacker": "Noblelift electric stacker",
            "pallet": "Noblelift pallet truck",
            "reach": "Noblelift reach truck",
            "tow": "Noblelift tow tractor",
            "picker": "Noblelift order picker",
            "clean": "Noblelift floor scrubber",
        }
        _YT_CACHE[kind] = enrich_video_list(youtube_search_ids(qmap[kind], limit=3))
    videos = list(_YT_CACHE[kind])

    row: dict[str, Any] = {
        "name": name,
        "company_slug": COMPANY_SLUG,
        "company_name": COMPANY_NAME,
        "manufacturer_country_code": "CN",
        "description": description[:1200],
        "purpose": description[:1200],
        "features": features,
        "url": url,
        "image": hero,
        "images": images[:4],
        "video_urls": videos,
        "movement_type_keys": "wheeled",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "logistics-warehouse",
        "tags": tags_for(kind),
        "sources": [{"url": url, "type": "website", "title": pdp.get("tit") or name}],
        "research_notes": (
            f"Noblelift content-queue backfill from {url} ({resolution}). "
            f"Page title={pdp.get('page_name') or pdp.get('tit')}."
        ),
    }
    payload = pdp.get("payload_kg")
    if payload is None:
        payload = parse_name_payload(name)
    notes_parts = []
    if payload is not None:
        row["payload_kg"] = payload
        notes_parts.append(f"Payload: {payload:g} kg")
    if pdp.get("weight_kg") is not None:
        row["weight_kg"] = pdp["weight_kg"]
        row["weight"] = f"{pdp['weight_kg']} kg"
        notes_parts.append(f"Service weight: {pdp['weight_kg']:g} kg")
    if pdp.get("lift_mm") is not None:
        notes_parts.append(f"Lift height: {pdp['lift_mm']:g} mm")
    if notes_parts:
        row["notes"] = " | ".join(notes_parts)
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


def page_matches_robot(robot_name: str, pdp: dict[str, Any]) -> bool:
    page = (pdp.get("page_name") or pdp.get("tit") or "").upper()
    if not page or page == "SOCIAL MEDIA":
        return False
    tok = model_key(robot_name).upper()
    if tok in page or page in tok:
        return True
    # family pages e.g. FEP-16-20P/25-38P for FEP-30/35/38P
    root = re.sub(r"[/\-].*", "", tok)
    if len(root) >= 3 and root in page:
        return True
    # customization / category pages
    if any(x in tok for x in ("COUNTERBALANCED", "REACH TRUCK", "PALLET TRUCK", "ES15")):
        return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix Noblelift robots company 1028")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--copy-media", action="store_true")
    parser.add_argument("--created-by-id", type=int, default=1)
    parser.add_argument("--only", nargs="*")
    parser.add_argument("--allow-family", action="store_true", default=True,
                        help="Allow family-page enrichment when exact PDP missing")
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
        url, resolution = resolve_url(robot["name"], (robot.get("url") or "").strip())
        if not url:
            print(f"SKIP {robot['id']} {robot['name']}: no url")
            continue
        print(f"scrape {robot['name']} → {url} ({resolution})")
        try:
            pdp = scrape_pdp(url)
        except requests.RequestException as exc:
            print(f"  FAIL scrape: {exc}")
            continue
        matched = page_matches_robot(robot["name"], pdp)
        if not matched and not args.allow_family:
            print(f"  SKIP page mismatch page={pdp.get('page_name')}")
            continue
        if not matched:
            print(f"  WARN family/mismatch page={pdp.get('page_name')!r} tit={pdp.get('tit')!r}")
        row = build_row(robot, pdp, url, resolution)
        staging[int(robot["id"])] = row
        item = {
            "id": robot["id"],
            "name": robot["name"],
            "url": row["url"],
            "resolution": resolution,
            "page_name": pdp.get("page_name"),
            "matched": matched,
            "image": bool(row.get("image")),
            "image_url": row.get("image"),
            "features_len": len(row.get("features") or ""),
            "videos": len(row.get("video_urls") or []),
            "tags": row.get("tags"),
            "payload_kg": row.get("payload_kg"),
            "kind": classify(robot["name"], url, pdp.get("subtit") or ""),
        }
        plan.append(item)
        print(
            f"  img={'yes' if item['image'] else 'no'} feat={item['features_len']} "
            f"vids={item['videos']} payload={item['payload_kg']} kind={item['kind']} "
            f"page={item['page_name']}"
        )

    preview = _RESEARCH_DIR / "staging" / "reports" / "noblelift-fix-preview.json"
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if not plan:
        print("ERROR: nothing to import", file=sys.stderr)
        return 1
    bad = [p for p in plan if not p["image"] or p["features_len"] < 40 or not p["videos"] or not p["tags"]]
    if bad:
        print(f"ERROR: incomplete enrichment for {len(bad)} robots", file=sys.stderr)
        for p in bad:
            print(
                f"  {p['name']}: img={p['image']} feat={p['features_len']} vids={p['videos']} "
                f"url={p['url']} page={p.get('page_name')}",
                file=sys.stderr,
            )
        return 1
    if not args.apply:
        print(f"Preview: {preview}. Re-run with --apply --copy-media")
        return 0

    tmp = Path(tempfile.mkdtemp(prefix="noblelift-fix-"))
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
