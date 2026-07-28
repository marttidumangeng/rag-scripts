#!/usr/bin/env python3
"""Repair KUKA pending_review AVIF stub heroes via wsrv-forced family PNGs.

Same root cause as published repair: KUKA Accept/AVIF content negotiation stored
tiny ftypavif placeholders. Also re-encodes larger AVIF heroes when a vetted
family OEM URL exists (wsrv → real PNG).

Usage:
  python fix_kuka_pending_avif.py
  python fix_kuka_pending_avif.py --apply --copy-media
  python fix_kuka_pending_avif.py --apply --copy-media --stubs-only
  python fix_kuka_pending_avif.py --apply --copy-media --ids 4085 5464
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient
from import_staging import resolve_created_by_id
from map_to_bulk_import import staging_dict_to_bulk_import_row

COMPANY_ID = 1396
COMPANY_SLUG = "kuka"
SUSPECT_JSON = _RESEARCH_DIR / "staging" / "reports" / "kuka-1396-pending-avif.json"
REPORT = _RESEARCH_DIR / "staging" / "reports" / "kuka-1396-pending-avif-repair.json"
K = "https://www.kuka.com/-/media/kuka-corporate/images"

# family_key without or with kuka: prefix → OEM URL (visually vetted in prior passes).
FAMILY_OEM: dict[str, str] = {
    "kr-quantec": f"{K}/products/robots/cta-images/kr-quantec.png?rev=-1",
    "kr-fortec": (
        f"{K}/products/robots/cta-images/kr-fortec-360.png"
        "?rev=-1&w=767&hash=6E4AED83F1B96CF73A79A4A1B6386805"
    ),
    "kr-fortec-ultra": (
        f"{K}/products/robots/cta-images/kr-fortec-ultra.png"
        "?rev=-1&w=767&hash=0D6C590B351A21BD2868FFF3F131215F"
    ),
    "kr-fortec-ultra-pa": (
        f"{K}/products/robots/kr-fortec/kr-fortec-ultra-pa/"
        "product-picture-mykuka-fortec-ultra-pa.png"
        "?rev=-1&w=767&hash=DFA07BE348804323773EEE2"
    ),
    "kr-fortec-pa": (
        f"{K}/products/robots/kr-fortec/kr-fortec-pa/kr-470-r3200-2-pa_teaser.jpg"
    ),
    "lbr-iiwa": f"{K}/products/robots/cta-images/lbr-iiwa.png",
    "lbr-iisy": (
        f"{K}/products/robots/lbr-iisy-cobot/"
        "kuka-lbr-iisy-industrial-cobot-flexible-automation.jpg"
    ),
    "lbr-med": f"{K}/industries/healthcare/lbr-med/lbr-med-feature-cell.jpg",
    "kr-cybertech-nano": f"{K}/products/robots/cta-images/kr-cybertech-nano.png?rev=-1",
    "kr-cybertech": (
        f"{K}/products/robots/kr-cybertech/cybertech_2.jpg"
    ),
    "kr-iontec": (
        f"{K}/products/robots/kr-iontec/kr_iontec_robot_features.jpg"
    ),
    "kr-agilus": f"{K}/products/robots/kr-agilus/kr-agilus.jpg",
    "kr-4-agilus": f"{K}/products/robots/kr-agilus/kr-agilus.jpg",
    "kr-scara": (
        f"{K}/products/robots/kr-scara/kuka-kr-scara-industrial-robot-with-4-axes.jpg"
    ),
    "kr-delta": (
        f"{K}/products/robots/kr-delta/delta-secondary-packaging.jpg"
        "?rev=-1&hash=A6516EB8C6AA66EF1965520B03AF30AE"
    ),
    "kr-1000-titan": (
        f"{K}/products/robots/kr-titan/kr-1000-titan_header.jpg"
    ),
    "palletizing-robots": (
        f"{K}/products/robots/kr-quantec/kr_quantec_pa_header_teaser.jpg"
    ),
    "kr-quantec-pa": (
        f"{K}/products/robots/kr-quantec/kr_quantec_pa_header_teaser.jpg"
    ),
}

# Known tiny stub cluster prefixes — always repair when family render exists.
STUB_MD5_PREFIXES = {
    "51d34593d7c8",
    "23ab42a3df99",
    "c060fb8893e5",
    "c47b8a3ada1a",
    "3440730bf12f",
    "424e52b6495a",
    "96c03ccd1420",
    "341e718e1331",
}

STUB_MAX_BYTES = 35000
UA = {
    "User-Agent": "Mozilla/5.0 (compatible; RobotAIGeekResearch/1.0)",
    "Accept": "image/png,image/jpeg,image/webp,image/*,*/*;q=0.8",
}


def fam_key(raw: str | None) -> str:
    s = (raw or "").strip().lower()
    if s.startswith("kuka:"):
        s = s[5:]
    return s


def png_force(url: str) -> str:
    return f"https://wsrv.nl/?url={quote(url, safe='')}&output=png"


def _secret() -> str:
    s = os.environ.get("INTERNAL_API_SECRET", "").strip()
    if s:
        return s
    env = _RESEARCH_DIR.parents[1] / "robotaigeek-server" / ".env"
    if env.is_file():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                return line.split("=", 1)[1].strip()
    return ""


def _admin_base() -> str:
    return (
        os.environ.get("IMPORT_SYNC_API_BASE_URL", "")
        .rstrip("/")
        .replace("/api/v1", "")
    )


def copy_media(rid: int) -> str:
    secret = _secret()
    api = _admin_base()
    if not secret or not api:
        return "no-secret"
    url = f"{api}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/?force=1"
    try:
        resp = requests.post(url, headers={"X-Internal-Secret": secret}, timeout=180)
        return "ok" if resp.ok else f"HTTP {resp.status_code}"
    except requests.RequestException as e:
        return f"ERR {e}"


def verify_hero(client: ResearchApiClient, rid: int) -> dict[str, Any]:
    r = client._get(f"robots/robots/{rid}/")
    url = (r.get("s3_image") or r.get("image") or "").strip()
    body = requests.get(url, timeout=60).content if url else b""
    is_avif = len(body) > 12 and body[4:8] == b"ftyp" and body[8:12] in (b"avif", b"avis")
    return {
        "md5": hashlib.md5(body).hexdigest() if body else "",
        "bytes": len(body),
        "is_avif": is_avif,
        "ok": bool(body) and not is_avif and len(body) > 20000,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--copy-media", action="store_true")
    ap.add_argument("--stubs-only", action="store_true", help="Only tiny/known stub clusters")
    ap.add_argument("--ids", type=int, nargs="*")
    ap.add_argument("--created-by-id", type=int, default=1)
    args = ap.parse_args()

    data = json.loads(SUSPECT_JSON.read_text(encoding="utf-8"))
    suspects = data["suspects"]
    if args.ids:
        want = set(args.ids)
        suspects = [s for s in suspects if int(s["id"]) in want]

    client = ResearchApiClient()
    plan = []
    for s in suspects:
        rid = int(s["id"])
        fk = fam_key(s.get("family_key"))
        oem = FAMILY_OEM.get(fk)
        md5p = (s.get("md5") or "")[:12]
        nbytes = int(s.get("bytes") or 0)
        is_stub = md5p in STUB_MD5_PREFIXES or nbytes <= STUB_MAX_BYTES
        if args.stubs_only and not is_stub:
            continue
        if not oem:
            plan.append(
                {
                    "id": rid,
                    "name": s.get("name"),
                    "family": fk,
                    "action": "no_render",
                    "old_md5": md5p,
                    "old_bytes": nbytes,
                }
            )
            print(f"SKIP {rid} {s.get('name')}: no render for {fk}")
            continue
        plan.append(
            {
                "id": rid,
                "name": s.get("name"),
                "family": fk,
                "action": "repair",
                "stub": is_stub,
                "old_md5": md5p,
                "old_bytes": nbytes,
                "oem": oem,
                "render": png_force(oem),
            }
        )
        print(
            f"{'STUB' if is_stub else 'AVIF'} {rid} {str(s.get('name'))[:32]:32s} "
            f"{fk:22s} -> wsrv"
        )

    todo = [p for p in plan if p["action"] == "repair"]
    report = {"plan": plan, "results": []}
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"todo={len(todo)} no_render={sum(1 for p in plan if p['action']=='no_render')}")
    if not args.apply:
        print("dry-run; pass --apply --copy-media")
        return 0

    results = []
    for p in todo:
        rid = p["id"]
        row = staging_dict_to_bulk_import_row(
            {
                "id": rid,
                "name": p["name"],
                "company_slug": COMPANY_SLUG,
                "image": p["render"],
                "images": [{"url": p["render"]}],
                "research_notes": (
                    f"Repaired AVIF hero ({p['old_md5']}/{p['old_bytes']}B) with "
                    f"wsrv PNG of OEM {p['family']} render (2026-07-19)."
                ),
                "source_locale": "en",
            }
        )
        row["id"] = rid
        try:
            result = client.bulk_import_robots(
                [row],
                update_existing=True,
                patch_existing=True,
                replace_media=True,
                status="pending_review",
                skip_company_update=True,
                created_by_id=resolve_created_by_id(args.created_by_id),
            )
            print(f"import {rid}: updated={result.get('updated_count')}")
        except Exception as e:  # noqa: BLE001
            print(f"FAIL import {rid}: {e}")
            results.append({"id": rid, "ok": False, "error": str(e)})
            continue
        cm = "via-bulk"
        if args.copy_media:
            cm = copy_media(rid)
            print(f"  copy-media {rid}: {cm}")
        time.sleep(0.4)
        v = verify_hero(client, rid)
        print(f"  verify {rid}: ok={v['ok']} avif={v['is_avif']} bytes={v['bytes']}")
        results.append({"id": rid, "ok": v["ok"] and cm in ("ok", "via-bulk"), "verify": v, "cm": cm})
        time.sleep(0.25)

    report["results"] = results
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    fail = sum(1 for x in results if not x.get("ok"))
    print(f"DONE n={len(results)} fail={fail} -> {REPORT}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
