#!/usr/bin/env python3
"""Automated mechanical compliance validator for RobotAIGeek Sunday articles."""
import re
import sys
import os
import glob

ARTICLE_DIR = "/home/ubuntu/sunday_run_20260802/articles"
articles = sorted(glob.glob(os.path.join(ARTICLE_DIR, "20260802_article_*.md")))

CHECKS = {
    "has_meta_title": lambda t: "Meta Title:" in t,
    "has_meta_description": lambda t: "Meta Description:" in t,
    "has_hero_image": lambda t: "Hero Image:" in t,
    "has_category": lambda t: "Category:" in t,
    "has_slug": lambda t: "Slug:" in t,
    "has_tags": lambda t: "Tags:" in t,
    "has_executive_summary": lambda t: "**Executive Summary**" in t,
    "has_verification_sentence": lambda t: "This analysis synthesizes company statements and public market activity." in t,
    "has_internal_evidence_note": lambda t: "**Internal Evidence Note**" in t,
    "no_em_dashes": lambda t: "\u2014" not in t and "\u2013" not in t,
    "no_parentheses": lambda t: "(" not in t.split("**Internal Evidence Note**")[0] if "**Internal Evidence Note**" in t else "(" not in t,
    "no_public_urls_in_body": lambda t: not re.search(r'https?://', t.split("**Internal Evidence Note**")[0]) if "**Internal Evidence Note**" in t else not re.search(r'https?://', t),
    "no_self_reference": lambda t: not re.search(r'\b(we|our|this publication|RobotAIGeek)\b', t.split("Meta Title:")[1].split("**Internal Evidence Note**")[0], re.I) if "**Internal Evidence Note**" in t else True,
    "word_count_floor": lambda t: len(t.split("**Executive Summary**")[1].split("**Internal Evidence Note**")[0].split()) >= 1200 if "**Executive Summary**" in t and "**Internal Evidence Note**" in t else False,
}

print("=" * 70)
print("COMPLIANCE VALIDATION REPORT - 2 August 2026 Weekly Run")
print("=" * 70)

all_pass = True
for article_path in articles:
    fname = os.path.basename(article_path)
    with open(article_path, "r") as f:
        content = f.read()
    
    print(f"\n--- {fname} ---")
    body_text = content.split("**Executive Summary**")[1].split("**Internal Evidence Note**")[0] if "**Executive Summary**" in content and "**Internal Evidence Note**" in content else ""
    word_count = len(body_text.split())
    print(f"  Word count (body): {word_count}")
    
    for check_name, check_fn in CHECKS.items():
        try:
            result = check_fn(content)
        except Exception as e:
            result = False
        status = "PASS" if result else "FAIL"
        if not result:
            all_pass = False
        print(f"  {check_name}: {status}")

print("\n" + "=" * 70)
print(f"OVERALL: {'ALL PASS' if all_pass else 'FAILURES DETECTED'}")
print("=" * 70)
sys.exit(0 if all_pass else 1)
