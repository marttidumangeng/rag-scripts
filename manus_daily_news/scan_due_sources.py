#!/usr/bin/env python3
"""Deterministic daily scan of the RAI first-hand source registry.

Replaces agent-driven browsing of ~472 sources with one script run:
  1. Selects today's DUE sources from the registry (priority tier +
     update frequency drive cadence — P0 daily, weekly/monthly rotate).
  2. Polls RSS/API-fed sources for new entries.
  3. Conditionally fetches page-scrape sources (ETag/Last-Modified) and
     diffs their link sets against the last run; new links = candidates.
  4. Fetches each candidate article once to extract title, description,
     og:image (hero candidate), and published time.
  5. Writes out/scan_delta_YYYYMMDD.json — the ONLY thing the drafting
     agent needs to read. Sources it cannot fetch (WeChat, JS-heavy,
     hard errors) are listed under needs_browser for targeted agent
     follow-up.

First run establishes the baseline (page-scrape diffs start on run 2;
RSS candidates appear immediately, filtered to the lookback window).

Usage:
    python3 scan_due_sources.py --registry registry_v4_20260805.csv
    python3 scan_due_sources.py --registry registry.csv --dry-run
    python3 scan_due_sources.py --registry registry.csv --tier P0 --limit 5

Stdlib only. State in ./state/, output in ./out/ (override with flags).
"""
import argparse
import concurrent.futures
import csv
import datetime as dt
import gzip
import hashlib
import html
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

UA = "RAIScanBot/1.0 (+https://robotaigeek.com; daily first-hand source scan)"
TIMEOUT = 15
MAX_RESPONSE_BYTES = 2_000_000  # slow-drip tarpits and huge pages get cut off
MAX_NEW_LINKS_PER_SOURCE = 10
MAX_LINK_HASHES = 2000
MAX_SEEN_RSS = 500
# Fetch window for feeds. Items older than the strict same-day rule are still
# collected (a feed's dates can be wrong) but are classified and quarantined
# into stale_excluded rather than handed to the drafting agent.
RSS_LOOKBACK_DAYS = 3

FEED_URL_RE = re.compile(r"(https?://\S+)")
A_TAG_RE = re.compile(
    r"<a\s[^>]*?href\s*=\s*[\"']([^\"'#]+)[\"'][^>]*>(.*?)</a>",
    re.IGNORECASE | re.DOTALL,
)
TAG_STRIP_RE = re.compile(r"<[^>]+>")
META_RE = re.compile(
    r"<meta\s[^>]*?(?:property|name)\s*=\s*[\"']([^\"']+)[\"'][^>]*?"
    r"content\s*=\s*[\"']([^\"']*)[\"']",
    re.IGNORECASE | re.DOTALL,
)
META_RE_REV = re.compile(
    r"<meta\s[^>]*?content\s*=\s*[\"']([^\"']*)[\"'][^>]*?"
    r"(?:property|name)\s*=\s*[\"']([^\"']+)[\"']",
    re.IGNORECASE | re.DOTALL,
)
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
SKIP_LINK_RE = re.compile(
    r"(mailto:|tel:|javascript:|\.(css|js|png|jpe?g|gif|svg|ico|webp|woff2?)([?#]|$)"
    r"|facebook\.com|twitter\.com|x\.com/|linkedin\.com|instagram\.com"
    r"|youtube\.com/(?!watch)|weibo\.com|/login|/signin|/cart|/privacy|/terms"
    r"|/cookie|/sitemap|/careers?/|/contact)",
    re.IGNORECASE,
)


def stable_hash(s):
    return int(hashlib.md5(s.encode("utf-8")).hexdigest()[:8], 16)


def sha1(s):
    return hashlib.sha1(s.encode("utf-8", "replace")).hexdigest()


def load_registry(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    seen, out = set(), []
    for r in rows:
        url = r["url_news"].strip()
        if not url or url in seen:
            continue  # registry lists some sources under two regions
        seen.add(url)
        out.append(r)
    return out


def is_due(row, date, force=False):
    """Cadence: P0/Daily every day; Weekly/Monthly rotate on a stable
    per-source slot; Event-driven P1 every 3 days; Occasional P1 weekly;
    Event-driven P2 weekly; Occasional P2 monthly."""
    if force:
        return True
    tier = row["priority_tier"].strip()
    freq = row["update_frequency"].strip()
    h = stable_hash(row["source_name"] + "|" + row["region"])
    weekday = date.weekday()
    dom = date.day
    ordinal = date.toordinal()

    if tier == "P0" or freq == "Daily":
        return True
    if freq == "Weekly":
        return h % 7 == weekday
    if freq == "Monthly":
        return (h % 28) + 1 == dom
    if freq == "Event-driven":
        return (ordinal % 3 == h % 3) if tier == "P1" else (h % 7 == weekday)
    if freq == "Occasional":
        return (h % 7 == weekday) if tier == "P1" else ((h % 28) + 1 == dom)
    return h % 7 == weekday  # unknown frequency: weekly


def feed_url_of(row):
    v = row["rss_or_api"].strip()
    if not v or v.lower().startswith("none"):
        return None
    m = FEED_URL_RE.search(v)
    return m.group(1) if m else None


def http_get(url, etag=None, last_modified=None):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "*/*",
        "Accept-Encoding": "gzip",
    })
    if etag:
        req.add_header("If-None-Match", etag)
    if last_modified:
        req.add_header("If-Modified-Since", last_modified)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read(MAX_RESPONSE_BYTES)
            if resp.headers.get("Content-Encoding", "") == "gzip" or \
                    raw[:2] == b"\x1f\x8b":
                try:
                    raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
                except OSError:
                    pass
            charset = resp.headers.get_content_charset() or "utf-8"
            return {
                "status": resp.status,
                "text": raw.decode(charset, "replace"),
                "etag": resp.headers.get("ETag"),
                "last_modified": resp.headers.get("Last-Modified"),
                "final_url": resp.url,
            }
    except urllib.error.HTTPError as e:
        if e.code == 304:
            return {"status": 304}
        return {"status": e.code, "error": f"HTTP {e.code}"}
    except Exception as e:  # timeouts, DNS, SSL, connection resets
        return {"status": 0, "error": f"{type(e).__name__}: {e}"}


def parse_feed(text):
    """Minimal RSS 2.0 / Atom parser -> [{id, title, link, published}]."""
    text = re.sub(r"^\s*<\?xml[^>]*\?>", "", text, count=1)
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []

    def local(tag):
        return tag.rsplit("}", 1)[-1].lower()

    items = []
    for el in root.iter():
        if local(el.tag) not in ("item", "entry"):
            continue
        title = link = pub = guid = None
        for c in el:
            t = local(c.tag)
            if t == "title":
                title = (c.text or "").strip()
            elif t == "link":
                link = (c.get("href") or c.text or "").strip() or link
            elif t in ("pubdate", "published", "updated", "date"):
                pub = pub or (c.text or "").strip()
            elif t in ("guid", "id"):
                guid = (c.text or "").strip()
        if title or link:
            items.append({
                "id": guid or link or title,
                "title": html.unescape(title or ""),
                "link": link or "",
                "published": pub or "",
            })
    return items


def parse_pubdate(s):
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z",
                "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
        try:
            d = dt.datetime.strptime(s.strip()[:31], fmt)
            return d.replace(tzinfo=None) if d.tzinfo else d
        except (ValueError, AttributeError):
            continue
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s or "")
    if m:
        return dt.datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


def extract_links(base_url, text):
    links = []
    for href, anchor in A_TAG_RE.findall(text):
        url = urllib.parse.urljoin(base_url, html.unescape(href.strip()))
        if not url.startswith("http") or SKIP_LINK_RE.search(url):
            continue
        label = html.unescape(TAG_STRIP_RE.sub(" ", anchor))
        label = re.sub(r"\s+", " ", label).strip()[:200]
        links.append((url.split("#")[0], label))
    return links


def extract_meta(text):
    meta = {}
    for pat, order in ((META_RE, (0, 1)), (META_RE_REV, (1, 0))):
        for m in pat.findall(text):
            key, val = m[order[0]].lower(), html.unescape(m[order[1]]).strip()
            if val and key not in meta:
                meta[key] = val
    title = None
    tm = TITLE_RE.search(text)
    if tm:
        title = html.unescape(TAG_STRIP_RE.sub("", tm.group(1))).strip()
    return {
        "title": meta.get("og:title") or title or "",
        "description": (meta.get("og:description")
                        or meta.get("description") or "")[:400],
        "og_image": meta.get("og:image") or "",
        "published": (meta.get("article:published_time")
                      or meta.get("date") or meta.get("pubdate") or ""),
    }


def run_bounded(fn, items, workers, deadline_ts):
    """Run fn(item) concurrently until done or the wall-clock deadline.
    Returns (results: {index: value}, abandoned: [index]). Hung threads are
    left behind (the process exits via os._exit at the end of main)."""
    ex = concurrent.futures.ThreadPoolExecutor(workers)
    futs = {ex.submit(fn, it): i for i, it in enumerate(items)}
    results, abandoned = {}, []
    try:
        for fut in concurrent.futures.as_completed(
                futs, timeout=max(1.0, deadline_ts - time.monotonic())):
            i = futs[fut]
            try:
                results[i] = fut.result()
            except Exception as e:
                results[i] = e
    except concurrent.futures.TimeoutError:
        pass
    for fut, i in futs.items():
        if i not in results:
            abandoned.append(i)
    ex.shutdown(wait=False, cancel_futures=True)
    return results, abandoned


def classify_date(published, run_date):
    """Strict same-day gate (SKILL.md Section 4).

    Returns (date_status, age_days, iso_date). A source in a timezone ahead
    of the run date can legitimately stamp run_date+1, so that still counts
    as same-day. Anything earlier than run_date is prior-day or stale and is
    NOT drafting-eligible without explicit user approval. Page-scrape links
    carry no date: they are 'unverified' and the agent must confirm the
    publication date at the source before drafting.
    """
    d = parse_pubdate(published or "")
    if d is None:
        return "unverified", None, ""
    day = d.date() if isinstance(d, dt.datetime) else d
    age = (run_date - day).days
    if age <= 0:
        return "same-day", age, day.isoformat()
    if age == 1:
        return "prior-day", age, day.isoformat()
    return "stale", age, day.isoformat()


def keyword_hits(row, *texts):
    kws = [k.strip().lower()
           for k in re.split(r"[;,]", row.get("watch_keywords") or "") if k.strip()]
    blob = " ".join(t or "" for t in texts).lower()
    return [k for k in kws if k and k in blob]


def scan_source(row, state, cutoff):
    """Returns (candidates, source_state, note). note in
    (rss, scrape, 304, no-change, needs_browser, error:<msg>)."""
    key = row["url_news"].strip()
    st = dict(state.get(key, {}))
    route = row["collection_route"].strip().lower()

    if "wechat" in route and "scrape" not in route:
        return [], st, "needs_browser"

    feed = feed_url_of(row)
    if feed:
        resp = http_get(feed)
        if resp["status"] != 200:
            return [], st, f"error:{resp.get('error', resp['status'])}"
        items = parse_feed(resp["text"])
        if not items:
            return [], st, "error:feed-unparseable"
        seen = set(st.get("seen_rss", []))
        fresh = []
        for it in items:
            if it["id"] in seen:
                continue
            pub = parse_pubdate(it["published"])
            if pub and pub < cutoff:
                continue
            fresh.append({"url": it["link"], "title": it["title"],
                          "published": it["published"], "via": "rss"})
        st["seen_rss"] = ([it["id"] for it in items] +
                          list(seen))[:MAX_SEEN_RSS]
        if len(fresh) > MAX_NEW_LINKS_PER_SOURCE:
            fresh = fresh[:MAX_NEW_LINKS_PER_SOURCE]
            fresh[-1]["note"] = "source had more new items; cap applied"
        return fresh, st, "rss"

    resp = http_get(key, st.get("etag"), st.get("last_modified"))
    if resp["status"] == 304:
        return [], st, "304"
    if resp["status"] != 200:
        return [], st, f"error:{resp.get('error', resp['status'])}"

    links = extract_links(resp.get("final_url") or key, resp["text"])
    if len(links) < 3:
        return [], st, "needs_browser"  # likely JS-rendered page

    old = set(st.get("link_hashes", []))
    first_run = not old
    fresh = []
    for url, label in links:
        if sha1(url) not in old and not first_run:
            fresh.append({"url": url, "title": label, "published": "",
                          "via": "scrape"})
    fresh = fresh[:MAX_NEW_LINKS_PER_SOURCE]
    st["etag"] = resp.get("etag")
    st["last_modified"] = resp.get("last_modified")
    merged = [sha1(u) for u, _ in links] + list(old)
    st["link_hashes"] = list(dict.fromkeys(merged))[:MAX_LINK_HASHES]
    if first_run:
        return [], st, "baseline"
    return fresh, st, ("scrape" if fresh else "no-change")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--registry", required=True)
    ap.add_argument("--state-dir", default="state")
    ap.add_argument("--out-dir", default="out")
    ap.add_argument("--date", help="YYYY-MM-DD (default: today UTC)")
    ap.add_argument("--max-candidates", type=int, default=120,
                    help="cap on candidate pages fetched for metadata")
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--deadline", type=int, default=300,
                    help="hard wall-clock limit in seconds for the whole "
                         "run; unfinished sources are reported as "
                         "deadline-abandoned, never hang the script")
    ap.add_argument("--force-all", action="store_true",
                    help="scan every source regardless of cadence")
    ap.add_argument("--tier", choices=["P0", "P1", "P2"],
                    help="restrict to one tier (testing)")
    ap.add_argument("--limit", type=int, help="scan at most N sources (testing)")
    ap.add_argument("--allow-prior-day", action="store_true",
                    help="widen the strict same-day rule to include "
                         "previous-day items (requires explicit user "
                         "approval per SKILL.md Section 4)")
    ap.add_argument("--missing-baseline-only", action="store_true",
                    help="scan ONLY sources that have never completed a "
                         "first fetch (no link hashes, no seen RSS ids). "
                         "Use with --force-all to top up an incomplete "
                         "baseline without refetching healthy sources.")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the due set and exit without fetching")
    args = ap.parse_args()

    date = (dt.date.fromisoformat(args.date) if args.date
            else dt.datetime.now(dt.timezone.utc).date())
    cutoff = (dt.datetime.combine(date, dt.time.min)
              - dt.timedelta(days=RSS_LOOKBACK_DAYS))

    rows = load_registry(args.registry)
    due = [r for r in rows if is_due(r, date, args.force_all)]
    if args.tier:
        due = [r for r in due if r["priority_tier"].strip() == args.tier]
    if args.limit:
        due = due[:args.limit]

    state_dir = Path(args.state_dir)
    out_dir = Path(args.out_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    state_path = state_dir / "scan_state.json"
    state = (json.loads(state_path.read_text(encoding="utf-8"))
             if state_path.exists() else {})

    if args.missing_baseline_only:
        # sources that never completed a first fetch: no link_hashes (page
        # scrape) and no seen_rss (feed). Until they have one, they can
        # never produce a diff, so top-ups should target only these.
        def unbaselined(r):
            st = state.get(r["url_news"].strip(), {})
            return not st.get("link_hashes") and not st.get("seen_rss")
        due = [r for r in due if unbaselined(r)]

    print(f"{date}: {len(due)}/{len(rows)} sources due", file=sys.stderr)
    if args.dry_run:
        for r in due:
            print(f"  {r['priority_tier']} {r['update_frequency']:<13} "
                  f"{r['region']:<14} {r['source_name']}")
        return

    candidates, needs_browser, errors = [], [], []
    stats = {"due": len(due), "rss": 0, "scrape_changed": 0, "no_change": 0,
             "not_modified_304": 0, "baseline": 0, "needs_browser": 0,
             "errors": 0}

    start = time.monotonic()
    phase1_deadline = start + args.deadline * 0.65
    results, abandoned = run_bounded(
        lambda r: scan_source(r, state, cutoff), due, args.workers,
        phase1_deadline)
    stats["deadline_abandoned"] = len(abandoned)

    for i, row in enumerate(due):
        if i in abandoned:
            fresh, st, note = [], state.get(row["url_news"].strip(), {}), \
                "error:deadline-abandoned (slow host)"
        elif isinstance(results[i], Exception):
            e = results[i]
            fresh, st, note = [], state.get(row["url_news"].strip(), {}), \
                f"error:{type(e).__name__}: {e}"
        else:
            fresh, st, note = results[i]
        state[row["url_news"].strip()] = st
        base = {"source": row["source_name"], "region": row["region"],
                "tier": row["priority_tier"],
                "source_url": row["url_news"].strip()}
        if note == "rss":
            stats["rss"] += 1
        elif note == "scrape":
            stats["scrape_changed"] += 1
        elif note == "304":
            stats["not_modified_304"] += 1
        elif note == "no-change":
            stats["no_change"] += 1
        elif note == "baseline":
            stats["baseline"] += 1
        elif note == "needs_browser":
            stats["needs_browser"] += 1
            needs_browser.append({**base, "reason": "wechat-or-js-rendered"})
        elif note.startswith("error:"):
            stats["errors"] += 1
            errors.append({**base, "error": note[6:]})
        for c in fresh:
            candidates.append({**base, **c})

    # phase 2: fetch each candidate article once for metadata + hero image
    capped = candidates[:args.max_candidates]
    dropped = len(candidates) - len(capped)

    def enrich(c):
        if not c["url"].startswith("http"):
            return c
        resp = http_get(c["url"])
        if resp.get("status") == 200:
            meta = extract_meta(resp["text"])
            c["title"] = meta["title"] or c["title"]
            c["description"] = meta["description"]
            c["og_image"] = (urllib.parse.urljoin(c["url"], meta["og_image"])
                             if meta["og_image"] else "")
            c["published"] = meta["published"] or c["published"]
        row = next((r for r in due if r["source_name"] == c["source"]), {})
        c["keyword_hits"] = keyword_hits(row, c.get("title"),
                                         c.get("description"))
        status, age, iso = classify_date(c.get("published"), date)
        c["date_status"] = status
        c["age_days"] = age
        c["published_date"] = iso
        return c

    results2, abandoned2 = run_bounded(enrich, capped, args.workers,
                                       start + args.deadline)
    capped = [results2[i] if i in results2
              and not isinstance(results2[i], Exception) else c
              for i, c in enumerate(capped)]
    stats["deadline_abandoned"] += len(abandoned2)

    # strict same-day gate: anything dated before the run date is quarantined
    for c in capped:
        if "date_status" not in c:
            status, age, iso = classify_date(c.get("published"), date)
            c["date_status"], c["age_days"], c["published_date"] = \
                status, age, iso
    eligible = [c for c in capped
                if c["date_status"] in ("same-day", "unverified")]
    stale = [c for c in capped
             if c["date_status"] in ("prior-day", "stale")]
    if args.allow_prior_day:
        eligible += [c for c in stale if c["date_status"] == "prior-day"]
        stale = [c for c in stale if c["date_status"] != "prior-day"]
    stats["same_day"] = sum(1 for c in eligible
                            if c["date_status"] == "same-day")
    stats["date_unverified"] = sum(1 for c in eligible
                                   if c["date_status"] == "unverified")
    stats["stale_excluded"] = len(stale)

    state_path.write_text(json.dumps(state), encoding="utf-8")
    delta = {
        "date": str(date),
        "registry": args.registry,
        "date_rule": ("strict same-day (SKILL.md Section 4): only "
                      "date_status 'same-day' is drafting-eligible; "
                      "'unverified' items MUST have their publication date "
                      "confirmed at the source before drafting; "
                      "stale_excluded items need explicit user approval"),
        "stats": {**stats, "candidates": len(eligible),
                  "candidates_dropped_over_cap": max(0, dropped)},
        "candidates": eligible,
        "stale_excluded": stale,
        "needs_browser": needs_browser,
        "errors": errors,
    }
    out_path = out_dir / f"scan_delta_{date.strftime('%Y%m%d')}.json"
    out_path.write_text(json.dumps(delta, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    print(f"wrote {out_path}", file=sys.stderr)
    print(json.dumps(delta["stats"], indent=2))
    sys.stdout.flush()
    sys.stderr.flush()
    # abandoned worker threads may still be blocked on slow sockets;
    # results are already on disk, so exit hard instead of joining them
    os._exit(0)


if __name__ == "__main__":
    main()
