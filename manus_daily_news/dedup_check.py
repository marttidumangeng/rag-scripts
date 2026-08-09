#!/usr/bin/env python3
"""Claim-level dedup for the RAI daily news agent — file-based, no browsing.

Replaces "crawl the live site's last 14 days" with a local published log.
The agent appends every published/packaged story to the log after each run;
dedup then costs one file read instead of dozens of browser steps.

Log: state/published_log.jsonl — one JSON object per line:
    {"date": "2026-08-05", "lane": "news", "title": "...", "url": "...",
     "companies": ["Unitree"], "event_type": "funding"}

Commands:
  check   — test one story or a scan_delta file against the last N days
      python3 dedup_check.py check --title "..." --companies "Unitree,Fourier" \
          --event-type funding
      python3 dedup_check.py check --candidates out/scan_delta_20260805.json
  append  — record published/packaged stories after a run
      python3 dedup_check.py append --date 2026-08-05 --lane news \
          --title "..." --url https://... --companies "Unitree" \
          --event-type funding
      python3 dedup_check.py append --from-json packaged_stories.json
  seed    — bulk-load historical entries (same JSON list format as --from-json)

Verdicts: duplicate-claim (same company + same event type within window),
duplicate-title (title similarity >= 0.75), pass.
Exit code for `check`: 0 = all pass, 2 = at least one duplicate.
Stdlib only.
"""
import argparse
import datetime as dt
import difflib
import json
import re
import sys
from pathlib import Path

WINDOW_DAYS = 14
TITLE_SIM_THRESHOLD = 0.75

# groups of interchangeable event-type words; extend as coverage grows
EVENT_SYNONYMS = [
    {"funding", "investment", "raise", "series", "financing", "capital"},
    {"launch", "unveil", "release", "debut", "announce", "introduce"},
    {"partnership", "collaboration", "alliance", "agreement", "mou", "deal"},
    {"acquisition", "merger", "acquire", "buyout", "takeover"},
    {"ipo", "listing", "public offering", "prospectus"},
    {"earnings", "results", "quarterly", "revenue", "financial"},
    {"order", "contract", "deployment", "delivery", "rollout", "installation"},
    {"regulation", "policy", "standard", "certification", "approval", "law"},
    {"award", "prize", "competition", "record"},
    {"factory", "plant", "facility", "expansion", "production"},
]


def norm(s):
    return re.sub(r"[^\w\s一-鿿]", " ", (s or "").lower()).strip()


def norm_company(s):
    s = norm(s)
    return re.sub(
        r"\b(inc|corp|corporation|co|ltd|llc|gmbh|ag|sa|robotics|robot|"
        r"technologies|technology|holdings|group|international|limited)\b",
        "", s).strip()


def event_group(event_type):
    words = set(norm(event_type).split())
    for i, group in enumerate(EVENT_SYNONYMS):
        if words & group:
            return i
    return None


def title_similarity(a, b):
    return difflib.SequenceMatcher(None, norm(a), norm(b)).ratio()


def load_log(path, window_days, today):
    if not path.exists():
        return []
    cutoff = today - dt.timedelta(days=window_days)
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
            if dt.date.fromisoformat(e.get("date", "1970-01-01")) >= cutoff:
                entries.append(e)
        except (json.JSONDecodeError, ValueError):
            continue
    return entries


def check_story(story, log, today=None):
    """Returns list of {verdict, against} matches (empty = pass)."""
    matches = []
    s_companies = {norm_company(c) for c in story.get("companies", []) if c}
    s_group = event_group(story.get("event_type", ""))
    s_title = story.get("title", "")

    for e in log:
        e_companies = {norm_company(c) for c in e.get("companies", []) if c}
        if not e_companies and s_companies:
            # CSV-log rows carry no company field; match names in the title
            e_title_n = norm(e.get("title", ""))
            e_companies = {c for c in s_companies if c and c in e_title_n}
        shared = {c for c in (s_companies & e_companies) if c}

        # SKILL 4.1.3: 5-day company-recency rule
        if shared and today:
            try:
                days = (today - dt.date.fromisoformat(e.get("date", ""))).days
            except ValueError:
                days = None
            if days is not None and 0 <= days <= 5:
                matches.append({
                    "verdict": "company-recency-5day",
                    "company": sorted(shared),
                    "note": "publish only if this is a materially different "
                            "Tier 1 development (SKILL.md 4.1.3)",
                    "against": {"date": e.get("date"), "title": e.get("title")},
                })
        if shared and s_group is not None \
                and event_group(e.get("event_type", "")) == s_group:
            matches.append({
                "verdict": "duplicate-claim",
                "company": sorted(shared),
                "against": {"date": e.get("date"), "title": e.get("title"),
                            "event_type": e.get("event_type")},
            })
            continue
        if s_title and e.get("title"):
            sim = title_similarity(s_title, e["title"])
            if sim >= TITLE_SIM_THRESHOLD:
                matches.append({
                    "verdict": "duplicate-title",
                    "similarity": round(sim, 2),
                    "against": {"date": e.get("date"), "title": e.get("title")},
                })
    return matches


def load_csv_log(path, window_days, today):
    """SKILL.md references/published_articles_log.csv -> log entries."""
    import csv as _csv
    cutoff = today - dt.timedelta(days=window_days)
    entries = []
    try:
        with open(path, encoding="utf-8-sig", newline="") as f:
            for r in _csv.DictReader(f):
                date = (r.get("publish_date") or "").strip()[:10]
                try:
                    if dt.date.fromisoformat(date) < cutoff:
                        continue
                except ValueError:
                    continue
                entries.append({
                    "date": date, "lane": r.get("destination_lane", ""),
                    "title": r.get("headline_en") or r.get("headline") or "",
                    "url": r.get("source_url", ""), "companies": [],
                    "event_type": r.get("category", ""),
                })
    except OSError:
        pass
    return entries


def cmd_check(args, log_path):
    today = dt.date.fromisoformat(args.date) if args.date else dt.date.today()
    log = load_log(log_path, args.window, today)
    if args.csv_log:
        log += load_csv_log(args.csv_log, args.window, today)

    stories = []
    if args.candidates:
        data = json.loads(Path(args.candidates).read_text(encoding="utf-8"))
        for c in data.get("candidates", data if isinstance(data, list) else []):
            stories.append({
                "title": c.get("title", ""),
                "companies": [c.get("source", "")],
                "event_type": " ".join(c.get("keyword_hits", [])),
                "url": c.get("url", ""),
            })
    else:
        if not args.title:
            sys.exit("check needs --title or --candidates")
        stories.append({
            "title": args.title,
            "companies": [c.strip() for c in (args.companies or "").split(",")
                          if c.strip()],
            "event_type": args.event_type or "",
        })

    any_dup = False
    report = []
    for s in stories:
        m = check_story(s, log, today)
        verdict = m[0]["verdict"] if m else "pass"
        if m:
            any_dup = True
        report.append({"title": s["title"], "url": s.get("url", ""),
                       "verdict": verdict, "matches": m})

    print(json.dumps({"window_days": args.window, "log_entries": len(log),
                      "results": report}, ensure_ascii=False, indent=1))
    sys.exit(2 if any_dup else 0)


def cmd_append(args, log_path):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    entries = []
    if args.from_json:
        data = json.loads(Path(args.from_json).read_text(encoding="utf-8"))
        entries = data if isinstance(data, list) else [data]
    else:
        if not (args.date and args.title):
            sys.exit("append needs --date and --title (or --from-json)")
        entries = [{
            "date": args.date, "lane": args.lane or "news",
            "title": args.title, "url": args.url or "",
            "companies": [c.strip() for c in (args.companies or "").split(",")
                          if c.strip()],
            "event_type": args.event_type or "",
        }]
    with log_path.open("a", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    print(f"appended {len(entries)} entries to {log_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["check", "append", "seed"])
    ap.add_argument("--log", default="state/published_log.jsonl")
    ap.add_argument("--window", type=int, default=WINDOW_DAYS)
    ap.add_argument("--date")
    ap.add_argument("--lane", choices=["news", "article", "video"])
    ap.add_argument("--title")
    ap.add_argument("--url")
    ap.add_argument("--companies", help="comma-separated")
    ap.add_argument("--event-type")
    ap.add_argument("--candidates", help="scan_delta JSON to bulk-check")
    ap.add_argument("--csv-log", help="also check the skill's "
                    "references/published_articles_log.csv")
    ap.add_argument("--from-json", help="JSON list of entries to append/seed")
    args = ap.parse_args()

    log_path = Path(args.log)
    if args.command == "check":
        cmd_check(args, log_path)
    else:  # append and seed share behavior
        cmd_append(args, log_path)


if __name__ == "__main__":
    main()
