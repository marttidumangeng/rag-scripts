"""Fix KUKA depth imports: availability, release_year, videos — then ready for AI verify.

Targets ids >= 5374 (company 1396). Uses family-level years/videos (KUKA publishes
per family). Availability matches existing fleet: released.

Usage:
  python fix_kuka_availability_year_video.py            # dry-run
  python fix_kuka_availability_year_video.py --apply
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

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient
from release_year_lookup import citation_line
from youtube_metadata import enrich_video_list

COMPANY_ID = 1396
MIN_ID = 5374
AVAILABILITY_RELEASED = 3  # matches existing KUKA fleet key=released

# Vetted family years (lookup + sibling inheritance + corrections).
# Corrections: cybertech-arc must not inherit nano-ARC press; ultra-PA uses the
# 2025 PA announcement that names both PA and ultra PA.
YEARS: dict[str, dict[str, Any]] = {
    "kr-1000-titan": {
        "year": 2007,
        "evidence": "Inherited from existing KUKA titan fleet year (majority)",
        "source_url": "",
        "confidence": "medium",
    },
    "kr-agilus": {
        "year": 2014,
        "evidence": "Inherited from existing KR AGILUS fleet year",
        "source_url": "",
        "confidence": "medium",
    },
    "kr-iontec": {
        "year": 2020,
        "evidence": "Inherited from existing KR IONTEC fleet year (majority 2020)",
        "source_url": "",
        "confidence": "medium",
    },
    "kr-scara-robot": {
        "year": 2019,
        "evidence": "Inherited from existing KR SCARA fleet year (majority 2019)",
        "source_url": "",
        "confidence": "medium",
    },
    "lbr-iisy": {
        "year": 2021,
        "evidence": "Inherited from existing LBR iisy fleet year (majority 2021)",
        "source_url": "",
        "confidence": "medium",
    },
    "lbr-iiwa": {
        "year": 2013,
        "evidence": "Inherited from existing LBR iiwa fleet year",
        "source_url": "",
        "confidence": "medium",
    },
    "kr-cybertech": {
        "year": 2017,
        "evidence": "KUKA launched the KR CYBERTECH series at China International Industry Fair",
        "source_url": "",
        "confidence": "medium",
    },
    "kr-cybertech-nano": {
        "year": 2020,
        "evidence": "KUKA presents KR CYBERTECH nano (14 Sep 2020 press)",
        "source_url": "",
        "confidence": "high",
    },
    "kr-cybertech-nano-arc": {
        "year": 2021,
        "evidence": "KUKA presents KR CYBERTECH nano ARC family (23 Apr 2021)",
        "source_url": "https://www.kuka.com/de-de/company/press/news/2021/04/kr-cybertech-nano-arc-hollow-wrist-robot",
        "confidence": "high",
    },
    # Parent CYBERTECH launch — not the nano ARC press (wrong subfamily).
    "kr-cybertech-arc": {
        "year": 2017,
        "evidence": "KR CYBERTECH ARC treated as CYBERTECH series launch year (2017)",
        "source_url": "",
        "confidence": "medium",
    },
    "kr-fortec": {
        "year": 2024,
        "evidence": "KUKA revealed KR FORTEC industrial robot (between QUANTEC and FORTEC ultra)",
        "source_url": "",
        "confidence": "high",
    },
    "kr-fortec-pa": {
        "year": 2025,
        "evidence": "New KR FORTEC PA and KR FORTEC ultra PA palletizing announcement",
        "source_url": "",
        "confidence": "high",
    },
    "kr-fortec-ultra": {
        "year": 2023,
        "evidence": "KUKA announced KR FORTEC ultra double-link arm family (Jan 2023)",
        "source_url": "https://www.control.com/news/robotics/23/01/kuka-introduces-double-link-arm-robots/",
        "confidence": "high",
    },
    "kr-fortec-ultra-pa": {
        "year": 2025,
        "evidence": "New KR FORTEC PA and KR FORTEC ultra PA palletizing announcement",
        "source_url": "",
        "confidence": "high",
    },
    "kr-quantec": {
        "year": 2010,
        "evidence": "In 2010 KUKA released the KR QUANTEC line",
        "source_url": "",
        "confidence": "high",
    },
    "kr-quantec-pa": {
        "year": 2016,
        "evidence": "Aligned with existing KUKA PA fleet years (KR 300-2 PA=2016)",
        "source_url": "",
        "confidence": "medium",
    },
}


def _load_videos() -> dict[str, list[dict[str, str]]]:
    clean_path = _RESEARCH_DIR / "staging/reports/kuka_family_videos_clean.json"
    extra_path = _RESEARCH_DIR / "staging/reports/kuka_family_videos_extra.json"
    merged: dict[str, list[dict[str, str]]] = {}
    if clean_path.is_file():
        for fam, vids in json.loads(clean_path.read_text(encoding="utf-8")).items():
            merged[fam] = list(vids or [])
    if extra_path.is_file():
        for fam, vids in json.loads(extra_path.read_text(encoding="utf-8")).items():
            # Prefer OEM-page cleans; only fill gaps from YouTube search.
            if not merged.get(fam):
                merged[fam] = list(vids or [])
    # PA ultra: reject non-PA clips from search; reuse PA palletizing clip.
    pa = merged.get("kr-fortec-pa") or []
    if pa:
        merged["kr-fortec-ultra-pa"] = pa[:1]
    # Prefer official FORTEC ultra intro over junk for ultra (already in clean).
    # Prefer old-fleet style PA video for quantec-pa if search was weak.
    if merged.get("kr-quantec-pa"):
        title = (merged["kr-quantec-pa"][0].get("title") or "").lower()
        if "linear unit" in title and "pallet" not in title:
            # Keep but also allow fortec-pa style — better: use known PA demos from old fleet.
            merged["kr-quantec-pa"] = enrich_video_list(
                [
                    "https://www.youtube.com/watch?v=6iDjmCDX0u4",  # used on KR 700 PA
                    "https://www.youtube.com/watch?v=zB56iy3cEkg",  # KR 300-2 PA
                ]
            )[:1]
    return merged


def _year_note(hit: dict[str, Any]) -> str:
    return (
        f"[YEAR 2026-07-18] {citation_line(hit)} "
        f"(family-level; KUKA publishes launches per family not per variant)"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--ids", type=int, nargs="*")
    args = ap.parse_args()

    plan_path = _RESEARCH_DIR / "staging/reports/kuka_enrich_plan.json"
    family_by_id = {
        int(p["id"]): p.get("family") or ""
        for p in json.loads(plan_path.read_text(encoding="utf-8"))
    }
    videos_by_fam = _load_videos()

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
        if int(r.get("id") or 0) >= MIN_ID
        and (not args.ids or int(r["id"]) in set(args.ids))
    ]
    targets.sort(key=lambda r: int(r["id"]))

    missing_year = missing_vid = 0
    for r in targets:
        fam = family_by_id.get(int(r["id"]), "")
        if fam not in YEARS:
            missing_year += 1
            print(f"NO YEAR MAP {r['id']} {r.get('name')} fam={fam}")
        if not videos_by_fam.get(fam):
            missing_vid += 1
            print(f"NO VIDEO MAP {r['id']} {r.get('name')} fam={fam}")

    print(
        f"targets={len(targets)} families_with_year={len(YEARS)} "
        f"families_with_video={sum(1 for v in videos_by_fam.values() if v)} "
        f"unmapped_year={missing_year} unmapped_video={missing_vid}"
    )
    if not args.apply:
        print("DRY-RUN — pass --apply to write")
        return 0 if missing_year == 0 and missing_vid == 0 else 1

    ok = fail = 0
    for r in targets:
        rid = int(r["id"])
        fam = family_by_id.get(rid, "")
        hit = YEARS.get(fam)
        vids = videos_by_fam.get(fam) or []
        if not hit or not vids:
            print(f"SKIP {rid}: fam={fam} year={bool(hit)} vids={len(vids)}")
            fail += 1
            continue

        notes = (r.get("notes") or "").strip()
        ynote = _year_note(hit)
        if ynote not in notes:
            notes = (ynote + "\n---\n" + notes).strip() if notes else ynote

        body: dict[str, Any] = {
            "availability_status": AVAILABILITY_RELEASED,
            "release_year": hit["year"],
            "video_urls": vids[:2],
            "notes": notes,
            "source_locale": "en",
        }
        try:
            patched = client._patch(f"robots/robots/{rid}/", body)
            n_vids = len(patched.get("videos") or patched.get("video_urls") or [])
            print(
                f"ok {rid} fam={fam} year={patched.get('release_year')} "
                f"av={(patched.get('availability_status') or {}).get('key')} "
                f"vids={n_vids}"
            )
            ok += 1
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL {rid}: {exc}")
            fail += 1
        time.sleep(0.08)

    print(f"\nDONE ok={ok} fail={fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
