"""Discover & import ERSM robot products missing from company 1602.

Already in DB: #6718 Robotic Bending Cell.
Adds:
  - SC7-1077 / SC6-1460 / SC15-1464 / SC20-2027 cobot welding family
    (OEM table on https://rsm-machinery.com/product/sc6-1460-cobot-welding-robot/)
  - Robotic Laser Welding (system page; arm specs not published — no invented payload)

Only SC6-1460 and Robotic Laser Welding get heroes (distinct OEM assets).
Sibling SC SKUs stay imageless with [IMAGE TO-DO] notes (shared series renders only).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
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
from import_staging import resolve_created_by_id
from map_to_bulk_import import staging_dict_to_bulk_import_row
from tag_suggest import TagCatalog

COMPANY_ID = 1602
COMPANY_SLUG = "rsm-machinery"
COMPANY_NAME = "RSM Machinery"
COMPANY_WEBSITE = "https://rsm-machinery.com"
CN_COUNTRY_ID = 3

COBOT_URL = f"{COMPANY_WEBSITE}/product/sc6-1460-cobot-welding-robot/"
LASER_URL = f"{COMPANY_WEBSITE}/product/robot-laser-welding/"

# Column-correct from OEM Technical Parameters table (Model | SC7-1077 | SC6-1460 | SC15-1464 | SC20-2027)
SC_MODELS: list[dict[str, Any]] = [
    {
        "name": "SC7-1077",
        "model_name": "SC7-1077",
        "variant_code": "SC7-1077",
        "variant_label": "7 kg / 1077 mm",
        "payload_kg": 7.0,
        "reach_mm": 1077.0,
        "repeatability_mm": 0.02,
        "weight_kg": 21.0,
        "tool_speed_mms": 3000,
        "power_w": 260,
        "image": None,
    },
    {
        "name": "SC6-1460",
        "model_name": "SC6-1460",
        "variant_code": "SC6-1460",
        "variant_label": "6 kg / 1460.7 mm",
        "payload_kg": 6.0,
        "reach_mm": 1460.7,
        "repeatability_mm": 0.05,
        "weight_kg": 22.0,
        "tool_speed_mms": 3000,
        "power_w": 550,
        "image": (
            f"{COMPANY_WEBSITE}/wp-content/uploads/2025/12/"
            "SC-Series-cobot-welding-robot.png.webp"
        ),
        "images": [
            f"{COMPANY_WEBSITE}/wp-content/uploads/2025/12/"
            "SC-Series-cobot-welding-robot.png.webp",
            f"{COMPANY_WEBSITE}/wp-content/uploads/2025/12/"
            "Heavy-Plate-Cobot-Welding-Robot-.jpg",
        ],
    },
    {
        "name": "SC15-1464",
        "model_name": "SC15-1464",
        "variant_code": "SC15-1464",
        "variant_label": "15 kg / 1464.3 mm",
        "payload_kg": 15.0,
        "reach_mm": 1464.3,
        "repeatability_mm": 0.03,
        "weight_kg": 36.0,
        "tool_speed_mms": 3000,
        "power_w": 1500,
        "image": None,
    },
    {
        "name": "SC20-2027",
        "model_name": "SC20-2027",
        "variant_code": "SC20-2027",
        "variant_label": "20 kg / 2027 mm",
        "payload_kg": 20.0,
        "reach_mm": 2027.0,
        "repeatability_mm": 0.05,
        "weight_kg": 68.0,
        "tool_speed_mms": 4000,
        "power_w": None,
        "image": None,
    },
]

TAGS_COBOT = "Collaborative|Industrial|6-Axis|Welding|Material Handling"
TAGS_LASER = "Industrial|Industrial Arm|6-Axis|Welding|Laser"


def _admin_base() -> str:
    return (os.environ.get("ADMIN_BASE") or "https://ragadmin.robotaigeek.com").rstrip("/")


def _internal_secret() -> str:
    secret = (
        os.environ.get("INTERNAL_API_SECRET")
        or os.environ.get("CONTENT_QUEUE_INTERNAL_SECRET")
        or ""
    ).strip()
    if secret:
        return secret
    for candidate in (
        _RESEARCH_DIR.parent.parent / "robotaigeek-server" / ".env",
        _RESEARCH_DIR.parent.parent / "robotaigeek-server" / ".env.local",
    ):
        if not candidate.exists():
            continue
        for line in candidate.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def resolve_tags(catalog: TagCatalog, pipe: str) -> str:
    out, missing = [], []
    for n in [x.strip() for x in pipe.split("|") if x.strip()]:
        hit = catalog._by_name.get(n.lower())
        if hit:
            out.append(str(hit.get("name") or n))
        else:
            missing.append(n)
    if missing:
        print(f"WARN unresolved tags: {missing}", file=sys.stderr)
    return "|".join(out)


def trigger_copy_media(robot_ids: list[int]) -> tuple[int, int]:
    secret = _internal_secret()
    api = _admin_base()
    ok = fail = 0
    for rid in robot_ids:
        url = f"{api}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/"
        try:
            resp = requests.post(url, headers={"X-Internal-Secret": secret}, timeout=120)
            if resp.status_code < 300:
                ok += 1
                print(f"copy-media ok {rid}", flush=True)
            else:
                fail += 1
                print(f"copy-media fail {rid}: HTTP {resp.status_code}", flush=True)
        except Exception as exc:
            fail += 1
            print(f"copy-media fail {rid}: {exc}", flush=True)
        time.sleep(0.2)
    return ok, fail


def image_todo_note(model: str) -> str:
    return (
        f"[IMAGE TO-DO — no hero, deliberate]\n"
        f"OEM documents {model} only in the shared SC-series Technical Parameters "
        f"table on {COBOT_URL}. Public media is a series-level cobot welding render "
        f"(already assigned to SC6-1460, the URL SKU) — not a distinct labeled "
        f"{model} product shot.\n"
        f"ACTION FOR TEAM: source a licensed {model}-specific photo from ERSM or "
        f"leave imageless.\n"
        f"Do NOT substitute a sibling render, a family banner, or marketing/diagram art.\n"
        f"---\n"
    )


def build_sc_row(m: dict[str, Any], *, tags: str) -> dict[str, Any]:
    power = f" rated power {m['power_w']} W;" if m.get("power_w") else ""
    features = (
        f"ERSM SC-series collaborative welding robot ({m['name']}). Six-axis cobot "
        f"for heavy-plate and sheet-metal welding: arc tracking, multi-layer "
        f"multi-pass, swing fixed-point arc; drag-and-drop / teach-handle "
        f"programming; fence-free ISO 10218-1 collaboration with force/collision "
        f"stop (>50 N). OEM Technical Parameters for this column: max working "
        f"radius {m['reach_mm']} mm; payload {m['payload_kg']} kg; repeat "
        f"positioning ±{m['repeatability_mm']} mm; tool-end max speed "
        f"{m['tool_speed_mms']} mm/s; body weight {m['weight_kg']} kg;{power} "
        f"IP65; EtherCAT 1 kHz; ambient −5–55/65°C. Integrates Magnetek welders/"
        f"wire feeders and optional welding cart (transport only — not for "
        f"operation while on cart)."
    )
    notes = (
        f"[AI Research] Discovered from ERSM SC cobot family table on {COBOT_URL}. "
        f"Column-correct specs for {m['name']} (not sibling columns)."
    )
    if not m.get("image"):
        notes = image_todo_note(m["name"]) + notes
    row: dict[str, Any] = {
        "company_slug": COMPANY_SLUG,
        "company_name": COMPANY_NAME,
        "source_locale": "en",
        "name": m["name"],
        "model_name": m["model_name"],
        "variant_code": m["variant_code"],
        "variant_label": m["variant_label"],
        "url": COBOT_URL,
        "family_key": f"{COMPANY_SLUG}:sc-cobot-welding",
        "family_name": "SC Cobot Welding",
        "family_url": COBOT_URL,
        "product_url_scope": "family",
        "description": (
            f"ERSM {m['name']} is a six-axis collaborative welding robot in the SC "
            f"series for heavy-plate and sheet-metal fabrication. Fence-free "
            f"human-robot collaboration with drag teaching and process packages "
            f"for arc welding."
        ),
        "purpose": (
            "Arc welding\n"
            "Heavy-plate welding\n"
            "Multi-pass welding\n"
            "Sheet-metal fabrication welding"
        ),
        "features": features,
        "payload_kg": m["payload_kg"],
        "reach_mm": m["reach_mm"],
        "dof": 6,
        "repeatability_mm": m["repeatability_mm"],
        "weight_kg": m["weight_kg"],
        "availability_status_key": "available",
        "movement_type_keys": "stationary|fixed",
        "industry_keys": "manufacturing|industrial|metalworking",
        "use_keys": "welding|material-handling|machine-tending",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "manufacturing-industrial",
        "tags": tags,
        "manufacturer_country_code": "CN",
        "information_source_urls": [COBOT_URL],
        "programming_interface": (
            "Drag-and-drop teaching, graphical UI, and welding-gun handle buttons "
            "(joint/linear/circular/arc start-end); EtherCAT controller (OEM)."
        ),
        "deployment_context": (
            "Fence-free collaborative welding cell; portable between workstations; "
            "optional welding cart for equipment transport."
        ),
        "mounting_options": "Floor / stable surface; multiple mounting methods (OEM)",
        "safety_fencing": (
            "Fence-free ISO 10218-1 collaboration; force-control stop when "
            "collision force exceeds 50 N; emergency stop (OEM)."
        ),
        "ecosystem_compatibility": (
            "Magnetek welding power sources and wire feeders; optional welding cart; "
            "customizable end effectors for grabbing/positioning/assembly."
        ),
        "notes": notes,
        "research_notes": COBOT_URL,
    }
    if m.get("image"):
        row["image"] = m["image"]
        row["images"] = m.get("images") or [m["image"]]
    return row


def build_laser_row(*, tags: str) -> dict[str, Any]:
    hero = (
        f"{COMPANY_WEBSITE}/wp-content/uploads/2026/03/"
        "Collaborative-Robot-with-Laser-Welding.png"
    )
    return {
        "company_slug": COMPANY_SLUG,
        "company_name": COMPANY_NAME,
        "source_locale": "en",
        "name": "Robotic Laser Welding",
        "model_name": "Robotic Laser Welding",
        "variant_code": "robotic-laser-welding",
        "variant_label": "multi-axis laser welding cell",
        "url": LASER_URL,
        "family_key": f"{COMPANY_SLUG}:robotic-laser-welding",
        "family_name": "Robotic Laser Welding",
        "family_url": LASER_URL,
        "product_url_scope": "family",
        "description": (
            "ERSM robotic laser welding mounts a fiber laser welder on a multi-axis "
            "arm for programmed, high-consistency seam welding in batch production. "
            "OEM page also covers handheld laser welding for repairs — this record "
            "is the robotic cell configuration only."
        ),
        "purpose": (
            "Laser welding\n"
            "Batch seam welding\n"
            "Precision metal joining"
        ),
        "features": (
            "ERSM Robotic Laser Welding (robotic configuration on the laser-welding "
            "product page). Multi-axis arm follows programmed paths for consistent "
            "penetration and reduced overspray on repetitive / hard-to-reach seams. "
            "OEM laser models on the same page: HFW-1000W / 1500W / 2000W / 3000W; "
            "wavelength 1070/1080 nm; continuous or modulated pulse; welding speed "
            "0–120 mm/s; dual-channel chiller; fiber length standard 7/10 m "
            "(customizable to 15 m). Handheld laser welder on the same page is a "
            "separate non-robot product and is not this record. Arm payload/reach "
            "not published for the robotic configuration — left blank."
        ),
        "availability_status_key": "available",
        "movement_type_keys": "stationary|fixed",
        "industry_keys": "manufacturing|industrial|metalworking",
        "use_keys": "welding|material-handling",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "manufacturing-industrial",
        "tags": tags,
        "manufacturer_country_code": "CN",
        "information_source_urls": [LASER_URL],
        "programming_interface": (
            "Program-driven path control with integrated sensors (OEM robotic "
            "laser welder description)."
        ),
        "deployment_context": (
            "Batch fabrication cell pairing a multi-axis arm with an ERSM fiber "
            "laser welder for repetitive seams."
        ),
        "mounting_options": "Floor-mounted robotic laser welding cell (OEM)",
        "safety_fencing": (
            "Industrial laser welding cell — follow OEM laser safety and cell "
            "guarding guidance."
        ),
        "notes": (
            "[AI Research] Discovered from "
            f"{LASER_URL}. Record covers robotic laser welding only; handheld "
            "variant intentionally excluded. No arm payload/reach cited on OEM page."
        ),
        "research_notes": LASER_URL,
        "image": hero,
        "images": [hero],
    }


def patch_typed(client: ResearchApiClient, rid: int, body: dict[str, Any]) -> None:
    ok = []
    for k, v in body.items():
        try:
            client._patch(f"robots/robots/{rid}/", {k: v})
            ok.append(k)
        except Exception as exc:
            print(f"  patch fail {rid}.{k}: {exc}", file=sys.stderr)
    print(f"  patched {rid}: {ok}")


def existing_names(client: ResearchApiClient) -> set[str]:
    return {
        str(r.get("name") or "").strip().lower()
        for r in client.list_robots_for_company(COMPANY_ID)
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--verify-cdn", action="store_true")
    parser.add_argument("--created-by-id", type=int, default=1)
    args = parser.parse_args()

    client = ResearchApiClient()
    catalog = TagCatalog.load(client=client)
    tags_c = resolve_tags(catalog, TAGS_COBOT)
    tags_l = resolve_tags(catalog, TAGS_LASER)
    have = existing_names(client)

    rows: list[dict[str, Any]] = []
    for m in SC_MODELS:
        if m["name"].lower() in have:
            print(f"SKIP existing {m['name']}")
            continue
        rows.append(build_sc_row(m, tags=tags_c))
    if "robotic laser welding" not in have:
        rows.append(build_laser_row(tags=tags_l))
    else:
        print("SKIP existing Robotic Laser Welding")

    preview = _RESEARCH_DIR / "staging" / "reports" / "rsm-1602-discover-preview.json"
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_text(
        json.dumps(
            [
                {
                    "name": r["name"],
                    "family_key": r["family_key"],
                    "payload_kg": r.get("payload_kg"),
                    "reach_mm": r.get("reach_mm"),
                    "has_image": bool(r.get("image")),
                    "url": r["url"],
                }
                for r in rows
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps(json.loads(preview.read_text(encoding="utf-8")), indent=2))
    if not rows:
        print("Nothing to import")
        return 0
    if not args.apply:
        print(f"Preview {preview}. Re-run --apply --verify-cdn")
        return 0

    created_ids: list[int] = []
    for row in rows:
        bulk = staging_dict_to_bulk_import_row(row)
        bulk["status"] = "pending_review"
        print(f"Creating {row['name']}…", flush=True)
        result = client.bulk_import_robots(
            [bulk],
            update_existing=False,
            patch_existing=False,
            replace_media=bool(row.get("image")),
            replace_videos=False,
            status="pending_review",
            skip_company_update=True,
            created_by_id=resolve_created_by_id(args.created_by_id),
        )
        created = int(result.get("created_count") or 0)
        err = int(result.get("error_count") or 0)
        print(f"  created={created} updated={result.get('updated_count')} err={err}")
        if err or not created:
            print(f"ERROR {row['name']}: {result}", file=sys.stderr)
            # try to find id if updated/matched
            robots = client.list_robots_for_company(COMPANY_ID)
            hit = next(
                (
                    r
                    for r in robots
                    if str(r.get("name") or "").lower() == row["name"].lower()
                ),
                None,
            )
            if not hit:
                return 1
            rid = int(hit["id"])
        else:
            # resolve id by name
            robots = client.list_robots_for_company(COMPANY_ID)
            hit = next(
                (
                    r
                    for r in robots
                    if str(r.get("name") or "").lower() == row["name"].lower()
                    and str(r.get("status") or "").lower() == "pending_review"
                ),
                None,
            )
            if not hit:
                print(f"ERROR could not resolve id for {row['name']}", file=sys.stderr)
                return 1
            rid = int(hit["id"])

        typed: dict[str, Any] = {
            "family_key": row["family_key"],
            "family_name": row["family_name"],
            "family_url": row["family_url"],
            "model_name": row["model_name"],
            "variant_code": row["variant_code"],
            "variant_label": row["variant_label"],
            "product_url_scope": row["product_url_scope"],
            "purpose": row["purpose"],
            "features": row["features"],
            "description": row["description"],
            "notes": row["notes"],
            "programming_interface": row["programming_interface"],
            "deployment_context": row["deployment_context"],
            "mounting_options": row["mounting_options"],
            "safety_fencing": row["safety_fencing"],
            "availability_status": 11,
            "manufacturer_countries": [CN_COUNTRY_ID],
            "manufacturer_country_ref": CN_COUNTRY_ID,
            "status": "pending_review",
        }
        if row.get("ecosystem_compatibility"):
            typed["ecosystem_compatibility"] = row["ecosystem_compatibility"]
        for k in ("payload_kg", "reach_mm", "dof", "repeatability_mm", "weight_kg"):
            if k in row and row[k] is not None:
                typed[k] = row[k]
        patch_typed(client, rid, typed)
        created_ids.append(rid)

    imaged = [
        rid
        for rid, row in zip(
            created_ids,
            rows,
            strict=False,
        )
        if row.get("image")
    ]
    # re-map: created_ids align with rows
    imaged = [created_ids[i] for i, row in enumerate(rows) if row.get("image")]
    if imaged:
        cm_ok, cm_fail = trigger_copy_media(imaged)
        print(f"copy-media ok={cm_ok} fail={cm_fail}")

    if args.verify_cdn and imaged:
        subprocess.check_call(
            [
                sys.executable,
                str(_RESEARCH_DIR / "verify_cdn_images.py"),
                "--ids",
                *[str(i) for i in imaged],
            ],
            cwd=str(_RESEARCH_DIR),
        )

    print(json.dumps({"created_ids": created_ids, "preview": str(preview)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
