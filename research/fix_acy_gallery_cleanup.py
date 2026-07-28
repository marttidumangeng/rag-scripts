"""ACY (1369) — strip variant-thumb gallery dupes + replace angular drawings.

Root cause of "4 identical images": fix_acy_media.py imported CDN *variants*
(w320/w640/w960) as separate RobotPhoto rows. Every pending SKU now has
primary + 3 thumb clones in `photos[]`.

Also: Angular Gripper *Double Acting* heroes are OEM dimension drawings
(AG*D-drawing) — never allowed as primary. Replace with catalog product
photos (AG10D / AG25D / AG32D / …).

Usage:
  python fix_acy_gallery_cleanup.py
  python fix_acy_gallery_cleanup.py --apply --copy-media
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
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse, urlsplit, urlunsplit, quote

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
REPORT = _HERE / "staging" / "reports" / "acy-gallery-cleanup.json"
UA = {"User-Agent": "RobotAIGeekACYGallery/1.0"}
OWNED = ("cdn.robotaigeek.com", "cdn-dev.robotaigeek.com")

def _enc_oem(url: str) -> str:
    """Percent-encode path spaces so server copy-media can fetch OpenCart URLs."""
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, quote(p.path), p.query, p.fragment))


# Curated OEM product photos (not *-drawing*) for angular grippers.
_ANGULAR_RAW: dict[int, str] = {
    1149: "http://acy.com.tw/image/catalog/Sprue-Finger Gripper/Angular Grippers/AG10D..jpg",
    1151: "http://acy.com.tw/image/catalog/Sprue-Finger Gripper/Angular Grippers/AG10O..jpg",
    1153: "http://acy.com.tw/image/catalog/Sprue-Finger Gripper/Angular Grippers/AG-16D..jpg",
    # No separate AG16O on OEM — use 16D product photo (same series body).
    1155: "http://acy.com.tw/image/catalog/Sprue-Finger Gripper/Angular Grippers/AG-16D..jpg",
    1157: "http://acy.com.tw/image/catalog/Sprue-Finger Gripper/Angular Grippers/AG20D BIG.jpg",
    1159: "http://acy.com.tw/image/catalog/Sprue-Finger Gripper/Angular Grippers/AG-20O.jpg",
    1161: "http://acy.com.tw/image/catalog/Sprue-Finger Gripper/Angular Grippers/AG25D..jpg",
    1163: "http://acy.com.tw/image/catalog/Sprue-Finger Gripper/Angular Grippers/AG25O.jpg",
    1165: "http://acy.com.tw/image/catalog/Sprue-Finger Gripper/Angular Grippers/AG32D..jpg",
    1167: "http://acy.com.tw/image/catalog/Sprue-Finger Gripper/Angular Grippers/AG32O.jpg",
}
ANGULAR_OEM: dict[int, str] = {k: _enc_oem(v) for k, v in _ANGULAR_RAW.items()}


def _is_owned(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return any(host == h or host.endswith("." + h) for h in OWNED)


def _is_variant_thumb(url: str) -> bool:
    u = unquote(url or "").lower()
    if "/thumb/" in u:
        return True
    if re.search(r"_w(320|640|960|1280)\.(jpe?g|png|webp)(\?|$)", u):
        return True
    return False


def _is_drawing(url: str) -> bool:
    return "drawing" in unquote(url or "").lower()


def _is_junk(url: str) -> bool:
    u = unquote(url or "").lower()
    if not u.startswith("http"):
        return True
    if _is_variant_thumb(u):
        return True
    if "en-gb.png" in u or "zh-tw.png" in u or "/language/" in u:
        return True
    if "acy-logo" in u or u.endswith("/eoat.jpg"):
        return True
    if re.search(r"/image/cache/catalog/[a-z0-9._-]+$", u) and "." not in u.rsplit("/", 1)[-1]:
        return True
    return False


def _fetch(url: str) -> bytes | None:
    try:
        resp = requests.get(url, headers=UA, timeout=35)
        if resp.status_code != 200:
            return None
        body = resp.content or b""
        if len(body) < 500:
            return None
        if not (
            body.startswith((b"\xff\xd8", b"\x89PNG", b"GIF8", b"RIFF"))
            or "image/" in (resp.headers.get("content-type") or "")
        ):
            return None
        return body
    except requests.RequestException:
        return None


def _md5(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def collect_original_urls(detail: dict[str, Any]) -> list[str]:
    """Original gallery URLs only — never CDN width variants."""
    seen: set[str] = set()
    out: list[str] = []
    for key in ("s3_image", "image"):
        u = (detail.get(key) or "").strip()
        if u and u not in seen and not _is_junk(u):
            seen.add(u)
            out.append(u)
    for p in detail.get("photos") or []:
        if not isinstance(p, dict):
            continue
        for key in ("s3_image", "url"):
            u = (p.get(key) or "").strip()
            if u and u not in seen and not _is_junk(u):
                seen.add(u)
                out.append(u)
    return out


def pick_gallery(rid: int, detail: dict[str, Any]) -> tuple[str, list[str], dict[str, Any]]:
    meta: dict[str, Any] = {"angular_override": False, "dropped_thumbs": 0, "unique_hashes": 0}

    # Count thumbs currently stored (for report)
    for p in detail.get("photos") or []:
        if isinstance(p, dict):
            u = (p.get("s3_image") or p.get("url") or "")
            if _is_variant_thumb(u):
                meta["dropped_thumbs"] += 1

    ordered: list[str] = []
    if rid in ANGULAR_OEM:
        ordered.append(ANGULAR_OEM[rid])
        meta["angular_override"] = True
        # Angular: OEM product photo only — never keep dimension drawings in gallery.
        verified: list[tuple[str, str, bytes]] = []
        body = _fetch(ANGULAR_OEM[rid])
        if body:
            verified.append((ANGULAR_OEM[rid], _md5(body), body))
        meta["unique_hashes"] = len(verified)
        hero = verified[0][0] if verified else ""
        gallery = [u for u, _, _ in verified]
        return hero, gallery, meta

    for u in collect_original_urls(detail):
        if _is_drawing(u):
            continue  # drawing may stay as secondary only after a real hero exists
        if u not in ordered:
            ordered.append(u)

    # If we still have nothing, allow a non-thumb drawing-free owned URL from photos
    if not ordered:
        for u in collect_original_urls(detail):
            ordered.append(u)

    verified: list[tuple[str, str, bytes]] = []  # url, md5, bytes
    seen_hash: set[str] = set()
    for u in ordered:
        body = _fetch(u)
        if not body:
            continue
        h = _md5(body)
        if h in seen_hash:
            continue
        # Skip dimension drawings as hero; allow once as trailing secondary only
        if _is_drawing(u) and not verified:
            continue
        seen_hash.add(h)
        verified.append((u, h, body))
        if len(verified) >= 3:
            break

    # If hero still missing but we have a drawing-only set, leave empty (fail closed)
    if not verified and rid in ANGULAR_OEM:
        body = _fetch(ANGULAR_OEM[rid])
        if body:
            verified.append((ANGULAR_OEM[rid], _md5(body), body))

    meta["unique_hashes"] = len(verified)
    hero = verified[0][0] if verified else ""
    gallery = [u for u, _, _ in verified]
    return hero, gallery, meta


def trigger_copy_media(robot_ids: list[int], force: bool = True) -> tuple[int, int]:
    secret = os.environ.get("INTERNAL_API_SECRET", "").strip()
    env_file = _HERE.parents[1] / "robotaigeek-server" / ".env"
    if not secret and env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                secret = line.split("=", 1)[1].strip()
    api = os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/").replace("/api/v1", "")
    if not secret or not api:
        print("WARN: missing INTERNAL_API_SECRET / API base")
        return 0, len(robot_ids)
    ok = fail = 0
    for rid in robot_ids:
        url = f"{api}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/"
        if force:
            url += "?force=1"
        try:
            resp = requests.post(
                url,
                headers={"X-Internal-Secret": secret, "Content-Type": "application/json"},
                json={"force": True} if force else {},
                timeout=180,
            )
            if resp.ok:
                ok += 1
            else:
                body = (resp.text or "")[:200]
                if "owned CDN" in body and '"copied": 0' in body and '"failed": 0' in body:
                    ok += 1
                else:
                    fail += 1
                    print(f"  copy-media fail {rid}: HTTP {resp.status_code} {body}")
        except requests.RequestException as exc:
            fail += 1
            print(f"  copy-media fail {rid}: {exc}")
        time.sleep(0.15)
    return ok, fail


def build_row(robot: dict, detail: dict, hero: str, gallery: list[str]) -> dict[str, Any]:
    name = (robot.get("name") or detail.get("name") or "").strip()
    return {
        "id": int(robot["id"]),
        "name": name,
        "company_slug": COMPANY_SLUG,
        "company_name": COMPANY_NAME,
        "url": (detail.get("url") or "").strip(),
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
            "[AI Research] ACY gallery cleanup 2026-07-20: remove variant-thumb "
            "photo rows; replace angular dimension drawings with OEM product photos."
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
        hero, gallery, meta = pick_gallery(rid, detail)
        entry = {
            "id": rid,
            "name": robot.get("name"),
            "n_photos_before": len(detail.get("photos") or []),
            "hero": hero[:110] if hero else "",
            "gallery_n": len(gallery),
            **meta,
        }
        plan.append(entry)
        if hero:
            staging[rid] = build_row(robot, detail, hero, gallery)
        else:
            missing.append(rid)
        if (i + 1) % 15 == 0:
            print(f"... {i + 1}/{len(robots)}")

    stats = {
        "scanned": len(plan),
        "with_hero": sum(1 for p in plan if p["hero"]),
        "angular_overrides": sum(1 for p in plan if p.get("angular_override")),
        "thumbs_dropped_sum": sum(p.get("dropped_thumbs") or 0 for p in plan),
        "missing": missing,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(
        json.dumps({"stats": stats, "plan": plan}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(stats, indent=2))
    for p in plan:
        if p.get("angular_override") or (p.get("dropped_thumbs") or 0) >= 3:
            if p.get("angular_override") or p["id"] in (1101, 1161, 1165):
                print(
                    f"  {p['id']} {p['name']}: before={p['n_photos_before']} "
                    f"thumbs={p['dropped_thumbs']} gallery={p['gallery_n']} "
                    f"angular={p['angular_override']} hero={p['hero'][:65]}"
                )

    if not args.apply:
        print("dry-run; pass --apply --copy-media")
        return 1 if missing else 0

    tmp = Path(tempfile.mkdtemp(prefix="acy-gallery-"))
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
                print(f"  imported {rid} {row['name']}")
        except Exception as exc:  # noqa: BLE001
            err += 1
            print(f"  FAIL {rid}: {exc}")
        time.sleep(0.12)

    print(f"import ok={ok} err={err}")
    if args.copy_media and imported:
        cok, cfail = trigger_copy_media(imported)
        print(f"copy-media ok={cok} fail={cfail}")
    return 0 if err == 0 and not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
