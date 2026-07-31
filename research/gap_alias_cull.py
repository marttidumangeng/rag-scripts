"""Cull confirmed prod-alias duplicates from staged_import.json.

possible_prod_aliases.json flags staged companies whose normalized name
overlaps a prod company name. That list needs HUMAN JUDGMENT, not blind
deletion — e.g. "Boschung ~ Bosch" is a false positive (independent Swiss
company), while "Yaskawa ~ YASKAWA Electric" is a confirmed duplicate.

Verdicts below were made per-suspect on 2026-07-29 (name + website + prod
record comparison). Three verdict types:

  cull    — confirmed alias/duplicate/subsidiary of an existing prod company,
            or a non-company artifact; removed entirely (robots too), recorded
            under qa_dropped.alias_cull.
  demote  — real entity but not an importable manufacturer (labs, wrong-site
            resolutions); moved to low_signal_companies with website cleared
            where the site is wrong.
  keep    — false positive; left staged.

Re-runnable: culling an already-culled slug is a no-op. After running, ALWAYS
run gap_sync_import_dirs.py to resync the per-company import dirs.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(__file__).resolve().parent / "staging" / "gap_discovery"
STAGED = BASE / "staged_import.json"

# slug -> (verdict, reason)
VERDICTS: dict[str, tuple[str, str]] = {
    # ── confirmed duplicates / subsidiaries of prod companies ──────────────
    "yaskawa": ("cull", "Duplicate of prod 'YASKAWA Electric' (yaskawa.com = same OEM as yaskawa-global.com)"),
    "6-river-systems": ("cull", "Duplicate of prod '6 River Systems (Shopify) - Ocado Group'"),
    "baidu-apollo-go": ("cull", "Robotaxi service of prod 'Baidu'; not a separate manufacturer"),
    "lg-electronics-inc-business-solutions": ("cull", "Division of prod 'LG Electronics'"),
    "shandong-unity-robotics": ("cull", "Same company as prod 'Unity Robotics' (unityrobots.com); prod record lacks website — flag for backfill instead"),
    "samsung-electronics-co-ltd-robotics-team": ("cull", "Team within prod 'Samsung Electronics'"),
    "panasonic-hospi": ("cull", "HOSPI is a robot of prod 'Panasonic', not a company"),
    "toyota-partner-robot": ("cull", "Program of prod 'Toyota', not a company"),
    "woven-by-toyota-inc": ("cull", "Subsidiary of prod 'Toyota' (software/mobility, no own robots)"),
    "hd-hyundai-robotics": ("cull", "Same OEM as prod 'Hyundai Robotics' (rebrand to HD Hyundai)"),
    "switchbot-uk": ("cull", "Regional storefront of prod 'SwitchBot'"),
    "shenzhen-standard-robots": ("cull", "Same company as prod 'Standard Robots' (standard-robots.com)"),
    "suzhou-escott-machinery-equipment": ("cull", "Duplicate of prod 'Suzhou Escott Machinery & Equipment Co., Ltd.'"),
    "donglisheng-m-e-technology": ("cull", "Duplicate of prod 'Wuhan Donglisheng M&E Technology Co., Ltd.'"),
    "guanhong-automation": ("cull", "Duplicate of prod 'Shenzhen Guanhong Automation'"),
    "jiangsu-jitri-intelligent-manufacturing-technology-institute": ("cull", "Duplicate of prod 'Jitri Intelligent Manufacturing'"),
    "robotis-kidsl": ("cull", "Product line / regional store of prod 'Robotis'"),
    "fraunhofer-ipa-and-mojin-robotics": ("cull", "Prod already has 'Fraunhofer IPA'; 'and Mojin Robotics' is a Wikipedia collab artifact"),
    "nasa-johnson-space-center-and-gm": ("cull", "Prod already has 'NASA Johnson Space Center'; collab artifact"),
    "uc-san-diego-kokoro-and-hanson-robotics": ("cull", "Prod already has 'Hanson Robotics'; collab artifact"),
    "hexagon": ("cull", "Same group as prod 'Hexagon Manufacturing Intelligence'; staged site hexagongroup.com is a different unrelated firm anyway"),
    "various": ("cull", "Not a company (Wikipedia 'Various' artifact)"),
    "robot-com": ("cull", "Not a manufacturer; resolved site nextmsc.com is a market-research firm"),
    # ── real entities but not importable manufacturers ──────────────────────
    "biorobotics-laboratory-at-epfl": ("demote", "University lab, not a manufacturer"),
    "mit-biomimetic-robotics-lab": ("demote", "University lab, not a manufacturer"),
    "rehabilitation-robotics": ("demote", "Topic page resolved to umich.edu lab, not a company"),
    "farmwi": ("demote", "Truncated 'FarmWise' artifact; resolved site farmwisconsin.org is unrelated"),
    "st-robotics": ("demote", "Real company but resolved website senster.com is wrong; needs manual re-resolution"),
    "kirobo": ("demote", "Toyota/JAXA project robot, not a company; site kibo-robo.jp is a project page"),
    # ── false positives — explicitly kept ───────────────────────────────────
    "boschung": ("keep", "Independent Swiss company, not Bosch"),
    "construction-robotics": ("keep", "US SAM/MULE maker, unrelated to OnRobot"),
    "daimon-robotics": ("keep", "Dexterous-hand startup, unrelated to OnRobot"),
    "path-robotics": ("keep", "Welding-robot company, unrelated to Clearpath"),
    "ehang": ("keep", "eVTOL maker, unrelated to RaysEngine"),
    "bot-auto": ("keep", "Autonomous trucking co, unrelated to Lyric Robot"),
    "e-cobot": ("keep", "French cobot maker, unrelated to ICE Cobotics"),
    "cobot": ("keep", "cobotteam.com, distinct company"),
    "corobot": ("keep", "Distinct from Ecorobotix"),
    "exrobot": ("keep", "ExRobotics (exrobotics.com), distinct company"),
    "ffrobotics": ("keep", "Fruit-picking robots, unrelated to Spinoff"),
    "gmex-robotics": ("keep", "Unrelated to XRobotics"),
    "milox-robotics": ("keep", "Unrelated to XRobotics"),
    "nanoflex-robotics": ("keep", "Unrelated to XRobotics"),
    "simplex-robotics": ("keep", "Unrelated to XRobotics"),
    "white-box-robotics": ("keep", "Unrelated to XRobotics"),
    "logistech": ("keep", "logistech.co, distinct from NTI Logis-Tech"),
    "hefei-honor-automation-technology": ("keep", "Automation firm, unrelated to HONOR phones"),
    "scott": ("keep", "Scott Automation (scottautomation.com), real robotics OEM, unrelated to Escott"),
    "humanoid": ("keep", "thehumanoid.ai startup, distinct from Beijing Humanoid Robot Innovation Center"),
    "turing-robot": ("keep", "turing.ai, distinct from Futuring Robot"),
}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    data = json.loads(STAGED.read_text(encoding="utf-8"))
    cos, robs = data["companies"], data["robots"]
    staged_slugs = {c["slug"] for c in cos}

    cull = {s for s, (v, _) in VERDICTS.items() if v == "cull" and s in staged_slugs}
    demote = {s for s, (v, _) in VERDICTS.items() if v == "demote" and s in staged_slugs}
    unhandled = staged_slugs & set()  # placeholder for symmetry

    kept_cos, demoted_cos, culled_names = [], [], []
    for c in cos:
        slug = c["slug"]
        if slug in cull:
            culled_names.append(f"{c['name']} — {VERDICTS[slug][1]}")
            continue
        if slug in demote:
            c["website"] = ""
            c["research_notes"] = (c.get("research_notes") or "") + \
                f" [alias-cull] Demoted: {VERDICTS[slug][1]}."
            demoted_cos.append(c)
            continue
        kept_cos.append(c)

    removed = cull | demote
    kept_robs = [r for r in robs if r["company_slug"] not in removed]

    # Also purge cull-verdict entries already sitting in low_signal_companies,
    # so reviewers can't rescue a confirmed prod duplicate from that bucket.
    all_cull = {s for s, (v, _) in VERDICTS.items() if v == "cull"}
    low = data.get("low_signal_companies", [])
    low_kept = [c for c in low if c.get("slug") not in all_cull]
    low_culled = [c["name"] for c in low if c.get("slug") in all_cull]
    for name in low_culled:
        slug = next(s for s, (v, _) in VERDICTS.items()
                    if v == "cull" and any(c.get("slug") == s and c.get("name") == name for c in low))
        culled_names.append(f"{name} (from low_signal) — {VERDICTS[slug][1]}")

    print(f"companies: {len(cos)} -> {len(kept_cos)} "
          f"(culled {len(culled_names)}, demoted {len(demoted_cos)})")
    print(f"robots: {len(robs)} -> {len(kept_robs)}")
    for line in culled_names:
        print("  CULL:", line)
    for c in demoted_cos:
        print("  DEMOTE:", c["name"])

    if args.dry_run:
        return

    data["companies"] = kept_cos
    data["robots"] = kept_robs
    data["company_count"] = len(kept_cos)
    data["robot_count"] = len(kept_robs)
    data["low_signal_companies"] = low_kept + demoted_cos
    data.setdefault("qa_dropped", {})["alias_cull"] = culled_names
    STAGED.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"written: {STAGED}")
    print("NOTE: prod 'Unity Robotics' lacks a website; consider backfilling "
          "https://www.unityrobots.com on the prod record.")
    print("NEXT: run gap_sync_import_dirs.py to resync import dirs.")


if __name__ == "__main__":
    main()
