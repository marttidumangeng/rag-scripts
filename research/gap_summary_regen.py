"""Regenerate gap_discovery_summary.md from the final cleaned staged_import.json.

The in-run write_summary() only reflects the most recent batch; this script
reports on the complete staged file after all runs and QA.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(__file__).resolve().parent / "staging" / "gap_discovery"
STAGED = BASE / "staged_import.json"
GAPS = BASE / "gap_manufacturers.json"
SUMMARY = BASE / "gap_discovery_summary.md"

d = json.loads(STAGED.read_text(encoding="utf-8"))
cos, robs = d["companies"], d["robots"]
low = d.get("low_signal_companies", [])
alias = d.get("skipped_alias_domains", [])
gaps_meta = json.loads(GAPS.read_text(encoding="utf-8")) if GAPS.exists() else {}

per_co = Counter(r["company_slug"] for r in robs)

src_counter: Counter = Counter()
for c in cos:
    for s in c.get("sources", []):
        t = s.get("title") or ""
        if t.startswith("Found via"):
            for src in t.replace("Found via", "").split(","):
                src_counter[src.strip()] += 1

cat_counter: Counter = Counter()
for c in cos:
    for cat in c.get("primary_focus", []):
        cat_counter[cat] += 1

now = datetime.now(timezone.utc).isoformat()
lines = [
    "# Manufacturer & Robot Gap Discovery — Summary",
    "",
    f"- Generated: {now}",
    f"- Prod baseline: 695 companies, 4533 robots (2026-07-29)",
    f"- Harvested (all sources, merged): {gaps_meta.get('merged_total', '?')} manufacturers",
    f"- New manufacturers not in prod (gap list): {gaps_meta.get('gaps_found', '?')}",
    f"- **Staged companies (validated website, QA-passed): {len(cos)}**",
    f"- **Staged robots (new, deduped vs prod): {len(robs)}**",
    f"- Companies with ≥1 staged robot: {sum(1 for c in cos if per_co.get(c['slug'], 0) > 0)}",
    f"- Low-signal companies (no website & no robots, kept for manual review): {len(low)}",
    f"- Skipped (resolved domain already in prod under another name): {len(alias)}",
    "",
    "## Discovery source contribution (staged companies)",
    "",
    "| Source | Companies |",
    "|---|---|",
]
for src, n in src_counter.most_common():
    lines.append(f"| {src} | {n} |")

lines += ["", "## Category distribution (staged companies)", "",
          "| Category | Companies |", "|---|---|"]
for cat, n in cat_counter.most_common(25):
    lines.append(f"| {cat} | {n} |")

lines += ["", "## Top staged manufacturers by robots found", "",
          "| Company | Website | Robots staged |", "|---|---|---|"]
by_robots = sorted(cos, key=lambda c: -per_co.get(c["slug"], 0))[:60]
for c in by_robots:
    lines.append(f"| {c['name']} | {c.get('website') or '—'} | {per_co.get(c['slug'], 0)} |")

lines += [
    "",
    "## Files",
    "",
    "| File | Purpose |",
    "|---|---|",
    "| `staging/gap_discovery/staged_import.json` | Review-ready staged data (companies + robots, QA-cleaned) |",
    "| `staging/gap_discovery/staged_import.raw.json` | Pre-QA raw staging (for rescue/debugging) |",
    "| `staging/gap_discovery/gap_manufacturers.json` | Full gap list incl. companies not yet staged |",
    "| `staging/gap_discovery/robots/{slug}/*.json` | Per-company robot staging files (import-ready) |",
    "| `staging/gap_discovery/local_sources_harvest.json` | LLM-extracted companies from user-provided lists |",
    "| `staging/reports/prod_baseline.json` | Prod dedupe baseline used by this run |",
    "",
    "## Next steps",
    "",
    "1. Review `staged_import.json` (companies + robots). Names/URLs only — specs need enrichment.",
    "2. Import companies first, then robots: `python cli.py import --dir staging/gap_discovery/robots/{slug}/ --dry-run`",
    "3. Enrich imported robots via the overnight enrichment workflow before approval.",
    "",
]
SUMMARY.write_text("\n".join(lines), encoding="utf-8")
print(f"wrote {SUMMARY} ({len(lines)} lines)")
