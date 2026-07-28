"""ACY Automation Inc. (1369) soft enrich — family, purpose, URLs, availability.

Must-clear gates (photo/features/country/cats/uses) already pass on the 90
pending_review EOAT SKUs. Soft gaps: empty family_*, purpose≈description on ~47,
stale availability=Released, and dead `/en/` product URLs (live site is root paths).

Family keys follow OEM catalog hubs on https://acy.com.tw/ (no /en/).
Purpose lines are EOAT application tasks (newline-separated), not description copies.
Typed dims already on most rows are preserved; name-parsed bore/stroke/size fill gaps only.

Usage:
  python fix_acy_enrich.py
  python fix_acy_enrich.py --apply
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
from validate_staging import purpose_duplicates_description  # noqa: E402

COMPANY_ID = 1369
TW_ID = 18
AVAILABLE = 11
REPORT = _HERE / "staging" / "reports" / "acy-enrich-patch.json"
AUDIT = _HERE / "staging" / "reports" / "acy-fleet-audit.json"

# Use PKs
USE = {
    "assembly": 21,
    "pick-and-place": 22,
    "palletizing": 25,
    "material-handling": 32,
    "machine-tending": 36,
}

# OEM series hubs → family_* + application purpose
FAMILY: dict[str, dict[str, Any]] = {
    "square-quick-changer": {
        "family_key": "acy:square-quick-changer",
        "family_name": "Square Quick Changers",
        "family_url": "https://acy.com.tw/Quick-Change-System/square-quick-changers",
        "purpose": "EOAT tool changing\nModular end-of-arm tool swap\nSquare robot/tool interface",
        "uses": [USE["assembly"], USE["pick-and-place"], USE["material-handling"]],
    },
    "round-quick-changer": {
        "family_key": "acy:round-quick-changer",
        "family_name": "Round Quick Changers",
        "family_url": "https://acy.com.tw/Quick-Change-System",
        "purpose": "EOAT tool changing\nRound robot/gripper quick-change interface\nPneumatic tool swap",
        "uses": [USE["assembly"], USE["pick-and-place"], USE["material-handling"]],
    },
    "star-quick-changer": {
        "family_key": "acy:star-quick-changer",
        "family_name": "Star / Yushin Type Quick Changers",
        "family_url": "https://acy.com.tw/Quick-Change-System/Rectangle-Quick-Changer",
        "purpose": "Star/Yushin-compatible EOAT quick change\nInjection-molding robot tool swap",
        "uses": [USE["machine-tending"], USE["pick-and-place"], USE["assembly"]],
    },
    "qc-base-plate": {
        "family_key": "acy:qc-base-plate",
        "family_name": "EOAT Base Plates",
        "family_url": "https://acy.com.tw/Quick-Change-System/EOAT-Base-Plate",
        "purpose": "EOAT base mounting\nQuick-changer robot-side plate interface",
        "uses": [USE["assembly"], USE["pick-and-place"]],
    },
    "qc-holding-bracket": {
        "family_key": "acy:qc-holding-bracket",
        "family_name": "EOAT Holding Brackets",
        "family_url": "https://acy.com.tw/Quick-Change-System/EOAT-Holding-Bracket",
        "purpose": "EOAT tool storage\nQuick-changer holding / parking bracket",
        "uses": [USE["assembly"], USE["machine-tending"]],
    },
    "qc-hanger": {
        "family_key": "acy:qc-hanger",
        "family_name": "Quick Changer Hangers",
        "family_url": "https://acy.com.tw/Quick-Change-System/Quick-Changer-Hanger",
        "purpose": "EOAT hanger storage\nQuick-changer parking / hanging bracket",
        "uses": [USE["assembly"], USE["machine-tending"]],
    },
    "micro-sprue-gripper": {
        "family_key": "acy:micro-sprue-gripper",
        "family_name": "Micro Sprue Grippers",
        "family_url": "https://acy.com.tw/Sprue-Finger-Gripper/Micro-Sprue-Gripper",
        "purpose": "Sprue picking\nInjection-molding demolding\nFine-gate / micro sprue grip",
        "uses": [USE["machine-tending"], USE["pick-and-place"], USE["material-handling"]],
    },
    "mini-sprue-gripper": {
        "family_key": "acy:mini-sprue-gripper",
        "family_name": "Mini Sprue Grippers",
        "family_url": "https://acy.com.tw/Sprue-Finger-Gripper/Mini-Sprue-Gripper",
        "purpose": "Sprue picking\nInjection-molding demolding\nSerrated / textured sprue grip",
        "uses": [USE["machine-tending"], USE["pick-and-place"], USE["material-handling"]],
    },
    "slide-sprue-gripper": {
        "family_key": "acy:slide-sprue-gripper",
        "family_name": "Slide Sprue Grippers",
        "family_url": "https://acy.com.tw/Sprue-Finger-Gripper/Slide-Sprue-Gripper-with-optional-Sensor",
        "purpose": "Sprue picking with optional sensor confirmation\nInjection-molding demolding",
        "uses": [USE["machine-tending"], USE["pick-and-place"]],
    },
    "large-sprue-gripper": {
        "family_key": "acy:large-sprue-gripper",
        "family_name": "Large Sprue Grippers",
        "family_url": "https://acy.com.tw/Sprue-Finger-Gripper/Large-Sprue-Gripper",
        "purpose": "Heavy sprue picking\nLarge-gate demolding\nInjection-molding part handling",
        "uses": [USE["machine-tending"], USE["material-handling"], USE["pick-and-place"]],
    },
    "angular-gripper": {
        "family_key": "acy:angular-gripper",
        "family_name": "Angular Grippers",
        "family_url": "https://acy.com.tw/Sprue-Finger-Gripper",
        "purpose": "Angular gripping\nPart clamping for demolding\nPick-and-place with angled jaws",
        "uses": [USE["pick-and-place"], USE["machine-tending"], USE["material-handling"]],
    },
    "parallel-gripper": {
        "family_key": "acy:parallel-gripper",
        "family_name": "Parallel Grippers",
        "family_url": "https://acy.com.tw/Sprue-Finger-Gripper/Parallel-Grippers",
        "purpose": "Parallel jaw gripping\nPick-and-place\nMachine tending",
        "uses": [USE["pick-and-place"], USE["machine-tending"], USE["material-handling"]],
    },
    "wide-opening-gripper": {
        "family_key": "acy:wide-opening-gripper",
        "family_name": "Wide-Opening Air Grippers",
        "family_url": "https://acy.com.tw/Sprue-Finger-Gripper/Wide-Opening-Air-Grippers",
        "purpose": "Wide-part gripping\nLarge sprue / part demolding\nLong-stroke jaw open",
        "uses": [USE["pick-and-place"], USE["machine-tending"], USE["material-handling"]],
    },
    "radial-gripper": {
        "family_key": "acy:radial-gripper",
        "family_name": "Radial 3-Jaw High Precision Grippers",
        "family_url": "https://acy.com.tw/Sprue-Finger-Gripper/Radial-3Jaws-High-Precision-Grippers",
        "purpose": "Centric 3-jaw gripping\nHigh-precision part handling\nRound-part pick-and-place",
        "uses": [USE["pick-and-place"], USE["assembly"], USE["machine-tending"]],
    },
    "finger-gripper-sensor": {
        "family_key": "acy:finger-gripper-sensor",
        "family_name": "Finger Grippers with Sensor Modules",
        "family_url": "https://acy.com.tw/finger-gripper-with-sensor-modules",
        "purpose": "Soft finger gripping\nSensor-confirmed part presence\nDelicate pick-and-place",
        "uses": [USE["pick-and-place"], USE["machine-tending"], USE["material-handling"]],
    },
    "vacuum-cup": {
        "family_key": "acy:vacuum-cup",
        "family_name": "Vacuum Cups & Cup Fittings",
        "family_url": "https://acy.com.tw/Vacuum-Suction-CupConnector-CupFitting",
        "purpose": "Vacuum part handling\nFlat-surface pick-and-place\nEOAT suction gripping",
        "uses": [USE["pick-and-place"], USE["material-handling"], USE["palletizing"]],
    },
    "mounting-clamp": {
        "family_key": "acy:mounting-clamp",
        "family_name": "EOAT Mounting Clamps",
        "family_url": "https://acy.com.tw/EOAT-Mounting-Clamp",
        "purpose": "EOAT frame mounting\nTube/profile clamp joints\nVacuum-cup and gripper positioning",
        "uses": [USE["assembly"], USE["material-handling"]],
    },
    "aluminum-profile": {
        "family_key": "acy:aluminum-profile",
        "family_name": "EOAT Aluminum Profiles",
        "family_url": "https://acy.com.tw/EOAT-Profile-Frame-connector-Channel-Nut/EOAT-Aluminum-Profile",
        "purpose": "EOAT frame structure\nT-slot aluminum tooling frame\nEnd-of-arm frame build",
        "uses": [USE["assembly"]],
    },
    "frame-connector": {
        "family_key": "acy:frame-connector",
        "family_name": "EOAT Frame Connectors",
        "family_url": "https://acy.com.tw/EOAT-Profile-Frame-connector-Channel-Nut/EOAT-Profile-Connector",
        "purpose": "EOAT profile joining\nL/T-type frame connectors\nTooling frame assembly",
        "uses": [USE["assembly"]],
    },
    "channel-nut": {
        "family_key": "acy:channel-nut",
        "family_name": "EOAT Channel Nuts",
        "family_url": "https://acy.com.tw/EOAT-Profile-Frame-connector-Channel-Nut/EOAT-Channel-Nut",
        "purpose": "EOAT profile fastening\nT-slot channel nut mounting",
        "uses": [USE["assembly"]],
    },
    "gripper-arm": {
        "family_key": "acy:gripper-arm",
        "family_name": "Gripper Mounting Arms",
        "family_url": "https://acy.com.tw/Gripper-Mounting-Arm",
        "purpose": "Gripper/vacuum arm extension\nEOAT reach positioning\nElbow / angle arm mounting",
        "uses": [USE["assembly"], USE["pick-and-place"], USE["material-handling"]],
    },
    "mini-cylinder": {
        "family_key": "acy:mini-cylinder",
        "family_name": "Mini / Twin-Rod / Slide Cylinders",
        "family_url": "https://acy.com.tw/Mini-Twin-Rod-Slide-Cylinder",
        "purpose": "EOAT linear actuation\nGuided slide / twin-rod motion\nRotary / table cylinder motion",
        "uses": [USE["assembly"], USE["material-handling"], USE["machine-tending"]],
    },
    "holder-suspension": {
        "family_key": "acy:holder-suspension",
        "family_name": "Vacuum Cup Holders & Suspensions",
        "family_url": "https://acy.com.tw/Holder-Bracket-Suspension",
        "purpose": "Vacuum cup suspension\nNon-rotating suction-cup holder\nCompliant EOAT cup mounting",
        "uses": [USE["pick-and-place"], USE["material-handling"], USE["assembly"]],
    },
    "air-nipper": {
        "family_key": "acy:air-nipper",
        "family_name": "Air Gate Cutters / Nippers",
        "family_url": "https://acy.com.tw/Air-Gate-Cutter",
        "purpose": "Gate cutting\nSprue / runner cutting\nInjection-molding trim",
        "uses": [USE["machine-tending"], USE["material-handling"]],
    },
}

# Misfiled product URLs on OEM (hash/category mismatch) → correct hub/PDP
URL_OVERRIDE: dict[int, str] = {
    1399: "https://acy.com.tw/EOAT-Profile-Frame-connector-Channel-Nut/EOAT-Aluminum-Profile",
    1394: "https://acy.com.tw/EOAT-Mounting-Clamp/End-Of-Arm-Tooling-Angle-Clamp",
}


def fix_url(url: str) -> str:
    if not url:
        return url
    frag = ""
    if "#" in url:
        url, frag = url.split("#", 1)
        frag = "#" + frag
    url = url.replace("https://acy.com.tw/en/", "https://acy.com.tw/")
    url = url.replace("http://acy.com.tw/en/", "https://acy.com.tw/")
    if url.startswith("http://acy.com.tw/"):
        url = "https://" + url[len("http://") :]
    return url + frag


def classify(name: str, url: str) -> str:
    n = (name or "").lower()
    path = fix_url(url).lower()

    if "aluminum profile" in n or ("x-type" in n and "profile" in n):
        return "aluminum-profile"
    if "air nipper" in n or (
        "air-gate-cutter" in path and "aluminum" not in n and "x-type" not in n
    ):
        return "air-nipper"
    if "channel nut" in n:
        return "channel-nut"
    if "frame connector" in n or "l-type frame" in n or "t-type frame" in n:
        return "frame-connector"
    if (
        "angle clamp" in n
        or "cross clamp" in n
        or "angle plate" in n
        or ("swivel" in n and "clamp" in n)
        or "heavy-duty angle clamp" in n
        or re.search(r"\bhdac\b", n)
    ):
        return "mounting-clamp"
    if (
        "mounting arm" in n
        or "elbow arm" in n
        or "angle arm" in n
        or "gripper-mounting-arm" in path
    ):
        return "gripper-arm"
    if "suspension" in n or "holder bracket" in n or "holder-bracket-suspension" in path:
        return "holder-suspension"
    if "vacuum cup" in n or "cup fitting" in n or "suction cup" in n:
        return "vacuum-cup"

    # Grippers — name tokens first (path Sprue-Finger-Gripper must NOT steal these)
    if "wide-opening" in n or "wide opening" in n:
        return "wide-opening-gripper"
    if "radial" in n or "3-jaw" in n or "high precision gripper" in n:
        return "radial-gripper"
    if "parallel gripper" in n:
        return "parallel-gripper"
    if "angular gripper" in n:
        return "angular-gripper"
    if "slide sprue" in n:
        return "slide-sprue-gripper"
    if "large sprue" in n:
        return "large-sprue-gripper"
    if "mini sprue" in n:
        return "mini-sprue-gripper"
    if "micro sprue" in n or "micro-4mm" in path:
        return "micro-sprue-gripper"
    if "finger gripper" in n or "finger-gripper-with-sensor" in path:
        return "finger-gripper-sensor"
    if "cylinder" in n or "mini-twin-rod" in path or "slide table" in n or "twin rod" in n:
        return "mini-cylinder"

    # Quick-change family — check before \bhanger\b (substring of "changer")
    if "base plate" in n or "eoat-base-plate" in path:
        return "qc-base-plate"
    if "holding bracket" in n or "eoat-holding-bracket" in path:
        return "qc-holding-bracket"
    if re.search(r"\bhanger\b", n) or "quick-changer-hanger" in path:
        return "qc-hanger"
    if "star" in n or "yushin" in n or "rectangle-quick-changer" in path:
        return "star-quick-changer"
    if (
        "round quick" in n
        or re.search(r"\b(aq|bq)\d+", n)
        or "standard-robot-side" in path
        or "standard-gripper-side" in path
    ):
        return "round-quick-changer"
    if "square quick" in n or "square-quick" in path:
        return "square-quick-changer"
    if "quick changer" in n or "quick-change" in path:
        return "square-quick-changer"
    if "sprue" in n:
        return "mini-sprue-gripper"
    raise ValueError(f"unclassified: {name!r} url={url!r}")


def variant_label(name: str) -> str:
    m = re.search(r"#(\d+F?)", name)
    if m:
        return f"Size #{m.group(1)}"
    m = re.search(r"(\d+)\s*mm\s*Bore.*?(\d+)\s*mm\s*Stroke", name, re.I)
    if m:
        return f"{m.group(1)} mm bore / {m.group(2)} mm stroke"
    m = re.search(r"(\d+)\s*mm\s*Bore", name, re.I)
    if m:
        return f"{m.group(1)} mm bore"
    m = re.search(r"(FG-?\d+\w*|HDAC-\d+|NS-\d+|AR\d+|B\d+)", name, re.I)
    if m:
        return m.group(1).upper()
    return name


def parse_dims(name: str, existing: dict[str, Any]) -> dict[str, float]:
    """Fill missing typed dims from model designation only."""
    out: dict[str, float] = {}
    n = name or ""

    def miss(key: str) -> bool:
        return existing.get(key) is None

    m = re.search(r"#(\d+)", n)
    if m and miss("width_mm"):
        out["width_mm"] = float(m.group(1))
    m = re.search(r"(?:AQ|BQ|QC)(\d+)", n, re.I)
    if m and miss("width_mm"):
        out["width_mm"] = float(m.group(1))
    m = re.search(r"(\d+)\s*mm\s*Bore", n, re.I)
    if m and miss("width_mm"):
        out["width_mm"] = float(m.group(1))
    m = re.search(r"(\d+)\s*mm\s*Stroke", n, re.I)
    if m and miss("height_mm"):
        out["height_mm"] = float(m.group(1))
    m = re.search(r"(\d+)\s*x\s*(\d+)", n, re.I)
    if m and "profile" in n.lower():
        if miss("width_mm"):
            out["width_mm"] = float(m.group(1))
        if miss("height_mm"):
            out["height_mm"] = float(m.group(2))
        if miss("length_mm"):
            out["length_mm"] = 1000.0  # 1m profile designation
    return out


def build_patch(robot: dict[str, Any], detail: dict[str, Any] | None = None) -> dict[str, Any]:
    rid = int(robot["id"])
    detail = detail or {}
    name = (detail.get("name") or robot.get("name") or "").strip()
    raw_url = detail.get("url") or robot.get("url") or ""
    if rid in URL_OVERRIDE:
        url = URL_OVERRIDE[rid]
    else:
        url = fix_url(raw_url)

    fam_id = classify(name, URL_OVERRIDE.get(rid, raw_url))
    fam = FAMILY[fam_id]

    existing = {
        "width_mm": (detail or {}).get("width_mm"),
        "height_mm": (detail or {}).get("height_mm"),
        "length_mm": (detail or {}).get("length_mm"),
        "weight_kg": (detail or {}).get("weight_kg"),
    }
    dims = parse_dims(name, existing)

    scope = "family" if ("#" in raw_url or fam_id in {
        "square-quick-changer", "vacuum-cup", "finger-gripper-sensor", "air-nipper",
    }) else "exact_variant"

    patch: dict[str, Any] = {
        "id": rid,
        "name": name,
        "model_name": name,
        "variant_code": name,
        "variant_label": variant_label(name),
        "family_key": fam["family_key"],
        "family_name": fam["family_name"],
        "family_url": fam["family_url"],
        "product_url_scope": scope,
        "url": url,
        "purpose": fam["purpose"],
        "uses": list(fam["uses"]),
        "manufacturer_countries": [TW_ID],
        "manufacturer_country_ref": TW_ID,
        "availability_status": AVAILABLE,
        "source_locale": "en",
        "notes": (
            "[AI Research] ACY soft enrich 2026-07-20: family_* from OEM catalog hubs, "
            "application purpose lines, strip dead /en/ URLs, availability=Available."
        ),
        "_fam_id": fam_id,
    }
    patch.update(dims)
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
        "source_locale": "en",
        "notes": patch["notes"],
    }
    for k in ("width_mm", "height_mm", "length_mm", "weight_kg"):
        if patch.get(k) is not None:
            body[k] = patch[k]
    return body


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--ids", type=int, nargs="*")
    ap.add_argument("--patch-company-website", action="store_true", default=True)
    args = ap.parse_args()

    client = ResearchApiClient()
    robots = None
    for attempt in range(8):
        try:
            robots = client.list_robots_for_company(COMPANY_ID)
            break
        except Exception as exc:  # noqa: BLE001
            print(f"list retry {attempt}: {exc}")
            time.sleep(5)
    if robots is None:
        print("ERROR: could not list robots", file=sys.stderr)
        return 2

    robots = [r for r in robots if (r.get("status") or "") == "pending_review"]
    if args.ids:
        want = set(args.ids)
        robots = [r for r in robots if int(r["id"]) in want]

    # Prefer audit cache for dims; refresh detail only when needed
    audit_by_id: dict[int, dict] = {}
    if AUDIT.exists():
        for row in json.loads(AUDIT.read_text(encoding="utf-8")):
            audit_by_id[int(row["id"])] = row

    patches: list[dict[str, Any]] = []
    dup_warns: list[tuple] = []
    class_err: list[str] = []

    for r in robots:
        rid = int(r["id"])
        detail = audit_by_id.get(rid)
        if detail is None:
            try:
                detail = client._get(f"robots/robots/{rid}/")
            except Exception as exc:  # noqa: BLE001
                print(f"  skip detail {rid}: {exc}")
                detail = {"url": r.get("url") or "", "name": r.get("name")}
        try:
            p = build_patch(r, detail)
        except ValueError as exc:
            class_err.append(str(exc))
            continue
        desc = (detail.get("description") or r.get("description") or "").strip()
        dup = purpose_duplicates_description(p["purpose"], desc)
        if dup:
            dup_warns.append((p["id"], p["name"], dup))
        patches.append(p)

    fam_counts: dict[str, int] = {}
    for p in patches:
        fam_counts[p["family_key"]] = fam_counts.get(p["family_key"], 0) + 1

    stats = {
        "total": len(patches),
        "families": sorted(fam_counts.items()),
        "purpose_dup_warns": len(dup_warns),
        "classify_errors": class_err,
        "url_en_fixed": sum(1 for p in patches if "/en/" not in (p.get("url") or "")),
        "dims_filled": sum(
            1
            for p in patches
            if any(p.get(k) is not None for k in ("width_mm", "height_mm", "length_mm"))
            and p.get("_fam_id")
        ),
    }
    plan = {"stats": stats, "apply": args.apply, "patches": patches}
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(json.dumps({k: v for k, v in stats.items() if k != "families"}, indent=2))
    print("families:")
    for fk, n in sorted(fam_counts.items(), key=lambda x: -x[1]):
        print(f"  {n:3d}  {fk}")
    for p in patches[:6]:
        print(
            f"  {p['id']} {p['name']}: {p['family_key']} "
            f"url={p['url'][:60]} purpose={p['purpose'].split(chr(10))[0]}"
        )
    if class_err:
        print("CLASSIFY ERRORS", len(class_err))
        for e in class_err[:20]:
            print(" ", e)
    if dup_warns:
        print("WARN purpose_dup still", len(dup_warns))

    if not args.apply:
        print("dry-run only; pass --apply to PATCH")
        return 1 if class_err else 0

    if args.patch_company_website:
        try:
            client.patch_company(COMPANY_ID, {"website": "https://acy.com.tw/"})
            print("company website -> https://acy.com.tw/")
        except Exception as exc:  # noqa: BLE001
            print(f"company website patch failed: {exc}")

    ok = err = 0
    for p in patches:
        rid = p["id"]
        body = build_body(p)
        try:
            client._patch(f"robots/robots/{rid}/", body)
            # Re-PATCH soft fields (bulk/import wipe pattern)
            soft = {
                "availability_status": AVAILABLE,
                "family_key": p["family_key"],
                "family_name": p["family_name"],
                "family_url": p["family_url"],
                "manufacturer_countries": [TW_ID],
                "manufacturer_country_ref": TW_ID,
                "purpose": p["purpose"],
                "uses": p["uses"],
                "url": p["url"],
            }
            for k in ("width_mm", "height_mm", "length_mm"):
                if p.get(k) is not None:
                    soft[k] = p[k]
            client._patch(f"robots/robots/{rid}/", soft)
            ok += 1
            if ok <= 5 or ok % 20 == 0:
                print(f"  patched {rid} {p['name']}")
        except Exception as exc:  # noqa: BLE001
            err += 1
            print(f"  FAIL {rid}: {exc}")
        time.sleep(0.08)

    print(f"done ok={ok} err={err}")
    return 0 if err == 0 and not class_err else 1


if __name__ == "__main__":
    raise SystemExit(main())
