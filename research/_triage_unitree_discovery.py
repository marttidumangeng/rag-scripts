#!/usr/bin/env python3
"""Triage Unitree discovery staging against DB + quality flags."""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from api_client import ResearchApiClient

STAGING = Path(__file__).resolve().parent / "staging" / "robots" / "unitree-robotics"


def norm(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).casefold()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def aliases(name: str) -> set[str]:
    n = norm(name)
    out = {n}
    out.add(re.sub(r"^unitree\s+", "", n).strip())
    out.add(re.sub(r"\s+(standard|exploration|version|edition|pro|air|edu|max|flagship)\b", " ", n))
    out = {re.sub(r"\s+", " ", x).strip() for x in out if x}
    return out


REVIEW_PATTERNS = (
    "lidar",
    "pump",
    "iron fist",
    "boxing",
    "remote operation",
    "teleoperation",
    "dex1",
    "dex2",
    "dex3",
    "dex5",
    "fire rescue",
)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    client = ResearchApiClient()
    existing = client.list_robots_for_company(109, page_size=50)
    exist_keys: set[str] = set()
    for row in existing:
        exist_keys |= aliases(row.get("name") or "")

    # This-run discoveries from evidence/report if present; else all staging json
    files = sorted(STAGING.glob("*.json"))
    print(f"DB robots: {len(existing)}")
    print(f"Staging JSON files: {len(files)}")

    recommend_import: list[dict] = []
    skip_dup: list[dict] = []
    review: list[dict] = []

    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        name = data.get("name") or path.stem
        url = data.get("url") or data.get("website_url") or ""
        keys = aliases(name)
        is_dup = bool(keys & exist_keys)
        blob = f"{name} {url}".casefold()
        needs_review = any(p in blob for p in REVIEW_PATTERNS)
        # also review if URL looks wrong / homepage-ish
        if url.rstrip("/") in {"https://www.unitree.com", "https://www.unitree.com/cn"}:
            needs_review = True
        if "boxing" in (url or "").casefold():
            needs_review = True

        row = {
            "file": path.name,
            "name": name,
            "url": url,
            "has_image": bool(data.get("image") or data.get("images")),
            "sources": [s.get("url") for s in (data.get("sources") or []) if s.get("url")],
        }
        if is_dup:
            skip_dup.append(row)
        elif needs_review:
            review.append(row)
        else:
            recommend_import.append(row)

    report = {
        "company_id": 109,
        "company": "Unitree Robotics",
        "db_count": len(existing),
        "recommend_import": recommend_import,
        "review_first": review,
        "skip_already_in_db": skip_dup,
    }
    out = Path(__file__).resolve().parent / "staging" / "reports" / "unitree_discovery_triage.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nRECOMMEND IMPORT ({len(recommend_import)}):")
    for r in recommend_import:
        img = "img" if r["has_image"] else "NO_IMG"
        print(f"  + {r['name']}  [{img}]  {r['url']}")

    print(f"\nREVIEW FIRST ({len(review)}) — accessories / kits / weak URL / components:")
    for r in review:
        print(f"  ? {r['name']}  {r['url']}")

    print(f"\nSKIP — already in DB ({len(skip_dup)}):")
    for r in skip_dup:
        print(f"  - {r['name']}")

    print(f"\nWrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
