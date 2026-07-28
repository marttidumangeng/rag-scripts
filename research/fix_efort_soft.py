#!/usr/bin/env python3
"""EFORT (1479) soft patch — family, purpose, typed specs, clean uses.

Prior fix_efort_robots.py cleared must-clear gates but left empty purpose/family_*
and did not persist payload_kg/reach_mm. GR6150 rows picked up junk Chinese uses.

Usage:
  python fix_efort_soft.py
  python fix_efort_soft.py --apply
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

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient  # noqa: E402
from fix_efort_robots import FAMILY, RECON_PATH, parse_specs  # noqa: E402
from validate_staging import purpose_duplicates_description  # noqa: E402

COMPANY_ID = 1479
CN_ID = 3
AVAILABLE = 11
REPORT = _HERE / "staging" / "reports" / "efort-soft-patch.json"

# Use PKs (robots/uses/)
USE = {
    "assembly": 21,
    "material-handling": 32,
    "machine-tending": 36,
    "welding": 29,
    "palletizing": 25,
    "painting": 39,
    "inspection": 7,
    "sorting": 47,
    "transport": 16,
}

# Category → family hub (first OEM PDP in series from recon)
CAT_FAMILY: dict[str, dict[str, Any]] = {
    "53": {
        "family_key": "efort:er-a-compact",
        "family_name": "ER A-Series (Compact)",
        "family_url": "https://efort.com.cn/en/index.php/product/product/53/279.html",
        "purpose": "Assembly\nPick-and-place\nMachine tending",
        "uses": [USE["assembly"], USE["machine-tending"]],
    },
    "54": {
        "family_key": "efort:er-a",
        "family_name": "ER A-Series",
        "family_url": "https://efort.com.cn/en/index.php/product/product/54/283.html",
        "purpose": "Assembly\nMaterial handling\nWelding\nMachine tending",
        "uses": [USE["assembly"], USE["material-handling"], USE["welding"]],
    },
    "55": {
        "family_key": "efort:er-a-high",
        "family_name": "ER A-Series (High Payload)",
        "family_url": "https://efort.com.cn/en/index.php/product/product/55/291.html",
        "purpose": "Material handling\nWelding\nPalletizing",
        "uses": [USE["material-handling"], USE["welding"], USE["palletizing"]],
    },
    "57": {
        "family_key": "efort:er-a-heavy",
        "family_name": "ER A-Series (Heavy Payload)",
        "family_url": "https://efort.com.cn/en/index.php/product/product/57/297.html",
        "purpose": "Heavy material handling\nPalletizing\nSpot welding",
        "uses": [USE["material-handling"], USE["palletizing"], USE["welding"]],
    },
    "260": {
        "family_key": "efort:er-f",
        "family_name": "ER F-Series (Foundry)",
        "family_url": "https://efort.com.cn/en/index.php/product/product/260/321.html",
        "purpose": "Foundry duty\nHeavy material handling\nLarge-part transfer",
        "uses": [USE["material-handling"], USE["transport"]],
    },
    "268": {
        "family_key": "efort:exr",
        "family_name": "EXR (Explosion-Proof)",
        "family_url": "https://efort.com.cn/en/index.php/product/product/268/363.html",
        "purpose": "Hazardous-area material handling\nSpraying\nAssembly",
        "uses": [USE["material-handling"], USE["assembly"]],
    },
    "58": {
        "family_key": "efort:gr6150",
        "family_name": "GR6150 (Spray Painting)",
        "family_url": "https://efort.com.cn/en/index.php/product/product/58/313.html",
        "purpose": "Spray painting\nCoating application\nExplosion-proof painting",
        "uses": [USE["painting"]],
    },
    "59": {
        "family_key": "efort:er-c",
        "family_name": "ER C-Series (Cobot)",
        "family_url": "https://efort.com.cn/en/index.php/product/product/59/335.html",
        "purpose": "Collaborative assembly\nMachine tending\nInspection",
        "uses": [USE["assembly"], USE["machine-tending"], USE["inspection"]],
    },
    "92": {
        "family_key": "efort:scara",
        "family_name": "ER SCARA",
        "family_url": "https://efort.com.cn/en/index.php/product/product/92/330.html",
        "purpose": "Pick-and-place\nAssembly\nSorting",
        "uses": [USE["assembly"], USE["sorting"]],
    },
    "109": {
        "family_key": "efort:er-4",
        "family_name": "ER 4-Axis (Palletizing)",
        "family_url": "https://efort.com.cn/en/index.php/product/product/109/324.html",
        "purpose": "Palletizing\nEnd-of-line stacking\nMaterial handling",
        "uses": [USE["palletizing"], USE["material-handling"]],
    },
}
DEFAULT_CAT = CAT_FAMILY["54"]


def load_recon() -> dict[int, dict]:
    rows = json.loads(RECON_PATH.read_text(encoding="utf-8"))
    return {int(r["id"]): r for r in rows}


def variant_label(name: str) -> str:
    """Human suffix from EFORT SKU (reach/payload token)."""
    m = re.match(r"^(?:ER|EXR|GR)(\d+(?:\.\d+)?)(?:A)?(?:-(\d+)(?:F|C|H)?)?", name.upper())
    if m and m.group(2):
        return f"{m.group(2)} mm reach"
    if "-" in name:
        return name.split("-", 1)[-1]
    return name


def build_patch(robot: dict, recon: dict[int, dict]) -> dict[str, Any]:
    rid = int(robot["id"])
    name = (robot.get("name") or "").strip()
    rr = recon.get(rid, {})
    cat = str(rr.get("category") or "")
    fam_cfg = CAT_FAMILY.get(cat, DEFAULT_CAT)
    fam = FAMILY.get(cat, FAMILY["54"])
    payload, reach, dof = parse_specs(name, cat)

    patch: dict[str, Any] = {
        "id": rid,
        "name": name,
        "model_name": name,
        "variant_code": name,
        "variant_label": variant_label(name),
        "family_key": fam_cfg["family_key"],
        "family_name": fam_cfg["family_name"],
        "family_url": fam_cfg["family_url"],
        "product_url_scope": "exact_variant",
        "url": (rr.get("url") or robot.get("url") or "").strip(),
        "purpose": fam_cfg["purpose"],
        "uses": fam_cfg["uses"],
        "manufacturer_countries": [CN_ID],
        "manufacturer_country_ref": CN_ID,
        "availability_status": AVAILABLE,
        "dof": dof,
        "source_locale": "en",
        "notes": (
            "[AI Research] EFORT soft patch 2026-07-20: family metadata, OEM application "
            f"purpose lines, typed payload/reach from model designation ({fam['kind']})."
        ),
    }
    if payload is not None:
        patch["payload_kg"] = float(payload)
    if reach is not None:
        patch["reach_mm"] = float(reach)
    return patch


def build_body(patch: dict[str, Any]) -> dict[str, Any]:
    body: dict[str, Any] = {
        "manufacturer_countries": patch["manufacturer_countries"],
        "manufacturer_country_ref": patch["manufacturer_country_ref"],
        "availability_status": patch["availability_status"],
        "name": patch["name"],
        "model_name": patch["model_name"],
        "variant_code": patch["variant_code"],
        "variant_label": patch["variant_label"],
        "family_key": patch["family_key"],
        "family_name": patch["family_name"],
        "family_url": patch["family_url"],
        "product_url_scope": patch["product_url_scope"],
        "url": patch["url"],
        "purpose": patch["purpose"],
        "uses": patch["uses"],
        "dof": patch["dof"],
        "source_locale": "en",
        "notes": patch["notes"],
    }
    for k in ("payload_kg", "reach_mm"):
        if patch.get(k) is not None:
            body[k] = patch[k]
    return body


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--ids", type=int, nargs="*")
    args = ap.parse_args()

    recon = load_recon()
    client = ResearchApiClient()
    robots = [
        r
        for r in client.list_robots_for_company(COMPANY_ID)
        if (r.get("status") or "") == "pending_review"
    ]
    if args.ids:
        want = set(args.ids)
        robots = [r for r in robots if int(r["id"]) in want]

    patches = []
    dup_warns = []
    for r in robots:
        p = build_patch(r, recon)
        desc = (r.get("description") or "").strip()
        if not desc:
            full = client._get(f"robots/robots/{p['id']}/")
            desc = (full.get("description") or "").strip()
        dup = purpose_duplicates_description(p["purpose"], desc)
        if dup:
            dup_warns.append((p["id"], p["name"], dup))
        patches.append(p)

    stats = {
        "total": len(patches),
        "with_payload": sum(1 for p in patches if p.get("payload_kg") is not None),
        "with_reach": sum(1 for p in patches if p.get("reach_mm") is not None),
        "families": sorted({p["family_key"] for p in patches}),
        "purpose_dup_warns": len(dup_warns),
    }
    plan = {"stats": stats, "apply": args.apply, "patches": patches}
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(json.dumps(stats, indent=2))
    print(f"plan -> {REPORT}")
    for p in patches[:8]:
        print(
            f"  {p['id']} {p['name']}: fam={p['family_key']} "
            f"p={p.get('payload_kg')} r={p.get('reach_mm')} uses={p['uses']}"
        )
        print(f"    purpose: {p['purpose'].replace(chr(10), ' | ')}")
    if dup_warns:
        print("WARN purpose duplicates description on", len(dup_warns), "rows")

    if not args.apply:
        print("dry-run only; pass --apply to PATCH")
        return 0

    ok = err = 0
    for p in patches:
        rid = p["id"]
        body = build_body(p)
        try:
            client._patch(f"robots/robots/{rid}/", body)
            # Re-PATCH typed columns (import/bulk wipe pattern)
            soft = {
                "availability_status": AVAILABLE,
                "family_key": p["family_key"],
                "family_name": p["family_name"],
                "family_url": p["family_url"],
                "manufacturer_countries": [CN_ID],
                "manufacturer_country_ref": CN_ID,
                "purpose": p["purpose"],
                "uses": p["uses"],
                "dof": p["dof"],
            }
            for k in ("payload_kg", "reach_mm"):
                if p.get(k) is not None:
                    soft[k] = p[k]
            client._patch(f"robots/robots/{rid}/", soft)
            ok += 1
            if ok <= 5 or ok % 15 == 0:
                print(f"  patched {rid} {p['name']}")
        except Exception as exc:  # noqa: BLE001
            err += 1
            print(f"  FAIL {rid}: {exc}")
        time.sleep(0.08)

    print(f"done ok={ok} err={err}")
    return 0 if err == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
