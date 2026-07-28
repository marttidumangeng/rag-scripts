"""Fix remaining Hyundai Robotics (company 49) held pending robots.

Rejects alias + industry/7 package shells; remaps FPD → HC3303B Series;
splits HDC25/HDC35 heroes; refreshes LABOT + Robot Barista signed notice heroes.

Usage:
  python fix_hyundai_held_robots.py
  python fix_hyundai_held_robots.py --apply --copy-media
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

import requests

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient
from import_staging import import_staging, resolve_created_by_id

# Skip youtube_metadata.enrich_video_list — oEmbed can hang for minutes on this host.
# Curated watch URLs below were previously validated for this OEM.

COMPANY_ID = 49
COMPANY_SLUG = "hyundai-robotics"
COMPANY_NAME = "Hyundai Robotics"
SITE = "https://hd-hyundairobotics.com"
WWW = "https://www.hd-hyundairobotics.com"
API = f"{WWW}/api/v1"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": f"{SITE}/en/biz/product/60010002",
}

FIX_IDS = (3709, 3710, 3711, 3729, 3730)
REJECTS: dict[int, str] = {
    3719: (
        "duplicate: OEM alias of published HDR50-22 (3717); "
        "same product page/specs/media"
    ),
    3722: (
        "non_robot_workflow: industry/7 application label without dedicated "
        "OEM package PDP or package-specific hero; fail-closed "
        "(do not use sibling arm renders)"
    ),
    3723: (
        "non_robot_workflow: industry/7 application label without dedicated "
        "OEM package PDP or package-specific hero; fail-closed "
        "(do not use sibling arm renders)"
    ),
    3724: (
        "non_robot_workflow: industry/7 application label without dedicated "
        "OEM package PDP or package-specific hero; fail-closed "
        "(do not use sibling arm renders)"
    ),
    3725: (
        "non_robot_workflow: industry/7 application label without dedicated "
        "OEM package PDP or package-specific hero; fail-closed "
        "(do not use sibling arm renders)"
    ),
    3726: (
        "non_robot_workflow: industry/7 application label without dedicated "
        "OEM package PDP or package-specific hero; fail-closed "
        "(do not use sibling arm renders)"
    ),
}

HDC25_HERO = f"{SITE}/resources/resource/images/thumb/thumb_prod_hdc_01.png"
HDC35_HERO = f"{SITE}/resources/resource/images/thumb/thumb_hdc_applied_01.png"

TAGS_COBOT = (
    "Cobot|Collaborative|6-Axis|Industrial|Factory Automation|Manufacturing|"
    "Industrial Arm|Industrial Robot|Assembly|Pick-and-Place"
)
TAGS_FPD = "Industrial|Factory Automation|Manufacturing|Industrial Robot|Display"
TAGS_APP = (
    "Industrial|Factory Automation|Manufacturing|Industrial Robot|"
    "Machine Tending|Assembly"
)

NOTE_STAMP = "[HELD FIX 2026-07-22]"


def unwrap(payload: dict) -> dict:
    if isinstance(payload, dict) and "resCd" in payload and "data" in payload:
        return payload.get("data") or {}
    return payload


def session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def short_file_url(file_seq: int | None, signed: str) -> str:
    """Prefer short OEM file view URL when signed S3 URL exceeds Robot.image varchar(500)."""
    if file_seq and len(signed or "") > 480:
        return f"{WWW}/api/v1/file/ck/view/{int(file_seq)}"
    return signed


def fetch_product(s: requests.Session, match: str) -> dict[str, Any]:
    """Return fresh product API row matching prdNm / alias (signed hero)."""
    for page in range(1, 30):
        r = s.get(
            f"{API}/product/page",
            params={"prdStateCd": "00010001", "page": page, "size": 10},
            timeout=60,
        )
        r.raise_for_status()
        data = unwrap(r.json())
        for item in data.get("content") or []:
            nm = (item.get("prdNm") or "").replace("\r", "").strip()
            aliases = {nm, nm.split("(")[0].strip()}
            m = re.search(r"\(([^)]+)\)", nm)
            if m:
                aliases.add(m.group(1).strip())
            if match not in aliases and match.lower() not in nm.lower():
                continue
            bd = item.get("bdContent") or {}
            atts = bd.get("attachments") or []
            att = atts[0] if atts else bd.get("bdcThumbFile1")
            if not isinstance(att, dict) or not att.get("fileDwLink"):
                raise RuntimeError(f"No signed hero for product {nm}")
            return {
                "prdSeq": item.get("prdSeq"),
                "prdNm": nm,
                "payload": item.get("prdBscSpec1"),
                "reach": str(item.get("prdBscSpec2") or "").replace(",", ""),
                "ctrl": item.get("prdBscSpec3"),
                "dof": item.get("prdDtlSpec2"),
                "repeat": item.get("prdDtlSpec20"),
                "mass_kg": item.get("prdDtlSpec22"),
                "fileSeq": att.get("fileSeq"),
                "fileOriNm": att.get("fileOriNm"),
                "fileDwLink": short_file_url(att.get("fileSeq"), att.get("fileDwLink") or ""),
            }
        if data.get("last") or not (data.get("content") or []):
            break
    raise RuntimeError(f"Product not found in OEM API: {match}")


def fetch_solution_hero(
    s: requests.Session, rbs_seq: int, *, notice_substr: str, ori_hint: str = ""
) -> dict[str, Any]:
    """Fresh signed notice thumb from robot-solution/page."""
    for page in range(1, 10):
        r = s.get(
            f"{API}/robot-solution/page",
            params={"page": page, "size": 10},
            timeout=60,
            headers={**HEADERS, "Referer": f"{SITE}/en/application/robot-solution/{rbs_seq}"},
        )
        r.raise_for_status()
        data = unwrap(r.json())
        for item in data.get("content") or []:
            if int(item.get("rbsSeq") or 0) != rbs_seq:
                continue
            bd = item.get("bdContent") or {}
            thumb = bd.get("bdcThumbFile1") or {}
            link = (thumb or {}).get("fileDwLink") or ""
            ori = (thumb or {}).get("fileOriNm") or ""
            path = (thumb or {}).get("filePath") or ""
            file_seq = (thumb or {}).get("fileSeq")
            if notice_substr not in link and notice_substr not in path:
                raise RuntimeError(
                    f"Solution {rbs_seq} thumb missing notice {notice_substr}: "
                    f"path={path}"
                )
            hero = short_file_url(file_seq, link)
            return {
                "rbsSeq": rbs_seq,
                "rbsNmEn": item.get("rbsNmEn") or "",
                "fileOriNm": ori,
                "filePath": path,
                "fileSeq": file_seq,
                "fileDwLink": hero,
                "signedLink": link,
                "desc_en": re.sub(r"<[^>]+>", " ", item.get("rbsDescEn") or ""),
            }
        if data.get("last") or not (data.get("content") or []):
            break
    raise RuntimeError(f"robot-solution rbsSeq={rbs_seq} not found")


def verify_image_url(url: str) -> tuple[bool, int, str]:
    if not url:
        return False, 0, ""
    try:
        r = requests.get(url, headers={"User-Agent": HEADERS["User-Agent"]}, timeout=90)
        content = r.content or b""
        ok = r.status_code < 400 and len(content) > 2000
        magic_ok = content[:3] == b"\xff\xd8\xff" or content[:8] == b"\x89PNG\r\n\x1a\n"
        digest = hashlib.sha256(content).hexdigest() if content else ""
        return bool(ok and magic_ok), len(content), digest
    except requests.RequestException:
        return False, 0, ""


def _num(val: Any) -> float | None:
    if val is None:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)", str(val).replace(",", ""))
    return float(m.group(1)) if m else None


def build_rows(s: requests.Session) -> dict[int, dict[str, Any]]:
    hc = fetch_product(s, "HC3303B Series")
    if "HC3303B" not in hc["prdNm"] or "Series.png" not in (hc.get("fileOriNm") or ""):
        # fileOriNm is "HC3303B Series.png"
        if "HC3303B" not in (hc.get("fileOriNm") or "") and "HC3303B" not in hc["prdNm"]:
            raise RuntimeError(f"Unexpected FPD product: {hc}")
    ok, nbytes, digest = verify_image_url(hc["fileDwLink"])
    if not ok:
        raise RuntimeError(f"HC3303B hero failed verify bytes={nbytes}")
    print(f"  HC3303B hero ok bytes={nbytes} sha16={digest[:16]} ori={hc.get('fileOriNm')}")

    ok25, n25, h25 = verify_image_url(HDC25_HERO)
    ok35, n35, h35 = verify_image_url(HDC35_HERO)
    if not ok25 or not ok35:
        raise RuntimeError(f"HDC static heroes failed: 25={ok25}/{n25} 35={ok35}/{n35}")
    if h25 == h35:
        raise RuntimeError("HDC25 and HDC35 heroes have identical content hashes")
    print(f"  HDC25 sha16={h25[:16]} bytes={n25}")
    print(f"  HDC35 sha16={h35[:16]} bytes={n35} (distinct OK)")

    labot = fetch_solution_hero(
        s,
        28,
        notice_substr="e0ba0c6b65fc458fa5cf130c02584eda",
        ori_hint="_DSC1426",
    )
    ok_l, n_l, h_l = verify_image_url(labot["fileDwLink"])
    if not ok_l:
        raise RuntimeError(f"LABOT notice hero failed bytes={n_l}")
    print(f"  LABOT hero ok bytes={n_l} sha16={h_l[:16]} ori={labot.get('fileOriNm')}")

    barista = fetch_solution_hero(
        s,
        24,
        notice_substr="aa17ec26cd8f49d8b787caca2fd09322",
        ori_hint="",  # Hangul thumbnail name; notice hash is authoritative
    )
    ok_b, n_b, h_b = verify_image_url(barista["fileDwLink"])
    if not ok_b:
        raise RuntimeError(f"Barista notice hero failed bytes={n_b}")
    print(f"  Barista hero ok bytes={n_b} sha16={h_b[:16]} ori={barista.get('fileOriNm')}")

    vids_hdc = [
        "https://www.youtube.com/watch?v=G7UG4AB4zlU",
        "https://www.youtube.com/watch?v=LFMzwt-erac",
    ]
    vids_fpd = ["https://www.youtube.com/watch?v=QE1NDxx4a-Y"]
    vids_labot = ["https://www.youtube.com/watch?v=8DOHwqtPKlo"]
    vids_barista = ["https://www.youtube.com/watch?v=gVKnBVRJ1Hc"]

    fpd_url = f"{SITE}/en/biz/product/detail/43"
    fpd_family = f"{SITE}/en/biz/product/60010002"
    rows: dict[int, dict[str, Any]] = {
        3709: {
            "id": 3709,
            "name": "HC3303B Series",
            "company_slug": COMPANY_SLUG,
            "company_name": COMPANY_NAME,
            "manufacturer_country_code": "KR",
            "description": (
                "HC3303B Series is an HD Hyundai Robotics FPD (flat-panel display) "
                "substrate transfer robot for 11G / 10.5G display manufacturing lines."
            ),
            "purpose": "Flat-panel display substrate transfer and handling",
            "features": (
                "Official OEM FPD catalog product HC3303B Series (prdSeq=43). "
                "Cited generation coverage 11G / 10.5G; applicable controller Hi5a-C "
                f"per OEM product record. Hero is OEM file {hc.get('fileOriNm')}. "
                "CRM category label 'FPD Robot' remapped to this exact series."
            ),
            "url": fpd_url,
            "image": hc["fileDwLink"],
            "images": [hc["fileDwLink"]],
            "video_urls": vids_fpd,
            "movement_type_keys": "stationary",
            "category_slugs": "industrial-robots",
            "sub_category_slug": "manufacturing-industrial",
            "tags": TAGS_FPD,
            "sources": [
                {"url": fpd_url, "type": "website", "title": "HC3303B Series"},
                {"url": fpd_family, "type": "website", "title": "FPD Robot category"},
            ],
            "research_notes": (
                f"{NOTE_STAMP} Remapped FPD Robot → HC3303B Series; fresh signed S3 "
                f"hero from product API (fileOriNm={hc.get('fileOriNm')})."
            ),
            "notes": (
                f"{NOTE_STAMP} OEM FPD HC3303B Series; generation 11G/10.5G; "
                "controller Hi5a-C (catalog). HOLD cleared."
            ),
            "_patch": {
                "name": "HC3303B Series",
                "model_name": "HC3303B Series",
                "variant_code": "HC3303B",
                "variant_label": "HC3303B Series",
                "family_key": "hyundai-robotics:fpd-transfer",
                "family_name": "FPD Transfer",
                "family_url": fpd_family,
                "product_url_scope": "family",
                "purpose": "Flat-panel display substrate transfer and handling",
                "availability_status": 11,
                "information_source_urls": [fpd_url, fpd_family],
            },
            "_hero_sha": digest,
        },
        3710: {
            "id": 3710,
            "name": "HDC25-18",
            "company_slug": COMPANY_SLUG,
            "company_name": COMPANY_NAME,
            "manufacturer_country_code": "KR",
            "description": (
                "HDC25-18 is an HD Hyundai Robotics collaborative robot for high-speed "
                "collaborative automation with industrial-grade motion performance."
            ),
            "purpose": "Collaborative handling\nMachine tending\nPalletizing",
            "features": (
                "Official HDC Series page and OEM product record for HDC25-18. "
                "Cited maximum payload 25 kg and reach 1,880 mm; repeatability ±0.05 mm. "
                "6-axis articulated collaborative arm; applicable controller Hi7-N00-70. "
                "Hero uses stable OEM thumb_prod_hdc_01.png (distinct from HDC35 applied photo)."
            ),
            "url": f"{SITE}/en/biz/hdc",
            "image": HDC25_HERO,
            "images": [HDC25_HERO],
            "video_urls": vids_hdc,
            "movement_type_keys": "stationary",
            "category_slugs": "industrial-robots",
            "sub_category_slug": "manufacturing-industrial",
            "tags": TAGS_COBOT,
            "dof": 6,
            "weight_kg": 215.0,
            "sources": [{"url": f"{SITE}/en/biz/hdc", "type": "website", "title": "HDC25-18"}],
            "research_notes": (
                f"{NOTE_STAMP} HDC25-18 hero thumb_prod_hdc_01.png; cleared identical-byte HOLD."
            ),
            "notes": (
                f"{NOTE_STAMP} Payload 25 kg; reach 1,880 mm; repeatability ±0.05 mm; "
                "mass 215 kg; ctrl Hi7-N00-70. HOLD cleared."
            ),
            "_patch": {
                "model_name": "HDC25-18",
                "variant_code": "HDC25-18",
                "variant_label": "HDC25-18",
                "family_key": "hyundai-robotics:hdc",
                "family_name": "HDC",
                "family_url": f"{SITE}/en/biz/hdc",
                "product_url_scope": "exact_variant",
                "purpose": "Collaborative handling\nMachine tending\nPalletizing",
                "payload_kg": 25.0,
                "reach_mm": 1880.0,
                "repeatability_mm": 0.05,
                "weight_kg": 215.0,
                "dof": 6,
                "availability_status": 11,
                "information_source_urls": [f"{SITE}/en/biz/hdc"],
            },
            "_hero_sha": h25,
        },
        3711: {
            "id": 3711,
            "name": "HDC35-18",
            "company_slug": COMPANY_SLUG,
            "company_name": COMPANY_NAME,
            "manufacturer_country_code": "KR",
            "description": (
                "HDC35-18 is an HD Hyundai Robotics collaborative robot for diverse "
                "industrial automation with higher payload collaborative handling."
            ),
            "purpose": "Collaborative heavy-part handling\nMachine tending\nPalletizing",
            "features": (
                "Official HDC Series page and OEM product record for HDC35-18. "
                "Cited maximum payload 35 kg and reach 1,880 mm; repeatability ±0.05 mm. "
                "6-axis articulated collaborative arm; applicable controller Hi7-N00-70. "
                "Hero uses official HDC application photo thumb_hdc_applied_01.png "
                "(robot-dominant; content hash distinct from HDC25 prod_01). "
                "Do not use thumb_hdc_01.png (text-heavy) or thumb_prod_hdc_02.png "
                "(byte-identical to prod_01)."
            ),
            "url": f"{SITE}/en/biz/hdc",
            "image": HDC35_HERO,
            "images": [HDC35_HERO],
            "video_urls": vids_hdc,
            "movement_type_keys": "stationary",
            "category_slugs": "industrial-robots",
            "sub_category_slug": "manufacturing-industrial",
            "tags": TAGS_COBOT,
            "dof": 6,
            "weight_kg": 215.0,
            "sources": [{"url": f"{SITE}/en/biz/hdc", "type": "website", "title": "HDC35-18"}],
            "research_notes": (
                f"{NOTE_STAMP} HDC35-18 hero thumb_hdc_applied_01.png; "
                "asserted distinct SHA from HDC25."
            ),
            "notes": (
                f"{NOTE_STAMP} Payload 35 kg; reach 1,880 mm; repeatability ±0.05 mm; "
                "mass 215 kg; ctrl Hi7-N00-70. HOLD cleared."
            ),
            "_patch": {
                "model_name": "HDC35-18",
                "variant_code": "HDC35-18",
                "variant_label": "HDC35-18",
                "family_key": "hyundai-robotics:hdc",
                "family_name": "HDC",
                "family_url": f"{SITE}/en/biz/hdc",
                "product_url_scope": "exact_variant",
                "purpose": "Collaborative heavy-part handling\nMachine tending\nPalletizing",
                "payload_kg": 35.0,
                "reach_mm": 1880.0,
                "repeatability_mm": 0.05,
                "weight_kg": 215.0,
                "dof": 6,
                "availability_status": 11,
                "information_source_urls": [f"{SITE}/en/biz/hdc"],
            },
            "_hero_sha": h35,
        },
        3729: {
            "id": 3729,
            "name": "LABOT",
            "company_slug": COMPANY_SLUG,
            "company_name": COMPANY_NAME,
            "manufacturer_country_code": "KR",
            "description": (
                "LABOT is HD Hyundai Robotics' CNC machine-tending package solution "
                "developed with Young Chang Robotech, combining a turntable, software, "
                "and industrial robot for flexible production."
            ),
            "purpose": "CNC machine tending",
            "features": (
                "Official robot-solution application page (rbsSeq=28). "
                "LABOT is a CNC machine-tending package (turntable + Smart-EZ software + arm), "
                "not a unique arm SKU. Hero is the OEM notice image "
                f"{labot.get('fileOriNm')} (notice/e0ba0c6b65fc458fa5cf130c02584eda). "
                "Applicable products on the page include HH020-class arms."
            ),
            "url": f"{SITE}/en/application/robot-solution/28",
            "image": labot["fileDwLink"],
            "images": [labot["fileDwLink"]],
            "video_urls": vids_labot,
            "movement_type_keys": "stationary",
            "category_slugs": "industrial-robots",
            "sub_category_slug": "manufacturing-industrial",
            "tags": TAGS_APP,
            "sources": [
                {
                    "url": f"{SITE}/en/application/robot-solution/28",
                    "type": "website",
                    "title": "LABOT CNC Machine Tending",
                }
            ],
            "research_notes": (
                f"{NOTE_STAMP} Fresh signed notice hero from robot-solution/page rbsSeq=28."
            ),
            "notes": f"{NOTE_STAMP} CNC machine-tending package; HOLD cleared.",
            "_patch": {
                "model_name": "LABOT",
                "variant_code": "LABOT",
                "variant_label": "LABOT",
                "family_key": "hyundai-robotics:labot",
                "family_name": "LABOT",
                "family_url": f"{SITE}/en/application/robot-solution/28",
                "product_url_scope": "exact_variant",
                "purpose": "CNC machine tending",
                "availability_status": 11,
                "information_source_urls": [f"{SITE}/en/application/robot-solution/28"],
            },
            "_hero_sha": h_l,
        },
        3730: {
            "id": 3730,
            "name": "Robot Barista",
            "company_slug": COMPANY_SLUG,
            "company_name": COMPANY_NAME,
            "manufacturer_country_code": "KR",
            "description": (
                "Robot Barista is an HD Hyundai Robotics beverage-service application "
                "package that uses compact industrial arms (HH7-class) for automated "
                "café preparation and dispensing."
            ),
            "purpose": "Beverage preparation and service",
            "features": (
                "Official robot-solution application page (rbsSeq=24). "
                "Application / demo package rather than a standalone catalog SKU. "
                "Hero is the OEM notice thumbnail "
                f"{barista.get('fileOriNm')} (notice/aa17ec26cd8f49d8b787caca2fd09322)."
            ),
            "url": f"{SITE}/en/application/robot-solution/24",
            "image": barista["fileDwLink"],
            "images": [barista["fileDwLink"]],
            "video_urls": vids_barista,
            "movement_type_keys": "stationary",
            "category_slugs": "industrial-robots",
            "sub_category_slug": "manufacturing-industrial",
            "tags": TAGS_APP,
            "sources": [
                {
                    "url": f"{SITE}/en/application/robot-solution/24",
                    "type": "website",
                    "title": "Robot Barista",
                }
            ],
            "research_notes": (
                f"{NOTE_STAMP} Fresh signed notice hero from robot-solution/page rbsSeq=24."
            ),
            "notes": f"{NOTE_STAMP} Robot Barista application package; HOLD cleared.",
            "_patch": {
                "model_name": "Robot Barista",
                "variant_code": "Robot Barista",
                "variant_label": "Robot Barista",
                "family_key": "hyundai-robotics:robot-barista",
                "family_name": "Robot Barista",
                "family_url": f"{SITE}/en/application/robot-solution/24",
                "product_url_scope": "exact_variant",
                "purpose": "Beverage preparation and service",
                "availability_status": 11,
                "information_source_urls": [f"{SITE}/en/application/robot-solution/24"],
            },
            "_hero_sha": h_b,
        },
    }
    return rows


def trigger_copy_media(robot_ids: list[int]) -> tuple[int, int]:
    secret = os.environ.get("INTERNAL_API_SECRET", "").strip()
    env_file = _RESEARCH_DIR.parents[1] / "robotaigeek-server" / ".env"
    if not secret and env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                secret = line.split("=", 1)[1].strip()
    api = os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/").replace("/api/v1", "")
    if not secret or not api:
        print("copy-media skipped: missing INTERNAL_API_SECRET or API base")
        return 0, len(robot_ids)
    ok = fail = 0
    for rid in robot_ids:
        url = f"{api}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/"
        try:
            resp = requests.post(url, headers={"X-Internal-Secret": secret}, timeout=180)
            if resp.ok:
                ok += 1
                print(f"  copy-media {rid}: OK")
            else:
                fail += 1
                print(f"  copy-media {rid}: HTTP {resp.status_code} {resp.text[:120]}")
        except requests.RequestException as exc:
            fail += 1
            print(f"  copy-media {rid}: {exc}")
        time.sleep(0.2)
    return ok, fail


def verify_owned_cdn(client: ResearchApiClient, robot_ids: list[int]) -> dict[int, dict]:
    out: dict[int, dict] = {}
    for rid in robot_ids:
        d = client._get(f"robots/robots/{rid}/")
        url = (d.get("s3_image") or d.get("image") or "").strip()
        photos = d.get("photos") or []
        for p in photos:
            if isinstance(p, dict) and p.get("is_primary"):
                url = (p.get("s3_image") or p.get("url") or url or "").strip()
                break
        ok, nbytes, digest = verify_image_url(url) if url else (False, 0, "")
        out[rid] = {
            "name": d.get("name"),
            "status": d.get("status"),
            "url": url[:120],
            "http_ok": ok,
            "bytes": nbytes,
            "sha256": digest,
            "sha16": digest[:16] if digest else "",
        }
        print(
            f"  CDN {rid} {d.get('name')}: ok={ok} bytes={nbytes} "
            f"sha16={digest[:16] if digest else ''} status={d.get('status')}"
        )
    return out


def apply_rejects(client: ResearchApiClient, *, apply: bool) -> list[dict]:
    results = []
    for rid, reason in REJECTS.items():
        body = {
            "status": "rejected",
            "rejection_reason": reason,
            "notes": f"{NOTE_STAMP} {reason}",
        }
        if apply:
            client._patch(f"robots/robots/{rid}/", body)
            print(f"REJECT {rid}: {reason[:70]}…")
        else:
            print(f"DRY reject {rid}: {reason[:70]}…")
        results.append({"id": rid, "outcome": "rejected", "reason": reason})
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix Hyundai held pending robots")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--copy-media", action="store_true")
    parser.add_argument("--created-by-id", type=int, default=1)
    parser.add_argument("--skip-rejects", action="store_true")
    parser.add_argument("--only-fix", nargs="*", type=int)
    args = parser.parse_args()

    print("Building held-robot rows (fresh signed heroes)…", flush=True)
    s = session()
    rows = build_rows(s)
    if args.only_fix:
        rows = {k: v for k, v in rows.items() if k in set(args.only_fix)}

    preview = []
    for rid, row in rows.items():
        preview.append(
            {
                "id": rid,
                "name": row["name"],
                "url": row["url"],
                "image_preview": (row.get("image") or "")[:100],
                "hero_sha16": (row.get("_hero_sha") or "")[:16],
                "features_len": len(row.get("features") or ""),
            }
        )
    report_path = _RESEARCH_DIR / "staging" / "reports" / "hyundai-held-fix-preview.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(preview, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Preview: {report_path}")

    # Assert HDC hashes differ in staging
    if 3710 in rows and 3711 in rows and rows[3710]["_hero_sha"] == rows[3711]["_hero_sha"]:
        print("ERROR: HDC25/HDC35 staging hashes identical", file=sys.stderr)
        return 1

    client = ResearchApiClient()
    # Guard: do not touch published
    live = {int(r["id"]): r for r in client.list_robots_for_company(COMPANY_ID)}
    for rid in list(rows) + list(REJECTS):
        st = (live.get(rid) or {}).get("status") or ""
        if st == "published":
            print(f"ERROR: refusing to touch published robot {rid}", file=sys.stderr)
            return 1

    reject_results: list[dict] = []
    if not args.skip_rejects:
        reject_results = apply_rejects(client, apply=args.apply)

    if not args.apply:
        print("Dry-run complete. Re-run with --apply --copy-media")
        return 0

    created_by = resolve_created_by_id(args.created_by_id)
    imported: list[int] = []
    for rid, row in rows.items():
        staging_row = {k: v for k, v in row.items() if not k.startswith("_")}
        path = _RESEARCH_DIR / "staging" / "hyundai" / f"held_robot_{rid}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps([staging_row], indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"import {rid} {staging_row['name']}")
        result = import_staging(
            path,
            dry_run=False,
            force_overwrite=True,
            replace_media=True,
            status="pending_review",
            batch_size=1,
            skip_company_update=True,
            created_by_id=created_by,
        )
        print(f"  result={result}")
        patch = dict(row.get("_patch") or {})
        patch.update(
            {
                "status": "pending_review",
                "description": staging_row["description"],
                "features": staging_row["features"],
                "url": staging_row["url"],
                "notes": staging_row.get("notes") or "",
            }
        )
        client._patch(f"robots/robots/{rid}/", patch)
        imported.append(rid)
        time.sleep(0.2)

    copy_stats = None
    if args.copy_media and imported:
        print("copy-media…")
        ok, fail = trigger_copy_media(imported)
        copy_stats = {"ok": ok, "fail": fail, "requested": len(imported)}
        time.sleep(1.0)

    print("CDN verify…")
    cdn = verify_owned_cdn(client, imported)
    hdc_ok = True
    if 3710 in cdn and 3711 in cdn:
        if not cdn[3710]["http_ok"] or not cdn[3711]["http_ok"]:
            hdc_ok = False
        elif cdn[3710]["sha256"] and cdn[3710]["sha256"] == cdn[3711]["sha256"]:
            hdc_ok = False
            print("ERROR: post-apply HDC25/HDC35 CDN hashes still identical", file=sys.stderr)

    # Final pending census
    pending = [
        int(r["id"])
        for r in client.list_robots_for_company(COMPANY_ID)
        if (r.get("status") or "") == "pending_review"
    ]
    published = [
        int(r["id"])
        for r in client.list_robots_for_company(COMPANY_ID)
        if (r.get("status") or "") == "published"
    ]
    cdn_slim = {}
    for k, v in cdn.items():
        cdn_slim[str(k)] = {
            "name": v.get("name"),
            "status": v.get("status"),
            "url": v.get("url"),
            "http_ok": v.get("http_ok"),
            "bytes": v.get("bytes"),
            "sha16": v.get("sha16"),
        }
    failures: list[str] = []
    if not hdc_ok:
        failures.append("hdc_hash_collision_or_cdn_fail")
    if any(not v.get("http_ok") for v in cdn.values()):
        failures.append("cdn_http_fail")
    if copy_stats and copy_stats.get("fail", 0):
        failures.append("copy_media_fail")
    summary = {
        "company_id": COMPANY_ID,
        "rejected": len(reject_results),
        "fixed": len(imported),
        "still_held": 0,
        "pending_ids": sorted(pending),
        "published_ids": sorted(published),
        "approve_allowlist": sorted(set(published) | set(imported)),
        "copy_media": copy_stats,
        "cdn": cdn_slim,
        "hdc_hashes_distinct": hdc_ok,
        "failures": failures,
    }
    out = _RESEARCH_DIR / "staging" / "reports" / "hyundai-held-fix-apply.json"
    out.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"Report: {out}")
    return 0 if not summary["failures"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
