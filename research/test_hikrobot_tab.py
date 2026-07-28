"""Smoke test for the Hikrobot tab extractor.

Tests a single robot from each product family to verify the extractor works.
"""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from hikrobot_catalog import (
    normalize_hikrobot_model,
    hikrobot_family_for_model,
    hikrobot_category_url_for_model,
    extract_hikrobot_tab,
    hikrobot_tab_to_page_content,
)

TEST_MODELS = [
    "TP0-T50",          # LMR
    "Q2-400D",          # LMR
    "TP5-50DC",         # CTU
    "C3-200LB2",        # CMR
]

for model in TEST_MODELS:
    bare = normalize_hikrobot_model(model)
    family = hikrobot_family_for_model(bare)
    cat_url = hikrobot_category_url_for_model(bare)
    print(f"\n{'='*60}")
    print(f"Model: {model!r}  →  bare={bare!r}  family={family}  url={cat_url}")

    result = extract_hikrobot_tab(bare)
    if result is None:
        print("  RESULT: None (Playwright unavailable)")
        continue

    if not result.success:
        print(f"  RESULT: FAILED — {result.error}")
        continue

    page = hikrobot_tab_to_page_content(result)
    print(f"  tab_id: {result.tab_id!r}")
    print(f"  images: {len(result.images)}")
    print(f"  text length: {len(result.text)}")
    print(f"  text snippet: {result.text[:300]!r}")
    print(f"  first 3 images: {result.images[:3]}")
    print(f"  FULL TEXT:\n{result.text}")
    print()

print("\nDone.")
