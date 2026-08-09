#!/usr/bin/env python3
"""Deterministic compliance lint for RAI daily-news public copy.

Enforces the mechanical style rules that prose instructions apply
inconsistently (e.g. runs where 4 of 6 News Posts shipped without the
mandatory disclaimer). Run on every public body before packaging; all
ERRORs must be fixed. Not a substitute for audit_originality.py.

Checks (rule references are to the rai-tier1-daily-news-agent SKILL.md):
  - standard disclaimer present            (ERROR if missing; 14.10)
  - word count within lane band            (ERROR below; 3.4.1)
      news: 1,500-1,800 / article: 1,500-2,500
  - em dashes                              (ERROR; 14.6)
  - bare "$" without US prefix             (ERROR; 14.14)
  - third-party outlet attribution in body (ERROR; 14.11)
  - formulaic "What is X?" opener          (ERROR; 3.5.1)
  - labeled ELI5 / Hard Truth headings     (ERROR; 3.5.1)
  - banned AI phrasing                     (WARNING; 3.5)
  - non-USD currency amount with no US$ conversion nearby (WARNING; 14.14)

Usage:
    python3 package_lint.py body.md --lane news
    python3 package_lint.py drafts/*.md --lane news --json
Exit 0 = all files pass (warnings allowed), 1 = at least one ERROR.
Stdlib only.
"""
import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

ISO_DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")

BANDS = {"news": (1500, 1800), "article": (1500, 2500)}  # SKILL.md 3.4.1
DISCLAIMER_RE = re.compile(
    r"(general information (purposes )?only|does not constitute\s+"
    r"(investment|financial|legal|professional))", re.IGNORECASE)
WHAT_IS_OPENER_RE = re.compile(r"^\s*#*\s*what\s+is\s+[^?\n]{1,60}\?",
                               re.IGNORECASE)
LABELED_HEADING_RE = re.compile(
    r"^\s*#{1,6}\s*(eli5|explain like i'?m (5|five)|hard truth)\b",
    re.IGNORECASE | re.MULTILINE)
NON_USD_RE = re.compile(
    r"(?:[¥€£₩]|(?:RMB|CNY|JPY|KRW|EUR|GBP|HKD|TWD|SGD)\s?)\s?[\d,.]+\s?"
    r"(?:billion|million|trillion|bn|m|k)?", re.IGNORECASE)
# SKILL.md 14.14: never a bare "$" without the US prefix
BARE_DOLLAR_RE = re.compile(r"(?<!US)\$\s?\d")
# SKILL.md 14.11: no third-party outlet attribution in the body
ATTRIBUTION_RE = re.compile(
    r"\b(?:according to|as reported by|reported by|as per|per a report (?:by|from))\s+"
    r"(Reuters|Bloomberg|CNBC|Financial Times|the FT|Nikkei(?:\s+Asia)?|"
    r"TechCrunch|The Verge|WSJ|The Wall Street Journal|Forbes|"
    r"The Information|SCMP|South China Morning Post|Xinhua|PR Newswire|"
    r"The Economist|Wired|Axios|The Japan Times|The Korea Herald)",
    re.IGNORECASE)
# SKILL.md 3.5 banned AI phrasing (warning level)
BANNED_PHRASES = [
    "delve", "tapestry", "testament", "unlocking", "landscape", "navigate",
    "multifaceted", "pivotal", "essentially", "ultimately", "empower",
    "foster", "orchestrate", "it is worth noting", "furthermore",
    "this demonstrates", "in conclusion",
]
BANNED_RE = re.compile(
    r"\b(" + "|".join(re.escape(p) for p in BANNED_PHRASES) + r")\b",
    re.IGNORECASE)


def count_words(text):
    return len(re.findall(r"[\w'$.-]+", text))


def check_source_date(text, run_date):
    """SKILL.md Section 4 strict same-day rule, enforced on the body's own
    date claims. Any explicit date in the copy that is older than the run
    date is flagged for the agent to justify (event context is legitimate;
    a stale trigger event is not)."""
    problems = []
    try:
        run = dt.date.fromisoformat(run_date)
    except ValueError:
        return [f"--run-date {run_date!r} is not YYYY-MM-DD"]
    for m in ISO_DATE_RE.finditer(text):
        try:
            d = dt.date.fromisoformat(m.group(0))
        except ValueError:
            continue
        age = (run - d).days
        if 1 <= age <= 30:
            problems.append(
                f"body cites {m.group(0)} ({age} day(s) before the run "
                "date) — confirm this is background context, not the "
                "trigger event (SKILL.md Section 4 strict same-day rule)")
    return problems


def lint_file(path, lane, run_date=None):
    text = Path(path).read_text(encoding="utf-8")
    errors, warnings = [], []
    if run_date:
        warnings += check_source_date(text, run_date)

    if not DISCLAIMER_RE.search(text):
        errors.append("standard disclaimer missing")

    words = count_words(text)
    lo, hi = BANDS[lane]
    if words < lo:
        errors.append(f"word count {words} below {lane} band {lo}-{hi}")
    elif words > hi:
        errors.append(f"word count {words} above {lane} band {lo}-{hi}")

    em = text.count("—")
    if em:
        errors.append(f"{em} em dash(es) found")

    first_block = text.lstrip()[:200]
    if WHAT_IS_OPENER_RE.match(first_block):
        errors.append("opens with formulaic 'What is X?' block")

    m = LABELED_HEADING_RE.search(text)
    if m:
        errors.append(f"labeled heading not allowed: {m.group(0).strip()!r}")

    m = BARE_DOLLAR_RE.search(text)
    if m:
        errors.append(
            f"bare '$' without currency prefix near {text[m.start():m.start()+20]!r}"
            " — write US$ (SKILL.md 14.14)")

    m = ATTRIBUTION_RE.search(text)
    if m:
        errors.append(
            f"third-party outlet attribution in body: {m.group(0)!r} — "
            "state facts directly; sources live in the internal evidence "
            "note (SKILL.md 14.11)")

    banned = sorted({b.group(0).lower() for b in BANNED_RE.finditer(text)})
    if banned:
        warnings.append(f"banned AI phrasing (SKILL.md 3.5): {banned}")

    for m in NON_USD_RE.finditer(text):
        window = text[m.start():m.end() + 120]
        if "US$" not in window:
            warnings.append(
                f"currency {m.group(0).strip()!r} has no US$ conversion "
                "within 120 chars")

    return {"file": str(path), "lane": lane, "words": words,
            "errors": errors, "warnings": warnings,
            "ok": not errors}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--lane", choices=list(BANDS), required=True)
    ap.add_argument("--run-date", help="YYYY-MM-DD; enables the strict "
                                       "same-day date check on body dates")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    results = [lint_file(f, args.lane, args.run_date) for f in args.files]
    all_ok = all(r["ok"] for r in results)

    if args.json:
        print(json.dumps({"ok": all_ok, "results": results},
                         ensure_ascii=False, indent=1))
    else:
        for r in results:
            print(f"{r['file']} ({r['words']} words): "
                  f"{'PASS' if r['ok'] else 'FAIL'}")
            for e in r["errors"]:
                print(f"  ERROR   {e}")
            for w in r["warnings"]:
                print(f"  warning {w}")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
