#!/usr/bin/env python3
"""Deterministic editorial-assignment resolver for the ARPI Dedicated Topic
Writer. Replaces the manual date/calendar preflight in prompt v8.

Resolves RUN_DATE in Asia/Shanghai (fixed UTC+8, no DST), exact-matches the
Tab 4 row, derives Asset Class + Post Slot, extracts the matching Tab 5
Content Framework section, and computes the deliverable filenames.

Usage:
    python3 assignment_lookup.py --calendar ARPI_Content_Calendar_Strategy_v6.xlsx
    python3 assignment_lookup.py --calendar cal.xlsx --date 2026-08-06 \
        --out assignment.json

Exit codes (the v8 stop conditions, made mechanical):
    0 = assignment resolved, JSON written/printed
    2 = calendar file missing or unreadable
    3 = no Tab 4 row exactly matches RUN_DATE (no post scheduled)
    4 = no Tab 5 framework section matches the post slot

Requires openpyxl (pip install openpyxl).
"""
import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

TAB4 = "4. Week-by-Week (Wk 1–8)"
TAB5 = "5. Content Framework"
PHASE_WORDS = re.compile(
    r"\b(foundations?|up[- ]and[- ]com\w*|leaders?|focus|ground game)\b",
    re.IGNORECASE)
POST_HEADER_RE = re.compile(r"^Post\s+(\d+)\s*\|\s*(.+)$")


def shanghai_today():
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date()


def parse_week_label(label):
    """'Week 5\nAMR / AGV / Foundations' -> ('Week 5', 'AMR / AGV')."""
    parts = [p.strip() for p in str(label).splitlines() if p.strip()]
    week = parts[0] if parts else ""
    rest = " ".join(parts[1:])
    segs = [s.strip() for s in rest.split("/") if s.strip()]
    while segs and PHASE_WORDS.fullmatch(segs[-1]):
        segs.pop()
    asset = " / ".join(segs)
    asset = PHASE_WORDS.sub("", asset).strip(" /")
    return week, asset or rest


def load_articles(ws):
    """All dated, titled Tab 4 rows in date order."""
    out = []
    for r in ws.values:
        if len(r) >= 4 and isinstance(r[2], dt.datetime) and r[3]:
            week, asset = parse_week_label(r[0])
            out.append({
                "date": r[2].date(), "week_label": week, "asset_class": asset,
                "day": str(r[1] or "").strip(), "title": str(r[3]).strip(),
            })
    out.sort(key=lambda a: a["date"])
    return out


def load_frameworks(ws):
    """Tab 5 -> {slot: {post_title, purpose, subheaders: [{heading, guidance}]}}"""
    frameworks, current = {}, None
    for r in ws.values:
        c0 = str(r[0]).strip() if r[0] else ""
        c1 = str(r[1]).strip() if len(r) > 1 and r[1] else ""
        m = POST_HEADER_RE.match(c0)
        if m:
            current = {"post_title": m.group(2).strip(), "purpose": "",
                       "subheaders": []}
            frameworks[int(m.group(1))] = current
            continue
        if current is None or not c0:
            continue
        if c0.lower().startswith("purpose:"):
            current["purpose"] = c0.split(":", 1)[1].strip()
        elif c0.lower() == "subheader":
            continue  # column header row
        elif c1:
            current["subheaders"].append({"heading": c0, "guidance": c1})
    return frameworks


def sanitize(s):
    """'AMR / AGV' -> 'AMR_AGV', matching the established filename
    convention used by delivered packages."""
    return re.sub(r"_+", "_", re.sub(r"[^A-Za-z0-9]+", "_", s)).strip("_")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--calendar", required=True)
    ap.add_argument("--date", help="RUN_DATE YYYY-MM-DD (manual rerun); "
                                   "default = today in Asia/Shanghai")
    ap.add_argument("--out", help="write assignment JSON here as well")
    args = ap.parse_args()

    run_date = (dt.date.fromisoformat(args.date) if args.date
                else shanghai_today())

    try:
        import openpyxl
        wb = openpyxl.load_workbook(args.calendar, read_only=True)
        articles = load_articles(wb[TAB4])
        frameworks = load_frameworks(wb[TAB5])
    except Exception as e:
        print(f"STOP: calendar unreadable: {type(e).__name__}: {e}",
              file=sys.stderr)
        sys.exit(2)

    row = next((a for a in articles if a["date"] == run_date), None)
    if row is None:
        print(f"STOP: no Tab 4 row exactly matches RUN_DATE {run_date}. "
              "No post is scheduled; do not pick another slot.",
              file=sys.stderr)
        sys.exit(3)

    series = [a for a in articles if a["asset_class"] == row["asset_class"]]
    slot = series.index(row) + 1
    fw = frameworks.get(slot)
    if fw is None:
        print(f"STOP: no Tab 5 framework section for post slot {slot} "
              f"(asset class {row['asset_class']!r}).", file=sys.stderr)
        sys.exit(4)

    prior = [{"date": str(a["date"]), "title": a["title"],
              "slot": i + 1} for i, a in enumerate(series) if a["date"] < run_date]
    ymd = run_date.strftime("%Y%m%d")
    tag = sanitize(row["asset_class"])
    assignment = {
        "run_date": str(run_date),
        "editorial_timezone": "Asia/Shanghai (UTC+8)",
        "week_label": row["week_label"],
        "day": row["day"],
        "asset_class": row["asset_class"],
        "title": row["title"],
        "post_slot": slot,
        "framework": fw,
        "series_prior_posts": prior,
        "hero_filename": f"{ymd}_{tag}_Post{slot}_hero.jpg",
        "docx_filename": f"RobotAIGeek_Draft_{ymd}_{tag}_Post{slot}.docx",
    }
    text = json.dumps(assignment, ensure_ascii=False, indent=1)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out}", file=sys.stderr)
    print(text)


if __name__ == "__main__":
    main()
