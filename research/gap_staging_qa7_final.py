"""QA round 7 — reviewer's fourth-pass residue.

  1. Two non-companies:
     - "Does It Count If You Lose Your Virginity to an Android?" — a light
       novel harvested from Wikipedia's category tree; passed the QA2 domain
       check because the STOPWORD token "an" matched animenewsnetwork.com
       (filter bug fixed alongside this pass in gap_staging_qa2.py).
     - HowToRobot (howtorobot.com) — robot-buying marketplace/advisory
       platform, not a manufacturer.
  2. ~35 residual junk robot rows: fragment styles like "All Robots learn
     more", bare spec fragments (">1000kg", "0.5-6kg"), list-item fragments
     ("- RD rotary packaging machine" -> keep cleaned? NO: drop, name is a
     nav fragment), and language-switcher links ("Italiano", "Deutsch").

Deliberately NOT touched: institute entries (ESA, ESA+JAXA, KIST) and the
irreducible tail of off-category products at diversified manufacturers
(SharkNinja cleaning solutions, Veichi energy storage) — those are for the
per-company review at import time.

Supports --dry-run. Run gap_sync_import_dirs.py + gap_final_verify.py after.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(__file__).resolve().parent / "staging" / "gap_discovery"
STAGED = BASE / "staged_import.json"

COMPANY_CULL: dict[str, str] = {
    "does-it-count-if-you-lose-your-virginity-to-an-android":
        "Light-novel article from Wikipedia category tree; domain check "
        "passed via stopword token 'an' ~ animenewsnetwork.com (bug fixed)",
    "howtorobot": "Robot-buying marketplace/advisory platform, not a manufacturer",
}

# Language names used as site language-switcher links.
_LANG_SWITCH_RE = re.compile(
    r"^\s*(english|italiano|deutsch|français|francais|español|espanol|"
    r"português|portugues|nederlands|polski|русский|日本語|中文|한국어|"
    r"türkçe|čeština|svenska|norsk|suomi|dansk|magyar|ελληνικά|العربية)\s*$",
    re.I)

# Bare spec fragments: ">1000kg", "0.5-6kg", "500 mm", "IP65" alone.
_SPEC_FRAGMENT_RE = re.compile(
    r"^\s*[<>~≤≥]?\s*\d[\d.,\s-]*\s*(kg|g|lbs?|mm|cm|m|inch(es)?|\"|kw|w|v|a|"
    r"hz|rpm|ip\d{2}|axis|axes|dof)\s*$", re.I)

# List-item / dash fragments: names starting with punctuation.
_FRAGMENT_START_RE = re.compile(r"^\s*[-–—•·*>|:,.]")

# "All Robots learn more" style: category word + trailing CTA.
_TRAILING_CTA_RE = re.compile(
    r"\b(learn more|read more|see more|view more|find out more|discover more|"
    r"shop now|buy now|order now|contact us|get a quote)\s*[!.>»]*\s*$", re.I)


# Genuine short model names: letter(s)+digit(s) like "M9", "Z4", "R1" — keep.
_MODEL_NAME_RE = re.compile(r"^[A-Za-z]{1,3}[- ]?\d{1,4}[A-Za-z]?$")

# Bare page numbers / counters and 2-letter language/country codes.
_PAGE_NUM_RE = re.compile(r"^\d{1,3}$")
_LANG_CODE_RE = re.compile(
    r"^(en|de|fr|es|it|nl|pl|se|fi|dk|cz|no|pt|ru|ja|zh|ko|tr|hu|gr|ar|cn)$", re.I)


def is_junk(name: str) -> bool:
    nm = (name or "").strip()
    if not nm:
        return True
    if _PAGE_NUM_RE.match(nm) or _LANG_CODE_RE.match(nm):
        return True
    if _MODEL_NAME_RE.match(nm):
        return False  # keep genuine short model names (M9, Z4, R1)
    if len(nm) < 3:
        return True
    if _LANG_SWITCH_RE.match(nm):
        return True
    if _SPEC_FRAGMENT_RE.match(nm):
        return True
    if _FRAGMENT_START_RE.match(nm):
        return True
    if _TRAILING_CTA_RE.search(nm):
        return True
    return False


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    data = json.loads(STAGED.read_text(encoding="utf-8"))
    cos, robs = data["companies"], data["robots"]
    n_c, n_r = len(cos), len(robs)

    dropped_cos, keep_cos = [], []
    for c in cos:
        if c["slug"] in COMPANY_CULL:
            dropped_cos.append(f"{c['name']} — {COMPANY_CULL[c['slug']]}")
        else:
            keep_cos.append(c)
    culled_slugs = set(COMPANY_CULL) & {c["slug"] for c in cos}

    # also purge from low_signal so they can't be rescued
    low = data.get("low_signal_companies", [])
    low_before = len(low)
    data["low_signal_companies"] = [c for c in low if c.get("slug") not in COMPANY_CULL]

    dropped_robs, keep_robs = [], []
    for r in robs:
        if r["company_slug"] in culled_slugs:
            dropped_robs.append(f"{r['name']} [{r['company_slug']}] — company culled")
        elif is_junk(r["name"]):
            dropped_robs.append(f"{r['name']} [{r['company_slug']}] — junk fragment")
        else:
            keep_robs.append(r)

    print(f"companies: {n_c} -> {len(keep_cos)}; "
          f"low_signal: {low_before} -> {len(data['low_signal_companies'])}")
    print(f"robots: {n_r} -> {len(keep_robs)} (dropped {len(dropped_robs)})")
    for line in dropped_cos:
        print("  CO-DROP:", line)
    for line in dropped_robs:
        print("  ROB-DROP:", line)

    if args.dry_run:
        return

    data["companies"] = keep_cos
    data["robots"] = keep_robs
    data["company_count"] = len(keep_cos)
    data["robot_count"] = len(keep_robs)
    qa = data.setdefault("qa_dropped", {}).setdefault("qa7", {})
    qa["companies"] = dropped_cos
    qa["robots"] = dropped_robs
    STAGED.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"written: {STAGED}")
    print("NEXT: gap_sync_import_dirs.py, gap_summary_regen.py, gap_final_verify.py")


if __name__ == "__main__":
    main()
