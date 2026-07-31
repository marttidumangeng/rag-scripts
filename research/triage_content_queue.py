"""Triage admin content-queue (To Review) robots and rank companies by missing data.

Usage:
  python triage_content_queue.py
  python triage_content_queue.py --limit 15 --status pending_review
  python triage_content_queue.py --mark-done 975
  python triage_content_queue.py --include-done

Only robots that still have gaps are counted. Companies already marked done in
state/content_queue_done.json are skipped unless --include-done.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient

STATE_PATH = _RESEARCH_DIR / "state" / "content_queue_done.json"
REPORT_PATH = _RESEARCH_DIR / "staging" / "reports" / "content-queue-triage.json"

# Gap weights used for ranking (higher = more urgent).
GAP_WEIGHTS = {
    "no_image": 5,
    "no_features": 4,
    # `no_country` is the only ERROR-severity flag in this list
    # (quality.FLAG_REGISTRY) and it is the cheapest to fix — usually a copy from
    # the company — so it outranks the warnings.
    "no_country": 5,
    "no_videos": 3,
    "no_url": 3,
    "no_category": 3,
    "no_tags": 2,
    "no_specs": 1,
    "no_company": 4,
}

# Companies already curated via fix_* scripts (seed seed list).
SEED_DONE = {
    50,   # IIT
    52,   # Intuitive
    342,  # iRobot
    783,  # Infinium
    975,  # EVE
    1073, # INTAMSYS
    1369, # ACY Automation (company backfill)
    1396, # KUKA
    1445, # Epson Robots
    1398, # Geek+
    1424, # SIASUN
}


def _load_done() -> dict[str, Any]:
    if STATE_PATH.is_file():
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    else:
        data = {"companies": [], "notes": {}}
    ids = set(int(x) for x in data.get("companies") or [])
    ids |= SEED_DONE
    data["companies"] = sorted(ids)
    return data


def _save_done(data: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "companies": sorted(set(int(x) for x in data.get("companies") or [])),
        "notes": data.get("notes") or {},
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    STATE_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _has_image(robot: dict[str, Any]) -> bool:
    return bool(robot.get("s3_image") or robot.get("image") or robot.get("image_url"))


def _has_features(robot: dict[str, Any]) -> bool:
    return len((robot.get("features") or "").strip()) >= 40


def _has_videos(robot: dict[str, Any]) -> bool:
    vids = robot.get("videos") or robot.get("video_urls") or []
    return isinstance(vids, list) and len(vids) > 0


def _has_tags(robot: dict[str, Any]) -> bool:
    tags = robot.get("tags") or []
    if isinstance(tags, list):
        return len(tags) > 0
    return bool(str(tags).strip())


def _has_url(robot: dict[str, Any]) -> bool:
    return bool((robot.get("url") or "").strip())


def _has_specs(robot: dict[str, Any]) -> bool:
    if robot.get("weight_kg") is not None:
        return True
    if robot.get("dof") is not None:
        return True
    if robot.get("length_mm") is not None or robot.get("width_mm") is not None or robot.get("height_mm") is not None:
        return True
    if (robot.get("dimensions_mm") or "").strip():
        return True
    if (robot.get("weight") or "").strip():
        return True
    notes = (robot.get("notes") or "").lower()
    if "payload:" in notes or "dimensions:" in notes:
        return True
    return False


def _has_country(robot: dict[str, Any]) -> bool:
    ref = robot.get("manufacturer_country_ref")
    if isinstance(ref, dict) and (ref.get("code") or ref.get("id")):
        return True
    return bool(str(robot.get("manufacturer_country") or "").strip())


def _has_category(robot: dict[str, Any]) -> bool:
    cats = robot.get("categories") or []
    return isinstance(cats, list) and len(cats) > 0


def robot_gaps(robot: dict[str, Any]) -> list[str]:
    gaps: list[str] = []
    if not _has_image(robot):
        gaps.append("no_image")
    if not _has_features(robot):
        gaps.append("no_features")
    if not _has_videos(robot):
        gaps.append("no_videos")
    if not _has_tags(robot):
        gaps.append("no_tags")
    if not _has_url(robot):
        gaps.append("no_url")
    if not _has_specs(robot):
        gaps.append("no_specs")
    # Country and category were absent from this list until 2026-07-31, and
    # `overnight_queue_enrich` filters its work queue on `robot_gaps(r)` being
    # non-empty — so a robot whose ONLY problems were "No country" and "No
    # category" was silently dropped from every remediation pass. 295 pending
    # robots were missing both.
    if not _has_country(robot):
        gaps.append("no_country")
    if not _has_category(robot):
        gaps.append("no_category")
    if not (robot.get("company_ref") or robot.get("company")):
        gaps.append("no_company")
    return gaps


def gap_score(gaps: list[str]) -> int:
    return sum(GAP_WEIGHTS.get(g, 1) for g in gaps)


def _company_meta(robot: dict[str, Any]) -> dict[str, Any]:
    cref = robot.get("company_ref")
    if isinstance(cref, dict):
        return {
            "id": cref.get("id"),
            "name": cref.get("name") or robot.get("company") or "Unknown",
            "slug": cref.get("slug") or "",
            "website": (cref.get("website") or "").strip(),
            "country": (cref.get("country") or {}).get("code")
            if isinstance(cref.get("country"), dict)
            else cref.get("country"),
            "has_logo": bool(cref.get("logo_url")),
            "has_description": bool((cref.get("description") or "").strip()),
        }
    return {
        "id": None,
        "name": robot.get("company") or "Unknown",
        "slug": "",
        "website": "",
        "country": None,
        "has_logo": False,
        "has_description": False,
    }


def iter_pending_robots(
    client: ResearchApiClient,
    *,
    status: str,
    page_size: int,
    max_pages: int | None,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    page = 1
    while True:
        if max_pages is not None and page > max_pages:
            break
        # Prod intermittently 502s on these heavily-serialized pages; a single
        # blip used to kill the whole scan mid-way (see api_client.list_robots_for_company,
        # which retries for the same reason). Retry with backoff before giving up.
        data = None
        last_exc: Exception | None = None
        for attempt in range(6):
            try:
                data = client._get(
                    "robots/robots/",
                    params={"status": status, "page": page, "page_size": page_size},
                )
                break
            except Exception as exc:  # noqa: BLE001 - surface after retries
                last_exc = exc
                print(f"  page {page} retry {attempt}: {str(exc)[:70]}", flush=True)
                time.sleep(2 ** attempt)
        if data is None:
            # Prefer a partial ranking over aborting the whole session when the
            # API flaps mid-scan (common 502s around page 20+ of ~40).
            if results and page > 5:
                print(
                    f"  WARN page {page} failed after retries ({last_exc}); "
                    f"continuing with partial scan of {len(results)} robots",
                    flush=True,
                )
                break
            raise RuntimeError(
                f"triage: page {page} failed after retries ({last_exc}); "
                f"collected {len(results)} robots so far"
            )
        batch = data.get("results") or []
        results.extend(batch)
        print(f"  page {page}: +{len(batch)} (total {len(results)}/{data.get('count')})")
        if not data.get("next") or not batch:
            break
        page += 1
    return results


def triage(
    *,
    status: str,
    limit: int,
    page_size: int,
    max_pages: int | None,
    include_done: bool,
) -> dict[str, Any]:
    done = _load_done()
    done_ids = set(done["companies"])
    client = ResearchApiClient()
    print(f"Scanning status={status} …")
    robots = iter_pending_robots(
        client, status=status, page_size=page_size, max_pages=max_pages
    )

    by_company: dict[Any, dict[str, Any]] = {}
    incomplete_robots = 0
    for robot in robots:
        gaps = robot_gaps(robot)
        if not gaps:
            continue
        incomplete_robots += 1
        meta = _company_meta(robot)
        cid = meta["id"] if meta["id"] is not None else f"name:{meta['name']}"
        bucket = by_company.get(cid)
        if not bucket:
            bucket = {
                "company_id": meta["id"],
                "company_name": meta["name"],
                "slug": meta["slug"],
                "website": meta["website"],
                "country": meta["country"],
                "company_has_logo": meta["has_logo"],
                "company_has_description": meta["has_description"],
                "incomplete_count": 0,
                "score": 0,
                "gap_counts": defaultdict(int),
                "sample_robots": [],
                "admin_url": (
                    f"https://ragadmin.robotaigeek.com/admin/robots/robot/content-queue/"
                    f"?company_id={meta['id']}"
                    if meta["id"] is not None
                    else ""
                ),
                "done": meta["id"] in done_ids if meta["id"] is not None else False,
            }
            by_company[cid] = bucket
        bucket["incomplete_count"] += 1
        bucket["score"] += gap_score(gaps)
        for g in gaps:
            bucket["gap_counts"][g] += 1
        if len(bucket["sample_robots"]) < 5:
            bucket["sample_robots"].append({
                "id": robot["id"],
                "name": robot["name"],
                "gaps": gaps,
                "url": robot.get("url") or "",
            })

    companies = []
    for bucket in by_company.values():
        bucket["gap_counts"] = dict(bucket["gap_counts"])
        # Soft boost: has website → easier to enrich.
        if bucket.get("website"):
            bucket["rank_score"] = bucket["score"] + 2
        else:
            bucket["rank_score"] = bucket["score"]
        # Deprioritize marketplace-only / empty company shells slightly still included.
        companies.append(bucket)

    companies.sort(key=lambda c: (-c["rank_score"], -c["incomplete_count"], c["company_name"]))
    if not include_done:
        ranked = [c for c in companies if not c.get("done")]
    else:
        ranked = companies

    top = ranked[:limit]
    # Compact full ranking for mid-size filtering without re-scanning.
    all_compact = [
        {
            "company_id": c.get("company_id"),
            "company_name": c["company_name"],
            "incomplete_count": c["incomplete_count"],
            "rank_score": c["rank_score"],
            "website": c.get("website") or "",
            "gap_counts": c["gap_counts"],
            "done": bool(c.get("done")),
        }
        for c in ranked
    ]
    report = {
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "robots_scanned": len(robots),
        "incomplete_robots": incomplete_robots,
        "companies_with_gaps": len(by_company),
        "companies_ranked": len(ranked),
        "done_company_ids": sorted(done_ids),
        "top": top,
        "all_companies": all_compact,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def _safe_print(text: str) -> None:
    """Windows consoles (cp1252) blow up on CJK robot names — never abort the report."""
    try:
        print(text)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "ascii"
        print(text.encode(enc, errors="replace").decode(enc, errors="replace"))


def print_report(report: dict[str, Any]) -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    _safe_print("")
    _safe_print(
        f"Scanned {report['robots_scanned']} {report['status']} robots; "
        f"{report['incomplete_robots']} incomplete across "
        f"{report['companies_with_gaps']} companies "
        f"({report['companies_ranked']} after done-filter)."
    )
    _safe_print(f"Report: {REPORT_PATH}")
    _safe_print("")
    _safe_print(f"{'#':>2} {'score':>5} {'n':>3}  company_id  name")
    _safe_print("-" * 88)
    for i, c in enumerate(report["top"], 1):
        gaps = ",".join(f"{k}:{v}" for k, v in sorted(c["gap_counts"].items()))
        site = c.get("website") or "(no website)"
        _safe_print(
            f"{i:>2} {c['rank_score']:>5} {c['incomplete_count']:>3}  "
            f"{str(c.get('company_id') or '-'):>10}  {c['company_name'][:48]}"
        )
        _safe_print(f"     gaps={gaps}")
        _safe_print(f"     site={site}")
        if c.get("admin_url"):
            _safe_print(f"     {c['admin_url']}")
        samples = ", ".join(
            f"{s['name'][:28]}[{'+'.join(s['gaps'][:3])}]" for s in c["sample_robots"][:3]
        )
        _safe_print(f"     samples: {samples}")
        _safe_print("")


def main() -> int:
    parser = argparse.ArgumentParser(description="Triage content-queue incomplete robots by company")
    parser.add_argument("--status", default="pending_review")
    parser.add_argument("--limit", type=int, default=12, help="Top companies to print/write")
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--max-pages", type=int, default=None, help="Cap pages for quick scans")
    parser.add_argument("--include-done", action="store_true")
    parser.add_argument("--mark-done", type=int, nargs="+", help="Mark company id(s) as done")
    parser.add_argument("--unmark-done", type=int, nargs="+", help="Remove company id(s) from done")
    args = parser.parse_args()

    if args.mark_done or args.unmark_done:
        done = _load_done()
        ids = set(done["companies"])
        for cid in args.mark_done or []:
            ids.add(int(cid))
            done.setdefault("notes", {})[str(cid)] = {
                "marked_at": datetime.now(timezone.utc).isoformat(),
            }
        for cid in args.unmark_done or []:
            ids.discard(int(cid))
        done["companies"] = sorted(ids)
        _save_done(done)
        print(f"Updated {STATE_PATH}: {len(done['companies'])} done companies")
        return 0

    report = triage(
        status=args.status,
        limit=args.limit,
        page_size=args.page_size,
        max_pages=args.max_pages,
        include_done=args.include_done,
    )
    print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
