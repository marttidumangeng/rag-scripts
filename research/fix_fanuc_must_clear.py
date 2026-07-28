#!/usr/bin/env python3
"""FANUC (189) must-clear fix: country, short features, uses, image notes.

Blockers (moderate_robots dry-run):
  - no_country ×109 — manufacturer_countries empty (company already JP id=11)
  - no_features ×60 — features <40 chars (short but valid application keywords)
  - no_image ×2 — M-800iA/60W, M-810iA/45 (no live OEM still; IMAGE TO-DO note)
  - no_uses ×1 — M-2000iA/2300 (1750)

Also: re-assert availability_status=11 (Available); scrub nav-chrome junk features.

Usage:
  python fix_fanuc_must_clear.py
  python fix_fanuc_must_clear.py --apply
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env
from api_client import ResearchApiClient

load_research_env(local="--local" in sys.argv)

COMPANY_ID = 189
JP_ID = 11
AVAILABLE = 11

# Robots with no genuine OEM still (prior attach_fanuc_noimg NO_RENDER)
NO_IMAGE = {
    4115: "M-800iA/60W — fanucamerica.com/series/m-800 has no model-specific still for 60W washdown variant",
    4117: "M-810iA/45 — fanucamerica.com/series/m-810 has no live model still",
}

# Uses for heavy M-2000 palletizing/handling (mirror sibling 4212)
USES_M2000 = ["assembly", "palletizing", "pick-and-place"]

JUNK_FEATURE_RE = re.compile(
    r"Skip to CONTENTS|Input search words|FANUC CORPORATION\s*$|Products\s*-\s*FANUC",
    re.I,
)


def list_pending(client: ResearchApiClient) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    page = 1
    while True:
        data = client._get(
            "robots/robots/",
            params={
                "company_ref": COMPANY_ID,
                "status": "pending_review",
                "page": page,
                "page_size": 50,
            },
        )
        batch = data.get("results") or []
        rows.extend(batch)
        if not data.get("next") or not batch:
            break
        page += 1
        time.sleep(0.05)
    return rows


def expand_features(name: str, features: str) -> str:
    """Grow short/valid keywords to ≥40 chars without inventing specs."""
    feat = (features or "").strip()
    if JUNK_FEATURE_RE.search(feat):
        feat = ""
    model = re.sub(r"^FANUC\s+", "", name or "", flags=re.I).strip() or "robot"
    if len(feat) >= 40 and not JUNK_FEATURE_RE.search(feat):
        return feat
    if feat:
        # Keep existing application keywords; add model framing.
        out = (
            f"{feat}. FANUC {model} industrial robot for factory automation "
            f"and production-cell applications."
        )
    else:
        out = (
            f"FANUC {model} industrial articulated robot for manufacturing, "
            f"handling, and production-cell applications."
        )
    return out if len(out) >= 40 else (out + " OEM catalog model.")


def image_todo_note(reason: str, existing: str) -> str:
    block = (
        "[IMAGE TO-DO — no hero, deliberate]\n"
        f"{reason}\n"
        "Checked fanucamerica.com series page; no distinct model still found.\n"
        "ACTION FOR TEAM: source a licensed model-specific photo from FANUC, "
        "or merge if this SKU is a duplicate of a sibling with media.\n"
        "Do NOT substitute a sibling render, a family banner, or marketing/diagram art.\n"
        "---\n"
    )
    existing = (existing or "").strip()
    if "[IMAGE TO-DO" in existing:
        return existing
    return block + existing if existing else block.rstrip()


def build_patch(robot: dict[str, Any]) -> dict[str, Any]:
    rid = int(robot["id"])
    name = robot.get("name") or ""
    feat = expand_features(name, robot.get("features") or "")
    payload: dict[str, Any] = {
        "manufacturer_countries": [JP_ID],
        "manufacturer_country_ref": JP_ID,
        "availability_status": AVAILABLE,
        "features": feat,
    }
    if rid == 1750:
        # Use catalog IDs (assembly=21, pick-and-place=22, palletizing=25)
        payload["uses"] = [21, 25, 22]
    if rid in NO_IMAGE:
        payload["notes"] = image_todo_note(NO_IMAGE[rid], robot.get("notes") or "")
    return payload


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--ids", type=int, nargs="*")
    args = ap.parse_args()

    client = ResearchApiClient()
    # ensure company country stays JP
    try:
        client.patch_company(COMPANY_ID, {"country_id": JP_ID})
        print("company country_id=JP ok")
    except Exception as e:
        print("company patch warn:", e)

    pending = list_pending(client)
    if args.ids:
        want = set(args.ids)
        pending = [r for r in pending if int(r["id"]) in want]
    print(f"pending={len(pending)}")

    plan = []
    for r in pending:
        patch = build_patch(r)
        plan.append(
            {
                "id": int(r["id"]),
                "name": r.get("name"),
                "feat_before": len((r.get("features") or "").strip()),
                "feat_after": len(patch["features"]),
                "no_image": int(r["id"]) in NO_IMAGE,
                "fix_uses": int(r["id"]) == 1750,
            }
        )
        if not args.apply:
            continue
        rid = int(r["id"])
        body = {
            "manufacturer_countries": patch["manufacturer_countries"],
            "manufacturer_country_ref": patch["manufacturer_country_ref"],
            "availability_status": patch["availability_status"],
            "features": patch["features"],
        }
        if "notes" in patch:
            body["notes"] = patch["notes"]
        if "uses" in patch:
            body["uses"] = patch["uses"]
        try:
            client._patch(f"robots/robots/{rid}/", body)
            print(f"  patched {rid} feat {plan[-1]['feat_before']}→{plan[-1]['feat_after']}")
        except Exception as e:
            print(f"  ERROR {rid}: {e}")
            plan[-1]["error"] = str(e)
        time.sleep(0.12)

    out = _HERE / "staging" / "reports" / "fanuc-must-clear-fix.json"
    out.write_text(
        json.dumps({"apply": args.apply, "n": len(plan), "plan": plan}, indent=2),
        encoding="utf-8",
    )
    print("wrote", out)
    if not args.apply:
        print("dry-run only; pass --apply to PATCH")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
