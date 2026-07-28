"""
fix_rokae_overlap_family.py
---------------------------
Fixes two issues for ROKAE robots (company 1416):
  1. Content overlap: If `description` and `features` are identical (or highly overlapping),
     clears the `features` field so it can be re-generated or left blank (avoiding duplication).
  2. Missing family_name: Derives and sets `family_name` from the model_name prefix.

Usage:
  python fix_rokae_overlap_family.py [--dry-run]
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from api_client import ResearchApiClient


def tokenize(text: str) -> set[str]:
    """Lowercase word tokens from a string, ignoring punctuation."""
    if not text:
        return set()
    return set(re.findall(r"\b[a-z]{3,}\b", text.lower()))


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


OVERLAP_THRESHOLD = 0.35


def derive_family_name(model_name: str) -> str:
    """Derive family_name from model_name for ROKAE robots."""
    if not model_name:
        return ""
    
    # Chinese series names (e.g. NB80系列)
    if "系列" in model_name:
        return model_name.replace("系列", " Series")
        
    # xMate Pro series
    if "xMate" in model_name and "Pro" in model_name:
        return "xMate Pro Series"
        
    # Standard prefixes: CR, SR, ER, NB, XB
    m = re.match(r"^([A-Z]+)\d*", model_name, re.IGNORECASE)
    if m:
        prefix = m.group(1).upper()
        if prefix in ["CR", "SR", "ER"]:
            return f"xMate {prefix} Series"
        elif prefix in ["NB", "XB"]:
            return f"{prefix} Series"
            
    # SCARA
    if "SCARA" in model_name.upper():
        return "SCARA Series"
        
    return ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--company-id", type=int, default=1416)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    client = ResearchApiClient()
    robots = client.list_robots_for_company(args.company_id)
    print(f"Fetched {len(robots)} robots for company {args.company_id}\n")

    fixed_overlap = 0
    fixed_family = 0
    results_log = []

    for robot in robots:
        rid        = robot["id"]
        name       = robot.get("name", f"Robot {rid}")
        model_name = robot.get("model_name", "")
        desc       = robot.get("description") or ""
        features   = robot.get("features") or ""
        family     = robot.get("family_name") or ""

        patch = {}

        # 1. Fix overlap
        desc_tok     = tokenize(desc)
        features_tok = tokenize(features)
        
        if jaccard(desc_tok, features_tok) >= OVERLAP_THRESHOLD:
            # Clear features if it's just a duplicate of description
            patch["features"] = ""
            print(f"[{rid}] {name} - Cleared duplicate features")
            fixed_overlap += 1

        # 2. Fix missing family_name
        if not family.strip():
            derived_family = derive_family_name(model_name)
            if derived_family:
                patch["family_name"] = derived_family
                print(f"[{rid}] {name} - Assigned family: {derived_family}")
                fixed_family += 1

        if not patch:
            continue

        if args.dry_run:
            print(f"  [DRY RUN] Would PATCH robot {rid} with {patch}")
            results_log.append({"id": rid, "name": name, "patch": patch, "status": "dry_run"})
        else:
            try:
                client._patch(f"robots/robots/{rid}/", patch)
                print(f"  [OK] Patched robot {rid}")
                results_log.append({"id": rid, "name": name, "patch": patch, "status": "ok"})
            except Exception as e:
                print(f"  [ERROR] Failed to patch robot {rid}: {e}")
                results_log.append({"id": rid, "name": name, "patch": patch, "status": "error", "error": str(e)})

    print(f"\n{'='*60}")
    print(f"Summary: Overlaps fixed={fixed_overlap}, Families assigned={fixed_family}")

    out_path = os.path.join(
        os.path.dirname(__file__), "staging", "reports",
        f"overlap_family_fix_{args.company_id}.json"
    )
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "company_id": args.company_id,
            "fixed_overlap": fixed_overlap,
            "fixed_family": fixed_family,
            "results": results_log
        }, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
