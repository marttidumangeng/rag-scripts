#!/usr/bin/env python3
"""Watch rival robot catalogs and report what changed between runs.

Counterpart to the per-company discovery scripts, pointed at competitors:

* ``robolist``  — robolist.ai: every category page's public JSON-LD robot
  list (same extraction as ``scrape_robolist.py``), one snapshot across all
  categories. Requests honor the site's published five-second crawl delay.
* ``notion``    — Petr Novikov's public Robotics Companies Database
  (petrnovikov.notion.site), queried through Notion's public collection API.
* ``aparobot``  — aparobot.com: robot and company slugs from its public
  sitemap.xml (one request per run; their robots.txt advertises the sitemap
  and has no disallow rules).
* ``self``      — our own published/total counts from the ragadmin API, so
  snapshots line up rivals and RobotAIGeek on the same dates. Skipped
  unless ``IMPORT_SYNC_API_KEY`` (or ``IMPORT_SYNC_API_KEY_PROD``) is set.

Each run writes ``rival_watch/<rival>/YYYY-MM-DDTHH-MM.json`` and diffs
against the previous snapshot of the same rival: new/removed robots (or
companies), and per-category count changes.

    python watch_rivals.py                # all watchers
    python watch_rivals.py --rival robolist
    python watch_rivals.py --rival robolist --diff-only   # re-diff last two
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from scrape_robolist import BASE_URL as ROBOLIST_BASE
from scrape_robolist import USER_AGENT, fetch, read_category

WATCH_DIR = Path(__file__).resolve().parent / "rival_watch"
CATEGORY_DELAY_SECONDS = 5.0
# Category pages serve at most ~500 robot links; no pagination params work
# (verified 2026-07-22: ?page/?offset/?limit all return the same 500).
# A category at or above this is truncated, so its diffs can include churn
# around the cutoff rather than real additions/removals.
CATEGORY_PAGE_CAP = 500

NOTION_BASE = "https://petrnovikov.notion.site"
NOTION_COLLECTION_ID = "aeb69882-af63-4817-a35d-2c825eef7290"
NOTION_VIEW_ID = "59126cdf-c7b5-419d-8145-900d7f65831b"
NOTION_SPACE_ID = "312de948-17bf-4a2f-9f2c-638818e53c0a"

APAROBOT_SITEMAP = "https://www.aparobot.com/sitemap.xml"

RAGADMIN_BASE = "https://ragadmin.robotaigeek.com/api/v1"

# Fallback if homepage discovery breaks; verified 2026-07-22.
ROBOLIST_CATEGORIES = [
    "agricultural",
    "agv",
    "amr-warehouse",
    "autonomous-vehicle",
    "cleaning",
    "cobot",
    "delivery",
    "exoskeleton",
    "hospitality-service",
    "humanoid",
    "industrial-arm",
    "quadruped",
    "surgical-medical",
]


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Encoding": "identity",
            "Connection": "close",
        }
    )
    return session


def discover_robolist_categories(session: requests.Session) -> list[str]:
    try:
        html = fetch(session, f"{ROBOLIST_BASE}/")
    except requests.RequestException as exc:
        print(f"  Homepage fetch failed ({exc}); using known category list.")
        return list(ROBOLIST_CATEGORIES)
    slugs = sorted(set(re.findall(r'href="/categories/([a-z0-9-]+)"', html)))
    if not slugs:
        print("  No category links on homepage; using known category list.")
        return list(ROBOLIST_CATEGORIES)
    known_only = set(ROBOLIST_CATEGORIES) - set(slugs)
    if known_only:
        print(f"  Categories gone from homepage (still trying): {sorted(known_only)}")
        slugs = sorted(set(slugs) | known_only)
    return slugs


def snapshot_robolist(session: requests.Session) -> dict[str, Any]:
    categories = discover_robolist_categories(session)
    print(f"  Categories: {len(categories)}")
    robots: dict[str, dict[str, Any]] = {}
    category_counts: dict[str, int] = {}
    errors: dict[str, str] = {}
    for index, category in enumerate(categories, start=1):
        try:
            listed = read_category(session, category)
        except (requests.RequestException, RuntimeError) as exc:
            errors[category] = str(exc)
            print(f"  [{index}/{len(categories)}] {category}: FAILED ({exc})")
            continue
        category_counts[category] = len(listed)
        if len(listed) >= CATEGORY_PAGE_CAP:
            print(f"    (at the {CATEGORY_PAGE_CAP}-link page cap — list truncated)")
        for robot in listed:
            # A slug can appear in one category only in practice; keep first.
            robots.setdefault(
                robot["slug"],
                {"name": robot["name"], "category": category},
            )
        print(f"  [{index}/{len(categories)}] {category}: {len(listed)}")
        if index < len(categories):
            time.sleep(CATEGORY_DELAY_SECONDS)
    return {
        "rival": "robolist",
        "fetched_at": utcnow(),
        "total_robots": len(robots),
        "category_counts": dict(sorted(category_counts.items())),
        "errors": errors,
        "items": dict(sorted(robots.items())),
    }


def snapshot_notion() -> dict[str, Any]:
    def post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = requests.post(
            NOTION_BASE + path,
            json=payload,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=(10, 30),
        )
        response.raise_for_status()
        return response.json()

    query = post(
        "/api/v3/queryCollection?src=reset",
        {
            "source": {
                "type": "collection",
                "id": NOTION_COLLECTION_ID,
                "spaceId": NOTION_SPACE_ID,
            },
            "collectionView": {"id": NOTION_VIEW_ID, "spaceId": NOTION_SPACE_ID},
            "loader": {
                "reducers": {
                    "collection_group_results": {"type": "results", "limit": 3000}
                },
                "searchQuery": "",
                "userTimeZone": "UTC",
            },
        },
    )
    chunk = post(
        "/api/v3/loadCachedPageChunkV2",
        {
            "page": {"id": "cabb6b9c-1937-4b9e-8c7b-4b2e1fb48c0b"},
            "limit": 30,
            "cursor": {"stack": []},
            "chunkNumber": 0,
            "verticalColumns": False,
        },
    )
    coll = chunk["recordMap"]["collection"][NOTION_COLLECTION_ID]["value"]
    if "value" in coll:
        coll = coll["value"]
    prop_by_name = {prop["name"]: key for key, prop in coll["schema"].items()}

    def plain(block: dict[str, Any], prop: str) -> str:
        parts = block.get("properties", {}).get(prop_by_name.get(prop, ""), [])
        return "".join(part[0] for part in parts if isinstance(part, list))

    blocks = query.get("recordMap", {}).get("block", {})
    block_ids = (
        query["result"]["reducerResults"]["collection_group_results"].get(
            "blockIds", []
        )
    )
    companies: dict[str, dict[str, str]] = {}
    for block_id in block_ids:
        block = blocks.get(block_id, {}).get("value", {})
        if "value" in block:
            block = block["value"]
        name = plain(block, "Company name")
        if not name:
            continue
        companies[name] = {
            "country": plain(block, "Country"),
            "type": plain(block, "Product type"),
        }
    return {
        "rival": "notion",
        "fetched_at": utcnow(),
        "total_companies": len(companies),
        "items": dict(sorted(companies.items())),
    }


def snapshot_aparobot(session: requests.Session) -> dict[str, Any]:
    """Read robot and company slugs from aparobot.com's public sitemap.

    One request per run. Their robots.txt advertises the sitemap and sets no
    disallow rules, so this is the lightest polite way to track the catalog.
    """
    xml = fetch(session, APAROBOT_SITEMAP)
    locations = re.findall(r"<loc>([^<]+)</loc>", xml)
    robots: dict[str, dict[str, Any]] = {}
    companies: dict[str, dict[str, Any]] = {}
    section_counts: dict[str, int] = {}
    for location in locations:
        parts = location.split("/")
        if len(parts) < 5:
            continue
        section, slug = parts[3], parts[-1]
        if not slug:
            continue
        section_counts[section] = section_counts.get(section, 0) + 1
        if section == "robots":
            robots[slug] = {"name": slug}
        elif section == "companies":
            companies[slug] = {"name": slug}
    return {
        "rival": "aparobot",
        "fetched_at": utcnow(),
        "total_robots": len(robots),
        "total_companies": len(companies),
        "section_counts": dict(sorted(section_counts.items())),
        "items": dict(sorted(robots.items())),
        "companies": dict(sorted(companies.items())),
    }


def snapshot_self() -> dict[str, Any] | None:
    api_key = os.environ.get("IMPORT_SYNC_API_KEY") or os.environ.get(
        "IMPORT_SYNC_API_KEY_PROD"
    )
    if not api_key:
        print("  IMPORT_SYNC_API_KEY not set; skipping self snapshot.")
        return None
    headers = {"X-API-Key": api_key, "User-Agent": USER_AGENT}

    def count(url: str) -> int:
        response = requests.get(url, headers=headers, timeout=(10, 60))
        response.raise_for_status()
        return int(response.json()["count"])

    robots_url = f"{RAGADMIN_BASE}/robots/robots/?page_size=1"
    return {
        "rival": "self",
        "fetched_at": utcnow(),
        "total_robots": count(robots_url),
        "published_robots": count(f"{robots_url}&status=published"),
        "companies": count(f"{RAGADMIN_BASE}/companies/?page_size=1"),
    }


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def snapshot_dir(rival: str) -> Path:
    directory = WATCH_DIR / rival
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def previous_snapshots(rival: str) -> list[Path]:
    return sorted(snapshot_dir(rival).glob("*.json"))


def save_snapshot(snapshot: dict[str, Any]) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    path = snapshot_dir(snapshot["rival"]) / f"{stamp}.json"
    path.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return path


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def diff_items(
    old: dict[str, Any], new: dict[str, Any], label: str
) -> list[str]:
    lines: list[str] = []
    old_items = old.get("items", {})
    new_items = new.get("items", {})
    added = sorted(set(new_items) - set(old_items))
    removed = sorted(set(old_items) - set(new_items))
    lines.append(
        f"{label}: {len(old_items)} -> {len(new_items)} "
        f"(+{len(added)} / -{len(removed)})"
    )
    for key in added:
        detail = new_items[key]
        extra = detail.get("category") or detail.get("country") or ""
        name = detail.get("name") or key
        lines.append(f"  + {name} ({extra})" if extra else f"  + {name}")
    for key in removed:
        detail = old_items[key]
        name = detail.get("name") or key
        lines.append(f"  - {name}")
    return lines


def report_diff(old: dict[str, Any], new: dict[str, Any]) -> str:
    rival = new["rival"]
    lines = [
        f"== {rival}: {old['fetched_at']} -> {new['fetched_at']} ==",
    ]
    if rival == "robolist":
        lines += diff_items(old, new, "robots")
        old_counts = old.get("category_counts", {})
        new_counts = new.get("category_counts", {})
        for category in sorted(set(old_counts) | set(new_counts)):
            before, after = old_counts.get(category), new_counts.get(category)
            if before != after:
                lines.append(f"  {category}: {before} -> {after}")
        capped = [
            category
            for category, count in new_counts.items()
            if count >= CATEGORY_PAGE_CAP
        ]
        if capped:
            lines.append(
                f"  note: {', '.join(sorted(capped))} at the "
                f"{CATEGORY_PAGE_CAP}-link page cap; adds/removes there may "
                "be cutoff churn, not real changes"
            )
    elif rival == "notion":
        lines += diff_items(old, new, "companies")
    elif rival == "aparobot":
        lines += diff_items(old, new, "robots")
        old_companies = {"items": old.get("companies", {})}
        new_companies = {"items": new.get("companies", {})}
        lines += diff_items(old_companies, new_companies, "companies")
    elif rival == "self":
        for field in ("total_robots", "published_robots", "companies"):
            before, after = old.get(field), new.get(field)
            marker = "" if before == after else "  <-- changed"
            lines.append(f"  {field}: {before} -> {after}{marker}")
    return "\n".join(lines)


def run_rival(rival: str, diff_only: bool) -> None:
    print(f"Watching {rival}...")
    if diff_only:
        existing = previous_snapshots(rival)
        if len(existing) < 2:
            print("  Need at least two snapshots to diff.")
            return
        print(report_diff(load(existing[-2]), load(existing[-1])))
        return

    if rival == "robolist":
        snapshot = snapshot_robolist(make_session())
    elif rival == "notion":
        snapshot = snapshot_notion()
    elif rival == "aparobot":
        snapshot = snapshot_aparobot(make_session())
    else:
        maybe = snapshot_self()
        if maybe is None:
            return
        snapshot = maybe

    earlier = previous_snapshots(rival)
    path = save_snapshot(snapshot)
    print(f"  Snapshot saved: {path.relative_to(WATCH_DIR.parent)}")
    if earlier:
        print(report_diff(load(earlier[-1]), snapshot))
    else:
        print("  First snapshot — nothing to diff yet.")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(
        description="Snapshot rival catalogs and report changes."
    )
    parser.add_argument(
        "--rival",
        choices=["robolist", "aparobot", "notion", "self", "all"],
        default="all",
    )
    parser.add_argument(
        "--diff-only",
        action="store_true",
        help="Diff the two most recent snapshots without fetching.",
    )
    args = parser.parse_args()
    rivals = (
        ["robolist", "aparobot", "notion", "self"]
        if args.rival == "all"
        else [args.rival]
    )
    for rival in rivals:
        run_rival(rival, args.diff_only)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
