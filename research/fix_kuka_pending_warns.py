#!/usr/bin/env python3
"""Fix fixable KUKA pending_review soft WARNs (tags / junk retags / verified videos).

Honest leftovers (do NOT invent):
  - missing_price — no public MSRP
  - few_photos — KUKA family single-render ceiling
  - shared_url — family PDP URLs are intentional
  - missing_release_year on OmniMove hubs — no per-model OEM launch cite
  - missing_specs on some AMRs — leave blank unless OEM-cited
  - missing_video on LBR Med — no Med-specific clip (do not attach iiwa promo)

Usage:
  python fix_kuka_pending_warns.py
  python fix_kuka_pending_warns.py --apply
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient
from youtube_metadata import enrich_video_list

COMPANY_ID = 1396
REPORT = _RESEARCH_DIR / "staging" / "reports" / "kuka-1396-pending-warn-fix.json"

# TagCatalog-exact names as lists (DRF tags = ListField — never send a pipe string).
TAGS_ARM = [
    "Industrial Robot",
    "Automation",
    "Manufacturing",
    "Assembly",
    "Material Handling",
]
TAGS_COBOT = [
    "Collaborative Robot",
    "Industrial Robot",
    "Automation",
    "Assembly",
    "Manufacturing",
]
TAGS_AMR = [
    "AGV",
    "AMR",
    "Autonomous Mobile Robot",
    "Logistics",
    "Material Handling",
    "Warehouse Automation",
    "Wheeled",
]
TAGS_NANO = list(TAGS_ARM)
TAGS_SCARA = list(TAGS_ARM)
TAGS_QUANTEC = list(TAGS_ARM)
TAGS_DELTA = list(TAGS_ARM)
TAGS_LBR_MED = list(TAGS_COBOT)
TAGS_MOBILE_MANIP = [
    "AGV",
    "AMR",
    "Autonomous Mobile Robot",
    "Collaborative Robot",
    "Logistics",
    "Material Handling",
    "Manufacturing",
]

# Title-verified family clips (from fix_kuka_url_video_family / old_fleet).
YT_NANO = "https://www.youtube.com/watch?v=44GC57lhdtc"
YT_SCARA = "https://www.youtube.com/watch?v=Te5AfPQFz8U"
YT_QUANTEC = "https://www.youtube.com/watch?v=kROzVbWpANw"
YT_AMR = "https://www.youtube.com/watch?v=DUrKvPSOL8U"
# KR 3 D1200 / delta — use KUKA channel packaging/pick only if title matches; else omit.
YT_DELTA_CANDIDATES = [
    "https://www.youtube.com/watch?v=YbK8QK8QK8Q",  # placeholder rejected below
]

# Tags only — nano/SCARA/QUANTEC already have verified family videos.
# LBR Med: no Med-specific clip (do not attach iiwa promo).
# KR 3 D1200 / AMRs: retag to drop Humanoid/junk catalog tags.
SAFE_FIXES: dict[int, dict[str, Any]] = {
    4076: {"tags": TAGS_LBR_MED},
    4077: {"tags": TAGS_LBR_MED},
    4078: {"tags": TAGS_NANO},
    4079: {"tags": TAGS_NANO},
    4080: {"tags": TAGS_NANO},
    4081: {"tags": TAGS_NANO},
    4085: {"tags": TAGS_QUANTEC},
    4090: {"tags": TAGS_DELTA},
    4091: {"tags": TAGS_SCARA},
    4092: {"tags": TAGS_SCARA},
    3425: {"tags": TAGS_AMR},
    3427: {"tags": TAGS_AMR},
    3429: {"tags": TAGS_MOBILE_MANIP},
    3430: {"tags": TAGS_AMR},
    3431: {"tags": TAGS_AMR},
}


def _tag_names(raw: Any) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, str):
        return [p.strip() for p in raw.replace(",", "|").split("|") if p.strip()]
    out = []
    for t in raw:
        if isinstance(t, dict):
            n = (t.get("name") or "").strip()
            if n:
                out.append(n)
        elif isinstance(t, str) and t.strip():
            out.append(t.strip())
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    client = ResearchApiClient()
    plan = []
    for rid, body in SAFE_FIXES.items():
        r = client._get(f"robots/robots/{rid}/")
        old_tags = _tag_names(r.get("tags"))
        vids = r.get("videos") or r.get("video_urls") or []
        n_vids = len(vids) if isinstance(vids, list) else 0
        patch: dict[str, Any] = {"tags": body["tags"]}
        if body.get("video_urls") and n_vids == 0:
            enriched = enrich_video_list(list(body["video_urls"]))
            # Drop clips whose title enrichment failed (empty title = reject).
            good = [v for v in enriched if (v.get("title") or "").strip()]
            if good:
                patch["video_urls"] = good
        entry = {
            "id": rid,
            "name": r.get("name"),
            "status": r.get("status"),
            "old_tags": old_tags,
            "n_videos": n_vids,
            "patch": patch,
        }
        plan.append(entry)
        print(
            f"{rid} {r.get('name')}: tags {old_tags[:2]}… -> {body['tags'][:3]}… "
            f"vids={n_vids}->{'set' if 'video_urls' in patch else 'keep'}"
        )
        time.sleep(0.05)

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps({"plan": plan}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not args.apply:
        print(f"dry-run wrote {REPORT}; pass --apply")
        return 0

    ok = fail = 0
    for entry in plan:
        rid = entry["id"]
        if str(entry.get("status") or "").lower() != "pending_review":
            print(f"SKIP {rid}: status={entry.get('status')}")
            continue
        try:
            client._patch(f"robots/robots/{rid}/", entry["patch"])
            print(f"ok {rid}")
            ok += 1
        except Exception as e:  # noqa: BLE001
            print(f"FAIL {rid}: {e}")
            fail += 1
        time.sleep(0.15)

    print(f"DONE ok={ok} fail={fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
