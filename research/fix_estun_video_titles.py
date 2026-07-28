"""Backfill blank video titles for a company's robots (default Estun 220).

Root cause: fix_estun_robots.py's search_youtube_series() discarded the oEmbed
titles it fetched and stored bare URL strings, so RobotVideos imported with empty
title. This oEmbed-enriches each UNIQUE video URL once (title + description) and
patches every robot's existing videos via bulk-import patch_existing, whose
backfill branch fills title/description on existing videos where blank
(matched by URL). Never creates videos; never touches non-blank titles.

Usage:
  python fix_estun_video_titles.py                 # dry-run (company 220)
  python fix_estun_video_titles.py --apply
  python fix_estun_video_titles.py --company-id 220 --apply
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except Exception:
    pass

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient
from import_staging import resolve_created_by_id
from youtube_metadata import fetch_youtube_metadata


def _fetch_robots(client: ResearchApiClient, company_id: int) -> list[dict[str, Any]]:
    for attempt in range(15):
        try:
            return client.list_robots_for_company(company_id)
        except Exception as exc:
            print(f"list retry {attempt}: {str(exc)[:70]}", file=sys.stderr)
            time.sleep(6)
    raise SystemExit("ERROR: could not fetch robot list (prod 502)")


def _video_url(v: Any) -> str:
    if isinstance(v, dict):
        return (v.get("url") or "").strip()
    return str(v).strip()


def _video_title(v: Any) -> str:
    if isinstance(v, dict):
        return (v.get("title") or "").strip()
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill blank robot video titles")
    parser.add_argument("--company-id", type=int, default=220)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--created-by-id", type=int, default=1)
    args = parser.parse_args()

    client = ResearchApiClient()
    robots = _fetch_robots(client, args.company_id)
    print(f"company {args.company_id}: {len(robots)} robots")

    # 1) Collect unique video URLs that are missing a title on at least one robot.
    urls_needing: set[str] = set()
    for r in robots:
        for v in r.get("videos") or []:
            u = _video_url(v)
            if u and not _video_title(v):
                urls_needing.add(u)
    print(f"unique video URLs needing a title: {len(urls_needing)}")

    # 2) oEmbed-enrich each unique URL once (title + description).
    meta: dict[str, dict[str, str]] = {}
    for i, u in enumerate(sorted(urls_needing), 1):
        m = fetch_youtube_metadata(u)
        title = (m.get("title") or "").strip()
        meta[u] = {"title": title, "description": (m.get("description") or "").strip()}
        print(f"  [{i}/{len(urls_needing)}] {'OK ' if title else 'NO-TITLE '}{u} -> {title[:70]}")
        time.sleep(0.15)

    resolved = {u: m for u, m in meta.items() if m["title"]}
    unresolved = sorted(u for u, m in meta.items() if not m["title"])
    print(f"\nresolved titles: {len(resolved)} | unresolved (private/removed): {len(unresolved)}")
    for u in unresolved:
        print(f"  UNRESOLVED {u}")

    # 3) Build one patch row per robot that has >=1 blank-title video we can fill.
    rows: list[dict[str, Any]] = []
    for r in robots:
        vids = r.get("videos") or []
        fillable = [v for v in vids if _video_url(v) in resolved and not _video_title(v)]
        if not fillable:
            continue
        video_urls = []
        for v in vids:
            u = _video_url(v)
            if not u:
                continue
            entry: dict[str, str] = {"url": u}
            if u in resolved:
                entry["title"] = resolved[u]["title"][:255]
                if resolved[u]["description"]:
                    entry["description"] = resolved[u]["description"]
            elif _video_title(v):
                entry["title"] = _video_title(v)
            video_urls.append(entry)
        rows.append({
            "id": int(r["id"]),
            "name": r["name"],
            "company_slug": (r.get("company_ref") or {}).get("slug") if isinstance(r.get("company_ref"), dict) else None,
            "video_urls": video_urls,
            "_fill_count": len(fillable),
        })

    total_fills = sum(x["_fill_count"] for x in rows)
    print(f"\nrobots to patch: {len(rows)} | video titles to backfill: {total_fills}")
    preview = _RESEARCH_DIR / "staging" / "reports" / f"estun-video-titles-{args.company_id}-preview.json"
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if not rows:
        print("Nothing to backfill.")
        return 0
    if not args.apply:
        print(f"Preview: {preview}. Re-run with --apply")
        return 0

    totals = {"updated_count": 0, "error_count": 0, "skipped_count": 0, "created_count": 0}
    all_ok = True
    for x in rows:
        rid = x["id"]
        bulk_row = {"id": rid, "name": x["name"], "video_urls": x["video_urls"]}
        if x.get("company_slug"):
            bulk_row["company_slug"] = x["company_slug"]
        try:
            result = client.bulk_import_robots(
                [bulk_row],
                update_existing=True,
                patch_existing=True,
                replace_media=False,
                status="pending_review",
                skip_company_update=True,
                created_by_id=resolve_created_by_id(args.created_by_id),
            )
        except Exception as exc:
            all_ok = False
            print(f"IMPORT FAIL {rid}: {exc}", file=sys.stderr)
            continue
        if int(result.get("created_count") or 0) > 0:
            all_ok = False
            print(f"WARNING {rid}: created a NEW robot (expected patch) -> {result}", file=sys.stderr)
        if int(result.get("error_count") or 0):
            all_ok = False
            print(f"IMPORT FAIL {rid}: {result}", file=sys.stderr)
        for k in totals:
            totals[k] += int(result.get(k) or 0)
        print(f"  patched {rid} ({x['_fill_count']} titles): {result.get('results')}")

    out = {"ok": all_ok, "company_id": args.company_id, "robots_patched": len(rows),
           "titles_backfilled": total_fills, **totals}
    print(json.dumps(out, indent=2, ensure_ascii=False))
    (_RESEARCH_DIR / "staging" / "reports" / f"estun-video-titles-{args.company_id}-result.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
