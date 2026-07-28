#!/usr/bin/env python3
"""SIASUN (1424) discover + must-clear enrichment.

1) ENRICH 6 pending with live EN PDPs but empty features
2) REJECT 49 pending whose EN PDPs 404 and CN /products/* are empty SPA shells
3) CREATE missing live EN catalog robots (SCARA / GCR cobots / automotive mobiles)
   — skip software/system pages (digital twin, IoT, planner, etc.)

Usage:
  python discover_siasun_robots.py
  python discover_siasun_robots.py --apply --copy-media
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
from fix_siasun_robots import (
    build_row,
    classify,
    prefer_en_url,
    scrape_pdp,
    trigger_copy_media,
)
from import_staging import import_staging, resolve_created_by_id
from robot_auto_research import slugify_robot_name

COMPANY_ID = 1424
COMPANY_SLUG = "siasun-robot-automation-co-ltd"
COMPANY_NAME = "SIASUN Robot & Automation Co., Ltd."
CN_ID = 3
REPORT = _RESEARCH_DIR / "staging" / "reports" / "siasun-discover.json"
UA = {"User-Agent": "Mozilla/5.0 (compatible; RobotAIGeekResearch/1.0)"}

# From staging/reports/siasun-needs.json (2026-07-20 probe)
FEATURE_FIX_IDS = [4619, 4618, 4617, 4616, 4615, 4614]

REJECT_404 = [
    # bare industrial codes — EN 404; CN products/* empty SPA ("Lego head")
    4605, 4604, 4603, 4602, 4601, 4600, 4599, 4598, 4597, 4596,
    4595, 4594, 4593, 4592, 4591, 4590,
    4290, 4289, 4288, 4287, 4286, 4285, 4284, 4280, 4279, 4278, 4274, 4272,
    4270, 4269, 4268, 4266, 4264, 4260, 4259, 4258, 4257, 4256, 4255, 4254, 4252,
    4251, 4250, 4249, 4248, 4247, 4246, 4245, 4244,
]

CREATE_FROM_CATALOG = [
    # SCARA (live EN)
    {"name": "SA4A-4/0.40", "url": "https://en.siasun.com/sa4a-4-0-40.html"},
    {"name": "SA7A-7/0.60", "url": "https://en.siasun.com/sa7a-7-0-60.html"},
    {"name": "SA7A-7/0.70", "url": "https://en.siasun.com/sa7a-7-0-70.html"},
    {"name": "SA10A-10/0.60", "url": "https://en.siasun.com/sa10a-10-0-60.html"},
    {"name": "SA10A-10/0.70", "url": "https://en.siasun.com/sa10a-10-0-70.html"},
    {"name": "SA20A-20/0.80", "url": "https://en.siasun.com/sa20a-20-0-80.html"},
    {"name": "SA20A-20/1.00", "url": "https://en.siasun.com/sa20a-20-1-00.html"},
    # GCR cobots
    {"name": "GCR5-910", "url": "https://en.siasun.com/gcr5-910-2.html"},
    {"name": "GCR10-1300", "url": "https://en.siasun.com/gcr10-1300-2.html"},
    {"name": "GCR25-1800", "url": "https://en.siasun.com/gcr25-1800-2.html"},
    # Automotive assembly mobiles (physical platforms)
    {"name": "Single-Lift Automotive Assembly Mobile Robot", "url": "https://en.siasun.com/single-lift-automotive-assembly-mobile-robot.html"},
    {"name": "Dual-Lift Automotive Assembly Mobile Robot", "url": "https://en.siasun.com/dual-lift-automotive-assembly-mobile-robot.html"},
    {"name": "Triple-Lift Automotive Assembly Mobile Robot", "url": "https://en.siasun.com/triple-lift-automotive-assembly-mobile-robot.html"},
    {"name": "Four-Lift Automotive Assembly Mobile Robot", "url": "https://en.siasun.com/four-lift-automotive-assembly-mobile-robot.html"},
    {"name": "Interior & Finishing Line Assisted Assembly Mobile Robot", "url": "https://en.siasun.com/interior-finishing-line-assisted-assembly-mobile-robot.html"},
    {"name": "Front-End Module Assisted Assembly Mobile Robot", "url": "https://en.siasun.com/front-end-module-assisted-assembly-mobile-robot.html"},
    {"name": "Engine Assisted Assembly Mobile Robot", "url": "https://en.siasun.com/engine-assisted-assembly-mobile-robot.html"},
    {"name": "Transmission Assisted Assembly Mobile Robot", "url": "https://en.siasun.com/transmission-assisted-assembly-mobile-robot.html"},
    {"name": "Central Gear Assisted Assembly Mobile Robot", "url": "https://en.siasun.com/central-gear-assisted-assembly-mobile-robot.html"},
    {"name": "Axle Base Line Assisted Assembly Mobile Robot", "url": "https://en.siasun.com/axle-base-line-assisted-assembly-mobile-robot.html"},
    {"name": "Axle Final Line Assisted Assembly Mobile Robot", "url": "https://en.siasun.com/axle-final-line-assisted-assembly-mobile-robot.html"},
    {"name": "Instrument Panel Line Assisted Assembly Mobile Robot", "url": "https://en.siasun.com/instrument-panel-line-assisted-assembly-mobile-robot.html"},
    {"name": "Commercial Vehicle Assembly Mobile Robot", "url": "https://en.siasun.com/commercial-vehicle-assembly-mobile-robot.html"},
]

SKIP_SOFTWARE = [
    "Mobile Robot Transport Control System",
    "Mobile Robot Logistics Warehouse System",
    "Mobile Robot Statistical Analysis System",
    "Mobile Robot Layout Planner Tools",
    "Mobile Robot Digital Twin System",
    "Mobile Robot Internet Of Things",
]

REJECT_REASON = (
    "off-catalog: EN PDP 404 on en.siasun.com; CN www.siasun.com/products/* is an empty "
    "SPA shell (no product media). Legacy short SKU / stub — not on live EN catalog."
)


def download_ok(url: str) -> tuple[bool, str, int]:
    try:
        r = requests.get(url, headers={**UA, "Referer": "https://en.siasun.com/"}, timeout=60)
    except Exception:
        return False, "", 0
    if r.status_code != 200 or len(r.content) < 3000:
        return False, "", 0
    if r.content[:1] == b"<":
        return False, "", 0
    # magic
    if not (r.content[:3] == b"\xff\xd8\xff" or r.content[:8] == b"\x89PNG\r\n\x1a\n" or r.content[:4] == b"RIFF"):
        # allow webp/jpeg without strict magic if large enough
        if len(r.content) < 8000:
            return False, "", 0
    return True, hashlib.md5(r.content).hexdigest(), len(r.content)


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
    except Exception as e:
        return f"fail:{e}"


def patch_must_clear(client: ResearchApiClient, rid: int, row: dict[str, Any]) -> None:
    body: dict[str, Any] = {
        "manufacturer_countries": [CN_ID],
        "manufacturer_country_ref": CN_ID,
        "features": row.get("features") or "",
        "description": row.get("description") or "",
        "purpose": row.get("purpose") or "",
        "url": row.get("url") or "",
    }
    if row.get("payload_kg") is not None:
        body["payload_kg"] = row["payload_kg"]
    client._patch(f"robots/robots/{rid}/", body)


def import_row(row: dict[str, Any], *, created_by_id: int) -> dict[str, Any]:
    tmp = Path(tempfile.mkdtemp(prefix="siasun-disc-"))
    fpath = tmp / f"{slugify_robot_name(row['name'])}.json"
    fpath.write_text(json.dumps(row, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return import_staging(
        fpath,
        patch=False,
        force_overwrite=True,
        status="pending_review",
        dry_run=False,
        created_by_id=resolve_created_by_id(created_by_id),
        replace_media=bool(row.get("image")),
        batch_size=1,
        skip_company_update=True,
    )


def plan_enrich(client: ResearchApiClient) -> list[dict[str, Any]]:
    robots = {int(r["id"]): r for r in client.list_robots_for_company(COMPANY_ID)}
    out = []
    for rid in FEATURE_FIX_IDS:
        lite = robots.get(rid)
        if not lite:
            out.append({"id": rid, "action": "skip", "reason": "not_found"})
            continue
        if str(lite.get("status") or "").lower() != "pending_review":
            out.append({"id": rid, "name": lite.get("name"), "action": "skip", "reason": lite.get("status")})
            continue
        url = prefer_en_url((lite.get("url") or "").strip(), lite["name"])
        pdp = scrape_pdp(url)
        row = build_row(lite, pdp, url)
        # keep existing image if scrape failed hero but DB already has one
        if not row.get("image"):
            existing = lite.get("s3_image") or lite.get("image")
            if existing:
                row["image"] = existing
                row["images"] = [existing]
        ok_img, md5, nbytes = (False, "", 0)
        if row.get("image") and str(row["image"]).startswith("http") and "cdn.robotaigeek" not in row["image"]:
            ok_img, md5, nbytes = download_ok(row["image"])
        out.append({
            "id": rid,
            "name": lite["name"],
            "action": "enrich",
            "url": url,
            "features_len": len(row.get("features") or ""),
            "image": bool(row.get("image")),
            "hero_ok": ok_img or ("cdn.robotaigeek" in str(row.get("image") or "")),
            "hero_md5": md5[:12] if md5 else "",
            "hero_bytes": nbytes,
            "kind": classify(lite["name"], url),
            "row": row,
        })
        print(
            f"enrich {rid} {lite['name']}: feat={len(row.get('features') or '')} "
            f"img={bool(row.get('image'))} hero_ok={ok_img or 'cdn'}"
        )
    return out


def plan_create(client: ResearchApiClient) -> list[dict[str, Any]]:
    robots = client.list_robots_for_company(COMPANY_ID)
    existing_norm = {re.sub(r"[^A-Za-z0-9]", "", r["name"]).upper() for r in robots}
    existing_urls = {str(r.get("url") or "").rstrip("/") for r in robots}
    out = []
    for spec in CREATE_FROM_CATALOG:
        n = re.sub(r"[^A-Za-z0-9]", "", spec["name"]).upper()
        if n in existing_norm or spec["url"].rstrip("/") in existing_urls:
            out.append({**spec, "action": "skip", "reason": "already_in_db"})
            print(f"skip create {spec['name']}: already in DB")
            continue
        url = spec["url"]
        try:
            pdp = scrape_pdp(url)
        except Exception as e:
            out.append({**spec, "action": "skip", "reason": f"scrape_fail:{e}"})
            print(f"skip create {spec['name']}: scrape fail {e}")
            continue
        fake = {"name": spec["name"], "url": url, "id": None}
        row = build_row(fake, pdp, url)
        row["company_slug"] = COMPANY_SLUG
        row["company_name"] = COMPANY_NAME
        row["manufacturer_country_code"] = "CN"
        ok_img, md5, nbytes = download_ok(row["image"]) if row.get("image") else (False, "", 0)
        if not ok_img or len(row.get("features") or "") < 40:
            out.append({
                **spec,
                "action": "skip",
                "reason": f"incomplete img={ok_img} feat={len(row.get('features') or '')}",
            })
            print(f"skip create {spec['name']}: incomplete")
            continue
        out.append({
            **spec,
            "action": "create",
            "features_len": len(row.get("features") or ""),
            "hero_md5": md5[:12],
            "hero_bytes": nbytes,
            "kind": classify(spec["name"], url),
            "row": row,
        })
        print(f"create {spec['name']}: feat={len(row['features'])} hero={md5[:12]} {nbytes}b")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--copy-media", action="store_true")
    ap.add_argument("--skip-reject", action="store_true")
    ap.add_argument("--skip-create", action="store_true")
    ap.add_argument("--created-by-id", type=int, default=1)
    args = ap.parse_args()

    client = ResearchApiClient()
    enrich_plan = plan_enrich(client)
    create_plan = [] if args.skip_create else plan_create(client)

    report = {
        "company_id": COMPANY_ID,
        "enrich": [{k: v for k, v in x.items() if k != "row"} for x in enrich_plan],
        "reject_ids": REJECT_404 if not args.skip_reject else [],
        "reject_reason": REJECT_REASON,
        "create": [{k: v for k, v in x.items() if k != "row"} for x in create_plan],
        "skip_software": SKIP_SOFTWARE,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {REPORT}")

    if not args.apply:
        print("dry-run; pass --apply --copy-media")
        return 0

    imported: list[int] = []
    # 1) enrich features (and refresh media if new external hero)
    for item in enrich_plan:
        if item.get("action") != "enrich":
            continue
        row = item["row"]
        rid = int(item["id"])
        # Prefer surgical feature patch; re-import media only when external hero verified
        patch_must_clear(client, rid, row)
        if item.get("hero_ok") and row.get("image") and "cdn.robotaigeek" not in str(row["image"]):
            row["id"] = rid
            result = import_row(row, created_by_id=args.created_by_id)
            print(f"  import enrich {rid}: ok={result.get('ok')}")
            if result.get("ok"):
                imported.append(rid)
        else:
            print(f"  patched features {rid}")
        time.sleep(0.2)

    # 2) reject 404 stubs
    reject_results = []
    if not args.skip_reject:
        for rid in REJECT_404:
            out = reject_robot(client, rid, REJECT_REASON)
            print(f"reject {rid}: {out}")
            reject_results.append({"id": rid, "result": out})
            time.sleep(0.15)

    # 3) create missing catalog
    created_ids = []
    for item in create_plan:
        if item.get("action") != "create":
            continue
        row = item["row"]
        result = import_row(row, created_by_id=args.created_by_id)
        print(f"create {item['name']}: ok={result.get('ok')} {result.get('errors') or ''}")
        # resolve new id
        if result.get("ok"):
            robots = client.list_robots_for_company(COMPANY_ID)
            hit = next((r for r in robots if r.get("name") == item["name"]), None)
            if hit:
                created_ids.append(int(hit["id"]))
                imported.append(int(hit["id"]))
                # country patch
                client._patch(
                    f"robots/robots/{int(hit['id'])}/",
                    {"manufacturer_countries": [CN_ID], "manufacturer_country_ref": CN_ID},
                )
        time.sleep(0.3)

    if args.copy_media and imported:
        ok, fail = trigger_copy_media(imported)
        print(f"copy-media ok={ok} fail={fail}")

    report["apply"] = {
        "enriched": [x["id"] for x in enrich_plan if x.get("action") == "enrich"],
        "rejects": reject_results,
        "created_ids": created_ids,
        "imported_for_media": imported,
    }
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # final readiness
    from _audit_ready_to_approve import _hard_blockers

    co = client._get("companies/1424/")
    pending = [
        r for r in client.list_robots_for_company(COMPANY_ID)
        if str(r.get("status") or "").lower() == "pending_review"
    ]
    ready = needs = 0
    for lite in pending:
        d = client._get(f"robots/robots/{int(lite['id'])}/")
        if _hard_blockers(d, co):
            needs += 1
        else:
            ready += 1
    print(f"FINAL pending={len(pending)} ready={ready} needs={needs}")
    report["final"] = {"pending": len(pending), "ready": ready, "needs": needs}
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
