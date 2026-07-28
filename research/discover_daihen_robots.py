#!/usr/bin/env python3
"""DAIHEN Corporation (1402) discover + enrich.

OEM hubs:
  https://www.daihen-robot.com/en/          (JP global robotic site — PDPs + heroes)
  https://www.daihen-usa.com/               (OTC DAIHEN USA — clear payload/reach cites)
  https://www.daihen.co.jp/en/              (corporate; cleanroom transfer)

Actions:
  - Patch company website + country_id=JP
  - Enrich all pending FD-* from live EN item pages
  - Create missing live catalog: FD-V25, FD-V25L, FD-VC4
  - Reject Almega AX-* (RoboDK/dealer URLs; off live FD catalog)
  - Enrich Flat Panel Transfer from daihen.co.jp cleanrobot page

Usage:
  python discover_daihen_robots.py
  python discover_daihen_robots.py --apply --copy-media
"""
from __future__ import annotations

import argparse
import hashlib
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
sys.path.insert(0, str(_RESEARCH_DIR))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient
from import_staging import import_staging, resolve_created_by_id
from robot_auto_research import slugify_robot_name

COMPANY_ID = 1402
COMPANY_SLUG = "daihen-corporation"
COMPANY_NAME = "DAIHEN Corporation"
COMPANY_WEBSITE = "https://www.daihen-robot.com/en/"
JP_ID = 11
AVAILABLE = 11
DISCONTINUED = 4
REPORT = _RESEARCH_DIR / "staging" / "reports" / "daihen-discover.json"
QA_DIR = _RESEARCH_DIR / "staging" / "reports" / "daihen_qa"
UA = {"User-Agent": "Mozilla/5.0 (compatible; RobotAIGeekResearch/1.0)"}
BASE = "https://www.daihen-robot.com"

TAGS = "Industrial|Manufacturing|Welding|6-Axis|Industrial Arm|Industrial Robot|Factory Automation|Arc Welding"
TAGS_7 = "Industrial|Manufacturing|Welding|7-Axis|Industrial Arm|Industrial Robot|Factory Automation|Arc Welding"
TAGS_COBOT = "Cobot|Collaborative|Industrial|Manufacturing|Welding|Factory Automation|Arc Welding"
TAGS_CLEAN = "Industrial|Manufacturing|Cleanroom|Semiconductor|Factory Automation|Transfer"

# Curated from OTC DAIHEN USA 6-axis page + JP wrist-payload tables (2026-07-20).
# Family pages share one OEM hero by design (same as Epson series).
CURATED: dict[str, dict[str, Any]] = {
    "FD-H5": {
        "url": f"{BASE}/en/items/fd_h5",
        "payload_kg": 5.0,
        "reach_mm": 866.0,
        "weight_kg": 58.0,
        "dof": 6,
        "features": (
            "OTC DAIHEN FD-H5 compact 6-axis arm for restricted-space arc welding, "
            "cutting, and material handling (OEM daihen-robot.com + daihen-usa.com). "
            "USA cite: 5 kg payload, 866 mm reach. JP cite: wrist payload 5 kg, mass 58 kg. "
            "Supports MIG/MAG, CO2, TIG and plasma; floor/vertical/ceiling mount; "
            "mechanical shock sensor; seamless digital link to OTC welding power sources."
        ),
    },
    "FD-B6": {
        "url": f"{BASE}/en/items/fd_b6",
        "payload_kg": 6.0,
        "reach_mm": 1445.0,
        "weight_kg": 145.0,
        "dof": 6,
        "features": (
            "OTC DAIHEN FD-B6 hollow through-arm arc-welding robot for tight fixtures "
            "(OEM). USA cite: 6 kg payload, 1.445 m reach. JP cite: wrist payload 6 kg, "
            "mass 145 kg. Coaxial through-arm cable reduces interference and improves "
            "wire feed; built for Synchro-feed / Cold Tandem welding packages."
        ),
    },
    "FD-B6L": {
        "url": f"{BASE}/en/items/fd_b6l",
        "payload_kg": 6.0,
        "reach_mm": 2008.0,
        "dof": 6,
        "features": (
            "OTC DAIHEN FD-B6L Series II long-reach hollow-wrist arc-welding robot (OEM). "
            "USA cite: 6 kg payload, 2.008 m reach. Series II improvements: up to 15% "
            "faster base axes, ~13% lighter, slimmer arm, denser multi-robot layouts, "
            "improved wet/dust durability and repeatability."
        ),
    },
    "FD-V8": {
        "url": f"{BASE}/en/items/fd_v8",
        "payload_kg": 8.0,
        "reach_mm": 1437.0,
        "weight_kg": 140.0,
        "dof": 6,
        "features": (
            "OTC DAIHEN FD-V8 6-axis conventional-wrist robot for arc/TIG welding, air "
            "plasma cutting, and handling (OEM). USA cite: 8 kg payload, 1.437 m reach. "
            "JP cite: wrist payload 8 kg, mass ~140 kg, maximum reach 1437 mm. Built-in "
            "cables/air for sensors and AI tools; IP54 wrist; Cold Tandem capable."
        ),
    },
    "FD-V8L": {
        "url": f"{BASE}/en/items/fd_v8l",
        "payload_kg": 8.0,
        "reach_mm": 2006.0,
        "dof": 6,
        "features": (
            "OTC DAIHEN FD-V8L Series II long-reach 6-axis welding/handling robot (OEM). "
            "USA cite: 8 kg payload, 2.006 m reach. Series II: up to 28% faster base "
            "axes, lighter arm, denser cell layouts, improved environmental durability."
        ),
    },
    "FD-V25": {
        "url": f"{BASE}/en/items/fd_v25",
        "payload_kg": 25.0,
        "reach_mm": 1710.0,
        "dof": 6,
        "create": True,
        "features": (
            "OTC DAIHEN FD-V25 Series II mid-payload 6-axis robot for welding, cutting, "
            "and material handling (OEM). USA cite: 25 kg payload, 1.71 m reach. Series "
            "II: up to 42% faster axes, lighter/slimmer arm, denser multi-robot installs."
        ),
    },
    "FD-V25L": {
        "url": f"{BASE}/en/items/fd_v25l",
        "payload_kg": 25.0,
        "dof": 6,
        "create": True,
        "features": (
            "OTC DAIHEN FD-V25L long-reach mid-payload 6-axis robot (OEM daihen-robot.com). "
            "Live JP item page for extended-reach welding/handling with ~25 kg wrist class."
        ),
    },
    "FD-V80": {
        "url": f"{BASE}/en/items/fd_v80_v100_v130",
        "payload_kg": 80.0,
        "reach_mm": 2500.0,
        "weight_kg": 780.0,
        "dof": 6,
        "family_hero": True,
        "features": (
            "OTC DAIHEN FD-V80 high-payload 6-axis handling/welding robot (OEM family page "
            "with V100/V130). USA cite: 80 kg payload, 2.5 m reach. JP family table: "
            "wrist payload 80 kg, mass ~780 kg. Through-arm utilities for EOAT."
        ),
    },
    "FD-V100": {
        "url": f"{BASE}/en/items/fd_v80_v100_v130",
        "payload_kg": 100.0,
        "reach_mm": 2236.0,
        "weight_kg": 770.0,
        "dof": 6,
        "family_hero": True,
        "features": (
            "OTC DAIHEN FD-V100 high-payload 6-axis robot (OEM family page with V80/V130). "
            "USA cite: 100 kg payload, 2.236 m reach. JP family table: wrist payload 100 kg, "
            "mass ~770 kg. Built-in application cabling for finishing and load/unload."
        ),
    },
    "FD-V130": {
        "url": f"{BASE}/en/items/fd_v80_v100_v130",
        "payload_kg": 130.0,
        "reach_mm": 2139.0,
        "weight_kg": 765.0,
        "dof": 6,
        "family_hero": True,
        "features": (
            "OTC DAIHEN FD-V130 high-payload 6-axis robot (OEM family page with V80/V100). "
            "USA cite: 130 kg payload, 2.139 m reach. JP family table: wrist payload 130 kg, "
            "mass ~765 kg."
        ),
    },
    "FD-B26": {
        "url": f"{BASE}/en/items/fd_b26",
        "payload_kg": 26.0,
        "dof": 6,
        "features": (
            "OTC DAIHEN FD-B26 hollow through-arm mid-payload welding/handling robot (OEM "
            "daihen-robot.com/en/items/fd_b26). Built for denser cells with integrated "
            "cable routing and OTC welding packages."
        ),
    },
    "FD-B100": {
        "url": f"{BASE}/en/items/fd_b100",
        "payload_kg": 100.0,
        "dof": 6,
        "features": (
            "OTC DAIHEN FD-B100 hollow-wrist high-payload industrial robot (OEM "
            "daihen-robot.com/en/items/fd_b100) for heavy handling and welding cells."
        ),
    },
    "FD-BT6": {
        "url": f"{BASE}/en/items/fd_bt6",
        "payload_kg": 6.0,
        "dof": 7,
        "features": (
            "OTC DAIHEN FD-BT6 7-axis through-arm welding/handling robot (OEM). Extra axis "
            "for reaching around fixtures without positioners; integrated cable routing."
        ),
    },
    "FD-BT6L": {
        "url": f"{BASE}/en/items/fd_bt6l",
        "payload_kg": 6.0,
        "dof": 7,
        "features": (
            "OTC DAIHEN FD-BT6L long-reach 7-axis through-arm welding robot (OEM "
            "daihen-robot.com/en/items/fd_bt6l) for larger or multi-zone weld cells."
        ),
    },
    "FD-VT8L": {
        "url": f"{BASE}/en/items/fd_vt8l",
        "payload_kg": 8.0,
        "dof": 6,
        "features": (
            "OTC DAIHEN FD-VT8L long-reach industrial robot (OEM daihen-robot.com/en/items/"
            "fd_vt8l) for welding and material-handling applications needing extended reach."
        ),
    },
    "FD-V166": {
        "url": f"{BASE}/en/items/fd_v166",
        "payload_kg": 166.0,
        "dof": 6,
        "features": (
            "OTC DAIHEN FD-V166 high-payload industrial robot (OEM daihen-robot.com/en/items/"
            "fd_v166) for heavy material handling and related factory automation."
        ),
    },
    "FD-V210": {
        "url": f"{BASE}/en/items/fd_v210",
        "payload_kg": 210.0,
        "dof": 6,
        "features": (
            "OTC DAIHEN FD-V210 high-payload industrial robot (OEM daihen-robot.com/en/items/"
            "fd_v210) for heavy handling in manufacturing cells."
        ),
    },
    "FD-A20": {
        "url": f"{BASE}/en/items/fd_a20",
        "payload_kg": 20.0,
        "dof": 6,
        "features": (
            "OTC DAIHEN FD-A20 laser welding/cutting robot (OEM daihen-robot.com/en/items/"
            "fd_a20). High-accuracy arm for CAD-driven laser processes with ~20 kg class "
            "wrist payload."
        ),
    },
    "FD-V350": {
        "url": f"{BASE}/en/items/fd_v280l_v350_v400l_v600_v700",
        "payload_kg": 350.0,
        "dof": 6,
        "family_hero": True,
        "features": (
            "OTC DAIHEN FD-V350 heavy-payload industrial robot (OEM family page with "
            "V280L/V400L/V600/V700). High-capacity handling for large-component factories."
        ),
    },
    "FD-V400L": {
        "url": f"{BASE}/en/items/fd_v280l_v350_v400l_v600_v700",
        "payload_kg": 400.0,
        "dof": 6,
        "family_hero": True,
        "features": (
            "OTC DAIHEN FD-V400L long-reach heavy-payload industrial robot (OEM family page). "
            "Extended envelope for oversized workpiece handling."
        ),
    },
    "FD-V600": {
        "url": f"{BASE}/en/items/fd_v280l_v350_v400l_v600_v700",
        "payload_kg": 600.0,
        "dof": 6,
        "family_hero": True,
        "features": (
            "OTC DAIHEN FD-V600 heavy-payload industrial robot (OEM family page with "
            "V280L/V350/V400L/V700) for ultra-heavy material handling."
        ),
    },
    "FD-V700": {
        "url": f"{BASE}/en/items/fd_v280l_v350_v400l_v600_v700",
        "payload_kg": 700.0,
        "dof": 6,
        "family_hero": True,
        "features": (
            "OTC DAIHEN FD-V700 heavy-payload industrial robot (OEM family page) — top of "
            "the V280L/V350/V400L/V600/V700 handling series."
        ),
    },
    "FD-VC4": {
        "url": f"{BASE}/en/items/fd_vc4",
        "payload_kg": 4.0,
        "dof": 6,
        "create": True,
        "cobot": True,
        "features": (
            "OTC DAIHEN FD-VC4 collaborative welding cobot (OEM daihen-robot.com/en/items/"
            "fd_vc4). Purpose-built for OTC welding processes and sensors with collaborative "
            "operation for flexible cells."
        ),
    },
    "Flat Panel Transfer Robot": {
        "url": "https://www.daihen.co.jp/en/products/cleanrobot/index04.html",
        "dof": 6,
        "clean": True,
        "features": (
            "DAIHEN cleanroom flat-panel transfer robot for FPD/semiconductor handling "
            "(OEM daihen.co.jp cleanrobot). Designed for contamination-controlled substrate "
            "transfer in display and electronics manufacturing."
        ),
    },
}

REJECT_ALMEGA = {
    4171: "DAIHEN Almega AX-V8",
    1902: "DAIHEN Almega AX-V6",
    1901: "DAIHEN Almega AX-V4",
}
REJECT_REASON = (
    "off-catalog / legacy Almega AX series: no live PDP on daihen-robot.com FD catalog; "
    "source URLs are RoboDK or dealer pages, not OEM. Prefer current FD-series SKUs."
)

_PAGE_CACHE: dict[str, dict[str, Any]] = {}


def fetch(url: str) -> tuple[int, str, str]:
    r = requests.get(url, headers=UA, timeout=45, allow_redirects=True)
    return r.status_code, r.url, r.text


def scrape_pdp(url: str) -> dict[str, Any]:
    if url in _PAGE_CACHE:
        return _PAGE_CACHE[url]
    status, final, html = fetch(url)
    base = f"{urlparse(final).scheme}://{urlparse(final).netloc}"
    imgs: list[str] = []
    for m in re.findall(
        r'(?:src|data-src)=["\']([^"\']+\.(?:png|jpe?g|webp)[^"\']*)["\']',
        html,
        re.I,
    ):
        u = urljoin(final, m).split("?")[0]
        low = u.lower()
        if any(
            x in low
            for x in (
                "logo", "icon", "favicon", "ogp.png", "btn_", "play.png",
                "youtube", "ytimg", "banner", "flag",
            )
        ):
            continue
        imgs.append(u)
    imgs = list(dict.fromkeys(imgs))
    # Prefer mv_ model heroes
    ranked = sorted(
        imgs,
        key=lambda u: (
            0 if "/mv_" in u.lower() else 1,
            0 if re.search(r"fd[-_]", u, re.I) else 1,
            0 if u.lower().endswith(".jpg") else 1,
            len(u),
        ),
    )
    text = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "\n", text)
    lines = [ln.strip() for ln in unescape(text).splitlines() if ln.strip()]
    paras = [ln for ln in lines if 80 <= len(ln) <= 500 and "cookie" not in ln.lower()]
    h1_m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.I | re.S)
    h1 = re.sub(r"<[^>]+>", "", h1_m.group(1)).strip() if h1_m else ""
    info = {
        "status": status,
        "final_url": final,
        "h1": h1,
        "images": ranked[:6],
        "hero": ranked[0] if ranked else "",
        "paras": paras[:8],
        "lines": lines[:150],
        "html_len": len(html),
    }
    _PAGE_CACHE[url] = info
    return info


def download_ok(url: str) -> tuple[bool, str, int, bytes]:
    try:
        r = requests.get(url, headers={**UA, "Referer": BASE + "/"}, timeout=60)
    except Exception:
        return False, "", 0, b""
    if r.status_code != 200 or len(r.content) < 3000:
        return False, "", 0, b""
    if r.content[:1] == b"<":
        return False, "", 0, b""
    ok_magic = (
        r.content[:3] == b"\xff\xd8\xff"
        or r.content[:8] == b"\x89PNG\r\n\x1a\n"
        or r.content[:4] == b"RIFF"
    )
    if not ok_magic and len(r.content) < 8000:
        return False, "", 0, b""
    return True, hashlib.md5(r.content).hexdigest(), len(r.content), r.content


def model_key(name: str) -> str:
    n = re.sub(r"^DAIHEN\s+", "", name.strip(), flags=re.I)
    return n


def build_description(name: str, spec: dict[str, Any], pdp: dict[str, Any]) -> str:
    bits = []
    if spec.get("payload_kg") is not None:
        bits.append(f"{spec['payload_kg']:g} kg payload")
    if spec.get("reach_mm") is not None:
        bits.append(f"{spec['reach_mm']:g} mm reach")
    if spec.get("dof") is not None:
        bits.append(f"{int(spec['dof'])}-axis")
    spec_txt = (", ".join(bits) + ". ") if bits else ""
    for p in pdp.get("paras") or []:
        if name.split("-")[0] in p or "DAIHEN" in p.upper() or "welding" in p.lower():
            if len(p) >= 100 and "Introducing Daihen" not in p:
                return p[:1200]
    kind = "collaborative welding cobot" if spec.get("cobot") else (
        "cleanroom transfer robot" if spec.get("clean") else "industrial welding/handling robot"
    )
    return (
        f"The OTC DAIHEN {name} is a {kind} from DAIHEN Corporation. {spec_txt}"
        f"It is listed on the manufacturer's English robotic product site for industrial "
        f"automation and welding applications."
    )[:1200]


def reject_robot(client: ResearchApiClient, rid: int, reason: str) -> str:
    sid = os.environ.get("ADMIN_SESSION_ID", "").strip()
    api = os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/").replace("/api/v1", "")
    if not api:
        api = os.environ.get("RESEARCH_API_BASE_URL", "").rstrip("/").replace("/api/v1", "")
    if sid and api:
        try:
            resp = requests.post(
                f"{api}/admin/robots/robot/content-queue/api/robot/{rid}/reject/",
                headers={"Cookie": f"sessionid={sid}", "Content-Type": "application/json"},
                json={"type": "robot", "reason": reason},
                timeout=120,
            )
            if resp.ok:
                return "admin-rejected"
        except requests.RequestException:
            pass
    try:
        client._patch(
            f"robots/robots/{rid}/",
            {
                "status": "rejected",
                "rejection_reason": reason[:500],
                "notes": f"[REJECTED 2026-07-20] {reason}"[:2000],
            },
        )
        return "patched-rejected"
    except Exception as e:  # noqa: BLE001
        return f"fail:{e}"


def trigger_copy_media(robot_id: int) -> str:
    api = os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/")
    key = os.environ.get("INTERNAL_API_SECRET") or os.environ.get("RESEARCH_API_KEY") or ""
    if not api:
        return "skip:no_api"
    url = f"{api}/robots/robots/{robot_id}/copy-media/"
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Api-Key {key}"
        headers["X-Internal-Api-Secret"] = key
    try:
        resp = requests.post(url, headers=headers, json={}, timeout=180)
        return f"http_{resp.status_code}"
    except Exception as e:  # noqa: BLE001
        return f"fail:{e}"


def row_for(name: str, spec: dict[str, Any], pdp: dict[str, Any], hero: str) -> dict[str, Any]:
    desc = build_description(name, spec, pdp)
    tags = TAGS_COBOT if spec.get("cobot") else (
        TAGS_CLEAN if spec.get("clean") else (TAGS_7 if spec.get("dof") == 7 else TAGS)
    )
    images = [hero] if hero else list(pdp.get("images") or [])[:3]
    if hero and hero not in images:
        images = [hero, *[u for u in (pdp.get("images") or []) if u != hero]][:4]
    row: dict[str, Any] = {
        "name": name,
        "model_name": name,
        "company_slug": COMPANY_SLUG,
        "company_name": COMPANY_NAME,
        "manufacturer_country_code": "JP",
        "description": desc,
        "purpose": desc,
        "features": spec["features"],
        "url": spec["url"],
        "image": hero or "",
        "images": images,
        "availability_status": AVAILABLE,
        "movement_type_keys": "stationary",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "manufacturing-industrial",
        "use_keys": "welding|material-handling|assembly" if not spec.get("clean") else "material-handling|other",
        "industry_keys": "manufacturing|automotive",
        "tags": tags,
        "dof": spec.get("dof"),
        "sources": [
            {"url": spec["url"], "type": "website", "title": name},
            {"url": "https://www.daihen-usa.com/6-axis-robots/", "type": "website", "title": "OTC DAIHEN USA 6-axis"},
        ],
        "research_notes": f"DAIHEN content-queue enrich from {spec['url']}.",
        "source_locale": "en",
    }
    for k in ("payload_kg", "reach_mm", "weight_kg", "repeatability_mm"):
        if spec.get(k) is not None:
            row[k] = spec[k]
    if spec.get("family_hero"):
        row["notes"] = (
            "Family shared OEM hero intentional — model lives on multi-SKU JP item page."
        )
    return row


def patch_fields(client: ResearchApiClient, rid: int, row: dict[str, Any]) -> None:
    body: dict[str, Any] = {
        "name": row["name"],
        "model_name": row.get("model_name"),
        "manufacturer_countries": [JP_ID],
        "manufacturer_country_ref": JP_ID,
        "availability_status": row.get("availability_status") or AVAILABLE,
        "description": row.get("description"),
        "purpose": row.get("purpose"),
        "features": row.get("features"),
        "url": row.get("url"),
        "source_locale": "en",
        "notes": row.get("notes") or "",
    }
    for k in ("payload_kg", "reach_mm", "weight_kg", "dof", "repeatability_mm"):
        if row.get(k) is not None:
            body[k] = row[k]
    client._patch(f"robots/robots/{rid}/", body)


def import_row(row: dict[str, Any], *, created_by_id: int, patch: bool, rid: int | None = None) -> dict[str, Any]:
    tmp = Path(tempfile.mkdtemp(prefix="daihen-"))
    fpath = tmp / f"{slugify_robot_name(row['name'])}.json"
    payload = dict(row)
    if rid is not None:
        payload["id"] = rid
    fpath.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return import_staging(
        fpath,
        patch=patch,
        force_overwrite=True,
        status="pending_review",
        dry_run=False,
        created_by_id=resolve_created_by_id(created_by_id),
        replace_media=bool(row.get("image")),
        batch_size=1,
        skip_company_update=True,
    )


def refine_v25l_reach(pdp: dict[str, Any]) -> float | None:
    blob = "\n".join(pdp.get("lines") or [])
    m = re.search(r"(?:Maximum\s+reach|Reach)[:：\s]*(\d[\d,]*(?:\.\d+)?)\s*mm", blob, re.I)
    if m:
        return float(m.group(1).replace(",", ""))
    m = re.search(r"(\d(?:\.\d)?)\s*m\s*reach", blob, re.I)
    if m:
        return float(m.group(1)) * 1000.0
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--copy-media", action="store_true")
    ap.add_argument("--created-by-id", type=int, default=1)
    args = ap.parse_args()

    client = ResearchApiClient()
    robots = {
        int(r["id"]): r
        for r in client.list_robots_for_company(COMPANY_ID)
        if (r.get("status") or "") == "pending_review"
    }
    by_model: dict[str, dict] = {}
    for r in robots.values():
        by_model[model_key(r["name"])] = r

    plan: list[dict[str, Any]] = []
    hero_hashes: dict[str, str] = {}

    # Company patch
    plan.append(
        {
            "action": "company_patch",
            "website": COMPANY_WEBSITE,
            "country_id": JP_ID,
        }
    )

    # Reject Almega
    for rid, nm in REJECT_ALMEGA.items():
        if rid in robots:
            plan.append({"action": "reject", "id": rid, "name": nm, "reason": REJECT_REASON})

    # Enrich / create curated
    for model, spec in CURATED.items():
        existing = by_model.get(model)
        pdp = scrape_pdp(spec["url"])
        if pdp.get("status") != 200:
            plan.append({"action": "skip", "name": model, "reason": f"pdp_{pdp.get('status')}"})
            continue
        if model == "FD-V25L":
            reach = refine_v25l_reach(pdp)
            if reach:
                spec = {**spec, "reach_mm": reach}

        hero = ""
        hero_md5 = ""
        for cand in pdp.get("images") or []:
            ok, md5, nbytes, content = download_ok(cand)
            if not ok:
                continue
            # Avoid tiny thumbs (_s.jpg)
            if cand.lower().endswith("_s.jpg") or nbytes < 12000:
                continue
            if md5 in hero_hashes.values() and not spec.get("family_hero"):
                # allow family share
                continue
            hero = cand
            hero_md5 = md5
            QA_DIR.mkdir(parents=True, exist_ok=True)
            ext = ".jpg" if cand.lower().endswith(".jpg") else ".png"
            (QA_DIR / f"{slugify_robot_name(model)}{ext}").write_bytes(content)
            break
        if not hero and (pdp.get("images") or []):
            # fallback first non-thumb
            for cand in pdp["images"]:
                if cand.lower().endswith("_s.jpg"):
                    continue
                ok, md5, nbytes, content = download_ok(cand)
                if ok:
                    hero = cand
                    hero_md5 = md5
                    QA_DIR.mkdir(parents=True, exist_ok=True)
                    (QA_DIR / f"{slugify_robot_name(model)}.jpg").write_bytes(content)
                    break

        if hero_md5:
            hero_hashes[model] = hero_md5

        row = row_for(model, spec, pdp, hero)
        entry = {
            "action": "enrich" if existing else ("create" if spec.get("create") else "skip"),
            "id": existing["id"] if existing else None,
            "name": model,
            "url": spec["url"],
            "hero": hero,
            "hero_md5": hero_md5[:12] if hero_md5 else "",
            "hero_bytes": None,
            "payload_kg": spec.get("payload_kg"),
            "reach_mm": spec.get("reach_mm"),
            "row": row,
        }
        if entry["action"] == "skip" and not existing:
            entry["reason"] = "not_in_db_and_not_create"
        plan.append(entry)
        print(
            f"{entry['action']:7} {model:28} hero={'Y' if hero else 'N'} "
            f"payload={spec.get('payload_kg')} reach={spec.get('reach_mm')}"
        )

    report = {"company_id": COMPANY_ID, "plan": [
        {k: v for k, v in e.items() if k != "row"} for e in plan
    ]}

    if args.apply:
        # company
        for path in (
            f"companies/{COMPANY_ID}/",
            f"companies/companies/{COMPANY_ID}/",
        ):
            try:
                client._patch(
                    path,
                    {"website": COMPANY_WEBSITE, "country_id": JP_ID},
                )
                print("company patched via", path)
                break
            except Exception as e:  # noqa: BLE001
                print("company patch fail", path, e)

        applied = []
        for e in plan:
            if e["action"] == "reject":
                st = reject_robot(client, int(e["id"]), e["reason"])
                print(f"REJECT {e['id']} {e['name']}: {st}")
                applied.append({"id": e["id"], "action": "reject", "status": st})
                continue
            if e["action"] not in ("enrich", "create"):
                continue
            row = e["row"]
            try:
                if e["action"] == "enrich":
                    # import with replace_media then patch typed fields
                    res = import_row(row, created_by_id=args.created_by_id, patch=True, rid=int(e["id"]))
                    patch_fields(client, int(e["id"]), row)
                    rid = int(e["id"])
                else:
                    res = import_row(row, created_by_id=args.created_by_id, patch=False)
                    # resolve created id
                    rid = None
                    created = (res or {}).get("created") or (res or {}).get("results") or []
                    if isinstance(created, list) and created:
                        rid = created[0].get("id") if isinstance(created[0], dict) else created[0]
                    if not rid:
                        # refetch by name
                        time.sleep(0.5)
                        for r in client.list_robots_for_company(COMPANY_ID):
                            if model_key(r.get("name") or "") == e["name"]:
                                rid = int(r["id"])
                                break
                    if rid:
                        patch_fields(client, rid, row)
                print(f"APPLY {e['action']} {e['name']} id={rid}")
                if args.copy_media and rid and row.get("image"):
                    cm = trigger_copy_media(int(rid))
                    print(f"  copy-media {cm}")
                applied.append({"name": e["name"], "id": rid, "action": e["action"]})
            except Exception as exc:  # noqa: BLE001
                print(f"APPLY FAIL {e['name']}: {exc}")
                applied.append({"name": e["name"], "error": str(exc)})
            time.sleep(0.25)

        # recount
        pending = [
            r for r in client.list_robots_for_company(COMPANY_ID)
            if (r.get("status") or "") == "pending_review"
        ]
        no_img = sum(1 for r in pending if not ((r.get("image") or "").strip() or r.get("s3_image")))
        no_feat = sum(1 for r in pending if len((r.get("features") or "").strip()) < 40)
        report["applied"] = applied
        report["final"] = {"pending": len(pending), "no_image": no_img, "no_features": no_feat}
        print("FINAL", report["final"])

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
