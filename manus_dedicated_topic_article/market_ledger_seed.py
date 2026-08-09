#!/usr/bin/env python3
"""Seeds the Market-Development Ledger for an ARPI dedicated-topic article
from data the daily news pipeline already collected, replacing the broad
90-day browser scan with a file query plus targeted RSS pulls.

Sources, in order of preference:
  1. Daily scan deltas (/home/ubuntu/rai_scan/out/scan_delta_*.json) —
     first-hand-source developments with dates, URLs, and descriptions.
  2. The dedup published log — what the site already covered (context and
     series-continuity leads, marked origin=published_log).
  3. Targeted RSS pulls: registry sources whose name/relevance/keywords
     match the topic get their feeds fetched live (only when --registry
     is given). Degrades gracefully: with no scan deltas available this
     still produces an RSS-only seed.

The output is a SEED: candidate developments matched by keyword. The agent
applies the v8/v9 relevance gate and Tier-1 verification on top; this
script does not decide what goes in the article.

Usage:
    python3 market_ledger_seed.py --assignment assignment.json \
        --keywords "amr,agv,autonomous mobile robot,automated guided vehicle" \
        --scan-dir /home/ubuntu/rai_scan/out \
        --published-log /home/ubuntu/rai_scan/state/published_log.jsonl \
        --registry /home/ubuntu/rai_scan/registry_v4_20260805.csv \
        --out ledger_seed.json

Keywords: pass explicitly with --keywords (recommended; include synonyms
and abbreviation expansions). Falls back to tokens from the assignment's
asset class. Matching is case-insensitive substring, so CJK terms work.
Stdlib only.
"""
import argparse
import csv
import datetime as dt
import glob
import gzip
import html
import io
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

UA = "RAIScanBot/1.0 (+https://robotaigeek.com; topic ledger seed)"
TIMEOUT = 15
MAX_ITEMS = 60
FEED_URL_RE = re.compile(r"(https?://\S+)")


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        raw = resp.read(2_000_000)
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
        return raw.decode(resp.headers.get_content_charset() or "utf-8",
                          "replace")


def parse_feed(text):
    text = re.sub(r"^\s*<\?xml[^>]*\?>", "", text, count=1)
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []
    items = []
    for el in root.iter():
        if el.tag.rsplit("}", 1)[-1].lower() not in ("item", "entry"):
            continue
        title = link = pub = ""
        for c in el:
            t = c.tag.rsplit("}", 1)[-1].lower()
            if t == "title":
                title = (c.text or "").strip()
            elif t == "link":
                link = (c.get("href") or c.text or "").strip() or link
            elif t in ("pubdate", "published", "updated", "date"):
                pub = pub or (c.text or "").strip()
        if title:
            items.append({"title": html.unescape(title), "url": link,
                          "published": pub})
    return items


def parse_date(s):
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s or "")
    if m:
        return dt.date(*map(int, m.groups()))
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z"):
        try:
            return dt.datetime.strptime((s or "").strip()[:31], fmt).date()
        except ValueError:
            continue
    return None


def matches(keywords, *texts):
    blob = " ".join(t or "" for t in texts).lower()
    return [k for k in keywords if k in blob]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--assignment", help="assignment.json from assignment_lookup")
    ap.add_argument("--keywords", help="comma-separated topic keywords")
    ap.add_argument("--scan-dir", default="scan_history",
                    help="directory of scan_delta_*.json copies from the "
                         "daily news pipeline; empty = RSS-only mode")
    ap.add_argument("--published-log", default="scan_history/published_log.jsonl",
                    help="optional copy of the daily pipeline's dedup log")
    ap.add_argument("--registry", help="registry CSV for targeted RSS pulls")
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--max-feeds", type=int, default=20)
    ap.add_argument("--out", default="ledger_seed.json")
    args = ap.parse_args()

    keywords = []
    if args.keywords:
        keywords = [k.strip().lower() for k in args.keywords.split(",")
                    if k.strip()]
    elif args.assignment:
        a = json.loads(Path(args.assignment).read_text(encoding="utf-8"))
        keywords = [w.lower() for w in re.split(r"[/\s]+", a["asset_class"])
                    if len(w) > 2]
    if not keywords:
        sys.exit("no keywords: pass --keywords or --assignment")

    today = dt.date.today()
    cutoff = today - dt.timedelta(days=args.days)
    entries, seen_urls = [], set()

    def add(entry):
        key = entry.get("url") or entry["title"]
        if key in seen_urls:
            return
        seen_urls.add(key)
        entries.append(entry)

    # sources whose registry relevance matches the topic: their candidates
    # count even when the individual headline lacks a keyword
    topic_sources = set()
    if args.registry and Path(args.registry).exists():
        with open(args.registry, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                if matches(keywords, r.get("source_name"),
                           r.get("robotics_relevance"),
                           r.get("watch_keywords"), r.get("notes")):
                    topic_sources.add(r["source_name"])

    # 1. daily scan deltas
    delta_files = sorted(glob.glob(str(Path(args.scan_dir) / "scan_delta_*.json")))
    for f in delta_files:
        try:
            d = json.loads(Path(f).read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for c in d.get("candidates", []):
            hit = matches(keywords, c.get("title"), c.get("description"),
                          " ".join(c.get("keyword_hits", [])))
            if not hit and c.get("source") in topic_sources:
                hit = ["(source-match)"]
            if not hit:
                continue
            date = parse_date(c.get("published")) or parse_date(d.get("date"))
            if date and date < cutoff:
                continue
            add({"date": str(date or d.get("date")), "title": c.get("title"),
                 "source": c.get("source"), "url": c.get("url"),
                 "snippet": (c.get("description") or "")[:300],
                 "matched": hit, "origin": "scan_delta"})

    # 2. published log (site's own prior coverage: context, not citations)
    log_path = Path(args.published_log)
    if log_path.exists():
        for line in log_path.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            hit = matches(keywords, e.get("title"),
                          " ".join(e.get("companies", [])), e.get("event_type"))
            if hit:
                add({"date": e.get("date"), "title": e.get("title"),
                     "source": "RobotAIGeek (own coverage)",
                     "url": e.get("url"), "snippet": "",
                     "matched": hit, "origin": "published_log"})

    # 3. targeted RSS pulls from topic-matching registry sources
    feeds_pulled = 0
    if args.registry and Path(args.registry).exists():
        with open(args.registry, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                if feeds_pulled >= args.max_feeds:
                    break
                rss = r.get("rss_or_api", "")
                m = FEED_URL_RE.search(rss) if rss and \
                    not rss.lower().startswith("none") else None
                if not m:
                    continue
                if not matches(keywords, r.get("source_name"),
                               r.get("robotics_relevance"),
                               r.get("watch_keywords"), r.get("notes")):
                    continue
                feeds_pulled += 1
                try:
                    for it in parse_feed(fetch(m.group(1))):
                        date = parse_date(it["published"])
                        if date and date < cutoff:
                            continue
                        hit = matches(keywords, it["title"]) or ["(source-match)"]
                        add({"date": str(date or ""), "title": it["title"],
                             "source": r["source_name"], "url": it["url"],
                             "snippet": "", "matched": hit, "origin": "rss"})
                except Exception:
                    continue

    entries.sort(key=lambda e: e.get("date") or "", reverse=True)
    dropped = max(0, len(entries) - MAX_ITEMS)
    entries = entries[:MAX_ITEMS]

    out = {
        "generated": str(today), "window_days": args.days,
        "keywords": keywords,
        "stats": {"scan_delta_files": len(delta_files),
                  "rss_feeds_pulled": feeds_pulled,
                  "entries": len(entries), "dropped_over_cap": dropped},
        "note": ("SEED ONLY: apply the relevance gate and Tier-1 "
                 "verification before using any entry in the article."),
        "entries": entries,
    }
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1),
                              encoding="utf-8")
    print(f"wrote {args.out}", file=sys.stderr)
    print(json.dumps(out["stats"], indent=2))


if __name__ == "__main__":
    main()
