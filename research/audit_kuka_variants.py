#!/usr/bin/env python3
"""Audit KUKA (1396) published robots for missing CDN image variants.

Probes primary + gallery: original must be HTTP 200; representative 640w
JPEG/WebP variant must exist. Reports originals OK with missing thumbs.

Usage:
  python audit_kuka_variants.py
  python audit_kuka_variants.py --repair   # POST repair-images for each miss
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient

COMPANY_ID = 1396
OUT = _RESEARCH_DIR / "staging" / "reports" / "kuka-1396-missing-variants.json"
OWNED = ("cdn.robotaigeek.com", "cdn-dev.robotaigeek.com")
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "RobotAIGeekKukaVariantAudit/1.0"})


def _is_owned(url: str) -> bool:
    host = urlparse(url or "").netloc.lower()
    return any(host == h or host.endswith("." + h) for h in OWNED)


def _head_ok(url: str) -> tuple[bool, int | None]:
    if not url:
        return False, None
    try:
        r = SESSION.head(url, timeout=20, allow_redirects=True)
        if r.status_code >= 400 or not r.headers.get("Content-Length"):
            r = SESSION.get(
                url,
                timeout=20,
                allow_redirects=True,
                headers={"Range": "bytes=0-1023"},
            )
        ok = r.status_code in (200, 206)
        code = r.status_code
        r.close()
        return ok, code
    except requests.RequestException:
        return False, None


def _pick_variant(variants: Any, prefer: str = "640") -> str:
    if not isinstance(variants, dict) or not variants:
        return ""
    if prefer in variants and variants[prefer]:
        return str(variants[prefer])
    for v in variants.values():
        if v:
            return str(v)
    return ""


def _variant_urls_from_original(original: str) -> list[str]:
    """Derive expected 640w jpg/webp paths from an original CDN key."""
    path = urlparse(original).path.lstrip("/")
    if not path:
        return []
    # robots/original/foo.png -> robots/variants/foo_640w.jpg
    # common.image_variants.get_variant_key pattern: insert /variants/ and _{w}w
    base, ext = os.path.splitext(path)
    # originals live under robots/original/ or robots/photos/
    if "/original/" in path:
        stem = path.replace("/original/", "/variants/", 1)
    elif "/photos/" in path:
        stem = path.replace("/photos/", "/variants/", 1)
    else:
        # fallback: sibling variants dir
        parts = path.rsplit("/", 1)
        stem = f"{parts[0]}/variants/{parts[1]}" if len(parts) == 2 else path
    stem_no_ext = os.path.splitext(stem)[0]
    host = "https://cdn.robotaigeek.com"
    return [
        f"{host}/{stem_no_ext}_640w.jpg",
        f"{host}/{stem_no_ext}_640w.webp",
    ]


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


def repair_images(rid: int) -> dict[str, Any]:
    secret = _secret()
    api = _admin_base()
    # Endpoint is GET (not POST)
    url = f"{api}/admin/robots/robot/content-queue/api/robot/{rid}/repair-images/"
    try:
        r = requests.get(url, headers={"X-Internal-Secret": secret}, timeout=300)
        try:
            body = r.json()
        except Exception:
            body = {"raw": r.text[:200]}
        return {"http": r.status_code, **(body if isinstance(body, dict) else {"body": body})}
    except requests.RequestException as e:
        return {"http": 0, "error": str(e)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repair", action="store_true")
    ap.add_argument("--workers", type=int, default=20)
    ap.add_argument("--ids", type=int, nargs="*")
    args = ap.parse_args()

    client = ResearchApiClient()
    robots = []
    for a in range(8):
        try:
            robots = client.list_robots_for_company(COMPANY_ID)
            break
        except Exception as e:
            print(f"list retry {a}: {e}")
            time.sleep(3)
    published = [
        r
        for r in robots
        if str(r.get("status") or "").lower() in ("published", "approved")
    ]
    if args.ids:
        want = set(args.ids)
        published = [r for r in published if int(r["id"]) in want]
    print(f"company={COMPANY_ID} published/approved={len(published)}")

    # Hydrate detail for variants + photos
    details: dict[int, dict] = {}

    def fetch(rid: int) -> tuple[int, dict | None]:
        for attempt in range(4):
            try:
                return rid, client._get(f"robots/robots/{rid}/")
            except Exception:
                time.sleep(1.2 * (attempt + 1))
        return rid, None

    print(f"Hydrating {len(published)} robots…")
    with ThreadPoolExecutor(max_workers=min(args.workers, 10)) as pool:
        futs = [pool.submit(fetch, int(r["id"])) for r in published]
        done = 0
        for fut in as_completed(futs):
            rid, d = fut.result()
            done += 1
            if d:
                details[rid] = d
            if done % 40 == 0 or done == len(published):
                print(f"  {done}/{len(published)}")

    # Build probe jobs
    jobs: list[dict[str, Any]] = []
    for rid, r in details.items():
        sources: list[tuple[str, str, str]] = []  # kind, label, original
        primary = (r.get("s3_image") or r.get("image") or "").strip()
        if primary and _is_owned(primary):
            sources.append(("primary", f"robot#{rid}", primary))
            api_var = _pick_variant(r.get("image_variants_webp")) or _pick_variant(
                r.get("image_variants")
            )
            jobs.append(
                {
                    "robot_id": rid,
                    "name": r.get("name"),
                    "kind": "primary",
                    "label": f"robot#{rid}",
                    "original": primary,
                    "api_variant": api_var,
                    "derived_variants": _variant_urls_from_original(primary),
                }
            )
        for p in r.get("photos") or []:
            if not isinstance(p, dict):
                continue
            orig = (p.get("s3_image") or p.get("url") or "").strip()
            if not orig or not _is_owned(orig):
                continue
            api_var = _pick_variant(p.get("variants_webp") or p.get("variants"))
            jobs.append(
                {
                    "robot_id": rid,
                    "name": r.get("name"),
                    "kind": "photo",
                    "label": f"photo#{p.get('id')}",
                    "original": orig,
                    "api_variant": api_var,
                    "derived_variants": _variant_urls_from_original(orig),
                }
            )

    urls: set[str] = set()
    for j in jobs:
        urls.add(j["original"])
        if j["api_variant"]:
            urls.add(j["api_variant"])
        urls.update(j["derived_variants"])

    print(f"Probing {len(urls)} CDN URLs…")
    cache: dict[str, tuple[bool, int | None]] = {}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(_head_ok, u): u for u in urls}
        for fut in as_completed(futs):
            u = futs[fut]
            try:
                cache[u] = fut.result()
            except Exception:
                cache[u] = (False, None)

    missing_robots: dict[int, dict[str, Any]] = {}
    no_original = 0
    ok_sources = 0
    for j in jobs:
        orig_ok, orig_code = cache.get(j["original"], (False, None))
        if not orig_ok:
            no_original += 1
            entry = missing_robots.setdefault(
                j["robot_id"],
                {"id": j["robot_id"], "name": j["name"], "issues": []},
            )
            entry["issues"].append(
                {
                    "type": "original_dead",
                    "label": j["label"],
                    "url": j["original"],
                    "code": orig_code,
                }
            )
            continue

        # Variant OK if API variant URL works OR any derived 640w works
        candidates = []
        if j["api_variant"]:
            candidates.append(j["api_variant"])
        candidates.extend(j["derived_variants"])
        var_ok = any(cache.get(u, (False, None))[0] for u in candidates if u)
        if var_ok:
            ok_sources += 1
            continue

        entry = missing_robots.setdefault(
            j["robot_id"],
            {"id": j["robot_id"], "name": j["name"], "issues": []},
        )
        entry["issues"].append(
            {
                "type": "missing_variant",
                "label": j["label"],
                "kind": j["kind"],
                "original": j["original"],
                "tried": candidates,
            }
        )

    miss_list = sorted(missing_robots.values(), key=lambda x: x["id"])
    missing_variant_only = [
        m
        for m in miss_list
        if any(i["type"] == "missing_variant" for i in m["issues"])
    ]
    report = {
        "company_id": COMPANY_ID,
        "published": len(published),
        "hydrated": len(details),
        "sources_probed": len(jobs),
        "sources_ok": ok_sources,
        "original_dead_hits": no_original,
        "robots_with_issues": len(miss_list),
        "robots_missing_variants": len(missing_variant_only),
        "robots": miss_list,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"sources_ok={ok_sources}/{len(jobs)} "
        f"robots_with_issues={len(miss_list)} "
        f"missing_variants={len(missing_variant_only)} -> {OUT}"
    )
    for m in missing_variant_only[:25]:
        kinds = [i["type"] for i in m["issues"]]
        print(f"  {m['id']} {m['name']}: {kinds}")

    if not args.repair or not missing_variant_only:
        return 0

    print(f"Repairing {len(missing_variant_only)} robots via repair-images…")
    results = []
    for m in missing_variant_only:
        rid = m["id"]
        res = repair_images(rid)
        print(f"  repair {rid}: http={res.get('http')} {str(res)[:120]}")
        results.append({"id": rid, **res})
        time.sleep(0.3)
    report["repair_results"] = results
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # Re-probe repaired
    still = []
    for m in missing_variant_only:
        rid = m["id"]
        r = details.get(rid) or client._get(f"robots/robots/{rid}/")
        primary = (r.get("s3_image") or r.get("image") or "").strip()
        derived = _variant_urls_from_original(primary)
        api_var = _pick_variant(r.get("image_variants_webp")) or _pick_variant(
            r.get("image_variants")
        )
        cands = ([api_var] if api_var else []) + derived
        ok = False
        for u in cands:
            if u and _head_ok(u)[0]:
                ok = True
                break
        if not ok:
            still.append(rid)
            print(f"  STILL MISSING {rid}")
        else:
            print(f"  fixed {rid}")
    print(f"repair done; still_missing={len(still)}")
    report["still_missing_after_repair"] = still
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if not still else 1


if __name__ == "__main__":
    raise SystemExit(main())
