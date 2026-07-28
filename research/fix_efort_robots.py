"""Full-fleet EFORT (company 1479) content-queue backfill.

Problem state (all 67 pending_review):
- features = identical footer/nav junk on every robot
- tags = wrong (Drone/Humanoid/Care Robot on industrial arms)
- industries/uses = mixed Chinese labels + irrelevant (Defence/Research)
- made_in = None; payload/reach/dof = None
- description = partly hallucinated (e.g. "4800 kg payload" on a painting robot)
- 47/67 missing images

Fix strategy (curated, per-family):
- Family type from visual verification of category hero renders (see recon):
  53/54/55/57 = 6-axis arm, 260 = 6-axis heavy/foundry, 268 = explosion-proof 6-axis,
  58 = GR6150 painting (CMA), 59 = ER..C cobot, 92 = SCARA (4-axis), 109 = 4-axis palletizer.
- payload/reach derived from EFORT model-name convention (cited as OEM designation);
  GR6150 painting suffix is ambiguous -> left null (never invented).
- hero + gallery from OEM PDP `.pic .cen` images (efort.com.cn hotlink needs Referer;
  server recopy sends domain-root Referer -> works). replace_media=True + copy-media + CDN verify.
- tags: exact TagCatalog names only. industries/uses: canonical keys only.
- videos: left untouched (existing family videos preserved; none invented).

Run:
  python fix_efort_robots.py                 # dry-run, writes preview
  python fix_efort_robots.py --apply --copy-media           # full fleet
  python fix_efort_robots.py --apply --copy-media --only-ids 4533 4553 4548  # test batch
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

import requests

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from load_env import load_research_env  # noqa: E402

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient  # noqa: E402
from map_to_bulk_import import staging_dict_to_bulk_import_row  # noqa: E402
from tag_suggest import TagCatalog  # noqa: E402

COMPANY_ID = 1479
COMPANY_SLUG = "efort-intelligent-equipment-co-ltd"
COMPANY_NAME = "EFORT Intelligent Equipment Co., Ltd."
RECON_PATH = _RESEARCH_DIR / "staging" / "reports" / "efort_recon.json"
PREVIEW_PATH = _RESEARCH_DIR / "staging" / "reports" / "efort-fix-preview.json"
REPORT_PATH = _RESEARCH_DIR / "staging" / "reports" / "efort-1479-report.json"

# --- per-family config keyed by URL category id --------------------------------
SIXAXIS_TAGS = "Industrial|Industrial Robot|Industrial Arm|6-Axis|Manufacturing|Assembly|Factory Automation|Material Handling|Automation"
HEAVY_TAGS = "Industrial|Industrial Robot|Industrial Arm|6-Axis|Manufacturing|Material Handling|Factory Automation|Automation"
PAINT_TAGS = "Industrial|Industrial Robot|Industrial Arm|6-Axis|Manufacturing|Painting|Factory Automation|Automation"
COBOT_TAGS = "Cobot|Collaborative|Industrial|Industrial Robot|6-Axis|Manufacturing|Assembly|Factory Automation"
SCARA_TAGS = "scara|4-axis|Industrial|Industrial Robot|Manufacturing|Assembly|Pick-and-Place|Factory Automation"
PALLET_TAGS = "Industrial|Industrial Robot|4-axis|palletizing|Material Handling|Warehouse Automation|Manufacturing|Automation"

FAMILY: dict[str, dict[str, Any]] = {
    "53": dict(kind="6-axis articulated robot", dof=6, tags=SIXAXIS_TAGS,
               uses="assembly|transport", sub="manufacturing-industrial",
               blurb="Compact 6-axis articulated robot for light assembly, handling and machine tending."),
    "54": dict(kind="6-axis articulated robot", dof=6, tags=SIXAXIS_TAGS,
               uses="assembly|transport", sub="manufacturing-industrial",
               blurb="Mid-payload 6-axis articulated robot for assembly, handling, welding and machine tending."),
    "55": dict(kind="6-axis articulated robot", dof=6, tags=HEAVY_TAGS,
               uses="transport|assembly", sub="manufacturing-industrial",
               blurb="High-payload 6-axis articulated robot for heavy handling and manufacturing automation."),
    "57": dict(kind="heavy-payload 6-axis articulated robot", dof=6, tags=HEAVY_TAGS,
               uses="transport", sub="manufacturing-industrial",
               blurb="Heavy-payload 6-axis articulated robot for large-part handling, palletizing and spot welding."),
    "260": dict(kind="heavy-payload 6-axis articulated robot", dof=6, tags=HEAVY_TAGS,
                uses="transport", sub="manufacturing-industrial",
                blurb="Heavy-duty 6-axis articulated robot built for foundry and heavy material-handling duty."),
    "268": dict(kind="explosion-proof 6-axis articulated robot", dof=6, tags=HEAVY_TAGS,
                uses="assembly|transport", sub="manufacturing-industrial",
                blurb="Explosion-proof (Ex) 6-axis articulated robot for hazardous-area handling and spraying."),
    "58": dict(kind="explosion-proof painting robot", dof=6, tags=PAINT_TAGS,
               uses="", sub="manufacturing-industrial",
               blurb="Explosion-proof spray-painting robot (EFORT/CMA GR series) with hollow wrist for paint pipeline routing."),
    "59": dict(kind="collaborative robot (cobot)", dof=6, tags=COBOT_TAGS,
               uses="assembly|inspection", sub="manufacturing-industrial",
               blurb="Collaborative 6-axis cobot with force sensing for human-nearby assembly, handling and inspection."),
    "92": dict(kind="SCARA robot", dof=4, tags=SCARA_TAGS,
               uses="assembly|picking", sub="manufacturing-industrial",
               blurb="4-axis SCARA robot for high-speed pick-and-place, assembly and sorting."),
    "109": dict(kind="4-axis palletizing robot", dof=4, tags=PALLET_TAGS,
                uses="transport|picking", sub="logistics-warehouse",
                blurb="4-axis palletizing robot with parallelogram linkage for end-of-line stacking and material handling."),
}
DEFAULT_FAM = FAMILY["54"]

MAX_GALLERY = 6


def parse_specs(name: str, cat: str) -> tuple[float | None, float | None, int]:
    """Return (payload_kg, reach_mm, dof) from EFORT model-name convention.

    GR6150 painting suffix is ambiguous (reach vs config) -> null payload/reach.
    """
    u = (name or "").upper().strip()
    dof = int(FAMILY.get(cat, DEFAULT_FAM)["dof"])

    def ok(p: float, r: float) -> bool:
        return p <= 1000 and 100 <= r <= 6500

    if cat == "58":  # GR6150-xxxx painting — do not invent
        return None, None, dof
    if cat == "109":  # ER15-4-1600 / ER130-4-2800 (H variant)
        m = re.match(r"ER(\d+(?:\.\d+)?)-4-(\d+)", u)
        if m and ok(float(m.group(1)), float(m.group(2))):
            return float(m.group(1)), float(m.group(2)), 4
        return None, None, 4
    if cat == "268":  # EXR8-1300
        m = re.match(r"EXR(\d+(?:\.\d+)?)-(\d+)", u)
        if m and ok(float(m.group(1)), float(m.group(2))):
            return float(m.group(1)), float(m.group(2)), 6
        return None, None, 6
    if cat == "260":  # ER230-3100F
        m = re.match(r"ER(\d+(?:\.\d+)?)-(\d+)F", u)
        if m and ok(float(m.group(1)), float(m.group(2))):
            return float(m.group(1)), float(m.group(2)), 6
        return None, None, 6
    if cat == "59":  # ER3-600C cobot
        m = re.match(r"ER(\d+(?:\.\d+)?)-(\d+)C", u)
        if m and ok(float(m.group(1)), float(m.group(2))):
            return float(m.group(1)), float(m.group(2)), 6
        return None, None, 6
    if cat == "92":  # SCARA ER3-400
        m = re.match(r"ER(\d+(?:\.\d+)?)-(\d+)", u)
        if m and ok(float(m.group(1)), float(m.group(2))):
            return float(m.group(1)), float(m.group(2)), 4
        return None, None, 4
    # 6-axis A-series: ER3A-400, ER20A-1700, ER500A-2800
    m = re.match(r"ER(\d+(?:\.\d+)?)A-(\d+)", u)
    if m and ok(float(m.group(1)), float(m.group(2))):
        return float(m.group(1)), float(m.group(2)), 6
    return None, None, dof


def resolve_tags(raw: str, tc: TagCatalog) -> str:
    names = [t.strip() for t in raw.split("|") if t.strip()]
    if tc.tags:
        known = {str(t.get("name") or "").lower(): str(t.get("name") or "") for t in tc.tags if t.get("name")}
        out = [known[n.lower()] for n in names if n.lower() in known]
        if out:
            return "|".join(dict.fromkeys(out))
    return "|".join(dict.fromkeys(names))


def build_features(name: str, fam: dict, payload, reach, dof) -> str:
    bits = [f"EFORT {name} — {fam['kind']}."]
    spec = []
    if payload is not None:
        spec.append(f"payload {payload:g} kg")
    if reach is not None:
        spec.append(f"reach {reach:g} mm")
    if dof:
        spec.append(f"{dof} axes")
    if spec:
        bits.append("Specifications: " + ", ".join(spec) + " (per EFORT model designation).")
    bits.append(fam["blurb"])
    bits.append("Built by EFORT Intelligent Equipment (Wuhu, China).")
    return " ".join(bits)


def build_description(name: str, fam: dict, payload, reach, dof) -> str:
    lead = []
    if payload is not None:
        lead.append(f"{payload:g} kg payload")
    if reach is not None:
        lead.append(f"{reach:g} mm reach")
    core = f"EFORT {name}"
    if lead:
        core += " — " + ", ".join(lead)
    return f"{core}. {fam['kind'].capitalize()} for industrial automation from EFORT (China)."


def gallery_from_recon(pics: list[str], hero: str) -> list[dict]:
    urls: list[str] = []
    for u in [hero, *pics]:
        if u and u not in urls:
            urls.append(u)
        if len(urls) >= MAX_GALLERY:
            break
    return [
        {
            "url": u,
            "source_page_url": "",
            "source_tier": "official",
            "source_publisher": "EFORT",
            "media_class": "product_photo" if i == 0 else "family_photo",
            "image_scope": "family",
            "rights_status": "review_required",
            "match_reason": "EFORT PDP .pic.cen product render (visually verified family hero)",
        }
        for i, u in enumerate(urls)
    ]


def build_row(robot: dict, recon: dict, tc: TagCatalog) -> dict[str, Any]:
    rid = robot["id"]
    name = robot["name"]
    rr = recon.get(rid, {})
    cat = rr.get("category") or ""
    fam = FAMILY.get(cat, DEFAULT_FAM)
    pics = rr.get("pics") or []
    hero = pics[0] if pics else (robot.get("image") or "")
    url = rr.get("url") or (robot.get("url") or "").strip()

    payload, reach, dof = parse_specs(name, cat)
    features = build_features(name, fam, payload, reach, dof)
    description = build_description(name, fam, payload, reach, dof)

    data: dict[str, Any] = {
        "id": rid,
        "name": name,
        "company_slug": COMPANY_SLUG,
        "company_name": COMPANY_NAME,
        "model_name": robot.get("model_name") or name,
        "manufacturer_country_code": "CN",
        "description": description[:1200],
        "features": features,
        "url": url,
        "tags": resolve_tags(fam["tags"], tc),
        "industry_keys": "manufacturing",
        "use_keys": fam["uses"],
        "movement_type_keys": "stationary",
        "category_slugs": "industrial-robots",
        "sub_category_slug": fam["sub"],
        "availability_status_key": "available",
        "dof": dof,
        "sources": [{"url": url, "type": "website", "title": name}] if url else [],
        "research_notes": (
            "EFORT full-fleet content-queue backfill 2026-07-16: rebuilt features/tags/"
            "industries/uses (prior data was footer-junk features + wrong tags), set made_in=CN, "
            "derived payload/reach from EFORT model-name convention, hero+gallery from OEM PDP."
        ),
    }
    if hero:
        data["image"] = hero
        data["images"] = gallery_from_recon(pics, hero)
    if payload is not None:
        data["payload_kg"] = float(payload)
    if reach is not None:
        data["reach_mm"] = float(reach)
    if robot.get("release_year"):
        data["release_year"] = robot["release_year"]
    return data


def load_recon() -> dict[int, dict]:
    if not RECON_PATH.is_file():
        raise SystemExit(f"Missing recon file {RECON_PATH}; run efort_recon.py first")
    rows = json.loads(RECON_PATH.read_text(encoding="utf-8"))
    return {r["id"]: r for r in rows}


def trigger_copy_media(robot_ids: list[int]) -> dict:
    import os

    api = os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/")
    admin = api.replace("/api/v1", "")
    secret = os.environ.get("INTERNAL_API_SECRET", "").strip()
    if not secret:
        env_file = _RESEARCH_DIR.parents[1] / "robotaigeek-server" / ".env"
        if env_file.is_file():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if line.startswith("INTERNAL_API_SECRET="):
                    secret = line.split("=", 1)[1].strip()
                    break
    if not secret:
        return {"ok": False, "error": "INTERNAL_API_SECRET missing"}
    ok = fail = 0
    errors = []
    for rid in robot_ids:
        u = f"{admin}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/"
        try:
            resp = requests.post(u, headers={"X-Internal-Secret": secret}, timeout=180)
            if resp.ok:
                ok += 1
            else:
                fail += 1
                errors.append({"id": rid, "status": resp.status_code, "body": resp.text[:200]})
        except requests.RequestException as exc:
            fail += 1
            errors.append({"id": rid, "error": str(exc)})
        time.sleep(0.2)
    return {"ok": fail == 0, "copied_ok": ok, "copied_fail": fail, "errors": errors[:20]}


def main() -> int:
    ap = argparse.ArgumentParser(description="EFORT (1479) content-queue backfill")
    ap.add_argument("--local", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--copy-media", action="store_true")
    ap.add_argument("--created-by-id", type=int, default=1)
    ap.add_argument("--batch-size", type=int, default=5)
    ap.add_argument("--only-ids", nargs="*", type=int)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    recon = load_recon()
    client = ResearchApiClient()
    tc = TagCatalog.load(client=client)
    robots = [r for r in client.list_robots_for_company(COMPANY_ID)
              if (r.get("status") or "") == "pending_review"]
    if args.only_ids:
        want = set(args.only_ids)
        robots = [r for r in robots if r["id"] in want]
    if args.limit:
        robots = robots[: args.limit]

    rows, preview = [], []
    for robot in robots:
        data = build_row(robot, recon, tc)
        rows.append(data)
        preview.append({
            "id": data["id"], "name": data["name"],
            "cat": recon.get(data["id"], {}).get("category"),
            "kind": FAMILY.get(recon.get(data["id"], {}).get("category") or "", DEFAULT_FAM)["kind"],
            "payload_kg": data.get("payload_kg"), "reach_mm": data.get("reach_mm"), "dof": data.get("dof"),
            "tags": data.get("tags"), "uses": data.get("use_keys"),
            "has_image": bool(data.get("image")), "n_gallery": len(data.get("images") or []),
            "feat_len": len(data.get("features") or ""),
        })

    PREVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    PREVIEW_PATH.write_text(json.dumps(preview, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    stats = {
        "total": len(preview),
        "with_image": sum(1 for p in preview if p["has_image"]),
        "with_payload": sum(1 for p in preview if p["payload_kg"] is not None),
        "with_reach": sum(1 for p in preview if p["reach_mm"] is not None),
        "with_tags": sum(1 for p in preview if p["tags"]),
        "gallery_ge4": sum(1 for p in preview if p["n_gallery"] >= 4),
        "families": dict(Counter(p["cat"] for p in preview)),
    }
    print(json.dumps(stats, indent=2))
    print(f"preview -> {PREVIEW_PATH}")

    if not args.apply:
        print("Dry-run. Re-run with --apply --copy-media")
        return 0

    import_rows = [staging_dict_to_bulk_import_row(d) for d in rows]
    ok = fail = 0
    details = []
    bs = args.batch_size
    for i in range(0, len(import_rows), bs):
        batch = import_rows[i:i + bs]
        try:
            resp = client.bulk_import_robots(
                batch,
                update_existing=True,
                patch_existing=False,
                status="pending_review",
                skip_company_update=True,
                created_by_id=args.created_by_id,
                replace_media=True,
            )
            details.append({k: resp.get(k) for k in ("ok", "updated_count", "created_count", "error_count", "errors")})
            if resp.get("errors") or resp.get("ok") is False:
                fail += 1
                print("  batch errors:", json.dumps(resp.get("errors"), ensure_ascii=False)[:300])
            else:
                ok += 1
            print(f"  batch {i//bs+1}: updated={resp.get('updated_count')} err={resp.get('error_count')}")
        except Exception as exc:  # noqa: BLE001
            fail += 1
            details.append({"error": str(exc)})
            print("  batch EXC:", str(exc)[:200])
        time.sleep(0.3)

    copy_result = None
    if args.copy_media:
        ids = [d["id"] for d in rows if d.get("image")]
        print(f"copy-media for {len(ids)} robots…")
        copy_result = trigger_copy_media(ids)
        print(json.dumps(copy_result, indent=2)[:600])

    REPORT_PATH.write_text(json.dumps(
        {"stats": stats, "batches_ok": ok, "batches_fail": fail, "details": details, "copy_media": copy_result},
        indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"report -> {REPORT_PATH}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
