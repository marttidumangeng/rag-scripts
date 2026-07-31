"""QA round 6 — brand-duplicates and residual nav-junk robot rows.

Reviewer findings (third pass):

  1. "Motoman" staged as its own company (motoman.com, 22 robots) but Motoman
     is YASKAWA Electric's robot BRAND — prod already has Yaskawa
     (yaskawa-global.com). Neither the name matcher nor the domain alias guard
     could catch it because both name and domain differ from the prod record.
     Action: drop the company entry, PARK its robot leads under
     `parked_for_enrichment` keyed to the prod company, for a later
     Yaskawa enrichment pass. Extend BRAND_DUPLICATES as reviewers find more.
  2. ~77 residual nav-junk robot rows ("View all storage solutions",
     "Download Whitepaper", "Newsletter", "ABOUT AVA ROBOTICS", ...).
     Action: extended pattern pass (leading verb/CTA phrases, ABOUT X,
     newsletter/whitepaper/webinar/catalog tokens anywhere in short names).

Agencies/institutes (ESA, KIST, NESCOM...) are deliberately KEPT — prod
already contains research orgs (UT Austin RPL, NASA JSC).

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

# staged slug -> (prod company name, reason)
BRAND_DUPLICATES: dict[str, tuple[str, str]] = {
    "motoman": ("YASKAWA Electric",
                "Motoman is Yaskawa's robot brand (motoman.com is Yaskawa "
                "America's site); robots parked for Yaskawa enrichment"),
}

# CTA / navigation phrases at the start of a name.
_CTA_START_RE = re.compile(
    r"^\s*(view( all)?|see( all)?|browse|explore|discover|learn( more)?|read( more)?|"
    r"download|request|get|find|shop|compare|watch|subscribe|contact|meet|why|"
    r"about)\b", re.I)

# Junk tokens that make a short name non-product regardless of position.
_JUNK_TOKEN_RE = re.compile(
    r"\b(whitepaper|white paper|newsletter|webinar|brochure|catalog(ue)?|"
    r"case stud(y|ies)|testimonial|datasheet|data sheet|press release|"
    r"careers?|events?|trade ?shows?|exhibitions?|privacy|cookie|sitemap|"
    r"login|sign ?(in|up)|faq)\b", re.I)


def is_nav_junk(name: str) -> bool:
    nm = (name or "").strip()
    if not nm:
        return True
    if _CTA_START_RE.match(nm):
        return True
    if len(nm) <= 60 and _JUNK_TOKEN_RE.search(nm):
        return True
    return False


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    data = json.loads(STAGED.read_text(encoding="utf-8"))
    cos, robs = data["companies"], data["robots"]
    n_c, n_r = len(cos), len(robs)

    # 1) brand duplicates: drop company, park robots.
    parked = data.get("parked_for_enrichment", [])
    dropped_cos = []
    keep_cos = []
    for c in cos:
        if c["slug"] in BRAND_DUPLICATES:
            prod_name, reason = BRAND_DUPLICATES[c["slug"]]
            dropped_cos.append(f"{c['name']} — brand of prod '{prod_name}': {reason}")
        else:
            keep_cos.append(c)
    brand_slugs = set(BRAND_DUPLICATES) & {c["slug"] for c in cos}

    keep_robs, parked_now, junk_rows = [], [], []
    for r in robs:
        if r["company_slug"] in brand_slugs:
            prod_name, _ = BRAND_DUPLICATES[r["company_slug"]]
            r["research_notes"] = (r.get("research_notes") or "") + \
                f" [qa6] Parked: lead belongs under prod company '{prod_name}'."
            r["prod_company_name"] = prod_name
            parked_now.append(r)
        elif is_nav_junk(r["name"]):
            junk_rows.append(f"{r['name']} [{r['company_slug']}]")
        else:
            keep_robs.append(r)

    print(f"companies: {n_c} -> {len(keep_cos)} (brand-dup drops: {len(dropped_cos)})")
    print(f"robots: {n_r} -> {len(keep_robs)} "
          f"(parked: {len(parked_now)}, nav-junk: {len(junk_rows)})")
    for line in dropped_cos:
        print("  CO-DROP:", line)
    for line in junk_rows:
        print("  JUNK:", line)

    if args.dry_run:
        return

    data["companies"] = keep_cos
    data["robots"] = keep_robs
    data["company_count"] = len(keep_cos)
    data["robot_count"] = len(keep_robs)
    data["parked_for_enrichment"] = parked + parked_now
    qa = data.setdefault("qa_dropped", {}).setdefault("qa6", {})
    qa["companies"] = dropped_cos
    qa["robots"] = junk_rows
    STAGED.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"written: {STAGED}")
    print("NEXT: gap_sync_import_dirs.py, gap_summary_regen.py, gap_final_verify.py")


if __name__ == "__main__":
    main()
