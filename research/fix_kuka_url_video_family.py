"""Fix KUKA depth imports: URL/video mismatches + family series metadata.

- Promote exact-model third-party pages (RoboDK/robots.com) when available
- Keep OEM family page as family_url; never use login-walled my.KUKA as primary URL
- Replace videos with series-named clips (oEmbed-validated)
- Fill family_name / family_key / family_url / variant_* / model_name / product_url_scope

Usage:
  python fix_kuka_url_video_family.py            # dry-run
  python fix_kuka_url_video_family.py --apply
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
from youtube_metadata import enrich_video_list

COMPANY_ID = 1396
MIN_ID = 5374
COMPANY_SLUG = "kuka"

FAMILY_META: dict[str, dict[str, str]] = {
    "kr-agilus": {
        "family_name": "KR AGILUS",
        "family_url": "https://www.kuka.com/en-us/products/robotics-systems/industrial-robots/kr-agilus",
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
    "lbr-iisy": {
        "family_name": "LBR iisy",
        "family_url": "https://www.kuka.com/en-us/products/robotics-systems/industrial-robots/lbr-iisy",
    },
    "lbr-iiwa": {
        "family_name": "LBR iiwa",
        "family_url": "https://www.kuka.com/en-us/products/robotics-systems/industrial-robots/lbr-iiwa",
    },
}

# Series-named clips only (oEmbed titles checked offline). Prefer official KUKA intros.
VIDEO_URLS: dict[str, list[str]] = {
    "kr-agilus": ["https://www.youtube.com/watch?v=bod5_R58V6A"],
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
    # Generic KUKA palletizer demo — better than wrong KR 700 PA title; family still in notes
    "kr-quantec-pa": ["https://www.youtube.com/watch?v=Sc-6A97GETY"],
    "kr-scara-robot": ["https://www.youtube.com/watch?v=Te5AfPQFz8U"],
    "kr-1000-titan": ["https://www.youtube.com/watch?v=uuIiBUvrCB4"],
    "lbr-iisy": ["https://www.youtube.com/watch?v=Bq8tTBW3R9g"],
    "lbr-iiwa": ["https://www.youtube.com/watch?v=_XU10uZbCy8"],
}

EXACT_HOSTS = ("robodk.com", "robots.com", "directindustry.com", "pdf.directindustry.com")


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def _is_exact_candidate(url: str) -> bool:
    h = _host(url)
    if not h or "my.kuka.com" in h:
        return False
    return any(h == d or h.endswith("." + d) for d in EXACT_HOSTS)


def _variant_label(name: str, payload: float | None, reach: float | None) -> str:
    bits: list[str] = []
    if payload is not None:
        bits.append(f"{payload:g} kg")
    if reach is not None:
        bits.append(f"{reach:g} mm")
    # retain distinguishing suffixes from the name
    suffixes = []
    for tok in re.findall(
        r"\b(CR|EX|WP|HO|HI|F|PA|MT|MT-F|C01|C-F|K|K-F|P|P-C|E|E D01|arctic|lite|ultra)\b",
        name,
        flags=re.I,
    ):
        t = tok.strip()
        if t and t.lower() not in {s.lower() for s in suffixes}:
            suffixes.append(t)
    if suffixes:
        bits.append(" ".join(suffixes))
    return " / ".join(bits) if bits else name


def _pick_url(plan_row: dict[str, Any], robodk_ok: dict[str, str]) -> tuple[str, str]:
    """Return (url, product_url_scope)."""
    name = plan_row["name"]
    fam = plan_row.get("family") or ""
    family_url = FAMILY_META.get(fam, {}).get("family_url") or plan_row.get("oem_url") or ""

    # 1) exact third-party already cited
    for ext in plan_row.get("external") or []:
        u = (ext.get("url") or "").strip()
        if _is_exact_candidate(u):
            return u, "exact_variant"

    for u in plan_row.get("information_source_urls") or []:
        if _is_exact_candidate(u):
            return u, "exact_variant"

    # 2) RoboDK HEAD-verified map
    if name in robodk_ok:
        return robodk_ok[name], "exact_variant"

    # 3) OEM family page
    return family_url, "family"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--ids", type=int, nargs="*")
    args = ap.parse_args()

    plan = json.loads(
        (_RESEARCH_DIR / "staging/reports/kuka_enrich_plan.json").read_text(encoding="utf-8")
    )
    plan_by_id = {int(p["id"]): p for p in plan}
    robodk_path = _RESEARCH_DIR / "staging/reports/kuka_robodk_urls.json"
    robodk_ok = {}
    if robodk_path.is_file():
        robodk_ok = json.loads(robodk_path.read_text(encoding="utf-8")).get("ok") or {}

    # Pre-enrich videos once
    videos_by_fam: dict[str, list[dict[str, str]]] = {}
    for fam, urls in VIDEO_URLS.items():
        videos_by_fam[fam] = enrich_video_list(urls)
        if not videos_by_fam[fam]:
            print(f"WARN no usable video for {fam}", file=sys.stderr)

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

    exact = family_scope = 0
    for r in targets:
        rid = int(r["id"])
        p = plan_by_id.get(rid) or {"name": r.get("name"), "family": "", "external": []}
        fam = p.get("family") or ""
        url, scope = _pick_url(p, robodk_ok)
        if scope == "exact_variant":
            exact += 1
        else:
            family_scope += 1
        meta = FAMILY_META.get(fam, {})
        print(
            f"{rid} fam={fam} scope={scope} "
            f"url={url[:70]} vids={len(videos_by_fam.get(fam) or [])} "
            f"family_name={meta.get('family_name')}"
        )

    print(f"targets={len(targets)} exact_url={exact} family_url={family_scope}")
    if not args.apply:
        print("DRY-RUN — pass --apply to write")
        return 0

    ok = fail = 0
    for r in targets:
        rid = int(r["id"])
        p = plan_by_id.get(rid)
        if not p:
            print(f"SKIP {rid}: not in enrich plan")
            fail += 1
            continue
        fam = p.get("family") or ""
        meta = FAMILY_META.get(fam)
        vids = videos_by_fam.get(fam) or []
        if not meta or not vids:
            print(f"SKIP {rid}: missing meta/video fam={fam}")
            fail += 1
            continue

        url, scope = _pick_url(p, robodk_ok)
        family_url = meta["family_url"]
        family_name = meta["family_name"]
        family_key = f"{COMPANY_SLUG}:{fam.replace('_', '-')}"
        # normalize scara key
        if fam == "kr-scara-robot":
            family_key = "kuka:kr-scara"

        label = _variant_label(p["name"], p.get("payload_kg"), p.get("reach_mm"))
        note = (
            f"[FAMILY/URL/VIDEO 2026-07-18] family={family_name} key={family_key}; "
            f"product_url_scope={scope}; primary={url}; family_page={family_url}; "
            f"video={vids[0].get('title', '')[:80]}"
        )
        notes = (r.get("notes") or "").strip()
        if note not in notes:
            notes = (note + "\n---\n" + notes).strip() if notes else note

        body: dict[str, Any] = {
            "source_locale": "en",
            "name": p["name"],
            "model_name": p["name"],
            "family_name": family_name,
            "family_key": family_key,
            "family_url": family_url,
            "variant_code": p["name"],
            "variant_label": label,
            "product_url_scope": scope,
            "url": url,
            "website_url": url,
            "video_urls": vids[:2],
            "notes": notes,
        }
        try:
            patched = client._patch(f"robots/robots/{rid}/", body)
            print(
                f"ok {rid} key={patched.get('family_key')} scope={patched.get('product_url_scope')} "
                f"url={(patched.get('url') or '')[:60]} "
                f"vids={len(patched.get('videos') or [])}"
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
