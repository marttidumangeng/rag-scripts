"""Audit Aethon rejected robots for empty notes / rejection_reason."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from api_client import ResearchApiClient
from load_env import load_research_env

load_research_env()
c = ResearchApiClient()
robots = c.list_robots_for_company(7) or []
print("status", dict(Counter(r.get("status") for r in robots)))

# Known reasons from discover_aethon_robots.py
REASONS = {
    1766: "duplicate: keep T3 (1533) — same live cart-AMR SKU under Aethon TUG T3 name",
    1767: "duplicate: keep T3 XL (1534) — same live cart-AMR SKU under Aethon TUG T3 XL name",
    1768: "duplicate: keep Zena RX (1532) — same live healthcare cabinet SKU under Aethon Zena RX name",
    1770: "phantom_sku: TUG Exchange part-number shell not on current aethon.com robot nav (T3 / Zena RX / Zena)",
    1771: "phantom_sku: TUG Drawer (293220) part-number shell not on current OEM catalog",
    1772: "phantom_sku: TUG Drawer (293219) part-number shell not on current OEM catalog",
    1773: "phantom_sku: TUG Drawer (293218) part-number shell not on current OEM catalog",
    1774: "phantom_sku: TUG Door (293200) part-number shell not on current OEM catalog",
    86: (
        "wrong_media: primary image is a Locus Vector (wrong brand); classic TUG "
        "superseded by live T3/Zena catalog; no clean robot-only OEM still available"
    ),
    567: (
        "wrong_media: primary image is a non-Aethon warehouse AMR base; TUG T4 "
        "not on current OEM nav (T3 / Zena RX / Zena); treat as superseded legacy"
    ),
}

rejected = []
for r in sorted(robots, key=lambda x: x.get("id") or 0):
    if r.get("status") != "rejected":
        continue
    rid = r["id"]
    d = c._get(f"robots/robots/{rid}/")
    notes = d.get("notes") or ""
    reason = d.get("rejection_reason") or ""
    rejected.append(
        {
            "id": rid,
            "name": d.get("name"),
            "rejection_reason": reason,
            "notes": notes,
            "keys": [k for k in d.keys() if "reject" in k.lower() or k == "notes"],
        }
    )
    print(f"=== {rid} {d.get('name')}")
    print(f"  rejection_reason empty={not bool(str(reason).strip())!s} len={len(str(reason))}")
    print(f"  notes empty={not bool(str(notes).strip())!s} len={len(str(notes))}")
    print(f"  rejection_reason={reason!r}"[:200])
    print(f"  notes={notes!r}"[:250])

Path("staging/reports/aethon-rejected-audit.json").write_text(
    json.dumps(rejected, indent=2, ensure_ascii=False), encoding="utf-8"
)
print("wrote staging/reports/aethon-rejected-audit.json count=", len(rejected))
