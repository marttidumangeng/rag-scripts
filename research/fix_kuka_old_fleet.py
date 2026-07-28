"""Remediate KUKA old fleet (ids < 5374): family series, specs, year, video, features, taxonomy.

Facts only — from kuka-recon OEM tables, LBR Med datasheet table, KUKA press/product pages.
Never invent prices (KUKA publishes no public MSRP). Never hop gen-1 → gen-2 for specs.

Usage:
  python fix_kuka_old_fleet.py            # dry-run
  python fix_kuka_old_fleet.py --apply
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient
from fix_kuka_features import MARKER, match, spec_line
from youtube_metadata import enrich_video_list

COMPANY_ID = 1396
MAX_ID = 5373  # old fleet only
COMPANY_SLUG = "kuka"
CATALOG = _RESEARCH_DIR / "staging" / "reports" / "kuka-recon.json"
AVAILABILITY_RELEASED = 3

FAMILY_META: dict[str, dict[str, str]] = {
    "kr-agilus": {
        "family_name": "KR AGILUS",
        "family_url": "https://www.kuka.com/en-us/products/robotics-systems/industrial-robots/kr-agilus",
    },
    "kr-4-agilus": {
        "family_name": "KR 4 AGILUS",
        "family_url": "https://www.kuka.com/en-us/products/robotics-systems/industrial-robots/kr-4-agilus",
    },
    "kr-cybertech": {
        "family_name": "KR CYBERTECH",
        "family_url": "https://www.kuka.com/en-us/products/robotics-systems/industrial-robots/kr-cybertech",
    },
    "kr-cybertech-nano": {
        "family_name": "KR CYBERTECH nano",
        "family_url": "https://www.kuka.com/en-us/products/robotics-systems/industrial-robots/kr-cybertech-nano",
    },
    "kr-cybertech-nano-arc": {
        "family_name": "KR CYBERTECH nano ARC",
        "family_url": "https://www.kuka.com/en-us/products/robotics-systems/industrial-robots/kr-cybertech-nano",
    },
    "kr-cybertech-arc": {
        "family_name": "KR CYBERTECH ARC",
        "family_url": "https://www.kuka.com/en-us/products/robotics-systems/industrial-robots/kr-cybertech",
    },
    "kr-iontec": {
        "family_name": "KR IONTEC",
        "family_url": "https://www.kuka.com/en-us/products/robotics-systems/industrial-robots/kr-iontec",
    },
    "kr-fortec": {
        "family_name": "KR FORTEC",
        "family_url": "https://www.kuka.com/en-us/products/robotics-systems/industrial-robots/kr-fortec",
    },
    "kr-fortec-pa": {
        "family_name": "KR FORTEC PA",
        "family_url": "https://www.kuka.com/en-us/products/robotics-systems/industrial-robots/kr-fortec-pa",
    },
    "kr-fortec-ultra": {
        "family_name": "KR FORTEC ultra",
        "family_url": "https://www.kuka.com/en-us/products/robotics-systems/industrial-robots/kr-fortec-ultra-heavy-duty-robot",
    },
    "kr-fortec-ultra-pa": {
        "family_name": "KR FORTEC ultra PA",
        "family_url": "https://www.kuka.com/en-us/products/robotics-systems/industrial-robots/kr-fortec-ultra-pa",
    },
    "kr-quantec": {
        "family_name": "KR QUANTEC",
        "family_url": "https://www.kuka.com/en-us/products/robotics-systems/industrial-robots/kr-quantec",
    },
    "kr-quantec-pa": {
        "family_name": "KR QUANTEC PA",
        "family_url": "https://www.kuka.com/en-us/products/robotics-systems/industrial-robots/kr-quantec-pa",
    },
    "kr-scara-robot": {
        "family_name": "KR SCARA",
        "family_url": "https://www.kuka.com/en-us/products/robotics-systems/industrial-robots/kr-scara-robot",
    },
    "kr-1000-titan": {
        "family_name": "KR 1000 titan",
        "family_url": "https://www.kuka.com/en-us/products/robotics-systems/industrial-robots/kr-1000-titan",
    },
    "kr-delta": {
        "family_name": "KR DELTA",
        "family_url": "https://www.kuka.com/en-us/products/robotics-systems/industrial-robots/kr-delta",
    },
    "kr-40-pa": {
        "family_name": "KR 40 PA",
        "family_url": "https://www.kuka.com/en-us/products/robotics-systems/industrial-robots/kr-40-pa",
    },
    "lbr-iisy": {
        "family_name": "LBR iisy",
        "family_url": "https://www.kuka.com/en-us/products/robotics-systems/industrial-robots/lbr-iisy",
    },
    "lbr-iiwa": {
        "family_name": "LBR iiwa",
        "family_url": "https://www.kuka.com/en-us/products/robotics-systems/industrial-robots/lbr-iiwa",
    },
    "lbr-med": {
        "family_name": "LBR Med",
        "family_url": "https://www.kuka.com/en-us/industries/health-care/kuka-medical-robotics/lbr-med",
    },
    "kmp": {
        "family_name": "KMP",
        "family_url": "https://www.kuka.com/en-us/products/amr-autonomous-mobile-robotics/topload-transport-robots",
    },
    "kmr-iisy": {
        "family_name": "KMR iisy",
        "family_url": "https://www.kuka.com/en-us/products/amr-autonomous-mobile-robotics/mobile-robot-systems/kmr-iisy-autonomous-mobile-cobot",
    },
    "omnimove": {
        "family_name": "KUKA omniMove",
        "family_url": "https://www.kuka.com/en-us/products/amr-autonomous-mobile-robotics/mobile-platforms",
    },
    "palletizing-robots": {
        "family_name": "KUKA palletizing robots",
        "family_url": "https://www.kuka.com/en-us/products/robotics-systems/industrial-robots/palletizing-robots",
    },
}

# Family-level years (same evidence set as depth batch + AMR press).
YEARS: dict[str, int] = {
    "kr-1000-titan": 2007,
    "kr-agilus": 2014,
    "kr-4-agilus": 2014,
    "kr-iontec": 2020,
    "kr-scara-robot": 2019,
    "lbr-iisy": 2021,
    "lbr-iiwa": 2013,
    "lbr-med": 2018,  # already on Med rows; family default
    "kr-cybertech": 2017,
    "kr-cybertech-nano": 2020,
    "kr-cybertech-nano-arc": 2021,
    "kr-cybertech-arc": 2017,
    "kr-fortec": 2024,
    "kr-fortec-pa": 2025,
    "kr-fortec-ultra": 2023,
    "kr-fortec-ultra-pa": 2025,
    "kr-quantec": 2010,
    "kr-quantec-pa": 2016,
    "kr-delta": 2018,
    "kr-40-pa": 2016,
    "kmp": 2023,  # KMP 600-S / 1500P press year for current P-line
    "kmr-iisy": 2023,
    "omnimove": 2010,  # long-running line; leave blank if unsure — override below
}

# Prefer blank over weak year for omniMove (no per-model launch found).
YEARS_OPTIONAL_BLANK = {"omnimove"}

VIDEO_URLS: dict[str, list[str]] = {
    "kr-agilus": ["https://www.youtube.com/watch?v=bod5_R58V6A"],
    "kr-4-agilus": ["https://www.youtube.com/watch?v=bod5_R58V6A"],
    "kr-cybertech": ["https://www.youtube.com/watch?v=Cx-l9jogO5I"],
    "kr-cybertech-nano": ["https://www.youtube.com/watch?v=44GC57lhdtc"],
    "kr-cybertech-nano-arc": ["https://www.youtube.com/watch?v=EbI5MjsNMpQ"],
    "kr-cybertech-arc": ["https://www.youtube.com/watch?v=Qzqlgs1phhE"],
    "kr-iontec": ["https://www.youtube.com/watch?v=4fCX3M7jPJs"],
    "kr-fortec": ["https://www.youtube.com/watch?v=AFjbTD7Wc1U"],
    "kr-fortec-ultra": ["https://www.youtube.com/watch?v=IEdDP_GA3gY"],
    "kr-fortec-pa": ["https://www.youtube.com/watch?v=Sc-6A97GETY"],
    "kr-fortec-ultra-pa": ["https://www.youtube.com/watch?v=Sc-6A97GETY"],
    "kr-quantec": ["https://www.youtube.com/watch?v=kROzVbWpANw"],
    "kr-quantec-pa": ["https://www.youtube.com/watch?v=6iDjmCDX0u4"],
    "kr-scara-robot": ["https://www.youtube.com/watch?v=Te5AfPQFz8U"],
    "kr-1000-titan": ["https://www.youtube.com/watch?v=uuIiBUvrCB4"],
    "lbr-iisy": ["https://www.youtube.com/watch?v=Bq8tTBW3R9g"],
    "lbr-iiwa": ["https://www.youtube.com/watch?v=_XU10uZbCy8"],
    "kr-delta": [],  # no verified series-titled clip in this pass
    "kr-40-pa": ["https://www.youtube.com/watch?v=6iDjmCDX0u4"],
    "palletizing-robots": ["https://www.youtube.com/watch?v=6iDjmCDX0u4"],
    "lbr-med": [],  # leave blank rather than attach non-Med iiwa promo
    "kmr-iisy": [],
    "kmp": [],
    "omnimove": [],
}

# Exact OEM facts not in industrial family tables.
MANUAL: dict[str, dict[str, Any]] = {
    "LBR Med 7 R800": {
        "family": "lbr-med",
        "payload_kg": 7.0,
        "reach_mm": 800.0,
        "features_line": (
            "Total load: 7 kg | Maximum reach: 800 mm | Axes: 7 | "
            "Protection class: IP 54 | Weight: approx. 25.5 kg | "
            "Controller: KUKA Sunrise Cabinet Med | "
            "Operating system: KUKA Sunrise.OS Med "
            "(OEM LBR Med technical data table)"
        ),
        "uses": [21, 22],
        "year": 2018,
    },
    "LBR Med 14 R820": {
        "family": "lbr-med",
        "payload_kg": 14.0,
        "reach_mm": 820.0,
        "features_line": (
            "Total load: 14 kg | Maximum reach: 820 mm | Axes: 7 | "
            "Protection class: IP 54 | Weight: approx. 32.3 kg | "
            "Controller: KUKA Sunrise Cabinet Med | "
            "Operating system: KUKA Sunrise.OS Med "
            "(OEM LBR Med technical data table)"
        ),
        "uses": [21, 22],
        "year": 2018,
    },
    "KR 4 AGILUS": {
        "family": "kr-4-agilus",
        "match_as": "KR 4 R600",
    },
    "KMP 600P": {
        "family": "kmp",
        "payload_kg": 600.0,
        "features_line": "Total load: 600 kg (OEM KMP 600P product page title/payload)",
        "uses": [32, 46],
        "year": 2023,
        "movement_types": [11],  # wheeled/mobile if exists — patched carefully below
        "url": "https://www.kuka.com/en-us/products/amr-autonomous-mobile-robotics/mobile-platforms/kmp-600p-diffdrive",
    },
    "KMP 1500P": {
        "family": "kmp",
        "payload_kg": 1500.0,
        "features_line": (
            "Total load: 1500 kg | Stroke: 60 mm "
            "(KUKA press 17 Jul 2023 — KMP 1500P)"
        ),
        "uses": [32, 46],
        "year": 2023,
        "url": "https://www.kuka.com/en-us/products/amr-autonomous-mobile-robotics/topload-transport-robots",
    },
    "KMR iisy": {
        "family": "kmr-iisy",
        "features_line": (
            "Load capacity cobot: 11 kg or 15 kg; "
            "mobile platform supplementary load up to 200 kg "
            "(KUKA press 17 Jul 2023 — KMR iisy)"
        ),
        "uses": [21, 22, 32],
        "year": 2023,
        "url": "https://www.kuka.com/en-us/products/amr-autonomous-mobile-robotics/mobile-robot-systems/kmr-iisy-autonomous-mobile-cobot",
    },
    "KMP 600W": {
        "family": "kmp",
        "features_line": "KUKA KMP topload AMR family (OEM topload-transport-robots hub)",
        "uses": [32, 46],
        "year": 2023,
    },
    "KMP 250P": {
        "family": "kmp",
        "features_line": "KUKA KMP topload AMR family (OEM topload-transport-robots hub)",
        "uses": [32, 46],
        "year": 2023,
    },
    "KUKA omniMove E375 3000": {
        "family": "omnimove",
        "features_line": "KUKA omniMove heavy-load omnidirectional transport platform (OEM mobile-platforms family)",
        "uses": [32, 46],
        # year left blank — no per-model launch citation
    },
    "KUKA omniMove E575 7000": {
        "family": "omnimove",
        "features_line": "KUKA omniMove heavy-load omnidirectional transport platform (OEM mobile-platforms family)",
        "uses": [32, 46],
    },
    "KR SCARA": {
        "family": "kr-scara-robot",
        # family placeholder row — no single-variant specs
    },
}

# Legacy / discontinued names → family only (no invented specs).
NAME_FAMILY: dict[str, str] = {
    "KR 700 PA": "palletizing-robots",
    "KR 300-2 PA": "palletizing-robots",
    "KR 470-2 PA": "palletizing-robots",
    "KR 120 R3500-2 PA": "kr-quantec-pa",
    "KR 120 R2700-2 K": "kr-quantec",
    "KR 120 R2300": "kr-quantec",  # URL may say agilus wrongly — name is quantec-class
    "KR 120 R2700": "kr-quantec",
    "KR 90 R2300": "kr-cybertech",
    "KR 90 R2700": "kr-cybertech",
    "KR 6 R1440-2 nano": "kr-cybertech-nano",
}

# Fix wrong URL families when name clearly implies another series.
NAME_FAMILY_FORCE: dict[str, str] = {
    "KR 120 R2300": "kr-quantec",  # stored URL pointed at agilus; name is not AGILUS
    "KR 120 R2700-2 IONTEC": "kr-quantec",  # IONTEC suffix on a QUANTEC model
}


def _parse_kg_mm(text: str) -> tuple[float | None, float | None]:
    payload = reach = None
    m = re.search(r"(?:Total load|payload)[:\s]+([\d.]+)\s*kg", text or "", re.I)
    if m:
        payload = float(m.group(1))
    m = re.search(r"(?:Maximum reach|reach)[:\s]+([\d.]+)\s*mm", text or "", re.I)
    if m:
        reach = float(m.group(1))
    return payload, reach


def _family_from_url(url: str) -> str:
    path = (urlparse(url or "").path or "").lower().rstrip("/")
    slug = path.split("/")[-1] if path else ""
    aliases = {
        "kr-scara": "kr-scara-robot",
        "kr-fortec-ultra-heavy-duty-robot": "kr-fortec-ultra",
        "kr-delta-roboter": "kr-delta",
        "palletizing-robots": "palletizing-robots",
        "topload-transport-robots": "kmp",
        "mobile-platforms": "omnimove",
        "kmr-iisy-autonomous-mobile-cobot": "kmr-iisy",
        "lbr-med": "lbr-med",
        "kuka-medical-robotics": "lbr-med",
    }
    if slug in FAMILY_META:
        return slug
    return aliases.get(slug, slug if slug in FAMILY_META else "")


def _family_key(fam: str) -> str:
    if fam == "kr-scara-robot":
        return "kuka:kr-scara"
    return f"{COMPANY_SLUG}:{fam.replace('_', '-')}"


def _variant_label(name: str, payload: float | None, reach: float | None) -> str:
    bits: list[str] = []
    if payload is not None:
        bits.append(f"{payload:g} kg")
    if reach is not None:
        bits.append(f"{reach:g} mm")
    return " / ".join(bits) if bits else name


def _append_features(cur: str, line: str) -> str:
    cur = (cur or "").strip()
    line = (line or "").strip()
    if not line:
        return cur
    if MARKER in cur and "Total load:" in line:
        # already has OEM table line — keep unless shorter than 40 and line richer
        if len(cur) >= 40:
            return cur
    if line in cur:
        return cur
    return f"{cur} | {line}" if cur else line


def build_plan(robot: dict[str, Any], catalog: dict[str, Any]) -> dict[str, Any] | None:
    rid = int(robot["id"])
    name = (robot.get("name") or "").strip()
    url = (robot.get("url") or "").strip()
    manual = MANUAL.get(name) or {}
    fam = (
        NAME_FAMILY_FORCE.get(name)
        or manual.get("family")
        or NAME_FAMILY.get(name)
        or ""
    )

    match_name = manual.get("match_as") or name
    cat_key = match(match_name, catalog) if match_name else None
    rec = catalog.get(cat_key) if cat_key else None
    if rec and not fam:
        fam = rec.get("family") or ""
    if not fam:
        fam = _family_from_url(url)

    # Normalize ultra/pa family slugs from recon
    if fam == "kr-fortec-ultra-heavy-duty-robot":
        fam = "kr-fortec-ultra"
    if fam == "kr-delta-roboter":
        fam = "kr-delta"

    meta = FAMILY_META.get(fam)
    if not meta and not manual:
        return None

    if not meta:
        meta = {
            "family_name": fam.replace("-", " ").upper(),
            "family_url": url or "",
        }

    payload = reach = None
    features_line = ""
    if rec:
        features_line = spec_line(rec)
        payload, reach = _parse_kg_mm(
            f"Total load: {rec.get('total_load') or ''} Maximum reach: {rec.get('max_reach') or ''}"
        )
        # Reject 0 mm junk rows
        if reach == 0:
            reach = None
        if payload == 0:
            payload = None

    if manual.get("payload_kg") is not None:
        payload = float(manual["payload_kg"])
    if manual.get("reach_mm") is not None:
        reach = float(manual["reach_mm"])
    if manual.get("features_line"):
        features_line = manual["features_line"]

    year = robot.get("release_year")
    if not year:
        if manual.get("year"):
            year = int(manual["year"])
        elif fam in YEARS and fam not in YEARS_OPTIONAL_BLANK:
            year = YEARS[fam]

    uses = manual.get("uses")
    # LBR Med has empty uses
    cur_uses = robot.get("uses") or robot.get("use_keys") or []
    if not cur_uses and not uses and ("lbr" in name.lower()):
        uses = [21, 22]

    avail = robot.get("availability_status") or robot.get("availability_status_id")
    need_avail = not avail

    body: dict[str, Any] = {
        "source_locale": "en",
        "model_name": name,
        "family_name": meta["family_name"],
        "family_key": _family_key(fam) if fam else "",
        "family_url": meta.get("family_url") or url,
        "variant_code": name if name != "KR SCARA" else "",
        "variant_label": _variant_label(name, payload, reach),
        "product_url_scope": "family",
    }
    if manual.get("url"):
        body["url"] = manual["url"]
        body["website_url"] = manual["url"]
    elif meta.get("family_url") and (
        not url
        or "palletizing-robots" in url
        or url.rstrip("/").endswith("/kr-scara")
        or url.rstrip("/").endswith("/lbr-med")
    ):
        # repair known-dead / generic URLs
        body["url"] = meta["family_url"]
        body["website_url"] = meta["family_url"]

    if payload is not None:
        body["payload_kg"] = payload
    if reach is not None:
        body["reach_mm"] = reach
    if year:
        body["release_year"] = int(year)
    if need_avail:
        body["availability_status"] = AVAILABILITY_RELEASED
    if uses:
        body["uses"] = uses

    cur_feat = (robot.get("features") or "").strip()
    if features_line and (len(cur_feat) < 40 or MARKER not in cur_feat):
        body["features"] = _append_features(cur_feat, features_line)[:1900]

    return {
        "id": rid,
        "name": name,
        "family": fam,
        "matched": cat_key,
        "body": body,
        "need_video": not (robot.get("videos") or robot.get("video_urls")),
        "payload": payload,
        "reach": reach,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--ids", type=int, nargs="*")
    args = ap.parse_args()

    if not CATALOG.is_file():
        print(f"ERROR: {CATALOG} missing — run kuka_recon.py first", file=sys.stderr)
        return 1
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))

    videos_by_fam: dict[str, list[dict[str, str]]] = {}
    for fam, urls in VIDEO_URLS.items():
        if urls:
            videos_by_fam[fam] = enrich_video_list(urls)

    client = ResearchApiClient()
    robots = None
    for a in range(12):
        try:
            robots = client.list_robots_for_company(COMPANY_ID)
            break
        except Exception as e:  # noqa: BLE001
            print(f"list retry {a}: {e}", file=sys.stderr)
            time.sleep(5)
    if robots is None:
        return 1

    targets = [
        r
        for r in robots
        if int(r.get("id") or 0) <= MAX_ID
        and (not args.ids or int(r["id"]) in set(args.ids))
    ]
    targets.sort(key=lambda r: int(r["id"]))

    plans: list[dict[str, Any]] = []
    skipped: list[str] = []
    for r in targets:
        p = build_plan(r, catalog)
        if not p:
            skipped.append(f"{r.get('id')} {r.get('name')}")
            continue
        plans.append(p)

    preview = _RESEARCH_DIR / "staging/reports/kuka-old-fleet-preview.json"
    preview.write_text(
        json.dumps(
            [
                {
                    "id": p["id"],
                    "name": p["name"],
                    "family": p["family"],
                    "matched": p["matched"],
                    "payload": p["payload"],
                    "reach": p["reach"],
                    "need_video": p["need_video"],
                    "keys": sorted(p["body"].keys()),
                    "features_preview": (p["body"].get("features") or "")[:160],
                }
                for p in plans
            ],
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    with_specs = sum(1 for p in plans if p["payload"] is not None)
    with_year = sum(1 for p in plans if p["body"].get("release_year"))
    with_feat = sum(1 for p in plans if "features" in p["body"])
    need_vid = sum(1 for p in plans if p["need_video"] and videos_by_fam.get(p["family"]))
    print(
        f"targets={len(targets)} planned={len(plans)} skipped={len(skipped)} "
        f"specs={with_specs} year_set={with_year} features_upd={with_feat} "
        f"videos_fillable={need_vid}"
    )
    if skipped:
        print("skipped:", "; ".join(skipped[:12]))
    for p in plans[:8]:
        print(
            f"  {p['id']} {p['name']} fam={p['family']} match={p['matched']} "
            f"p={p['payload']} r={p['reach']} vid={p['need_video']}"
        )
    print(f"Preview: {preview}")
    print("NOTE: price left blank — KUKA publishes no public MSRP (quote-only).")

    if not args.apply:
        print("DRY-RUN — pass --apply to write")
        return 0

    ok = fail = 0
    for p in plans:
        body = dict(p["body"])
        fam = p["family"]
        if p["need_video"] and videos_by_fam.get(fam):
            body["video_urls"] = videos_by_fam[fam][:2]
        note = (
            f"[OLD-FLEET 2026-07-18] family={body.get('family_name')} "
            f"key={body.get('family_key')}; matched={p['matched'] or 'manual/url'}; "
            f"payload={p['payload']}; reach={p['reach']}"
        )
        # notes not always on list payload — fetch skip; append if we have notes later
        try:
            patched = client._patch(f"robots/robots/{p['id']}/", body)
            print(
                f"ok {p['id']} fam={patched.get('family_key')} "
                f"p={patched.get('payload_kg')} r={patched.get('reach_mm')} "
                f"y={patched.get('release_year')} "
                f"vids={len(patched.get('videos') or [])}"
            )
            ok += 1
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL {p['id']}: {exc}")
            fail += 1
        time.sleep(0.08)

    print(f"\nDONE ok={ok} fail={fail} note_unused={note[:40]}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
