"""QA round 8 — reviewer's fifth-pass verdict: wrong-entity companies.

Root cause (systemic): single-word or robot-name harvests (mostly Wikipedia
robot pages staged as "companies") + serper token-match domain resolution =
the name token matches SOME domain, just not a robot manufacturer's. Fixed in
code alongside this pass:
  - company_website_resolve.py: skip-list now covers domain FAMILIES
    (linkedin.* not just linkedin.com) + landing-page "company-ness" check.
  - Harvest side: single-common-word names should never reach resolution.

Culled here (reviewer-classified, wrong entity entirely):
  FEDOR -> pool player merch; LinkedIn (.cn evaded skip-list); Ee -> UK
  telecom; Fi -> wi-fi.org; Us -> usa.gov; MABEL -> T-shirt shop;
  Soundwave -> K-pop merch; Murata Boy and Murata Girl -> murata.com
  (capacitors); RS Media -> video production; The Spectrum Building ->
  office cleaning; EcoTech -> aquarium equipment; Shengerxin (Chongqing) ->
  news site; Jiangsu Xinjiamiao -> made-in-jiangsu aggregator subdomain.

Also: Shanghai Yiying Crane Machinery's robot leads are charset mojibake
(GB2312 read as latin-1) — leads dropped, company kept with a re-mine flag.

Supports --dry-run. Run gap_sync_import_dirs.py + gap_final_verify.py after.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(__file__).resolve().parent / "staging" / "gap_discovery"
STAGED = BASE / "staged_import.json"

WRONG_ENTITY: dict[str, str] = {
    "fedor": "Wikipedia robot page (Russian humanoid FEDOR); resolved to "
             "fedorgorst.com, a pool player's merch shop (chalk holders/gloves)",
    "linkedin": "Social network; linkedin.cn evaded skip-list that only "
                "covered linkedin.com",
    "ee": "UK telecom (ee.co.uk), not a robot manufacturer",
    "fi": "Resolved to wi-fi.org (Wi-Fi Alliance), wrong entity",
    "us": "Resolved to usa.gov, wrong entity",
    "mabel": "Wikipedia robot page (bipedal robot MABEL); resolved to a "
             "T-shirt shop (shop.mabelofficial.com)",
    "soundwave": "Resolved to a K-pop merch store (en.sound-wave.co.kr)",
    "murata-boy-and-murata-girl": "Robots, not a company; resolved to "
                                  "murata.com with capacitors as leads",
    "rs-media": "Video production company (rsmedia.group), not the RS Media robot's maker",
    "the-spectrum-building": "Office-cleaning service, wrong entity",
    "ecotech": "Aquarium equipment maker (ecotechmarine.com), wrong entity",
    "shengerxin-technology-chongqing": "Resolved to ichongqing.info, a "
                                       "Chongqing news site",
    "jiangsu-xinjiamiao-automation-machinery-technology":
        "Resolved to cable.made-in-jiangsu.com, an aggregator subdomain",
}

# Company kept, but leads are charset mojibake — drop leads + flag re-mine.
REMINE_LEADS: dict[str, str] = {
    "shanghai-yiying-crane-machinery":
        "Robot names are GB2312-as-latin1 mojibake; leads dropped, re-mine "
        "with proper charset detection",
}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    data = json.loads(STAGED.read_text(encoding="utf-8"))
    cos, robs = data["companies"], data["robots"]
    n_c, n_r = len(cos), len(robs)

    dropped_cos, keep_cos = [], []
    for c in cos:
        if c["slug"] in WRONG_ENTITY:
            dropped_cos.append(f"{c['name']} — {WRONG_ENTITY[c['slug']]}")
        else:
            if c["slug"] in REMINE_LEADS:
                c["research_notes"] = (c.get("research_notes") or "") + \
                    f" [qa8] RE-MINE NEEDED: {REMINE_LEADS[c['slug']]}"
            keep_cos.append(c)
    culled = set(WRONG_ENTITY) & {c["slug"] for c in cos}

    # purge from low_signal too
    low = data.get("low_signal_companies", [])
    data["low_signal_companies"] = [c for c in low if c.get("slug") not in WRONG_ENTITY]

    dropped_robs, keep_robs = [], []
    for r in robs:
        if r["company_slug"] in culled:
            dropped_robs.append(f"{r['name']} [{r['company_slug']}] — wrong-entity company culled")
        elif r["company_slug"] in REMINE_LEADS:
            dropped_robs.append(f"{r['name']} [{r['company_slug']}] — mojibake lead, re-mine")
        else:
            keep_robs.append(r)

    print(f"companies: {n_c} -> {len(keep_cos)} (culled {len(dropped_cos)})")
    print(f"robots: {n_r} -> {len(keep_robs)} (dropped {len(dropped_robs)})")
    for line in dropped_cos:
        print("  CO-DROP:", line)

    if args.dry_run:
        return

    data["companies"] = keep_cos
    data["robots"] = keep_robs
    data["company_count"] = len(keep_cos)
    data["robot_count"] = len(keep_robs)
    qa = data.setdefault("qa_dropped", {}).setdefault("qa8", {})
    qa["companies"] = dropped_cos
    qa["robots"] = dropped_robs
    STAGED.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"written: {STAGED}")
    print("NEXT: gap_sync_import_dirs.py, gap_summary_regen.py, gap_final_verify.py")


if __name__ == "__main__":
    main()
