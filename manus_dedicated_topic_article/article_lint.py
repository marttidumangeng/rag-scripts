#!/usr/bin/env python3
"""Deterministic QC for ARPI dedicated-topic articles (the mechanical half
of the v8 quality-control checklist, as exit codes).

Checks on the body markdown/text:
  ERROR  word count below 1,200 (band 1,200-1,600; >1,700 warns)
  ERROR  inline citation markers ([1], superscripts, footnote daggers)
  ERROR  Evidence Source Notes section INSIDE the body file (it belongs in
         the separate evidence file; build_docx.py adds the closing page,
         and the docx check verifies it is there)
  ERROR  a 'References' heading anywhere
  ERROR  dash used as parenthetical break (em dash, or spaced en dash)
  ERROR  publication/workflow names in the publishable body
         (RobotAIGeek, Robot Age Intelligence, ARPI, Wise Peer, Manus)
  WARN   acronym used without a spelled-out first use (heuristic; exempts
         ISO currency codes and --exempt list for company/product names)

Optional artifact checks:
  --hero FILE      true JPEG magic bytes, 16:9 aspect (±3%), filename date
  --docx FILE      valid Word zip, Evidence section + disclaimer present,
                   filename date (no python-docx needed)
  --run-date DATE  YYYY-MM-DD used for the filename checks

Usage:
    python3 article_lint.py body.md --run-date 2026-08-06 \
        --hero 20260806_AMRAGV_Post9_hero.jpg \
        --docx RobotAIGeek_Draft_20260806_AMRAGV_Post9.docx \
        --exempt "ABB,KUKA,FANUC"
Exit 0 = pass (warnings allowed), 1 = errors. Stdlib only.
"""
import argparse
import json
import re
import struct
import sys
import zipfile
from pathlib import Path

EVIDENCE_RE = re.compile(
    r"Evidence Source Notes \(Internal Only [–—-] Do Not Publish\)")
REFERENCES_RE = re.compile(r"^\s*#*\s*References\s*$", re.MULTILINE | re.IGNORECASE)
CITATION_RE = re.compile(r"\[\d{1,3}\]|[¹²³⁰⁴-⁹]|†")
BAD_NAMES = ["RobotAIGeek", "Robot Age Intelligence", "ARPI", "Wise Peer",
             "Manus"]
CURRENCY_CODES = {"USD", "RMB", "GBP", "EUR", "CNY", "JPY", "KRW", "HKD",
                  "TWD", "SGD", "AUD", "CAD", "CHF", "INR"}
ACRONYM_RE = re.compile(r"\b[A-Z]{2,6}s?\b")
# SKILL.md Section 6 named formulaic phrases
BANNED_RE = re.compile(
    r"\b(in conclusion|it is worth noting|delve into|delving into|delve)\b",
    re.IGNORECASE)
# House currency rule: every amount carries an explicit currency prefix.
BARE_DOLLAR_RE = re.compile(r"(?<!US)(?<!A)(?<!C)(?<!HK)(?<!S)\$\s?[\d,]")
NON_USD_RE = re.compile(
    r"(?:[¥€£₩]|\b(?:RMB|CNY|JPY|KRW|EUR|GBP|HKD|TWD|SGD)\s?)\s?[\d,.]+\s?"
    r"(?:billion|million|trillion|bn|m|k)?", re.IGNORECASE)


def split_body(text):
    """Publishable body = everything before the Evidence section heading."""
    m = EVIDENCE_RE.search(text)
    return (text[:m.start()], True) if m else (text, False)


def check_acronyms(body, exempt):
    problems = []
    seen = set()
    for m in ACRONYM_RE.finditer(body):
        token = m.group(0).rstrip("s")
        if token in seen or token in CURRENCY_CODES or token in exempt:
            continue
        seen.add(token)
        # a compliant first use appears as "full expansion (ACRO)"
        before = body[max(0, m.start() - 2):m.start()]
        if before.endswith("("):
            continue
        if f"({token})" in body[:m.start()]:
            continue
        problems.append(token)
    return problems


def jpeg_dimensions(path):
    data = Path(path).read_bytes()
    if data[:2] != b"\xff\xd8":
        return None, None, False
    i = 2
    while i < len(data) - 9:
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            h, w = struct.unpack(">HH", data[i + 5:i + 9])
            return w, h, True
        seg_len = struct.unpack(">H", data[i + 2:i + 4])[0]
        i += 2 + seg_len
    return None, None, True


def lint_body(path, exempt):
    text = Path(path).read_text(encoding="utf-8")
    body, has_evidence = split_body(text)
    errors, warnings = [], []

    # Band per prompt v8/v9 (an explicit, documented override of SKILL.md
    # Sections 6 and 8, which still say 800-1,200).
    words = len(re.findall(r"[\w'$.-]+", body))
    if words < 1200:
        errors.append(f"body word count {words} below minimum 1,200 "
                      "(prompt v9 band 1,200-1,600)")
    elif words > 1600:
        warnings.append(f"body word count {words} above the 1,200-1,600 band; "
                        "SKILL.md Section 6 allows extension only when the "
                        "framework requires a deeper comparison and the "
                        "editor summary explains why")

    if has_evidence:
        errors.append("body file contains the Evidence Source Notes section; "
                      "keep evidence in its separate file (build_docx.py "
                      "places it on the internal closing page)")
    if REFERENCES_RE.search(text):
        errors.append("a 'References' heading exists; the source list must "
                      "be titled Evidence Source Notes")

    m = CITATION_RE.search(body)
    if m:
        errors.append(f"inline citation marker in body: {m.group(0)!r}")

    if "—" in body:
        errors.append(f"{body.count(chr(0x2014))} em dash(es) in body")
    if re.search(r"\s–\s", body):
        errors.append("spaced en dash used as parenthetical break")

    for name in BAD_NAMES:
        if re.search(rf"\b{re.escape(name)}\b", body):
            errors.append(f"publication/workflow name in body: {name!r}")

    banned = sorted({b.group(0).lower() for b in BANNED_RE.finditer(body)})
    if banned:
        errors.append(f"formulaic phrase(s) banned by SKILL.md Section 6: "
                      f"{banned}")

    m = BARE_DOLLAR_RE.search(body)
    if m:
        n = len(BARE_DOLLAR_RE.findall(body))
        errors.append(
            f"{n} bare '$' amount(s) without a currency prefix, first near "
            f"{body[m.start():m.start()+24]!r} — write US$ (house currency "
            "clarity rule)")

    for m in NON_USD_RE.finditer(body):
        if "US$" not in body[m.start():m.end() + 120]:
            warnings.append(
                f"currency {m.group(0).strip()!r} has no US$ conversion "
                "within 120 chars")

    missing = check_acronyms(body, exempt)
    if missing:
        warnings.append(
            "acronyms possibly lacking a spelled-out first use "
            f"(verify; company/product names are exempt): {missing}")

    return {"words": words, "errors": errors, "warnings": warnings}


def check_hero(path, run_date):
    errors = []
    p = Path(path)
    if not p.exists():
        return [f"hero file missing: {path}"]
    w, h, is_jpeg = jpeg_dimensions(p)
    if not is_jpeg:
        errors.append("hero is not a true JPEG (bad magic bytes)")
    elif w and h:
        ratio = w / h
        if abs(ratio - 16 / 9) > 16 / 9 * 0.03:
            errors.append(f"hero aspect {w}x{h} ({ratio:.3f}) is not 16:9")
    if run_date:
        ymd = run_date.replace("-", "")
        if not p.name.startswith(ymd):
            errors.append(f"hero filename does not start with {ymd}")
    return errors


def check_docx(path, run_date):
    errors = []
    p = Path(path)
    if not p.exists():
        return [f"docx file missing: {path}"]
    try:
        with zipfile.ZipFile(p) as z:
            xml = z.read("word/document.xml").decode("utf-8", "replace")
    except (zipfile.BadZipFile, KeyError) as e:
        return [f"docx is not a valid Word document: {e}"]
    text = re.sub(r"<[^>]+>", "", xml)
    if not EVIDENCE_RE.search(text):
        errors.append("docx lacks the Evidence Source Notes internal section")
    if not re.search(r"disclaimer|informational purposes|general information",
                     text, re.IGNORECASE):
        errors.append("docx lacks a disclaimer")
    if run_date:
        ymd = run_date.replace("-", "")
        if ymd not in p.name:
            errors.append(f"docx filename does not contain {ymd}")
    return errors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("body", help="article body markdown/text file")
    ap.add_argument("--run-date")
    ap.add_argument("--hero")
    ap.add_argument("--docx")
    ap.add_argument("--exempt", default="",
                    help="comma-separated company/product short forms to skip "
                         "in the acronym check")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    exempt = {e.strip() for e in args.exempt.split(",") if e.strip()}
    report = lint_body(args.body, exempt)
    if args.hero:
        report["errors"] += check_hero(args.hero, args.run_date)
    if args.docx:
        report["errors"] += check_docx(args.docx, args.run_date)
    report["ok"] = not report["errors"]

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=1))
    else:
        print(f"{args.body} ({report['words']} words): "
              f"{'PASS' if report['ok'] else 'FAIL'}")
        for e in report["errors"]:
            print(f"  ERROR   {e}")
        for w in report["warnings"]:
            print(f"  warning {w}")
    sys.exit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
