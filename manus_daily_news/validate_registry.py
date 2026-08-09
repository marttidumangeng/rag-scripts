#!/usr/bin/env python3
"""Validation gate for the RAI first-hand source registry.

Every registry produced or updated by the registry-growth agent MUST pass this
before it is accepted as canonical. Guards against the column-shift corruption
found in the Jul-30 registry (35 rows with prose fragments in priority_tier).

Usage:
    python3 validate_registry.py registry_v4_20260805.csv
    python3 validate_registry.py registry.csv --json   # machine-readable report

Exit code 0 = pass (warnings allowed), 1 = blocking errors found.
Stdlib only — no dependencies.
"""
import argparse
import csv
import json
import re
import sys
from collections import Counter

REQUIRED_COLUMNS = [
    "region", "source_name", "source_name_local", "type", "subtype",
    "url_news", "url_home", "language", "rss_or_api", "update_frequency",
    "robotics_relevance", "priority_tier", "collection_route",
    "watch_keywords", "verification_role", "ticker", "origin", "notes",
]
TIERS = {"P0", "P1", "P2"}
FREQUENCIES = {"Daily", "Weekly", "Monthly", "Occasional", "Event-driven"}
ROUTE_PARTS = {
    "page scrape", "rss", "api", "wechat", "search query",
    "ipo calendar", "ir calendar", "exchange filings", "hkex filings",
}
URL_RE = re.compile(r"^https?://\S+$")
# rss_or_api convention: "RSS: <url>", "API: <name or url>", or "None — ..."
RSS_API_RE = re.compile(r"^(RSS|API):\s*\S+", re.IGNORECASE)


def check_route(route):
    """Routes combine parts with '+', e.g. 'page scrape + IPO calendar'."""
    if not route:
        return False
    parts = [p.strip().lower() for p in re.split(r"\+", route)]
    return all(p in ROUTE_PARTS for p in parts)


def validate(path):
    errors, warnings = [], []
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        cols = reader.fieldnames or []
        missing = [c for c in REQUIRED_COLUMNS if c not in cols]
        if missing:
            errors.append(f"missing columns: {missing}")
            return errors, warnings, 0
        rows = list(reader)

    seen_urls = Counter(r["url_news"].strip() for r in rows if r["url_news"].strip())
    seen_names = Counter(
        (r["source_name"].strip(), r["region"].strip()) for r in rows
    )

    for i, r in enumerate(rows, start=2):  # 1-based + header
        name = r["source_name"].strip() or f"<row {i}>"
        loc = f"row {i} ({name})"

        if None in r.values() or None in r:
            errors.append(f"{loc}: wrong number of fields (column shift?)")
            continue
        if r["priority_tier"].strip() not in TIERS:
            errors.append(
                f"{loc}: priority_tier={r['priority_tier']!r} not in P0/P1/P2 "
                "— likely column-shifted row"
            )
        if r["update_frequency"].strip() not in FREQUENCIES:
            errors.append(
                f"{loc}: update_frequency={r['update_frequency']!r} invalid"
            )
        if not check_route(r["collection_route"].strip()):
            errors.append(
                f"{loc}: collection_route={r['collection_route']!r} invalid"
            )
        if not URL_RE.match(r["url_news"].strip()):
            errors.append(f"{loc}: url_news={r['url_news']!r} is not a URL")
        if r["url_home"].strip() and not URL_RE.match(r["url_home"].strip()):
            warnings.append(f"{loc}: url_home={r['url_home']!r} is not a URL")
        if not r["source_name"].strip():
            errors.append(f"row {i}: empty source_name")
        if not r["region"].strip():
            errors.append(f"{loc}: empty region")

        rss = r["rss_or_api"].strip()
        if rss and not rss.lower().startswith("none"):
            if not RSS_API_RE.match(rss) and not URL_RE.match(rss):
                warnings.append(
                    f"{loc}: rss_or_api={rss!r} matches neither "
                    "'RSS: <url>' / 'API: <name>' / 'None...' nor a bare URL"
                )

    for url, n in seen_urls.items():
        if n > 1:
            warnings.append(f"duplicate url_news x{n}: {url}")
    for (nm, reg), n in seen_names.items():
        if n > 1:
            errors.append(f"duplicate source ({nm}, {reg}) x{n}")

    return errors, warnings, len(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("registry", help="path to registry CSV")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    errors, warnings, n = validate(args.registry)
    ok = not errors

    if args.json:
        print(json.dumps(
            {"ok": ok, "rows": n, "errors": errors, "warnings": warnings},
            ensure_ascii=False, indent=2,
        ))
    else:
        print(f"{args.registry}: {n} rows")
        for e in errors:
            print(f"  ERROR   {e}")
        for w in warnings:
            print(f"  warning {w}")
        print(f"RESULT: {'PASS' if ok else 'FAIL'} "
              f"({len(errors)} errors, {len(warnings)} warnings)")

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
