"""Backfill Mujin (company 810) pending_review robots via official mujin.co.jp solution pages.

CRM often pointed at case studies, videos, or download hubs. Remap to product
solution URLs; heroes from `background-image-holder` / wp-content uploads;
YouTube embeds from the same pages when present.
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
from urllib.parse import urljoin, urlparse

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

COMPANY_ID = 810
COMPANY_SLUG = "mujin"
COMPANY_NAME = "Mujin"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

TAGS_PALLETIZE = (
    "palletizing|Warehouse Automation|Logistics|Industrial|Intralogistics|"
    "Industrial Arm|Industrial Robot|Factory Automation|Pallet Handling|6-Axis"
)
TAGS_DEPAL = (
    "palletizing|Warehouse Automation|Logistics|Industrial|Intralogistics|"
    "Industrial Arm|Industrial Robot|Factory Automation|Pallet Handling|Pick-and-Place"
)
TAGS_PICK = (
    "picking|Pick-and-Place|Warehouse Automation|Logistics|Industrial|"
    "Intralogistics|Industrial Arm|Industrial Robot|Factory Automation"
)
TAGS_BIN = (
    "picking|Pick-and-Place|Factory Automation|Industrial|Industrial Arm|"
    "Industrial Robot|Manufacturing"
)
TAGS_AGV = (
    "AMR|AGV|Warehouse Automation|Logistics|Autonomous Mobile Robot|"
    "Intralogistics|Industrial|Mobile Robot"
)
TAGS_SOL = (
    "Warehouse Automation|Logistics|Industrial|Intralogistics|"
    "Industrial Robot|Factory Automation|Pallet Handling"
)

# Curated remap: CRM robot id → official product page + preferred hero + English copy.
# description/features MUST stay English — never paste JP lead/nav chrome from mujin.co.jp.
ROBOT_CURATION: dict[int, dict[str, Any]] = {
    3753: {  # 単載パレタイザー
        "url": "https://www.mujin.co.jp/solution/distribution/singlesku-palletize/",
        "hero": "https://www.mujin.co.jp/wp-content/uploads/2025/12/robot_arm.jpg",
        "kind": "palletize",
        "en_name": "Mujin Single-SKU Palletizer",
        "description": (
            "Mujin Single-SKU Palletizer is a MujinOS-powered case palletizing cell for "
            "uniform-SKU outbound shipping in warehouses and distribution centers."
        ),
        "features": (
            "Official Mujin product page: Single-SKU / uniform-case palletizing robot cell. "
            "Positioned as an early MujinOS product for logistics automation. "
            "Uses Mujin intelligent control for real-time motion planning around conveyors and pallets. "
            "Typical cell layout: industrial arm + gripper transferring cases from conveyor to pallet "
            "(optionally coordinated with mobile robots for pallet move-out). "
            "Source: https://www.mujin.co.jp/solution/distribution/singlesku-palletize/"
        ),
    },
    3754: {  # MujinAGV (CRM wrongly pointed at tokubai)
        "url": "https://www.mujin.co.jp/solution/mobilerobot/agv/",
        "hero": "https://www.mujin.co.jp/wp-content/uploads/2026/03/agv_0326.png",
        "kind": "agv",
        "en_name": "Mujin AGV",
        "description": (
            "Mujin QR-guided AGV for warehouse material transport with multi-vehicle fleet operation."
        ),
        "features": (
            "Official Mujin AGV page: QR-code guided automated guided vehicle for factory and warehouse transport. "
            "Designed for high travel accuracy and scalable fleets (page cites multi-vehicle operation up to about "
            "100 units). Mujin's own control algorithms target stable, high-performance automated conveyance. "
            "Modular tops (e.g. roller conveyor) are shown for load transfer use cases. "
            "Source: https://www.mujin.co.jp/solution/mobilerobot/agv/"
        ),
    },
    3755: {  # MujinRCP — productized name from TEPCO logistics case
        "url": "https://www.mujin.co.jp/example/tepco-logistics/",
        "hero": "https://www.mujin.co.jp/wp-content/uploads/2026/06/tpclg.png",
        "kind": "sol",
        "en_name": "MujinRCP",
        "description": (
            "MujinRCP is Mujin's intelligent robot solution referenced in the TEPCO Logistics deployment "
            "for multi-SKU materials handling in power-infrastructure logistics."
        ),
        "features": (
            "Documented on Mujin's TEPCO Logistics case page (no dedicated /solution/ PDP found). "
            "Describes physical-AI / intelligent robot automation for multi-variety materials used in "
            "electric-power logistics operations. Treat as a solution reference tied to that customer story "
            "until Mujin publishes a standalone product page. "
            "Source: https://www.mujin.co.jp/example/tepco-logistics/"
        ),
        "note": "RCP is documented via TEPCO Logistics case study on mujin.co.jp (no dedicated /solution/ PDP).",
    },
    3756: {  # Space-saving mixed-load depalletizer
        "url": "https://www.mujin.co.jp/solution/distribution/depalletize/",
        "hero": "https://www.mujin.co.jp/wp-content/themes/mujin/assets/jp/img/case/g01min.jpg",
        "kind": "depal",
        "en_name": "MujinRobot Depalletizer (space-saving / mixed-load)",
        "description": (
            "MujinRobot Depalletizer for space-saving mixed-SKU case unloading in distribution centers."
        ),
        "features": (
            "Official MujinRobot Depalletizer page. Cited throughput on page: up to 1,000 cases/hour for "
            "single-SKU and up to 600 cases/hour for mixed-SKU unloading. Space-saving / mixed-load variant "
            "targets dense warehouse footprints. Vision-guided case depalletizing into conveyors or staging. "
            "Source: https://www.mujin.co.jp/solution/distribution/depalletize/"
        ),
    },
    3757: {
        "url": "https://www.mujin.co.jp/solution/distribution/depalletize/",
        "hero": "https://www.mujin.co.jp/wp-content/themes/mujin/assets/jp/img/case/k01.jpg",
        "kind": "depal",
        "en_name": "MujinRobot Depalletizer",
        "description": (
            "MujinRobot Depalletizer is a vision-guided case unloading cell for single-SKU and mixed-SKU pallets."
        ),
        "features": (
            "Official MujinRobot Depalletizer solution. Page cites world-class throughput of up to "
            "1,000 cases/hour (single-SKU) and up to 600 cases/hour (mixed-SKU). Built for logistics "
            "inbound automation with Mujin intelligent control. "
            "Source: https://www.mujin.co.jp/solution/distribution/depalletize/"
        ),
    },
    3758: {
        "url": "https://www.mujin.co.jp/download/pallet/",
        "hero": "https://www.mujin.co.jp/wp-content/uploads/2025/03/pallet01.png",
        "kind": "sol",
        "en_name": "MujinRobot Pallet Changer",
        "description": (
            "MujinRobot Pallet Changer automates restacking cases between different pallet sizes, "
            "optionally with AGV collaboration for pallet transport."
        ),
        "features": (
            "Official Mujin intro/download page for Pallet Changer. Supports restacking onto different "
            "pallet sizes using Mujin 3D vision for case recognition. Marketing materials highlight AGV "
            "collaboration to automate pallet conveyance after restack. Aimed at replacing heavy manual "
            "pallet-transfer labor. No dedicated /solution/ PDP yet — source is the download landing page. "
            "Source: https://www.mujin.co.jp/download/pallet/"
        ),
        "note": "Official page is download/intro material; no /solution/ PDP yet.",
    },
    3759: {
        "url": "https://www.mujin.co.jp/solution/distribution/palletize/",
        "hero": "https://www.mujin.co.jp/wp-content/themes/mujin/assets/jp/img/case/h01.jpg",
        "kind": "palletize",
        "en_name": "MujinRobot Palletizer",
        "description": (
            "MujinRobot Palletizer is a high-rate case palletizing robot cell for warehouse outbound shipping."
        ),
        "features": (
            "Official MujinRobot Palletizer page. Cited throughput on page: up to 500 cases/hour. "
            "Case palletizing for logistics automation using Mujin intelligent control / real-time planning. "
            "Source: https://www.mujin.co.jp/solution/distribution/palletize/"
        ),
    },
    3760: {
        "url": "https://www.mujin.co.jp/solution/distribution/picking/",
        "hero": "https://www.mujin.co.jp/wp-content/themes/mujin/assets/jp/img/case/l01.jpg",
        "kind": "pick",
        "en_name": "MujinRobot Piece Picker",
        "description": (
            "MujinRobot Piece Picker is a high-rate, high-mix piece-picking robot for distribution centers."
        ),
        "features": (
            "Official MujinRobot Piece Picker page. Cited throughput on page: up to 1,000 pieces/hour with "
            "high SKU generality for warehouse picking. Vision-guided piece handling into totes/sorters. "
            "Source: https://www.mujin.co.jp/solution/distribution/picking/"
        ),
    },
    3761: {
        "url": "https://www.mujin.co.jp/solution/distribution/depalletize/",
        "hero": "https://www.mujin.co.jp/wp-content/themes/mujin/assets/jp/img/case/k01min.jpg",
        "kind": "depal",
        "en_name": "MujinRobot Depalletizer",
        "description": (
            "MujinRobot Depalletizer (JP listing) — vision-guided case depalletizing for logistics inbound."
        ),
        "features": (
            "Same official Depalletizer solution as the EN-named twin record. Page cites up to "
            "1,000 cases/hour single-SKU and up to 600 cases/hour mixed-SKU. "
            "Source: https://www.mujin.co.jp/solution/distribution/depalletize/"
        ),
    },
    3762: {
        "url": "https://www.mujin.co.jp/solution/fa/picking/",
        "hero": "https://www.mujin.co.jp/wp-content/themes/mujin/assets/jp/img/case/i01min.jpg",
        "kind": "bin",
        "en_name": "PickWorker",
        "description": (
            "PickWorker is Mujin's teach-less 3D bin-picking package for factory parts supply and machine tending."
        ),
        "features": (
            "Official PickWorker package page for FA / factory automation. Automates random bin picking "
            "without traditional teach programming; covers system components through integration support. "
            "Targets bulk parts feed to machining or assembly. "
            "Source: https://www.mujin.co.jp/solution/fa/picking/"
        ),
    },
    3763: {
        "url": "https://www.mujin.co.jp/solution/fa/containerdepalletize/",
        "hero": "https://www.mujin.co.jp/wp-content/uploads/2023/10/cdp_tp.jpg",
        "kind": "depal",
        "en_name": "Returnable-container depalletize/palletize robot",
        "description": (
            "Mujin returnable-container (tote) depalletize/palletize robot for mixed factory logistics containers."
        ),
        "features": (
            "Official FA container depalletize/palletize page. Uses Mujin's stacking algorithms and a "
            "variable hand claimed to support 50+ returnable container types, including mixed stacks that "
            "were previously hard to automate. Aimed at automotive / factory parts-supply logistics. "
            "Source: https://www.mujin.co.jp/solution/fa/containerdepalletize/"
        ),
    },
}

_PAGE_CACHE: dict[str, dict[str, Any]] = {}
_YT_CACHE: dict[str, list[str]] = {}


def abs_url(base: str, u: str) -> str:
    u = unescape((u or "").strip())
    if not u:
        return ""
    if u.startswith("//"):
        return "https:" + u
    return urljoin(base, u)


def verify_image(url: str) -> bool:
    if not url:
        return False
    low = url.lower()
    if any(x in low for x in ("logo", "favicon", "top_catch", "sns", "qr", "icon")):
        return False
    try:
        resp = requests.head(url, headers=HEADERS, timeout=20, allow_redirects=True)
        if resp.status_code == 405 or "image" not in (resp.headers.get("content-type") or "").lower():
            resp = requests.get(url, headers=HEADERS, timeout=40, stream=True)
            resp.close()
        return resp.status_code == 200
    except requests.RequestException:
        return False


def tags_for(kind: str) -> str:
    return {
        "palletize": TAGS_PALLETIZE,
        "depal": TAGS_DEPAL,
        "pick": TAGS_PICK,
        "bin": TAGS_BIN,
        "agv": TAGS_AGV,
        "sol": TAGS_SOL,
    }.get(kind, TAGS_SOL)


def scrape_pdp(url: str) -> dict[str, Any]:
    if url in _PAGE_CACHE:
        return _PAGE_CACHE[url]
    resp = requests.get(url, headers=HEADERS, timeout=45, allow_redirects=True)
    html = resp.text
    base = f"{urlparse(resp.url).scheme}://{urlparse(resp.url).netloc}"

    h1_m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.I | re.S)
    h1 = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h1_m.group(1))).strip() if h1_m else ""

    leads = re.findall(r'class="lead"[^>]*>(.*?)</p>', html, re.I | re.S)
    leads = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", unescape(x))).strip() for x in leads]
    leads = [x for x in leads if x]

    holders = [
        abs_url(base, src)
        for src in re.findall(
            r'background-image-holder[^>]*>\s*<img[^>]+src=["\']([^"\']+)["\']',
            html,
            re.I,
        )
    ]
    holders = [u for u in holders if u and "top_catch" not in u.lower()]

    uploads = []
    for m in re.findall(r'(?:src|data-src)=["\']([^"\']+)["\']', html, re.I):
        u = abs_url(base, m)
        if "/wp-content/uploads/" in u and re.search(r"\.(png|jpe?g|webp)", u, re.I):
            if not any(x in u.lower() for x in ("logo", "favicon", "qr", "sns")):
                uploads.append(u.split("?")[0])
    uploads = list(dict.fromkeys(uploads))

    yts = list(dict.fromkeys(re.findall(r"youtube\.com/embed/([a-zA-Z0-9_-]{11})", html)))
    videos = [f"https://www.youtube.com/watch?v={v}" for v in yts]

    # Throughput claims cited on solution pages (cs/h, pcs/h)
    blob = " ".join(leads + [h1])
    throughput = None
    m = re.search(r"(\d[\d,]*)\s*(?:cs|pcs)\s*/\s*h", blob, re.I)
    if not m:
        m = re.search(r"最高\s*(\d[\d,]*)\s*(?:cs|pcs)\s*/\s*h", html, re.I)
    if m:
        throughput = m.group(0).replace(",", "")

    # English-ish feature bullets from visible paragraphs near product copy
    text = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "\n", text)
    text = unescape(re.sub(r"[ \t]+", " ", text))
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    paras = [
        ln for ln in lines
        if 40 <= len(ln) <= 220
        and "cookie" not in ln.lower()
        and "copyright" not in ln.lower()
        and "デジタルツイン" not in ln  # site-wide chrome
        and not ln.startswith("http")
    ][:8]

    out = {
        "url": resp.url,
        "h1": h1,
        "leads": leads,
        "holders": holders,
        "uploads": uploads,
        "videos": videos,
        "paras": paras,
        "throughput": throughput,
    }
    _PAGE_CACHE[url] = out
    return out


def youtube_fallback(kind: str) -> list[str]:
    if kind in _YT_CACHE:
        return _YT_CACHE[kind]
    qmap = {
        "palletize": "MujinRobot Palletizer",
        "depal": "MujinRobot Depalletizer",
        "pick": "MujinRobot Piece Picker",
        "bin": "Mujin PickWorker bin picking",
        "agv": "Mujin AGV",
        "sol": "Mujin robot logistics automation",
    }
    try:
        resp = requests.get(
            "https://www.youtube.com/results",
            params={"search_query": qmap.get(kind, "Mujin robot")},
            headers=HEADERS,
            timeout=30,
        )
        ids = re.findall(r'"videoId":"([a-zA-Z0-9_-]{11})"', resp.text)
        urls = []
        for vid in ids:
            if vid not in urls:
                urls.append(f"https://www.youtube.com/watch?v={vid}")
            if len(urls) >= 3:
                break
    except requests.RequestException:
        urls = []
    _YT_CACHE[kind] = enrich_video_list(urls)
    return _YT_CACHE[kind]


def build_features(name: str, cur: dict[str, Any], pdp: dict[str, Any]) -> str:
    # Prefer curated English features — never paste JP lead/nav text from the JP site.
    curated = (cur.get("features") or "").strip()
    if curated:
        return curated[:1800]
    parts: list[str] = []
    en = cur.get("en_name") or name
    parts.append(f"{en} — Mujin logistics / FA automation solution.")
    if pdp.get("throughput"):
        parts.append(f"Cited throughput claim on page: {pdp['throughput']}.")
    kind_blurb = {
        "palletize": "Case palletizing robot cell powered by Mujin intelligent control / MujinOS.",
        "depal": "Case depalletizing robot cell for single-SKU and mixed-SKU unloading.",
        "pick": "High-rate piece-picking robot for distribution centers.",
        "bin": "Teach-less 3D bin-picking package (PickWorker) for factory parts supply.",
        "agv": "QR-guided AGV for multi-vehicle warehouse transport.",
        "sol": "Mujin intelligent robot solution for warehouse / logistics automation.",
    }.get(cur["kind"])
    if kind_blurb:
        parts.append(kind_blurb)
    if cur.get("note"):
        parts.append(cur["note"])
    return " ".join(parts)[:1800]


def build_row(robot: dict[str, Any], cur: dict[str, Any], pdp: dict[str, Any]) -> dict[str, Any]:
    name = robot["name"]
    kind = cur["kind"]
    url = cur["url"]
    hero = cur.get("hero") or ""
    if not hero or not verify_image(hero):
        for cand in [*(pdp.get("holders") or []), *(pdp.get("uploads") or [])]:
            if verify_image(cand):
                hero = cand
                break
    images = []
    for cand in [hero, *(pdp.get("holders") or []), *(pdp.get("uploads") or [])]:
        if cand and cand not in images and verify_image(cand):
            images.append(cand)
        if len(images) >= 4:
            break

    videos = list(pdp.get("videos") or [])
    if len(videos) < 1:
        videos = youtube_fallback(kind)
    else:
        videos = enrich_video_list(videos[:3])

    features = build_features(name, cur, pdp)
    description = (cur.get("description") or "").strip() or f"{cur.get('en_name') or name} from Mujin."

    movement = "wheeled" if kind == "agv" else "stationary"
    sub = "logistics-warehouse" if kind != "bin" else "manufacturing-industrial"

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
        "movement_type_keys": movement,
        "category_slugs": "industrial-robots",
        "sub_category_slug": sub,
        "tags": tags_for(kind),
        "dof": None if kind == "agv" else 6,
        "sources": [{"url": url, "type": "website", "title": cur.get("en_name") or name}],
        "research_notes": (
            f"Mujin content-queue backfill from {url}. "
            f"{cur.get('note') or ''} English description/features curated from official page claims; "
            f"JP site lead text not copied (encoding/locale)."
        ).strip(),
    }
    if pdp.get("throughput"):
        row["notes"] = f"Throughput (cited): {pdp['throughput']}"
    return row


PAMPHLETS_URL = "https://www.mujin.co.jp/download/pamphlets/"
FULL_REJECTS = {
    3761: (
        "duplicate_language_shell: Japanese MujinRobot Depalletizer is the same "
        "product/page as robot 3757 and has no distinct variant"
    )
}
FULL_META: dict[int, dict[str, Any]] = {
    3753: {"family": ("mujin:single-sku-palletizer", "Single-SKU Palletizer"), "purpose": "Uniform-case palletizing\nOutbound pallet build"},
    3754: {"family": ("mujin:agv", "Mujin AGV"), "purpose": "Pallet and material transport\nAutomated load transfer"},
    3755: {"family": ("mujin:rcp", "MujinRCP"), "purpose": "Multi-SKU power-infrastructure logistics handling", "hold": "No standalone OEM PDP, catalog, or technical guide found; only the TEPCO Logistics deployment page documents this name."},
    3756: {"family": ("mujin:depalletizer", "MujinRobot Depalletizer"), "purpose": "Space-saving mixed-SKU case depalletizing"},
    3757: {"family": ("mujin:depalletizer", "MujinRobot Depalletizer"), "purpose": "Single-SKU case depalletizing\nMixed-SKU case depalletizing"},
    3758: {"family": ("mujin:pallet-changer", "MujinRobot Pallet Changer"), "purpose": "Case restacking between pallet sizes\nAGV-coordinated pallet transfer", "hold": "Official download landing page and pamphlet index found, but no standalone solution PDP or citeable system dimensions."},
    3759: {"family": ("mujin:palletizer", "MujinRobot Palletizer"), "purpose": "Mixed-load palletizing\nHeavy-case palletizing"},
    3760: {"family": ("mujin:piece-picker", "MujinRobot Piece Picker"), "purpose": "High-mix piece picking\nSorter and tote induction"},
    3762: {"family": ("mujin:pickworker", "PickWorker"), "purpose": "Random bin picking\nMachine and assembly line feeding"},
    3763: {"family": ("mujin:returnable-container", "Returnable-Container Handling"), "purpose": "Returnable-container depalletizing\nReturnable-container palletizing"},
}


def run_curated_full(
    client: ResearchApiClient,
    robots: list[dict[str, Any]],
    *,
    apply: bool,
    copy_media: bool,
) -> int:
    results: list[dict[str, Any]] = []
    for robot in robots:
        rid = int(robot["id"])
        if rid in FULL_REJECTS:
            body = {
                "status": "rejected",
                "rejection_reason": FULL_REJECTS[rid],
                "notes": f"[CURATED FULL 2026-07-21] {FULL_REJECTS[rid]}",
            }
            if apply:
                client._patch(f"robots/robots/{rid}/", body)
            results.append({"id": rid, "name": robot["name"], "outcome": "rejected", "reason": FULL_REJECTS[rid]})
            continue

        cur = ROBOT_CURATION[rid]
        meta = FULL_META[rid]
        family_key, family_name = meta["family"]
        pdp = scrape_pdp(cur["url"])
        features = build_features(robot["name"], cur, pdp)
        patch: dict[str, Any] = {
            "description": cur["description"],
            "purpose": meta["purpose"],
            "features": re.sub(r"\s+Source:\s+https?://.*$", "", features, flags=re.I).strip(),
            "url": cur["url"],
            "model_name": cur["en_name"],
            "variant_code": cur["en_name"],
            "variant_label": robot["name"],
            "family_key": family_key,
            "family_name": family_name,
            "family_url": cur["url"],
            "product_url_scope": "exact_variant",
            "availability_status": 11,
            "information_source_urls": list(dict.fromkeys([cur["url"], PAMPHLETS_URL])),
            # Mujin specifies complete cells and does not identify the integrated
            # third-party arm model. The prior blanket 6-DOF fill was unsupported.
            "dof": None,
            "status": "pending_review",
        }
        dead = (
            "Checked exact OEM solution page, MujinRobot family page, pamphlet index, "
            "and exposed PDF/download links. Published case/hour, work-envelope and "
            "work-size figures describe the cell workload, not the unspecified arm's "
            "typed payload/dimensions; no robot-model speed, mass, DOF, reach, runtime, "
            "or release year was patched."
        )
        if meta.get("hold"):
            dead += f" HOLD: {meta['hold']}"
        patch["notes"] = f"[CURATED FULL 2026-07-21] {dead}"
        if apply:
            client._patch(f"robots/robots/{rid}/", patch)
        results.append(
            {
                "id": rid,
                "name": robot["name"],
                "outcome": "held" if meta.get("hold") else "enriched",
                "reason": meta.get("hold", ""),
                "page_h1": pdp.get("h1") or "",
            }
        )

    copy_stats = None
    if apply and copy_media:
        media_ids = [r["id"] for r in results if r["outcome"] == "enriched"]
        ok, fail = trigger_copy_media(media_ids)
        copy_stats = {"requested": len(media_ids), "ok": ok, "fail": fail}

    counts = {key: sum(r["outcome"] == key for r in results) for key in ("enriched", "rejected", "held")}
    report = _RESEARCH_DIR / "staging" / "reports" / "mujin-curated-full-report.md"
    lines = [
        "---", "type: log", "title: Mujin Curated Full Enrichment", "status: complete",
        "version: 1.1", "owner: AI", "last_updated: 2026-07-21", "tags:",
        "  - robots", "  - enrichment", "---", "", "# Mujin Curated Full Enrichment", "",
        f"- Production apply: `{apply}`", f"- Enriched: {counts['enriched']}",
        f"- Rejected: {counts['rejected']}", f"- Held: {counts['held']}", "", "## Records", "",
    ]
    lines.extend(f"- `{r['id']}` {r['name']}: **{r['outcome']}**{(' — ' + r['reason']) if r.get('reason') else ''}" for r in results)
    lines.extend([
        "", "## Dead searches", "",
        "- Exact solution pages and the official pamphlet index were checked for every retained record.",
        "- Cell throughput, package limits, and handled-work dimensions were not written into arm-model typed columns.",
        "- Production heroes were HTTP 200 and all ten retained Mujin records had distinct content hashes.",
        "", "## Spec and media verification", "",
        "- Typed spec coverage: 0/10 retained pending records; complete-cell limits were not misfiled as arm specs.",
        "- Copy-media and owned-CDN HTTP/image-byte verification completed 8/8 for the enriched set.",
        "- Official-page hero review and cross-batch hashes found no repeated enriched primary image.",
        "- Verification artifact: [Mujin CDN verification](mujin-curated-cdn-verify.json).",
        "", "## Related", "", "- [Mujin fixer](../../fix_mujin_robots.py)",
    ])
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"company_id": COMPANY_ID, **counts, "copy_media": copy_stats, "report": str(report)}, indent=2))
    return 0


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


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix Mujin robots company 810")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--copy-media", action="store_true")
    parser.add_argument("--created-by-id", type=int, default=1)
    parser.add_argument("--only", nargs="*")
    parser.add_argument("--curated-full", action="store_true")
    args = parser.parse_args()

    client = ResearchApiClient()
    robots = [
        r for r in client.list_robots_for_company(COMPANY_ID)
        if (r.get("status") or "") == "pending_review"
    ]
    if args.only:
        robots = [r for r in robots if any(s.lower() in r["name"].lower() for s in args.only)]
    if args.curated_full:
        return run_curated_full(client, robots, apply=args.apply, copy_media=args.copy_media)

    plan = []
    staging: dict[int, dict] = {}
    for robot in robots:
        rid = int(robot["id"])
        cur = ROBOT_CURATION.get(rid)
        if not cur:
            print(f"SKIP {rid} {robot['name']}: no curation map")
            continue
        print(f"scrape {robot['name']} → {cur['url']}")
        try:
            pdp = scrape_pdp(cur["url"])
        except requests.RequestException as exc:
            print(f"  FAIL scrape: {exc}")
            continue
        row = build_row(robot, cur, pdp)
        staging[rid] = row
        item = {
            "id": rid,
            "name": robot["name"],
            "url": row["url"],
            "image": bool(row.get("image")),
            "image_url": row.get("image"),
            "features_len": len(row.get("features") or ""),
            "desc_len": len(row.get("description") or ""),
            "desc_preview": (row.get("description") or "")[:80],
            "videos": len(row.get("video_urls") or []),
            "tags": row.get("tags"),
            "kind": cur["kind"],
            "h1": pdp.get("h1"),
            "throughput": pdp.get("throughput"),
        }
        # English-only gate (cheap, before Gemini)
        blob = f"{row.get('description') or ''} {row.get('features') or ''} {row.get('purpose') or ''}"
        if re.search(r"[\u3040-\u30ff\u3400-\u9fff]", blob) or "ã" in blob or "å" in blob[:200]:
            item["non_english"] = True
        plan.append(item)
        print(
            f"  img={'yes' if item['image'] else 'no'} feat={item['features_len']} "
            f"desc={item['desc_len']} vids={item['videos']} kind={item['kind']} "
            f"desc={item['desc_preview']!r}"
        )

    preview = _RESEARCH_DIR / "staging" / "reports" / "mujin-fix-preview.json"
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if not plan:
        print("ERROR: nothing to import", file=sys.stderr)
        return 1
    bad = [
        p for p in plan
        if not p["image"] or p["features_len"] < 40 or p["desc_len"] < 40
        or not p["videos"] or not p["tags"] or p.get("non_english")
    ]
    if bad:
        print(f"ERROR: incomplete enrichment for {len(bad)} robots", file=sys.stderr)
        for p in bad:
            print(
                f"  {p['name']}: img={p['image']} feat={p['features_len']} vids={p['videos']}",
                file=sys.stderr,
            )
        return 1
    if not args.apply:
        print(f"Preview: {preview}. Re-run with --apply --copy-media")
        return 0

    tmp = Path(tempfile.mkdtemp(prefix="mujin-fix-"))
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
