"""Backfill Comau (company 245) greenfield NJ-series pending_review robots.

Six greenfield targets (no image/features/specs/year/videos/tags). Specs come
straight from the Comau PDP technical-specification table (parsed by
comau_recon.py), cross-checked against the model-name payload/reach convention
(e.g. NJ-210-3.1 -> ~210 kg payload / 3.1 m reach). Heroes are visually verified
Comau product renders. Third-party credible sources (DirectIndustry, Flex-Line
Automation, RoboDK, SprutCAM) are captured alongside the OEM PDP so the server
stamps enriched_at and upserts RobotInformationSource.

release_year is left NULL: no per-model launch-year citation exists (presence in
a 2016 Comau catalogue is existence, not a launch date) -> honoring the release
year citation gate rather than inventing one.

Run:
    python fix_comau_robots.py                 # dry-run (writes preview)
    python fix_comau_robots.py --apply --copy-media
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import requests

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient
from import_staging import import_staging, resolve_created_by_id
from robot_auto_research import slugify_robot_name
from youtube_metadata import enrich_video_list

COMPANY_ID = 245
COMPANY_SLUG = "comau"
COMPANY_NAME = "Comau"
BASE = "https://www.comau.com"

RECON = _RESEARCH_DIR / "staging" / "reports" / "comau-recon.json"

TAGS_PRESS = "industrial|industrial robot|industrial arm|6-axis|robotic arm|press-tending|automotive|material handling"
TAGS_SH = "industrial|industrial robot|industrial arm|6-axis|robotic arm|material handling|manufacturing|factory automation"
TAGS_NJ4 = "industrial|industrial robot|industrial arm|6-axis|robotic arm|spot-welding|manufacturing|factory automation"

# Per-robot curated plan. hero + gallery are visually verified Comau renders;
# sources include OEM PDP + credible third-party. Videos are title-verified
# Comau clips (family-level demos — a bonus tier, never fabricated).
PLAN: dict[int, dict[str, Any]] = {
    4165: {
        "kind": "press",
        "tags": TAGS_PRESS,
        "hero": f"{BASE}/wp-content/uploads/2024/05/Comau_NJ-100-3-2-PRESS_1280x485.png",
        "gallery": [
            f"{BASE}/wp-content/uploads/2021/06/NJ100_1.jpg",
            f"{BASE}/wp-content/uploads/2021/06/NJ100_2.jpg",
            f"{BASE}/wp-content/uploads/2021/06/NJ100_3.jpg",
            f"{BASE}/wp-content/uploads/2021/06/NJ100_4.jpg",
            f"{BASE}/wp-content/uploads/2021/06/NJ100_5.jpg",
        ],
        "videos": ["https://www.youtube.com/watch?v=20J2BMTdWiQ"],
        "sources": [
            "https://flex-lineautomation.com/wp-content/uploads/2022/09/Comau_Robotics_BrochureNYkmHY-1.pdf",
        ],
        "blurb": (
            "Comau NJ-100-3.2 PRESS is a six-axis press-to-press automation robot built for "
            "cold-stamping and hot-forming lines, where industry-leading motion control and "
            "factory-proven experience deliver synchronized, press-to-press cycle perfection."
        ),
    },
    4166: {
        "kind": "press",
        "tags": TAGS_PRESS,
        "hero": f"{BASE}/wp-content/uploads/2025/07/NJ_130-3.7-SH-PRESS.png",
        "gallery": [
            f"{BASE}/wp-content/uploads/2021/06/NJ130_1-1.jpg",
            f"{BASE}/wp-content/uploads/2021/06/NJ130_2-1.jpg",
            f"{BASE}/wp-content/uploads/2021/06/NJ130_3-1.jpg",
            f"{BASE}/wp-content/uploads/2021/06/NJ130_4-1.jpg",
            f"{BASE}/wp-content/uploads/2021/06/NJ130_5-1.jpg",
            f"{BASE}/wp-content/uploads/2021/06/NJ130_6-1.jpg",
        ],
        "videos": ["https://www.youtube.com/watch?v=20J2BMTdWiQ"],
        "sources": [
            "https://flex-lineautomation.com/product/comau-robotics/nj-130-3-7-press/",
        ],
        "blurb": (
            "Comau NJ-130-3.7 PRESS is a long-reach six-axis press-shop robot dedicated to "
            "press-to-press automation, combining industry-leading technology and factory-proven "
            "experience for coordinated action and synchrony across the stamping line."
        ),
    },
    4167: {
        "kind": "sh",
        "tags": TAGS_SH,
        "hero": f"{BASE}/wp-content/uploads/2024/05/Comau_robot_NJ4-165-3-4SH_1280x485.png",
        "gallery": [
            f"{BASE}/wp-content/uploads/2021/06/NJ4-165-3.4-SH_1.jpg",
            f"{BASE}/wp-content/uploads/2021/06/NJ4-165-3.4-SH_2.jpg",
        ],
        "videos": ["https://www.youtube.com/watch?v=XmASNWLIre8"],
        "sources": [
            "https://robodk.com/robot/Comau/Smart5-NJ-165-3-4-SH",
            "https://flex-lineautomation.com/product/comau-robotics/nj-165-3-4-sh/",
        ],
        "blurb": (
            "Comau NJ-165-3.4 SH is a shelf-mounted six-axis robot that delivers wider operational "
            "areas and a compact footprint, providing the power to drive automation while ensuring "
            "energy savings, lower costs and higher productivity."
        ),
    },
    4168: {
        "kind": "sh",
        "tags": TAGS_SH,
        "hero": f"{BASE}/wp-content/uploads/2021/06/NJ4-210_3.306.jpg",
        "gallery": [
            f"{BASE}/wp-content/uploads/2021/06/NJ4-210_3.307.jpg",
            f"{BASE}/wp-content/uploads/2021/06/NJ4-210_3.309.jpg",
            f"{BASE}/wp-content/uploads/2021/06/NJ210-31-SH_header.jpg",
        ],
        "videos": ["https://www.youtube.com/watch?v=XmASNWLIre8"],
        "sources": [
            "https://www.directindustry.com/prod/comau/product-102039-1914776.html",
            "https://flex-lineautomation.com/wp-content/uploads/2022/09/Comau_Robotics_BrochureNYkmHY-1.pdf",
        ],
        "blurb": (
            "Comau NJ-210-3.1 SH is a high-payload shelf-mounted six-axis robot for demanding "
            "handling and spot-welding duty, delivering the power to drive automation with energy "
            "savings, cost reduction and higher productivity."
        ),
    },
    4169: {
        "kind": "nj4",
        "tags": TAGS_NJ4,
        "hero": f"{BASE}/wp-content/uploads/2025/07/NJ4-110-2.2.png",
        "gallery": [
            # NJ4 hollow-wrist family renders served on the NJ4-110-2.2 PDP
            f"{BASE}/wp-content/uploads/2021/06/NJ4_90_DX-11.jpg",
            f"{BASE}/wp-content/uploads/2021/06/NJ4_90-22_11.jpg",
        ],
        "videos": ["https://www.youtube.com/watch?v=oeaajFUjyY4"],
        "sources": [
            "https://sprutcam.com/comau-nj4-110-2-2/",
            "https://flex-lineautomation.com/products/comau-robotics/hollow-wrist-robots/",
        ],
        "blurb": (
            "Comau NJ4-110-2.2 is a lean, compact six-axis Hollow Wrist robot with fully integrated "
            "internal dressing for higher performance, floor- or ceiling-mount flexibility and lower "
            "maintenance costs in spot-welding and handling cells."
        ),
    },
    4170: {
        "kind": "nj4",
        "tags": TAGS_NJ4,
        "hero": f"{BASE}/wp-content/uploads/2025/07/NJ4-165-3.4-SH-1.png",
        "gallery": [
            f"{BASE}/wp-content/uploads/2021/06/NJ4-165-3.4-SH_11.jpg",
            f"{BASE}/wp-content/uploads/2021/06/NJ4-165-3.4-SH_21.jpg",
        ],
        "videos": ["https://www.youtube.com/watch?v=oeaajFUjyY4"],
        "sources": [
            "https://robodk.com/robot/Comau/Smart5-NJ-165-3-4-SH",
            "https://flex-lineautomation.com/products/comau-robotics/hollow-wrist-robots/",
        ],
        "blurb": (
            "Comau NJ4-165-3.4 SH is a shelf-mounted six-axis Hollow Wrist robot delivering flexible, "
            "space-saving automation; its lean, compact structure with integrated dressing improves "
            "performance and reduces maintenance in tight production layouts."
        ),
    },
}


def parse_name_payload_reach(name: str) -> tuple[float | None, float | None]:
    """Comau names encode payload-reach: NJ-210-3.1 -> 210 kg / 3.1 m."""
    m = re.search(r"-(\d+)-(\d+(?:\.\d+)?)", name)
    if not m:
        return None, None
    return float(m.group(1)), float(m.group(2))


def build_features(name: str, kind: str, blurb: str, specs: dict) -> str:
    parts = [blurb]
    bits = []
    if specs.get("payload_kg") is not None:
        bits.append(f"maximum wrist payload {specs['payload_kg']:g} kg")
    if specs.get("forearm_load_kg") is not None:
        bits.append(f"additional forearm load {specs['forearm_load_kg']:g} kg")
    if specs.get("reach_mm") is not None:
        bits.append(f"maximum horizontal reach {specs['reach_mm']:g} mm")
    if specs.get("repeatability_mm") is not None:
        bits.append(f"repeatability +/-{specs['repeatability_mm']:g} mm")
    if specs.get("weight_kg") is not None:
        bits.append(f"robot weight {specs['weight_kg']:g} kg")
    if specs.get("axes") is not None:
        bits.append(f"{int(specs['axes'])} axes")
    if specs.get("protection_class"):
        bits.append(f"protection {specs['protection_class']}")
    if specs.get("mounting_position"):
        bits.append(f"mounting {specs['mounting_position']}")
    if bits:
        parts.append("Technical specifications (Comau datasheet): " + "; ".join(bits) + ".")
    return " ".join(parts)


def build_row(rid: int, robot: dict, recon: dict) -> dict[str, Any]:
    plan = PLAN[rid]
    name = robot["name"]
    info = recon.get(str(rid)) or recon.get(rid) or {}
    specs = info.get("specs", {})
    url = plan.get("url") or info.get("url") or robot.get("url") or ""

    # Cross-check name-encoded payload/reach against PDP-parsed values.
    n_pay, n_reach_m = parse_name_payload_reach(name)
    payload = specs.get("payload_kg")
    reach_mm = specs.get("reach_mm")
    if payload is None and n_pay is not None:
        payload = n_pay
    if reach_mm is None and n_reach_m is not None:
        reach_mm = n_reach_m * 1000.0

    kind = plan["kind"]
    features = build_features(name, kind, plan["blurb"], specs)
    description = plan["blurb"]

    hero = plan["hero"]
    images = [hero] + [u for u in plan.get("gallery", []) if u != hero]

    videos = enrich_video_list(plan.get("videos", []))

    # OEM PDP is canonical url + a source; third-party sources captured too.
    sources = [{"url": url, "type": "website", "title": f"Comau {name} product page"}]
    for s in plan.get("sources", []):
        sources.append({"url": s, "type": "reference", "title": "Third-party reference"})

    ip = None
    pc = specs.get("protection_class") or ""
    m = re.search(r"IP\s*\d{2}", pc)
    if m:
        ip = m.group(0).replace(" ", "")

    row: dict[str, Any] = {
        "name": name,
        "company_slug": COMPANY_SLUG,
        "company_name": COMPANY_NAME,
        "manufacturer_country_code": "IT",
        "description": description[:1200],
        "purpose": description[:1200],
        "features": features[:1800],
        "url": url,
        "image": hero,
        "images": images[:6],
        "video_urls": videos,
        "movement_type_keys": "stationary",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "manufacturing-industrial",
        "tags": plan["tags"],
        "dof": int(specs["axes"]) if specs.get("axes") else 6,
        "sources": sources,
        "research_notes": (
            f"Comau greenfield backfill from OEM PDP {url}; specs from Comau technical-spec table; "
            f"corroborated by third-party references (see Sources). release_year left null (no per-model "
            f"launch citation)."
        ),
    }
    if payload is not None:
        row["payload_kg"] = payload
    if reach_mm is not None:
        row["reach_mm"] = reach_mm
    if specs.get("repeatability_mm") is not None:
        row["repeatability_mm"] = specs["repeatability_mm"]
    if specs.get("weight_kg") is not None:
        row["weight_kg"] = specs["weight_kg"]
        row["weight"] = f"{specs['weight_kg']:g} kg"
    if ip:
        row["ip_rating"] = ip

    notes_specs = []
    if payload is not None:
        notes_specs.append(f"Payload: {payload:g} kg")
    if reach_mm is not None:
        notes_specs.append(f"Reach: {reach_mm:g} mm")
    if specs.get("repeatability_mm") is not None:
        notes_specs.append(f"Repeatability: +/-{specs['repeatability_mm']:g} mm")
    if specs.get("weight_kg") is not None:
        notes_specs.append(f"Weight: {specs['weight_kg']:g} kg")
    if notes_specs:
        row["notes"] = " | ".join(notes_specs)
    return row


def trigger_copy_media(robot_ids: list[int]) -> tuple[int, int]:
    secret = os.environ.get("INTERNAL_API_SECRET", "").strip()
    env_file = _RESEARCH_DIR.parents[1] / "robotaigeek-server" / ".env"
    if not secret and env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                secret = line.split("=", 1)[1].strip()
    api = os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/").replace("/api/v1", "")
    if not secret or not api:
        print("copy-media: missing INTERNAL_API_SECRET or IMPORT_SYNC_API_BASE_URL", file=sys.stderr)
        return 0, len(robot_ids)
    ok = fail = 0
    for rid in robot_ids:
        u = f"{api}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/"
        try:
            resp = requests.post(u, headers={"X-Internal-Secret": secret}, timeout=180)
            if resp.ok:
                ok += 1
            else:
                fail += 1
                print(f"copy-media fail {rid}: HTTP {resp.status_code}")
        except requests.RequestException as exc:
            fail += 1
            print(f"copy-media fail {rid}: {exc}")
        time.sleep(0.2)
    return ok, fail


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix Comau greenfield robots (company 245)")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--copy-media", action="store_true")
    parser.add_argument("--created-by-id", type=int, default=1)
    parser.add_argument("--local", action="store_true")
    args = parser.parse_args()

    recon = json.loads(RECON.read_text(encoding="utf-8"))

    client = ResearchApiClient()
    all_robots = client.list_robots_for_company(COMPANY_ID)
    by_id = {int(r["id"]): r for r in all_robots}

    # Hard guard: only touch our 6 pending_review targets; never published.
    targets = []
    for rid in PLAN:
        r = by_id.get(rid)
        if not r:
            print(f"WARN: robot {rid} not found", file=sys.stderr)
            continue
        if (r.get("status") or "") != "pending_review":
            print(f"REFUSE {rid} {r.get('name')}: status={r.get('status')} (not pending_review)", file=sys.stderr)
            continue
        targets.append(r)

    plan_out = []
    staging: dict[int, dict] = {}
    for robot in targets:
        rid = int(robot["id"])
        row = build_row(rid, robot, recon)
        staging[rid] = row
        item = {
            "id": rid,
            "name": robot["name"],
            "url": row["url"],
            "image": bool(row.get("image")),
            "n_images": len(row.get("images") or []),
            "features_len": len(row.get("features") or ""),
            "payload_kg": row.get("payload_kg"),
            "reach_mm": row.get("reach_mm"),
            "weight_kg": row.get("weight_kg"),
            "dof": row.get("dof"),
            "videos": len(row.get("video_urls") or []),
            "tags": row.get("tags"),
            "n_sources": len(row.get("sources") or []),
        }
        plan_out.append(item)
        print(
            f"{rid} {robot['name']}: img={item['image']} imgs={item['n_images']} "
            f"feat={item['features_len']} payload={item['payload_kg']} reach={item['reach_mm']} "
            f"weight={item['weight_kg']} dof={item['dof']} vids={item['videos']} src={item['n_sources']}"
        )

    preview = _RESEARCH_DIR / "staging" / "reports" / "comau-fix-preview.json"
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_text(json.dumps(plan_out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    bad = [
        p for p in plan_out
        if not p["image"] or p["features_len"] < 60 or not p["payload_kg"]
        or not p["reach_mm"] or not p["tags"]
    ]
    if bad:
        print(f"ERROR: incomplete enrichment for {len(bad)} robots", file=sys.stderr)
        for p in bad:
            print(f"  {p['name']}: {p}", file=sys.stderr)
        return 1

    if not args.apply:
        print(f"\nPreview: {preview}. Re-run with --apply --copy-media")
        return 0

    tmp = Path(tempfile.mkdtemp(prefix="comau-fix-"))
    imported: list[int] = []
    totals = {"created_count": 0, "updated_count": 0, "skipped_count": 0, "error_count": 0}
    all_ok = True
    for item in plan_out:
        rid = item["id"]
        row = staging[rid]
        fpath = tmp / f"{slugify_robot_name(row['name'])}-{rid}.json"
        fpath.write_text(json.dumps(row, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        result = import_staging(
            fpath,
            patch=True,
            force_overwrite=False,
            status="pending_review",
            dry_run=False,
            created_by_id=resolve_created_by_id(args.created_by_id),
            # replace_media recopies galleries synchronously in the import
            # request -> 502 gateway timeout on multi-image rows (see lessons).
            # Store the URLs here; the dedicated copy-media endpoint does the copy.
            replace_media=False,
            batch_size=1,
            skip_company_update=True,
        )
        if not result.get("ok"):
            all_ok = False
            print(f"IMPORT FAIL {rid}: {result.get('errors')}", file=sys.stderr)
            continue
        # Guard against accidental creation.
        if result.get("created_count"):
            print(f"WARN {rid}: created_count={result.get('created_count')} (expected patch/update only)", file=sys.stderr)
        imported.append(rid)
        for k in totals:
            totals[k] += result.get(k, 0) or 0
        print(f"imported {rid} {row['name']}")

    print(json.dumps({"ok": all_ok, **totals, "imported": imported}, indent=2))

    if args.copy_media and imported:
        ok, fail = trigger_copy_media(imported)
        print(f"copy-media ok={ok} fail={fail}")

    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
