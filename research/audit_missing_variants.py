"""Detect published robots whose CDN originals exist but image variants 403.

Usage:
  python audit_missing_variants.py
  python audit_missing_variants.py --limit 50
  python audit_missing_variants.py --json-out staging/reports/missing-variants.json
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from load_env import load_research_env

load_research_env()

from api_client import ResearchApiClient

OWNED_HOSTS = ("cdn.robotaigeek.com", "cdn-dev.robotaigeek.com")
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "RobotAIGeekVariantAudit/1.0"})


def _is_owned(url: str) -> bool:
    host = urlparse(url or "").netloc.lower()
    return any(host == h or host.endswith("." + h) for h in OWNED_HOSTS)


def _head_ok(url: str, timeout: float = 15.0) -> tuple[bool, int | None]:
    if not url:
        return False, None
    try:
        resp = SESSION.head(url, timeout=timeout, allow_redirects=True)
        # Some CDNs dislike HEAD — fall back to ranged GET
        if resp.status_code >= 400 or not resp.headers.get("Content-Length"):
            resp = SESSION.get(
                url,
                timeout=timeout,
                allow_redirects=True,
                headers={"Range": "bytes=0-1023"},
            )
        code = resp.status_code
        ok = code in (200, 206)
        resp.close()
        return ok, code
    except requests.RequestException:
        return False, None


def _pick_variant_url(variants: dict[str, Any] | None, prefer: str = "640") -> str:
    if not isinstance(variants, dict) or not variants:
        return ""
    if prefer in variants:
        return str(variants[prefer] or "")
    # any width
    for v in variants.values():
        if v:
            return str(v)
    return ""


def _source_rows(robot: dict[str, Any]) -> list[dict[str, str]]:
    """Primary + gallery sources with original URL and a representative variant URL."""
    rows: list[dict[str, str]] = []
    rid = str(robot.get("id") or "")

    primary = (robot.get("s3_image") or robot.get("image") or "").strip()
    if primary and _is_owned(primary):
        rows.append({
            "kind": "primary",
            "label": f"robot#{rid}",
            "original": primary,
            "variant": _pick_variant_url(robot.get("image_variants_webp"))
            or _pick_variant_url(robot.get("image_variants")),
        })

    for p in robot.get("photos") or []:
        if not isinstance(p, dict):
            continue
        original = (p.get("s3_image") or p.get("url") or "").strip()
        if not original or not _is_owned(original):
            continue
        rows.append({
            "kind": "photo",
            "label": f"photo#{p.get('id')}",
            "original": original,
            "variant": _pick_variant_url(p.get("variants_webp") or p.get("image_variants_webp"))
            or _pick_variant_url(p.get("variants") or p.get("image_variants")),
        })
    return rows


def _iter_published(client: ResearchApiClient, *, limit: int | None, lite: bool) -> list[dict[str, Any]]:
    robots: list[dict[str, Any]] = []
    page = 1
    while True:
        params: dict[str, Any] = {"status": "published", "page": page, "page_size": 100}
        if lite:
            params["lite"] = "1"
        for attempt in range(5):
            try:
                data = client._get("robots/robots/", params=params)
                break
            except requests.HTTPError as exc:
                code = exc.response.status_code if exc.response is not None else 0
                if code in (502, 503, 504) and attempt < 4:
                    import time
                    time.sleep(2 ** attempt)
                    continue
                raise
        batch = data.get("results") or []
        if not batch:
            break
        robots.extend(batch)
        if limit and len(robots) >= limit:
            return robots[:limit]
        if not data.get("next"):
            break
        page += 1
    return robots


def _hydrate_photos(client: ResearchApiClient, robots: list[dict[str, Any]], *, workers: int) -> None:
    """Fetch full detail for robots that may have gallery photos (lite list omits them)."""
    need = [r for r in robots if r.get("s3_image") or r.get("image")]
    print(f"Hydrating photos for {len(need)} robot(s)…", flush=True)

    def fetch(rid: int) -> tuple[int, dict[str, Any] | None]:
        for attempt in range(4):
            try:
                return rid, client._get(f"robots/robots/{rid}/")
            except Exception:
                import time
                time.sleep(1.5 * (attempt + 1))
        return rid, None

    by_id = {int(r["id"]): r for r in robots}
    with ThreadPoolExecutor(max_workers=min(workers, 8)) as pool:
        futs = [pool.submit(fetch, int(r["id"])) for r in need]
        done = 0
        for fut in as_completed(futs):
            rid, detail = fut.result()
            done += 1
            if done % 25 == 0 or done == len(need):
                print(f"  hydrated {done}/{len(need)}", flush=True)
            if not detail:
                continue
            target = by_id.get(rid)
            if not target:
                continue
            # Prefer detail media fields
            for key in ("s3_image", "image", "image_variants", "image_variants_webp", "photos", "slug"):
                if key in detail and detail.get(key) is not None:
                    target[key] = detail[key]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=0, help="Max robots to scan (0=all)")
    ap.add_argument("--workers", type=int, default=24)
    ap.add_argument("--primary-only", action="store_true", help="Skip gallery photo hydration")
    ap.add_argument(
        "--json-out",
        type=Path,
        default=_RESEARCH_DIR / "staging" / "reports" / "missing-variants-published.json",
    )
    args = ap.parse_args()

    client = ResearchApiClient()
    robots = _iter_published(client, limit=args.limit or None, lite=True)
    print(f"Listed {len(robots)} published robot(s) (lite).", flush=True)
    if not args.primary_only:
        _hydrate_photos(client, robots, workers=args.workers)

    # Build probe jobs
    jobs: list[tuple[dict[str, Any], dict[str, str]]] = []
    skipped_no_media = 0
    skipped_no_variant_url = 0
    for robot in robots:
        rows = _source_rows(robot)
        if not rows:
            skipped_no_media += 1
            continue
        for row in rows:
            if not row["variant"]:
                skipped_no_variant_url += 1
                continue
            jobs.append((robot, row))

    url_cache: dict[str, tuple[bool, int | None]] = {}

    def probe(url: str) -> tuple[bool, int | None]:
        if url in url_cache:
            return url_cache[url]
        result = _head_ok(url)
        url_cache[url] = result
        return result

    # Prefetch unique URLs concurrently
    unique_urls = {row["original"] for _, row in jobs} | {row["variant"] for _, row in jobs}
    print(f"Probing {len(unique_urls)} unique CDN URL(s) with {args.workers} workers…", flush=True)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(_head_ok, u): u for u in unique_urls}
        for fut in as_completed(futs):
            u = futs[fut]
            try:
                url_cache[u] = fut.result()
            except Exception:
                url_cache[u] = (False, None)

    broken: list[dict[str, Any]] = []
    healthy = 0
    for robot, row in jobs:
        orig_ok, orig_code = probe(row["original"])
        var_ok, var_code = probe(row["variant"])
        if orig_ok and not var_ok:
            broken.append({
                "robot_id": robot.get("id"),
                "name": robot.get("name"),
                "slug": robot.get("slug") or "",
                "company": robot.get("company"),
                "kind": row["kind"],
                "label": row["label"],
                "original": row["original"],
                "original_status": orig_code,
                "variant": row["variant"],
                "variant_status": var_code,
            })
        elif orig_ok and var_ok:
            healthy += 1

    # Collapse per robot
    by_robot: dict[int, dict[str, Any]] = {}
    for item in broken:
        rid = int(item["robot_id"])
        entry = by_robot.setdefault(
            rid,
            {
                "robot_id": rid,
                "name": item["name"],
                "slug": item["slug"],
                "company": item["company"],
                "broken_sources": [],
            },
        )
        entry["broken_sources"].append({
            "kind": item["kind"],
            "label": item["label"],
            "original": item["original"],
            "variant": item["variant"],
            "variant_status": item["variant_status"],
        })

    report = {
        "scanned_robots": len(robots),
        "skipped_no_owned_media": skipped_no_media,
        "skipped_no_variant_url": skipped_no_variant_url,
        "healthy_source_checks": healthy,
        "broken_source_checks": len(broken),
        "broken_robot_count": len(by_robot),
        "robots": sorted(by_robot.values(), key=lambda r: r["robot_id"]),
    }

    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print()
    print(f"Published scanned:     {report['scanned_robots']}")
    print(f"Broken robots:         {report['broken_robot_count']}")
    print(f"Broken source checks:  {report['broken_source_checks']}")
    print(f"Healthy source checks: {report['healthy_source_checks']}")
    print(f"Report: {args.json_out}")
    print()
    if by_robot:
        print("Robots with missing variants (original OK, thumb fail):")
        for entry in report["robots"]:
            n = len(entry["broken_sources"])
            kinds = ",".join(sorted({s["kind"] for s in entry["broken_sources"]}))
            slug = entry["slug"] or "?"
            print(
                f"  #{entry['robot_id']:>5}  {entry['name']!r:40}  "
                f"sources={n} ({kinds})  /robot/{slug}"
            )
    else:
        print("No published robots with this defect found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
