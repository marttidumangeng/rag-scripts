"""List pending KUKA robots with fixable WARNs (tags/video/year/specs)."""
from __future__ import annotations

import json
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
d = json.loads(open("staging/reports/kuka-1396-pending-qa.json", encoding="utf-8").read())

FIXABLE = {"missing_tags", "missing_video", "missing_release_year", "missing_specs"}
for r in d["robots"]:
    codes = []
    for w in r.get("warns") or []:
        codes.append(w.get("flag") or w.get("code") or "")
    hit = [c for c in codes if c in FIXABLE]
    if hit:
        print(r["id"], r["name"][:40], hit, "hub" if r.get("notes_hub") else "")
