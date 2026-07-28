"""ACY (1369) — repair orphan CDN heroes (owned URL, missing S3 object).

Approve blocks when ``image`` is on cdn.robotaigeek.com but ``s3_image`` is empty
AND the object is gone from S3 (CloudFront may still cache). Fix: scrape live OEM
product pages for external JPGs, replace_media, copy-media into fresh S3 keys.

Usage:
  python fix_acy_orphan_cdn.py
  python fix_acy_orphan_cdn.py --apply --copy-media
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlsplit, urlunsplit

import requests

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient  # noqa: E402
from import_staging import resolve_created_by_id  # noqa: E402
from map_to_bulk_import import staging_dict_to_bulk_import_row  # noqa: E402
from verify_cdn_images import _is_owned  # noqa: E402

COMPANY_ID = 1369
COMPANY_SLUG = "acy-automation-inc"
COMPANY_NAME = "ACY Automation Inc."
REPORT = _HERE / "staging" / "reports" / "acy-orphan-cdn-fix.json"
UA = {"User-Agent": "Mozilla/5.0 RobotAIGeekACYOrphan/1.0"}


def enc(url: str) -> str:
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, quote(p.path), p.query, p.fragment))


def probe_image(url: str) -> bool:
    try:
        r = requests.get(url, headers=UA, timeout=30)
        if r.status_code != 200 or len(r.content) < 2000:
            return False
        ct = (r.headers.get("content-type") or "").lower()
        return ct.startswith("image/") or r.content.startswith((b"\xff\xd8", b"\x89PNG"))
    except requests.RequestException:
        return False


def scrape_page_images(page_url: str) -> list[str]:
    page = page_url.split("#")[0]
    try:
        r = requests.get(page, headers=UA, timeout=45)
    except requests.RequestException:
        return []
    if r.status_code != 200:
        return []
    found = re.findall(
        r"""(?:src|data-src|href)=["']([^"']+/image/[^"']+\.(?:jpe?g|png|webp))["']""",
        r.text,
        re.I,
    )
    out: list[str] = []
    seen: set[str] = set()
    for raw in found:
        u = unquote(raw)
        if not u.startswith("http"):
            u = "http://acy.com.tw/" + u.lstrip("/")
        u = u.replace("https://acy.com.tw/en/", "https://acy.com.tw/")
        if "logo" in u.lower() or "language" in u.lower() or "eoat.jpg" in u.lower():
            continue
        if "drawing" in u.lower():
            continue
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def tokens(name: str) -> list[str]:
    n = (name or "").lower()
    toks = re.findall(r"[a-z]+|\d+", n)
    # keep meaningful tokens
    stop = {"mm", "bore", "stroke", "with", "for", "the", "and", "type", "side"}
    return [t for t in toks if t not in stop and len(t) > 1]


def score_image(url: str, name: str) -> int:
    low = unquote(url).lower()
    sc = 0
    if "/image/catalog/" in low and "/cache/" not in low:
        sc += 30
    if "-500x500" in low:
        sc += 15
    if "-228x228" in low or "-200x200" in low:
        sc -= 10
    for t in tokens(name):
        if t in low:
            sc += 8
    # model-ish codes
    for m in re.findall(r"\b([a-z]{1,5}\d{2,}[a-z0-9-]*)\b", name.lower()):
        if m.replace("-", "") in low.replace("-", "").replace(" ", ""):
            sc += 25
    for m in re.findall(r"(fg-?\d+\w*|hdac-?\d+|nss\d+|pg\d+|hpg\d+|ar\d+|b\d+|x\d+)", name.lower()):
        if m.replace("-", "") in low.replace("-", "").replace(" ", ""):
            sc += 30
    return sc


def pick_oem_hero(name: str, page_url: str) -> str:
    cands = scrape_page_images(page_url)
    ranked = sorted(cands, key=lambda u: score_image(u, name), reverse=True)
    for u in ranked[:12]:
        eu = enc(u)
        if probe_image(eu) or probe_image(u):
            return eu if probe_image(eu) else enc(u)
    # try top catalog full-size rewrite
    for u in ranked[:8]:
        full = re.sub(r"-\d+x\d+(?=\.(?:jpe?g|png|webp))", "", u, flags=re.I)
        full = full.replace("/image/cache/catalog/", "/image/catalog/")
        if full != u:
            eu = enc(full)
            if probe_image(eu):
                return eu
    return ""


def trigger_copy_media(robot_ids: list[int]) -> tuple[int, int]:
    secret = os.environ.get("INTERNAL_API_SECRET", "").strip()
    env_file = _HERE.parents[1] / "robotaigeek-server" / ".env"
    if not secret and env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                secret = line.split("=", 1)[1].strip()
    api = os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/").replace("/api/v1", "")
    if not api:
        api = "https://ragadmin.robotaigeek.com"
    ok = fail = 0
    for rid in robot_ids:
        url = f"{api}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/?force=1"
        try:
            resp = requests.post(
                url,
                headers={"X-Internal-Secret": secret, "Content-Type": "application/json"},
                json={"force": True},
                timeout=180,
            )
            if resp.ok:
                ok += 1
                print(f"  copy-media OK {rid}")
            else:
                fail += 1
                print(f"  copy-media FAIL {rid}: {resp.status_code} {(resp.text or '')[:160]}")
        except requests.RequestException as exc:
            fail += 1
            print(f"  copy-media FAIL {rid}: {exc}")
        time.sleep(0.15)
    return ok, fail


def needs_repair(detail: dict[str, Any]) -> bool:
    img = (detail.get("image") or "").strip()
    s3 = (detail.get("s3_image") or "").strip()
    photos = detail.get("photos") or []
    photo_s3 = any((p.get("s3_image") or "") for p in photos if isinstance(p, dict))
    if s3 or photo_s3:
        return False
    return bool(img) and _is_owned(img)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--copy-media", action="store_true")
    ap.add_argument("--ids", type=int, nargs="*")
    ap.add_argument("--created-by-id", type=int, default=1)
    args = ap.parse_args()

    client = ResearchApiClient()
    robots = None
    for attempt in range(8):
        try:
            robots = client.list_robots_for_company(COMPANY_ID)
            break
        except Exception as exc:  # noqa: BLE001
            print(f"list retry {attempt}: {exc}")
            time.sleep(4)
    if robots is None:
        return 2

    robots = [r for r in robots if (r.get("status") or "") == "pending_review"]
    if args.ids:
        want = set(args.ids)
        robots = [r for r in robots if int(r["id"]) in want]

    plan: list[dict[str, Any]] = []
    staging: dict[int, dict[str, Any]] = {}

    for robot in robots:
        rid = int(robot["id"])
        detail = client._get(f"robots/robots/{rid}/")
        if not needs_repair(detail) and not args.ids:
            continue
        name = (detail.get("name") or robot.get("name") or "").strip()
        page = (detail.get("url") or "").strip()
        hero = pick_oem_hero(name, page) if page else ""
        entry = {
            "id": rid,
            "name": name,
            "page": page,
            "old": (detail.get("image") or "")[:100],
            "hero": hero[:110],
            "ok": bool(hero),
        }
        plan.append(entry)
        print(f"  {rid} {name[:45]}: {'OK' if hero else 'MISS'} {hero[:70]}")
        if hero:
            staging[rid] = {
                "id": rid,
                "name": name,
                "company_slug": COMPANY_SLUG,
                "company_name": COMPANY_NAME,
                "url": page,
                "image": hero,
                "images": [hero],
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
                    "[AI Research] ACY orphan CDN repair 2026-07-20: re-copy from live "
                    "OEM URL (prior CDN path had no S3 object)."
                ),
                "sources": [{"url": page, "type": "website", "title": name}],
            }
        time.sleep(0.2)

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps({"plan": plan}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"targets={len(plan)} with_hero={sum(1 for p in plan if p['ok'])} -> {REPORT}")

    if not args.apply:
        print("dry-run; pass --apply --copy-media")
        return 0 if all(p["ok"] for p in plan) else 1

    ok = err = 0
    imported: list[int] = []
    for rid, row in staging.items():
        bulk = staging_dict_to_bulk_import_row(row)
        bulk["id"] = rid
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
            print(f"  imported {rid}")
        except Exception as exc:  # noqa: BLE001
            err += 1
            print(f"  FAIL {rid}: {exc}")
        time.sleep(0.12)

    print(f"import ok={ok} err={err}")
    if args.copy_media and imported:
        cok, cfail = trigger_copy_media(imported)
        print(f"copy-media ok={cok} fail={cfail}")
        # verify s3_image present
        still = []
        for rid in imported:
            d = client._get(f"robots/robots/{rid}/")
            if not (d.get("s3_image") or "").strip():
                still.append(rid)
            else:
                print(f"  s3 ok {rid} {(d.get('s3_image') or '')[:75]}")
        print("still no s3_image", still)
        return 0 if not still and err == 0 else 1
    return 0 if err == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
