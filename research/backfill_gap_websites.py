#!/usr/bin/env python3
"""One-off backfill: add a validated `website` to existing gap entries.

The competitor gap list (staging/reports/competitor_gap_companies.json) was
generated before website resolution existed, so its entries carry no `website`.
Re-running full discovery is expensive (re-scrapes Robolist + RAG inventory);
this script only resolves the missing websites and writes them back in place.

For each entry (in `top_gaps` first, then optionally `all_gaps`) that has no
`website`, it resolves via Robolist → serper.dev, validates the URL, and stores
`website` + `website_source`. Both lists are updated (they hold independent
copies of the same companies after JSON round-trip), keyed by slug.

Usage:
  python -u backfill_gap_websites.py                 # top_gaps only (default)
  python -u backfill_gap_websites.py --limit 20      # first 20 missing
  python -u backfill_gap_websites.py --all-gaps      # also backfill all_gaps
  python -u backfill_gap_websites.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import requests

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from company_website_resolve import resolve_company_website  # noqa: E402

GAP_REPORT = _HERE / "staging" / "reports" / "competitor_gap_companies.json"


def _safe_print(*args: Any, **kwargs: Any) -> None:
    kwargs.setdefault("flush", True)
    try:
        print(*args, **kwargs)
    except UnicodeEncodeError:
        text = " ".join(str(a) for a in args)
        enc = getattr(sys.stdout, "encoding", None) or "utf-8"
        print(text.encode(enc, errors="replace").decode(enc, errors="replace"), **kwargs)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--limit", type=int, default=0, help="Max entries to resolve (0 = all missing)")
    p.add_argument("--all-gaps", action="store_true", help="Also backfill the full all_gaps list")
    p.add_argument("--dry-run", action="store_true", help="Resolve but do not write the file")
    p.add_argument("--delay", type=float, default=0.5, help="Seconds between lookups")
    args = p.parse_args()

    if not GAP_REPORT.exists():
        _safe_print(f"Gap report not found: {GAP_REPORT}")
        return 1

    data = json.loads(GAP_REPORT.read_text(encoding="utf-8"))
    top_gaps: list[dict[str, Any]] = data.get("top_gaps", [])
    all_gaps: list[dict[str, Any]] = data.get("all_gaps", [])

    targets = list(top_gaps)
    if args.all_gaps:
        seen_slugs = {c.get("slug") for c in targets}
        targets += [c for c in all_gaps if c.get("slug") not in seen_slugs]

    missing = [c for c in targets if not (c.get("website") or "").strip()]
    if args.limit and args.limit > 0:
        missing = missing[: args.limit]

    _safe_print(f"Resolving websites for {len(missing)} entries "
                f"(top_gaps={len(top_gaps)}, all_gaps={len(all_gaps)})")

    sess = requests.Session()
    resolved: dict[str, tuple[str, str]] = {}  # slug -> (website, method)
    for i, c in enumerate(missing, 1):
        slug = c.get("slug", "")
        name = c.get("name") or slug.replace("-", " ").title()
        website, method = resolve_company_website(
            name, slug, country=c.get("country"), session=sess,
        )
        if website:
            resolved[slug] = (website, method)
            _safe_print(f"  [{i}/{len(missing)}] {name}: {website} ({method})")
        else:
            _safe_print(f"  [{i}/{len(missing)}] {name}: no website resolved")
        time.sleep(args.delay)

    # Apply to BOTH lists (independent copies) keyed by slug.
    applied = 0
    for lst in (top_gaps, all_gaps):
        for c in lst:
            hit = resolved.get(c.get("slug", ""))
            if hit and not (c.get("website") or "").strip():
                c["website"], c["website_source"] = hit
                applied += 1

    _safe_print(f"\nResolved {len(resolved)} / {len(missing)} missing; "
                f"applied to {applied} entries across both lists.")

    if args.dry_run:
        _safe_print("[dry-run] not writing file.")
        return 0

    GAP_REPORT.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    _safe_print(f"Wrote: {GAP_REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
