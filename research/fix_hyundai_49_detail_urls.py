"""Fix Hyundai Robotics (49) pending_review rows using OEM detail pages.

All pending URLs currently point at category lists like
`/biz/product/60010001`. Remap each model to
`https://www.hd-hyundairobotics.com/biz/product/detail/{prdSeq}`
(e.g. HA006L -> /detail/8), refresh features/specs from the product API /
detail CART payload, and backfill missing heroes from attachment/thumb
fileSeq via `/api/v1/file/ck/view/{seq}`.
"""
from __future__ import annotations

import argparse
import hashlib
import html as html_lib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import requests

_RESEARCH_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH_DIR))
from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient
from import_staging import resolve_created_by_id
from map_to_bulk_import import staging_dict_to_bulk_import_row

COMPANY_ID = 49
KR = 14
BASE = "https://www.hd-hyundairobotics.com"
API = f"{BASE}/api/v1/product/page"
IMG = f"{BASE}/api/v1/file/ck/view/{{seq}}"
HDRS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": f"{BASE}/",
    "Accept": "application/json, text/plain, */*",
}

USE_BY_CODE = {
    "60020001": "Arc welding",
    "60020002": "Spot welding",
    "60020004": "Material handling",
    "60020005": "Assembly",
    "60020006": "Machine tending",
    "60020008": "Material handling",
    "60020009": "Palletizing",
}
INDUSTRY_BY_CODE = {
    "60040001": "automotive",
    "60040003": "manufacturing",
    "60040004": "manufacturing",
    "60040005": "manufacturing",
    "6004000F": "electronics",
}


def strip_html(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", html_lib.unescape(s)).strip()


def num(v: Any) -> float | None:
    if v is None:
        return None
    m = re.search(r"[\d,]+(?:\.\d+)?", str(v).replace("±", "").replace("'", ""))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def split_name(raw: str) -> tuple[str, str]:
    raw = re.sub(r"^(제품관리_|PRODUCT_)\s*", "", (raw or "").strip())
    raw = raw.replace("\r", "").strip()
    m = re.match(r"^(.*?)\s*\(([^)]+)\)\s*$", raw)
    return (m.group(1).strip(), m.group(2).strip()) if m else (raw, "")


def key(n: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (n or "").lower())


def series_of(name: str) -> str:
    m = re.match(r"^([A-Za-z]+)", name or "")
    return (m.group(1).lower() if m else "misc")


def fetch_catalog() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for code in ("60010001", "60010002", "60010007"):
        r = requests.get(
            API, params={"prdTypeCd": code, "page": 0, "size": 300}, headers=HDRS, timeout=60
        )
        r.raise_for_status()
        for x in r.json().get("data", {}).get("content") or []:
            if (x.get("prdNm") or "").strip():
                rows.append(x)
    return rows


def index_catalog(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for x in rows:
        cur, leg = split_name(x.get("prdNm") or "")
        for v in (x.get("prdNm"), cur, leg):
            if v:
                out[key(v)] = x
    return out


def hero_file_seq(x: dict[str, Any]) -> int | None:
    bd = x.get("bdContent") or {}
    if bd.get("bdcThumbFile1Seq"):
        return int(bd["bdcThumbFile1Seq"])
    thumb = bd.get("bdcThumbFile1")
    if isinstance(thumb, dict) and thumb.get("fileSeq"):
        return int(thumb["fileSeq"])
    atts = bd.get("attachments") or []
    for att in atts:
        if not isinstance(att, dict):
            continue
        name = (att.get("fileOriNm") or "").lower()
        ext = (att.get("fileExt") or "").lower()
        if ext in (".png", ".jpg", ".jpeg", ".webp") or name.endswith(
            (".png", ".jpg", ".jpeg", ".webp")
        ):
            if att.get("fileSeq"):
                return int(att["fileSeq"])
    return None


def hero_url(x: dict[str, Any]) -> str | None:
    seq = hero_file_seq(x)
    return IMG.format(seq=seq) if seq else None


def build_purpose(x: dict[str, Any], code: str) -> str:
    apps = [
        USE_BY_CODE[c]
        for c in (x.get("prdApField") or "").split("|")
        if c in USE_BY_CODE
    ]
    apps = list(dict.fromkeys(apps))
    if apps:
        return "\n".join(apps)
    if code == "60010002":
        glass = strip_html(x.get("prdBscSpec2") or "")
        return (
            "FPD glass substrate transfer\n"
            "Display panel handling"
            + (f"\n{glass} glass generation" if glass else "")
        )
    return "Industrial articulated handling"


def build_features(name: str, code: str, x: dict[str, Any], legacy: str) -> str:
    is_fpd = code == "60010002"
    payload = None if is_fpd else num(x.get("prdBscSpec1"))
    reach = None if is_fpd else num(x.get("prdBscSpec2"))
    glass = strip_html(x.get("prdBscSpec2") or "") if is_fpd else ""
    structure = strip_html(x.get("prdDtlSpec1") or "")
    axes = strip_html(x.get("prdDtlSpec2") or "")
    drive = strip_html(x.get("prdDtlSpec3") or "")
    ctrl = strip_html(x.get("prdBscSpec3") or "")
    repeat = strip_html(x.get("prdDtlSpec20") or "")
    mass = num(x.get("prdDtlSpec22"))
    lines: list[str] = []
    if structure and axes:
        lines.append(f"{axes}-axis {structure.lower()} configuration")
    elif structure:
        lines.append(f"{structure} configuration")
    if payload:
        lines.append(f"Rated payload {payload:g} kg")
    if reach:
        lines.append(f"Maximum reach {reach:g} mm")
    if glass:
        lines.append(f"Handles {glass} substrate glass")
    if drive:
        lines.append(f"{drive} drive")
    if repeat:
        lines.append(f"Repeatability {repeat} mm")
    if mass:
        lines.append(f"Manipulator mass {mass:g} kg")
    if ctrl:
        lines.append(f"Compatible controllers: {ctrl}")
    apps = [
        USE_BY_CODE[c].lower()
        for c in (x.get("prdApField") or "").split("|")
        if c in USE_BY_CODE
    ]
    if apps:
        lines.append("OEM applications: " + ", ".join(dict.fromkeys(apps)))
    if legacy:
        lines.append(f"Legacy designation: {legacy}")
    if (x.get("prdMassYn") or "").upper() == "N":
        lines.append("Listed by OEM as no longer in production")
    detail = f"{BASE}/biz/product/detail/{x.get('prdSeq')}"
    lines.append(f"Source detail page: {detail}")
    # features field must not include URLs per skill — drop last line, put in sources
    lines = [l for l in lines if not l.startswith("Source detail")]
    return "\n".join(f"• {l}" for l in lines)


def build_description(name: str, legacy: str, code: str, x: dict[str, Any]) -> str:
    kind = {
        "60010001": "industrial articulated",
        "60010002": "FPD glass transfer",
        "60010007": "collaborative",
    }.get(code, "industrial")
    is_fpd = code == "60010002"
    payload = None if is_fpd else num(x.get("prdBscSpec1"))
    reach = None if is_fpd else num(x.get("prdBscSpec2"))
    glass = strip_html(x.get("prdBscSpec2") or "") if is_fpd else ""
    axes = strip_html(x.get("prdDtlSpec2") or "")
    drive = strip_html(x.get("prdDtlSpec3") or "")
    ctrl = strip_html(x.get("prdBscSpec3") or "")
    bits = [
        f"{name} is an HD Hyundai Robotics {axes + '-axis ' if axes else ''}{kind} robot."
    ]
    cap = []
    if payload:
        cap.append(f"rated payload {payload:g} kg")
    if reach:
        cap.append(f"maximum reach {reach:g} mm")
    if cap:
        bits.append("It has " + " and ".join(cap) + ".")
    if glass:
        bits.append(f"Rated for {glass} substrate glass handling.")
    if drive:
        bits.append(f"Drive type: {drive}.")
    if ctrl:
        bits.append(f"Compatible controllers: {ctrl}.")
    if legacy:
        bits.append(f"Previously designated {legacy}.")
    if (x.get("prdMassYn") or "").upper() == "N":
        bits.append("Listed by the manufacturer as no longer in production.")
    return " ".join(bits)


def typed_specs(code: str, x: dict[str, Any]) -> dict[str, Any]:
    is_fpd = code == "60010002"
    out: dict[str, Any] = {}
    if is_fpd:
        # Clear fabricated payload left from list ingest.
        out["payload_kg"] = None
        out["reach_mm"] = None
        out["dof"] = num(x.get("prdDtlSpec2"))
        out["weight_kg"] = num(x.get("prdDtlSpec22"))
        out["repeatability_mm"] = num(x.get("prdDtlSpec20"))
    else:
        out["payload_kg"] = num(x.get("prdBscSpec1"))
        out["reach_mm"] = num(x.get("prdBscSpec2"))
        out["dof"] = num(x.get("prdDtlSpec2"))
        out["weight_kg"] = num(x.get("prdDtlSpec22"))
        out["repeatability_mm"] = num(x.get("prdDtlSpec20"))
    return out


def tags_for(code: str, x: dict[str, Any]) -> str:
    tags = ["Industrial Robot", "Manufacturing", "Factory Automation", "6-Axis"]
    if code == "60010002":
        tags = ["Industrial Robot", "Manufacturing", "Factory Automation", "Electronics"]
    elif code == "60010007":
        tags.append("Collaborative")
    else:
        tags.append("Industrial Arm")
        tags.append("Material Handling")
    apps = set((x.get("prdApField") or "").split("|"))
    if apps & {"60020001", "60020002"}:
        tags.append("Welding")
    if "60020009" in apps:
        tags.append("Palletizing")
    return "|".join(dict.fromkeys(tags))


def _admin_base() -> str:
    return (os.environ.get("ADMIN_BASE") or "https://ragadmin.robotaigeek.com").rstrip("/")


def _internal_secret() -> str:
    secret = (
        os.environ.get("INTERNAL_API_SECRET")
        or os.environ.get("CONTENT_QUEUE_INTERNAL_SECRET")
        or ""
    ).strip()
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


def copy_media(rid: int) -> bool:
    url = f"{_admin_base()}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/"
    resp = requests.post(
        url, headers={"X-Internal-Secret": _internal_secret()}, timeout=180
    )
    print(f"  copy-media {rid}: HTTP {resp.status_code}")
    return resp.status_code < 300


def md5_url(sess: requests.Session, url: str) -> tuple[str, int]:
    r = sess.get(url, headers=HDRS, timeout=60)
    r.raise_for_status()
    return hashlib.md5(r.content).hexdigest(), len(r.content)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--local", action="store_true")
    args = parser.parse_args()

    client = ResearchApiClient()
    catalog = fetch_catalog()
    by_key = index_catalog(catalog)
    pending = [
        client._get(f"robots/robots/{r['id']}/")
        for r in client.list_robots_for_company(COMPANY_ID)
        if r.get("status") == "pending_review"
        or client._get(f"robots/robots/{r['id']}/").get("status") == "pending_review"
    ]
    # re-fetch cleanly
    pending = []
    for r in client.list_robots_for_company(COMPANY_ID):
        full = client._get(f"robots/robots/{r['id']}/")
        if full.get("status") == "pending_review":
            pending.append(full)

    plans: list[dict[str, Any]] = []
    sess = requests.Session()
    used_hashes: set[str] = set()

    for robot in pending:
        rid = robot["id"]
        name = (robot.get("name") or "").strip()
        x = by_key.get(key(name))
        if not x:
            for k, v in by_key.items():
                if key(name) and (key(name) in k or k in key(name)):
                    x = v
                    break
        if not x:
            plans.append({"id": rid, "name": name, "error": "no OEM match"})
            continue
        code = str(x.get("prdTypeCd") or "")
        cur, legacy = split_name(x.get("prdNm") or "")
        detail = f"{BASE}/biz/product/detail/{x['prdSeq']}"
        hero = hero_url(x)
        if hero:
            h, n = md5_url(sess, hero)
            if n < 8000:
                hero = None
            elif h in used_hashes:
                plans.append(
                    {
                        "id": rid,
                        "name": name,
                        "error": f"hero hash collision {h[:12]}",
                        "detail_url": detail,
                    }
                )
                continue
            else:
                used_hashes.add(h)
        specs = typed_specs(code, x)
        avail = 11 if (x.get("prdMassYn") or "Y").upper() == "Y" else 4
        series = series_of(cur or name)
        plan = {
            "id": rid,
            "name": name,
            "oem_name": x.get("prdNm"),
            "prdSeq": x.get("prdSeq"),
            "detail_url": detail,
            "family_key": f"hyundai-robotics:{series}",
            "family_name": series.upper(),
            "family_url": f"{BASE}/biz/product/{code}",
            "product_url_scope": "exact_variant",
            "description": build_description(cur or name, legacy, code, x),
            "purpose": build_purpose(x, code),
            "features": build_features(cur or name, code, x, legacy),
            "specs": specs,
            "availability_status": avail,
            "tags": tags_for(code, x),
            "hero": hero,
            "code": code,
        }
        plans.append(plan)

    out = _RESEARCH_DIR / "staging" / "reports" / "hyundai-49-detail-fix-preview.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(plans, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(
        [
            {
                "id": p.get("id"),
                "name": p.get("name"),
                "detail": p.get("detail_url"),
                "need_media": p.get("need_media"),
                "hero": p.get("hero"),
                "specs": p.get("specs"),
                "error": p.get("error"),
            }
            for p in plans
        ],
        indent=2,
        ensure_ascii=False,
    ))
    if not args.apply:
        print(f"Preview {out}. Re-run --apply")
        return 0

    results = []
    imaged_ids: list[int] = []
    for plan in plans:
        if plan.get("error"):
            results.append(plan)
            continue
        rid = plan["id"]
        robot = client._get(f"robots/robots/{rid}/")
        notes = (robot.get("notes") or "").rstrip()
        notes += (
            f"\n[AI Research] 2026-08-02: remapped URL to OEM detail page "
            f"{plan['detail_url']}; features/specs from product API + detail CART; "
            f"{'hero from ck/view attachment; ' if plan.get('hero') else ''}"
            f"list-page URL retired."
        )
        row: dict[str, Any] = {
            "company_slug": "hyundai-robotics",
            "company_name": "Hyundai Robotics",
            "source_locale": "en",
            "name": plan["name"],
            "model_name": plan["name"],
            "url": plan["detail_url"],
            "description": plan["description"],
            "purpose": plan["purpose"],
            "features": plan["features"],
            "information_source_urls": [plan["detail_url"]],
            "notes": notes,
            "manufacturer_country_code": "KR",
            "availability_status_key": (
                "available" if plan["availability_status"] == 11 else "discontinued"
            ),
            "family_key": plan["family_key"],
            "family_name": plan["family_name"],
            "family_url": plan["family_url"],
            "product_url_scope": "exact_variant",
            "category_slugs": "industrial-robots",
            "sub_category_slug": "manufacturing-industrial",
            "movement_type_keys": "stationary|fixed",
            "industry_keys": "manufacturing|industrial|automotive",
            "use_keys": "material-handling|assembly|machine-tending|welding",
            "tags": plan["tags"],
        }
        for k, v in plan["specs"].items():
            if v is not None:
                row[k] = v
        replace_media = True
        if plan.get("hero"):
            row["image"] = plan["hero"]
            row["images"] = [plan["hero"]]
        else:
            # Fail closed rather than re-import without a fresh OEM hero — prior
            # bulk imports without replace_media wiped s3_image on keepers.
            print(f"ERROR #{rid} {plan['name']}: no OEM hero fileSeq", file=sys.stderr)
            results.append({"id": rid, "name": plan["name"], "error": "no_hero"})
            continue

        bulk = staging_dict_to_bulk_import_row(row)
        bulk["id"] = rid
        bulk["status"] = "pending_review"
        print(f"Apply #{rid} {plan['name']} -> {plan['detail_url']}", flush=True)
        result = client.bulk_import_robots(
            [bulk],
            update_existing=True,
            patch_existing=False,
            replace_media=replace_media,
            replace_videos=False,
            status="pending_review",
            skip_company_update=True,
            created_by_id=resolve_created_by_id(1),
        )
        patch = {
            "status": "pending_review",
            "url": plan["detail_url"],
            "description": plan["description"],
            "purpose": plan["purpose"],
            "features": plan["features"],
            "notes": notes,
            "manufacturer_countries": [KR],
            "manufacturer_country_ref": KR,
            "availability_status": plan["availability_status"],
            "family_key": plan["family_key"],
            "family_name": plan["family_name"],
            "family_url": plan["family_url"],
            "product_url_scope": "exact_variant",
            "model_name": plan["name"],
            "tags": [t.strip() for t in plan["tags"].split("|")],
            **{k: v for k, v in plan["specs"].items()},
        }
        client._patch(f"robots/robots/{rid}/", patch)
        copy_media(rid)
        time.sleep(0.3)
        client._patch(f"robots/robots/{rid}/", patch)
        imaged_ids.append(rid)

        full = client._get(f"robots/robots/{rid}/")
        flags = full.get("quality_flags") or []
        results.append(
            {
                "id": rid,
                "name": full.get("name"),
                "url": full.get("url"),
                "updated": result.get("updated_count"),
                "s3": bool(full.get("s3_image") or full.get("image")),
                "hard": [
                    f.get("flag")
                    for f in flags
                    if isinstance(f, dict) and f.get("severity") == "error"
                ],
                "warns": [
                    f.get("flag")
                    for f in flags
                    if isinstance(f, dict) and f.get("severity") == "warn"
                ],
                "specs": {
                    k: full.get(k)
                    for k in (
                        "payload_kg",
                        "reach_mm",
                        "dof",
                        "weight_kg",
                        "repeatability_mm",
                    )
                },
            }
        )

    if imaged_ids:
        subprocess.check_call(
            [
                sys.executable,
                str(_RESEARCH_DIR / "verify_cdn_images.py"),
                "--ids",
                *[str(i) for i in imaged_ids],
            ],
            cwd=str(_RESEARCH_DIR),
        )

    report = _RESEARCH_DIR / "staging" / "reports" / "hyundai-49-detail-fix-result.json"
    report.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(results, indent=2, ensure_ascii=False))
    bad = [r for r in results if r.get("hard")]
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
