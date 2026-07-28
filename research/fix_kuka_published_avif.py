#!/usr/bin/env python3
"""Repair published KUKA (1396) heroes that are AVIF placeholders mislabeled as PNG.

Root cause (2026-07-19): KUKA.com content-negotiates tiny AVIF stubs when the
downloader's Accept prefers image/avif (our former DOWNLOAD_HEADERS). Those stubs
were stored as CDN heroes under .png names — shared within family by md5.

Until the DOWNLOAD_HEADERS fix is deployed, import via wsrv.nl `output=png` so
copy-media always receives real PNG bytes regardless of Accept.

Usage:
  python fix_kuka_published_avif.py
  python fix_kuka_published_avif.py --apply --copy-media
  python fix_kuka_published_avif.py --apply --copy-media --ids 5414
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
DEAD_JSON = _RESEARCH_DIR / "staging" / "reports" / "kuka-1396-dead-avif.json"
REPORT = _RESEARCH_DIR / "staging" / "reports" / "kuka-1396-avif-repair.json"
QA_DIR = _RESEARCH_DIR / "staging" / "kuka_avif_qa"
UA = {
    "User-Agent": "Mozilla/5.0 (compatible; RobotAIGeekResearch/1.0)",
    # Prefer PNG; avoid triggering KUKA AVIF negotiation during local QA.
    "Accept": "image/png,image/jpeg,image/webp,image/*,*/*;q=0.8",
}

K = "https://www.kuka.com/-/media/kuka-corporate/images"

# OEM family renders (direct). Import uses png_force_url() until Accept fix is live.
FAMILY_RENDER: dict[str, str] = {
    "kuka:kr-quantec": f"{K}/products/robots/cta-images/kr-quantec.png?rev=-1",
    "kuka:kr-fortec": (
        f"{K}/products/robots/cta-images/kr-fortec-360.png"
        "?rev=-1&w=767&hash=6E4AED83F1B96CF73A79A4A1B6386805"
    ),
    "kuka:kr-fortec-ultra": (
        f"{K}/products/robots/cta-images/kr-fortec-ultra.png"
        "?rev=-1&w=767&hash=0D6C590B351A21BD2868FFF3F131215F"
    ),
    "kuka:kr-fortec-ultra-pa": (
        f"{K}/products/robots/kr-fortec/kr-fortec-ultra-pa/"
        "product-picture-mykuka-fortec-ultra-pa.png"
        "?rev=-1&w=767&hash=DFA07BE348804323773EEE2"
    ),
    "kuka:lbr-iiwa": f"{K}/products/robots/cta-images/lbr-iiwa.png",
}

# Known stub cluster prefixes (md5) from published audit.
STUB_PREFIXES = {
    "51d34593d7c8",  # quantec
    "9b47c640d722",  # may be real fortec-ultra — checked via magic
}


def png_force_url(oem_url: str) -> str:
    """wsrv.nl always returns PNG bytes (defeats AVIF content-negotiation)."""
    return f"https://wsrv.nl/?url={quote(oem_url, safe='')}&output=png"


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


def copy_media(rid: int, *, attempts: int = 5) -> str:
    secret = _secret()
    api = _admin_base()
    if not secret or not api:
        return "no-secret"
    url = f"{api}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/?force=1"
    last = "ERR"
    for attempt in range(attempts):
        try:
            resp = requests.post(url, headers={"X-Internal-Secret": secret}, timeout=180)
            if resp.ok:
                return "ok"
            last = f"HTTP {resp.status_code}"
            if resp.status_code not in (502, 503, 504):
                return last
        except requests.RequestException as e:
            last = f"ERR {e}"
        time.sleep(2 ** attempt)
    return last


def download_ok(url: str) -> tuple[bool, str, bytes]:
    try:
        r = requests.get(url, headers=UA, timeout=60)
        body = r.content if r.ok else b""
        if not body.startswith((b"\x89PNG", b"\xff\xd8", b"GIF8", b"RIFF")):
            return False, "", body
        if body[4:8] == b"ftyp" and body[8:12] in (b"avif", b"avis"):
            return False, "", body
        return True, hashlib.md5(body).hexdigest(), body
    except requests.RequestException:
        return False, "", b""


def verify_hero(client: ResearchApiClient, rid: int) -> dict[str, Any]:
    r = client._get(f"robots/robots/{rid}/")
    url = (r.get("s3_image") or r.get("image") or "").strip()
    body = requests.get(url, timeout=60).content if url else b""
    md5 = hashlib.md5(body).hexdigest() if body else ""
    is_avif = body[4:8] == b"ftyp" and body[8:12] in (b"avif", b"avis")
    return {
        "id": rid,
        "url": url[:120],
        "md5": md5,
        "bytes": len(body),
        "is_avif": is_avif,
        "ok": bool(body) and not is_avif and len(body) > 40000,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--copy-media", action="store_true")
    ap.add_argument("--created-by-id", type=int, default=1)
    ap.add_argument("--ids", type=int, nargs="*")
    args = ap.parse_args()

    dead = json.loads(DEAD_JSON.read_text(encoding="utf-8"))
    robots = dead["robots"]
    if args.ids:
        want = set(args.ids)
        robots = [r for r in robots if int(r["id"]) in want]

    QA_DIR.mkdir(parents=True, exist_ok=True)
    client = ResearchApiClient()

    family_bytes: dict[str, tuple[str, bytes, str]] = {}
    for fam, oem in FAMILY_RENDER.items():
        forced = png_force_url(oem)
        ok, md5, body = download_ok(forced)
        if not ok:
            print(f"FAIL family render {fam}: {forced}")
            return 1
        family_bytes[fam] = (md5, body, forced)
        (QA_DIR / f"{fam.replace(':', '_')}_{md5[:12]}.png").write_bytes(body)
        print(f"family OK {fam} md5={md5[:12]} bytes={len(body)} via wsrv")

    plan = []
    for r in robots:
        rid = int(r["id"])
        fam = r.get("family_key") or ""
        oem = FAMILY_RENDER.get(fam)
        forced = png_force_url(oem) if oem else None
        entry = {
            "id": rid,
            "name": r.get("name"),
            "family_key": fam,
            "old_md5": r.get("md5"),
            "oem": oem,
            "render": forced,
            "action": "repair" if forced else "no_render",
        }
        if forced:
            entry["new_md5"] = family_bytes[fam][0]
        plan.append(entry)
        print(
            f"{rid} {str(r.get('name') or '')[:36]:36s} {fam:28s} "
            f"{'-> wsrv PNG' if forced else 'NO RENDER'}"
        )

    report: dict[str, Any] = {"company_id": COMPANY_ID, "plan": plan, "results": []}
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    todo = [p for p in plan if p["action"] == "repair"]
    if not args.apply:
        print(f"dry-run: {len(todo)} repairs. Pass --apply --copy-media")
        return 0

    results = []
    for p in todo:
        rid = p["id"]
        render = p["render"]
        row = staging_dict_to_bulk_import_row(
            {
                "id": rid,
                "name": p["name"],
                "company_slug": COMPANY_SLUG,
                "image": render,
                "images": [{"url": render}],
                "research_notes": (
                    f"Repaired AVIF-placeholder CDN hero ({(p.get('old_md5') or '')[:12]}) "
                    f"with wsrv-forced PNG of OEM family render for {p['family_key']} "
                    f"(KUKA Accept/AVIF negotiation, 2026-07-19)."
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
                status="published",
                skip_company_update=True,
                created_by_id=resolve_created_by_id(args.created_by_id),
            )
            print(f"import {rid}: {result}")
        except Exception as e:  # noqa: BLE001
            print(f"IMPORT FAIL {rid}: {e}")
            results.append({"id": rid, "ok": False, "error": str(e)})
            continue
        cm = "via-bulk"
        if args.copy_media:
            cm = copy_media(rid)
            print(f"  copy-media {rid}: {cm}")
        time.sleep(0.5)
        v = verify_hero(client, rid)
        print(
            f"  verify {rid}: ok={v['ok']} avif={v['is_avif']} "
            f"md5={v['md5'][:12]} bytes={v['bytes']}"
        )
        results.append(
            {
                "id": rid,
                "ok": v["ok"] and cm in ("ok", "via-bulk"),
                "import": result,
                "copy_media": cm,
                "verify": v,
            }
        )
        time.sleep(0.3)

    report["results"] = results
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    fail = sum(1 for x in results if not x.get("ok"))
    print(f"DONE repaired={len(results)} fail={fail} wrote {REPORT}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
