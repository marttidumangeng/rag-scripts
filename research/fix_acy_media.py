"""ACY Automation (1369) — promote working gallery heroes + copy-media to CDN.

Many pending SKUs have a *truncated* primary (`…/image/cache/catalog/Quick`) or a
language PNG stub as `image`, while secondary `photos[]` already hold full OEM
catalog JPGs and/or owned CDN copies. This script:

1. Picks the best working hero per robot (owned CDN > full OEM .jpg/.png)
2. bulk-imports with replace_media (identity + image/images only)
3. Triggers content-queue copy-media so `s3_image` is owned CDN

Usage:
  python fix_acy_media.py
  python fix_acy_media.py --apply --copy-media
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import requests

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient  # noqa: E402
from import_staging import resolve_created_by_id  # noqa: E402
from map_to_bulk_import import staging_dict_to_bulk_import_row  # noqa: E402
from robot_auto_research import slugify_robot_name  # noqa: E402

COMPANY_ID = 1369
COMPANY_SLUG = "acy-automation-inc"
COMPANY_NAME = "ACY Automation Inc."
REPORT = _HERE / "staging" / "reports" / "acy-media-fix.json"
OWNED = ("cdn.robotaigeek.com", "cdn-dev.robotaigeek.com")
UA = {"User-Agent": "RobotAIGeekACYMedia/1.0"}


def _is_owned(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return any(host == h or host.endswith("." + h) for h in OWNED)


def _is_junk(url: str) -> bool:
    u = unquote(url or "").lower()
    if not u.startswith("http"):
        return True
    if "/thumb/" in u or re.search(r"_w(320|640|960|1280)\.(jpe?g|png|webp)(\?|$)", u):
        return True
    if "en-gb.png" in u or "zh-tw.png" in u or "/language/" in u:
        return True
    # Truncated OpenCart cache paths (cut at first space on import)
    if re.search(r"/image/cache/catalog/[a-z0-9._-]+$", u) and "." not in u.rsplit("/", 1)[-1]:
        return True
    if u.rstrip("/").endswith(("/quick", "/sprue-finger", "/vacuum", "/air", "/holders")):
        return True
    if "acy-logo" in u:
        return True
    return False


def _probe(url: str) -> bool:
    try:
        resp = requests.get(url, headers=UA, timeout=25, stream=True)
        chunk = next(resp.iter_content(2048), b"") or b""
        ct = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
        ok = resp.status_code == 200 and (
            ct.startswith("image/")
            or chunk.startswith((b"\xff\xd8", b"\x89PNG", b"GIF8", b"RIFF"))
        )
        resp.close()
        return ok
    except requests.RequestException:
        return False


def _score(url: str) -> int:
    """Higher = better hero candidate."""
    u = unquote(url)
    low = u.lower()
    score = 0
    if _is_owned(u):
        score += 1000
    if low.endswith((".jpg", ".jpeg", ".png", ".webp")):
        score += 50
    if "/image/catalog/" in low and "/cache/" not in low:
        score += 40
    if "-500x500" in low or "-800x800" in low:
        score += 20
    if "-228x228" in low or "-200x200" in low:
        score -= 10
    if "example" in low:
        score += 5  # family demo still OK when SKU thumb missing
    return score


def collect_candidates(detail: dict[str, Any]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for key in ("s3_image", "image"):
        u = (detail.get(key) or "").strip()
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    for p in detail.get("photos") or []:
        if not isinstance(p, dict):
            continue
        for key in ("s3_image", "url"):
            u = (p.get(key) or "").strip()
            if u and u not in seen:
                seen.add(u)
                out.append(u)
        # NEVER promote width variants (w320/w640/…) into gallery images —
        # that creates duplicate photo rows (ACY 2026-07-20 incident).
    return out


def pick_hero(detail: dict[str, Any]) -> tuple[str, list[str]]:
    cands = [u for u in collect_candidates(detail) if not _is_junk(u)]
    cands.sort(key=_score, reverse=True)
    verified: list[str] = []
    for u in cands:
        if _probe(u):
            verified.append(u)
        if len(verified) >= 4:
            break
    hero = verified[0] if verified else ""
    return hero, verified


def trigger_copy_media(robot_ids: list[int]) -> tuple[int, int]:
    secret = os.environ.get("INTERNAL_API_SECRET", "").strip()
    env_file = _HERE.parents[1] / "robotaigeek-server" / ".env"
    if not secret and env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                secret = line.split("=", 1)[1].strip()
    api = os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/").replace("/api/v1", "")
    if not secret or not api:
        print("WARN: missing INTERNAL_API_SECRET or API base for copy-media")
        return 0, len(robot_ids)
    ok = fail = 0
    for rid in robot_ids:
        url = f"{api}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/"
        try:
            resp = requests.post(url, headers={"X-Internal-Secret": secret}, timeout=180)
            if resp.ok:
                ok += 1
            else:
                fail += 1
                print(f"  copy-media fail {rid}: HTTP {resp.status_code} {resp.text[:120]}")
        except requests.RequestException as exc:
            fail += 1
            print(f"  copy-media fail {rid}: {exc}")
        time.sleep(0.15)
    return ok, fail


def build_row(robot: dict[str, Any], detail: dict[str, Any], hero: str, gallery: list[str]) -> dict[str, Any]:
    name = (robot.get("name") or detail.get("name") or "").strip()
    return {
        "id": int(robot["id"]),
        "name": name,
        "company_slug": COMPANY_SLUG,
        "company_name": COMPANY_NAME,
        "url": (detail.get("url") or robot.get("url") or "").strip(),
        "image": hero,
        "images": gallery or [hero],
        "description": (detail.get("description") or "").strip(),
        "purpose": (detail.get("purpose") or "").strip(),
        "features": detail.get("features") or "",
        "family_key": detail.get("family_key") or "",
        "family_name": detail.get("family_name") or "",
        "family_url": detail.get("family_url") or "",
        "model_name": detail.get("model_name") or name,
        "variant_code": detail.get("variant_code") or name,
        "variant_label": detail.get("variant_label") or "",
        "product_url_scope": detail.get("product_url_scope") or "family",
        "research_notes": (
            "[AI Research] ACY media fix 2026-07-20: promote working gallery OEM/CDN "
            "hero; replace truncated primary / language PNG stubs."
        ),
        "sources": [{"url": detail.get("url") or "", "type": "website", "title": name}],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--copy-media", action="store_true")
    ap.add_argument("--ids", type=int, nargs="*")
    ap.add_argument("--created-by-id", type=int, default=1)
    args = ap.parse_args()

    client = ResearchApiClient()
    robots = None
    for attempt in range(10):
        try:
            robots = client.list_robots_for_company(COMPANY_ID)
            break
        except Exception as exc:  # noqa: BLE001
            print(f"list retry {attempt}: {exc}")
            time.sleep(5)
    if robots is None:
        return 2

    robots = [r for r in robots if (r.get("status") or "") == "pending_review"]
    if args.ids:
        want = set(args.ids)
        robots = [r for r in robots if int(r["id"]) in want]

    plan: list[dict[str, Any]] = []
    staging: dict[int, dict[str, Any]] = {}
    missing: list[int] = []

    for i, robot in enumerate(robots):
        rid = int(robot["id"])
        try:
            detail = client._get(f"robots/robots/{rid}/")
        except Exception as exc:  # noqa: BLE001
            print(f"  detail fail {rid}: {exc}")
            missing.append(rid)
            continue
        hero, gallery = pick_hero(detail)
        cur = (detail.get("image") or "").strip()
        needs = (not hero) or _is_junk(cur) or (hero and hero != cur) or (not _is_owned(cur) and not _is_owned(detail.get("s3_image") or ""))
        entry = {
            "id": rid,
            "name": robot.get("name"),
            "current": cur[:90],
            "hero": hero[:110] if hero else "",
            "gallery_n": len(gallery),
            "needs_fix": bool(hero) and needs,
            "owned_hero": _is_owned(hero) if hero else False,
        }
        plan.append(entry)
        if hero:
            staging[rid] = build_row(robot, detail, hero, gallery)
        else:
            missing.append(rid)
        if (i + 1) % 15 == 0:
            print(f"... scanned {i + 1}/{len(robots)}")

    stats = {
        "scanned": len(plan),
        "with_hero": sum(1 for p in plan if p["hero"]),
        "needs_fix": sum(1 for p in plan if p["needs_fix"]),
        "missing": missing,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(
        json.dumps({"stats": stats, "plan": plan}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(stats, indent=2))
    for p in plan[:8]:
        print(f"  {p['id']} fix={p['needs_fix']} hero={p['hero'][:70]}")
    if missing:
        print("MISSING heroes:", missing)

    if not args.apply:
        print("dry-run; pass --apply --copy-media")
        return 1 if missing else 0

    tmp = Path(tempfile.mkdtemp(prefix="acy-media-"))
    ok = err = 0
    imported: list[int] = []
    for rid, row in staging.items():
        bulk = staging_dict_to_bulk_import_row(row)
        bulk["id"] = rid
        (tmp / f"{slugify_robot_name(row['name'])}-{rid}.json").write_text(
            json.dumps([row], indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        try:
            client.bulk_import_robots(
                [bulk],
                update_existing=True,
                patch_existing=True,
                replace_media=True,
                status="pending_review",
                skip_company_update=True,
                created_by_id=resolve_created_by_id(args.created_by_id),
            )
            ok += 1
            imported.append(rid)
            if ok <= 5 or ok % 20 == 0:
                print(f"  imported media {rid} {row['name']}")
        except Exception as exc:  # noqa: BLE001
            err += 1
            print(f"  FAIL import {rid}: {exc}")
        time.sleep(0.12)

    print(f"import ok={ok} err={err}")
    if args.copy_media and imported:
        cok, cfail = trigger_copy_media(imported)
        print(f"copy-media ok={cok} fail={cfail}")
    return 0 if err == 0 and not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
