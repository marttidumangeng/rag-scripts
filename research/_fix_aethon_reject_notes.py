"""Expand Aethon rejected robots' rejection_reason + notes for content-queue UI."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from api_client import ResearchApiClient
from load_env import load_research_env

load_research_env()

# Reviewer-facing reasons (also stored in notes so the Notes field is populated).
REASONS: dict[int, str] = {
    1766: (
        "Duplicate of published T3 (1533). Same live cart-transport AMR under the "
        "older 'Aethon TUG T3' display name. Keep 1533."
    ),
    1767: (
        "Duplicate of published T3 XL (1534). Same live high-capacity cart AMR under "
        "the older 'Aethon TUG T3 XL' display name. Keep 1534."
    ),
    1768: (
        "Duplicate of published Zena RX (1532). Same live healthcare cabinet AMR "
        "under the older 'Aethon Zena RX' display name. Keep 1532."
    ),
    1770: (
        "Off-catalog phantom: TUG Exchange is a discontinued part-number / config "
        "shell. Current aethon.com robot nav is T3, Zena RX, and Zena only."
    ),
    1771: (
        "Off-catalog phantom: TUG Drawer (293220) part-number shell. Not on current "
        "OEM robot catalog (T3 / Zena RX / Zena)."
    ),
    1772: (
        "Off-catalog phantom: TUG Drawer (293219) part-number shell. Not on current "
        "OEM robot catalog (T3 / Zena RX / Zena)."
    ),
    1773: (
        "Off-catalog phantom: TUG Drawer (293218) part-number shell. Not on current "
        "OEM robot catalog (T3 / Zena RX / Zena)."
    ),
    1774: (
        "Off-catalog phantom: TUG Door (293200) part-number shell. Not on current "
        "OEM robot catalog (T3 / Zena RX / Zena)."
    ),
    86: (
        "Wrong media: primary image is a Locus Vector (wrong brand). Classic TUG is "
        "superseded by the live T3 / Zena / Zena RX catalog; no clean robot-only OEM "
        "still was available after site Wordfence blocks."
    ),
    567: (
        "Wrong media: primary image is a non-Aethon warehouse AMR base. TUG T4 is "
        "not on the current OEM nav (T3 / Zena RX / Zena); treat as superseded legacy."
    ),
}


def main() -> int:
    client = ResearchApiClient()
    for rid, reason in REASONS.items():
        notes = f"[REJECTED 2026-07-20]\n{reason}\n---\n"
        body = {
            "status": "rejected",
            "rejection_reason": reason,
            "notes": notes,
        }
        client._patch(f"robots/robots/{rid}/", body)
        after = client._get(f"robots/robots/{rid}/")
        print(
            rid,
            after.get("status"),
            "reason_len",
            len(after.get("rejection_reason") or ""),
            "notes_len",
            len(after.get("notes") or ""),
            (after.get("name") or "")[:40],
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
