"""Single-model smoke test for Hikrobot tab extractor — TP0-T50."""
from __future__ import annotations
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from hikrobot_catalog import extract_hikrobot_tab

result = extract_hikrobot_tab("TP0-T50")
if result and result.success:
    print(f"tab_id: {result.tab_id!r}")
    print(f"images: {len(result.images)}")
    print("FULL TEXT:")
    print(result.text)
    print()
    print("IMAGES:")
    for img in result.images:
        print(" ", img)
else:
    print("FAILED:", result.error if result else "None")
