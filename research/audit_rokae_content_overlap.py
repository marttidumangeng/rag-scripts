"""
audit_rokae_content_overlap.py
-------------------------------
Audits all robots for a given company for:
  1. Overlapping content between description, features, and purpose fields
     (detected via Jaccard similarity on sentence-level tokens)
  2. Missing or blank family_name

Outputs a JSON report to staging/reports/content_overlap_audit_{company_id}.json
and prints a human-readable summary.

Usage:
  python audit_rokae_content_overlap.py [--company-id 1416]
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
    """Jaccard similarity between two token sets."""
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# Threshold above which two fields are considered "overlapping"
OVERLAP_THRESHOLD = 0.35


def check_robot(robot: dict) -> dict:
    rid        = robot["id"]
    name       = robot.get("name", f"Robot {rid}")
    model_name = robot.get("model_name", "")
    desc       = robot.get("description") or ""
    features   = robot.get("features") or ""
    purpose    = robot.get("purpose") or ""
    family     = robot.get("family_name") or ""

    desc_tok     = tokenize(desc)
    features_tok = tokenize(features)
    purpose_tok  = tokenize(purpose)

    overlaps = []
    j_df = jaccard(desc_tok, features_tok)
    j_dp = jaccard(desc_tok, purpose_tok)
    j_fp = jaccard(features_tok, purpose_tok)

    if j_df >= OVERLAP_THRESHOLD:
        overlaps.append({"pair": "description↔features", "score": round(j_df, 3)})
    if j_dp >= OVERLAP_THRESHOLD:
        overlaps.append({"pair": "description↔purpose",  "score": round(j_dp, 3)})
    if j_fp >= OVERLAP_THRESHOLD:
        overlaps.append({"pair": "features↔purpose",     "score": round(j_fp, 3)})

    has_desc     = bool(desc.strip())
    has_features = bool(features.strip())
    has_purpose  = bool(purpose.strip())
    missing_family = not bool(family.strip())

    return {
        "id":            rid,
        "name":          name,
        "model_name":    model_name,
        "family_name":   family,
        "missing_family": missing_family,
        "has_description": has_desc,
        "has_features":    has_features,
        "has_purpose":     has_purpose,
        "overlaps":        overlaps,
        "overlap_count":   len(overlaps),
        # Snippet previews for the report
        "description_preview": desc[:120].replace("\n", " ") if desc else "",
        "features_preview":    features[:120].replace("\n", " ") if features else "",
        "purpose_preview":     purpose[:120].replace("\n", " ") if purpose else "",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--company-id", type=int, default=1416)
    args = parser.parse_args()

    client = ResearchApiClient()
    robots = client.list_robots_for_company(args.company_id)
    print(f"Fetched {len(robots)} robots for company {args.company_id}\n")

    results = [check_robot(r) for r in robots]

    overlap_robots   = [r for r in results if r["overlap_count"] > 0]
    no_family_robots = [r for r in results if r["missing_family"]]
    clean_robots     = [r for r in results if r["overlap_count"] == 0 and not r["missing_family"]]

    print(f"{'='*60}")
    print(f"Robots with content overlap:  {len(overlap_robots)}")
    print(f"Robots missing family_name:   {len(no_family_robots)}")
    print(f"Clean robots (no issues):     {len(clean_robots)}")
    print(f"{'='*60}\n")

    if overlap_robots:
        print("--- CONTENT OVERLAP ISSUES ---")
        for r in overlap_robots:
            print(f"\n[{r['id']}] {r['name']}  (model: {r['model_name']})")
            for ov in r["overlaps"]:
                print(f"  {ov['pair']}  similarity={ov['score']}")
            if r["description_preview"]:
                print(f"  desc:     {r['description_preview']}")
            if r["features_preview"]:
                print(f"  features: {r['features_preview']}")
            if r["purpose_preview"]:
                print(f"  purpose:  {r['purpose_preview']}")

    if no_family_robots:
        print("\n--- MISSING FAMILY NAME ---")
        for r in no_family_robots:
            print(f"  [{r['id']}] {r['name']}  (model: {r['model_name']})")

    out_path = os.path.join(
        os.path.dirname(__file__), "staging", "reports",
        f"content_overlap_audit_{args.company_id}.json"
    )
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "company_id":     args.company_id,
            "total":          len(results),
            "overlap_count":  len(overlap_robots),
            "no_family_count": len(no_family_robots),
            "overlap_robots": overlap_robots,
            "no_family_robots": no_family_robots,
        }, f, indent=2, ensure_ascii=False)
    print(f"\nReport saved to {out_path}")


if __name__ == "__main__":
    main()
