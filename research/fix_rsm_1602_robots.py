"""RSM Machinery / ERSM (company 1602) content-queue enrichment.

Only #6718 Robotic Bending Cell is a robot product. The other 18 pending rows are
sheet-metal machine tools / ASRS (press brakes, levelers, punches, storage, etc.)
and are rejected as wrong_category.

OEM: https://rsm-machinery.com (brand ERSM). Site blocks bare bots — use browser UA.
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

BENDING_CELL_ID = 6718
BENDING_CELL_URL = f"{COMPANY_WEBSITE}/product/bending-cell/"
# Full-cell OEM render (matches current CDN hero subject); secondary product shot.
HERO_URL = f"{COMPANY_WEBSITE}/wp-content/uploads/2024/08/123.png.webp"
GALLERY_EXTRA = f"{COMPANY_WEBSITE}/wp-content/uploads/2026/03/Bending-Cell.png"

REJECT_IDS = [
    6719,  # CNC Leveler
    6720,  # Countersinking & Tapping Combo Machine
    6721,  # Electric Press Brake
    6722,  # Grinding Machine
    6723,  # Hybrid Press Brake
    6724,  # Hydraulic Leveler
    6725,  # Hydraulic Press Brake
    6726,  # Leveling Decoiler
    6727,  # Manual Deburring Machine
    6728,  # Manual Leveler
    6729,  # Mini Press Brake
    6730,  # Punching and Laser Combined Machine
    6731,  # Punching Machine
    6732,  # Semi-Automatic Leveler
    6733,  # Sheet Metal Storage System (ASRS tower — not a robot)
    6734,  # Tandem Press Brake
    6735,  # Tapping Machine
    6736,  # Torsion Bar Press Brake
]

REJECT_REASON = (
    "wrong_category: ERSM/RSM sheet-metal machine tool or warehouse storage "
    "system (press brake, leveler, punch, deburr, tapping, grinding, or ASRS), "
    "not a robot product. Keep only the Robotic Bending Cell (#6718) under this "
    "company. Do not re-import machine-tool catalog rows as robots."
)

TAGS = "Industrial|Industrial Arm|6-Axis|Material Handling|Factory Automation"


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


def reject_robot(client: ResearchApiClient, rid: int) -> str:
    url = f"{_admin_base()}/admin/robots/robot/content-queue/api/robot/{rid}/reject/"
    headers = {
        "Content-Type": "application/json",
        "X-Internal-Secret": _internal_secret(),
    }
    payload = {
        "rejection_reason": REJECT_REASON[:500],
        "rejection_categories": ["wrong_category"],
    }
    admin_msg = ""
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        if resp.ok:
            return f"admin-reject {resp.status_code}"
        admin_msg = f"admin {resp.status_code} {(resp.text or '')[:160]}"
    except requests.RequestException as exc:
        admin_msg = f"admin ERR {exc}"
    try:
        client._patch(
            f"robots/robots/{rid}/",
            {
                "status": "rejected",
                "rejection_reason": REJECT_REASON[:500],
                "rejection_categories": ["wrong_category"],
            },
        )
        return f"api-patch-rejected (fallback after {admin_msg})"
    except Exception as exc:
        return f"FAIL {admin_msg} / patch {exc}"


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


def build_bending_cell_row(tags: str) -> dict[str, Any]:
    return {
        "company_slug": COMPANY_SLUG,
        "company_name": COMPANY_NAME,
        "source_locale": "en",
        "name": "Robotic Bending Cell",
        "model_name": "Robotic Bending Cell",
        "variant_code": "standard",
        "variant_label": "20 kg / 1780 mm arm",
        "url": BENDING_CELL_URL,
        "family_key": f"{COMPANY_SLUG}:bending-cell",
        "family_name": "Bending Cell",
        "family_url": BENDING_CELL_URL,
        "product_url_scope": "exact_variant",
        "description": (
            "ERSM Robotic Bending Cell pairs a CNC press brake with a six-axis "
            "industrial arm for automatic sheet loading, alignment, bending, and "
            "stacking. Mobile cell layout with PLC/CNC motion control for high-mix "
            "and volume sheet-metal production."
        ),
        "purpose": (
            "Sheet metal bending\n"
            "Press-brake tending\n"
            "Automatic loading and unloading\n"
            "Part stacking"
        ),
        "features": (
            "Fully automatic robotic bending cell (ERSM / RSM Machinery). Six-axis "
            "arm integrated with CNC press brake and PLC motion control; automates "
            "loading, alignment, bending, and stacking. Standard arm specs: max "
            "load 20 kg, max active radius 1780 mm, repeat positioning accuracy "
            "±0.03 mm; electric control cabinet with expandable multi-axis control; "
            "teach pendant with USB; ESTUN robot-specific high-performance servo; "
            "optional ball positioning / visual centering. Cell includes flexible "
            "bending device, real-time CNC angle compensation, safety fencing/"
            "light-curtain capable layout. OEM also cites bending accuracy up to "
            "±0.01 mm for the forming process."
        ),
        "payload_kg": 20.0,
        "reach_mm": 1780.0,
        "dof": 6,
        "repeatability_mm": 0.03,
        "availability_status_key": "available",
        "movement_type_keys": "stationary|fixed",
        "industry_keys": "manufacturing|industrial|metalworking",
        "use_keys": "material-handling|machine-tending",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "manufacturing-industrial",
        "tags": tags,
        "manufacturer_country_code": "CN",
        "information_source_urls": [BENDING_CELL_URL],
        "programming_interface": (
            "Teach pendant with USB; PLC motion control and CNC press-brake "
            "controller; programming wizards for fast cell setup (OEM)."
        ),
        "deployment_context": (
            "Fenced sheet-metal fabrication cell pairing a six-axis arm with a "
            "CNC press brake for lights-out or low-labor bending."
        ),
        "mounting_options": "Floor-mounted cell; arm on cell base / linear track layout",
        "safety_fencing": (
            "Cell safety fencing with light-curtain style access control "
            "(OEM cell renders); reduces manual press-brake interaction."
        ),
        "ecosystem_compatibility": (
            "Integrates with ERSM CNC press brakes; ESTUN robot servo drive; "
            "optional vision/ball centering."
        ),
        "notes": (
            "[AI Research] Renamed Bending Cell → Robotic Bending Cell. Specs "
            "from OEM Main Characteristics (20 kg / 1780 mm / ±0.03 mm / 6 axes). "
            "Sibling queue rows were non-robot machine tools — rejected."
        ),
        "research_notes": BENDING_CELL_URL,
        "image": HERO_URL,
        "images": [HERO_URL, GALLERY_EXTRA],
    }


def patch_typed(client: ResearchApiClient, rid: int) -> None:
    body: dict[str, Any] = {
        "name": "Robotic Bending Cell",
        "model_name": "Robotic Bending Cell",
        "variant_code": "standard",
        "variant_label": "20 kg / 1780 mm arm",
        "family_key": f"{COMPANY_SLUG}:bending-cell",
        "family_name": "Bending Cell",
        "family_url": BENDING_CELL_URL,
        "product_url_scope": "exact_variant",
        "payload_kg": 20.0,
        "reach_mm": 1780.0,
        "dof": 6,
        "repeatability_mm": 0.03,
        "purpose": (
            "Sheet metal bending\n"
            "Press-brake tending\n"
            "Automatic loading and unloading\n"
            "Part stacking"
        ),
        "programming_interface": (
            "Teach pendant with USB; PLC motion control and CNC press-brake "
            "controller; programming wizards for fast cell setup (OEM)."
        ),
        "deployment_context": (
            "Fenced sheet-metal fabrication cell pairing a six-axis arm with a "
            "CNC press brake for lights-out or low-labor bending."
        ),
        "mounting_options": "Floor-mounted cell; arm on cell base / linear track layout",
        "safety_fencing": (
            "Cell safety fencing with light-curtain style access control "
            "(OEM cell renders); reduces manual press-brake interaction."
        ),
        "ecosystem_compatibility": (
            "Integrates with ERSM CNC press brakes; ESTUN robot servo drive; "
            "optional vision/ball centering."
        ),
        "availability_status": 11,
        "manufacturer_countries": [CN_COUNTRY_ID],
        "manufacturer_country_ref": CN_COUNTRY_ID,
        "status": "pending_review",
    }
    ok = []
    for k, v in body.items():
        try:
            client._patch(f"robots/robots/{rid}/", {k: v})
            ok.append(k)
        except Exception as exc:
            print(f"  patch fail {rid}.{k}: {exc}", file=sys.stderr)
    print(f"  patched typed {rid}: {ok}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--skip-reject", action="store_true")
    parser.add_argument("--verify-cdn", action="store_true")
    parser.add_argument("--mark-done", action="store_true")
    parser.add_argument("--created-by-id", type=int, default=1)
    args = parser.parse_args()

    client = ResearchApiClient()
    catalog = TagCatalog.load(client=client)
    pending = {
        int(r["id"]): r
        for r in client.list_robots_for_company(COMPANY_ID)
        if str(r.get("status") or "").lower() == "pending_review"
    }
    tags = resolve_tags(catalog, TAGS)
    row = build_bending_cell_row(tags)

    # Validate industry/use keys that may not exist
    preview = {
        "enrich": {
            "id": BENDING_CELL_ID,
            "name": row["name"],
            "payload_kg": 20,
            "reach_mm": 1780,
            "dof": 6,
            "pending": BENDING_CELL_ID in pending,
        },
        "reject": [rid for rid in REJECT_IDS if rid in pending],
        "skip_not_pending": [
            rid
            for rid in [BENDING_CELL_ID, *REJECT_IDS]
            if rid not in pending
        ],
    }
    out = _RESEARCH_DIR / "staging" / "reports" / "rsm-1602-fix-preview.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(preview, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(preview, indent=2))
    if not args.apply:
        print(f"Preview {out}. Re-run --apply --verify-cdn --mark-done")
        return 0

    rejected = []
    if not args.skip_reject:
        for rid in REJECT_IDS:
            if rid not in pending:
                print(f"SKIP reject {rid}: not pending")
                continue
            msg = reject_robot(client, rid)
            print(f"REJECT {rid}: {msg}", flush=True)
            rejected.append(rid)
            time.sleep(0.1)

    if BENDING_CELL_ID not in pending and BENDING_CELL_ID not in (
        int(r["id"])
        for r in client.list_robots_for_company(COMPANY_ID)
        if str(r.get("status") or "").lower() == "pending_review"
    ):
        # re-check after rejects — enrich only if still pending or we saw it
        still = {
            int(r["id"]): r
            for r in client.list_robots_for_company(COMPANY_ID)
            if str(r.get("status") or "").lower() == "pending_review"
        }
        if BENDING_CELL_ID not in still:
            print("ERROR: bending cell not pending", file=sys.stderr)
            return 1

    # Prefer metalworking if present else drop
    try:
        industries = client._get("robots/industries/")
        if isinstance(industries, dict):
            industries = industries.get("results") or []
        ikeys = {i.get("key") for i in industries}
        if "metalworking" not in ikeys:
            row["industry_keys"] = "manufacturing|industrial"
    except Exception:
        row["industry_keys"] = "manufacturing|industrial"

    try:
        uses = client._get("robots/uses/")
        if isinstance(uses, dict):
            uses = uses.get("results") or []
        ukeys = {u.get("key") for u in uses}
        use_parts = [k for k in ["material-handling", "machine-tending", "manufacturing"] if k in ukeys]
        if not use_parts:
            use_parts = ["material-handling"]
        row["use_keys"] = "|".join(use_parts)
    except Exception:
        row["use_keys"] = "material-handling"

    bulk = staging_dict_to_bulk_import_row(row)
    bulk["id"] = BENDING_CELL_ID
    bulk["name"] = "Robotic Bending Cell"
    bulk["status"] = "pending_review"
    print(f"Importing {BENDING_CELL_ID}…", flush=True)
    result = client.bulk_import_robots(
        [bulk],
        update_existing=True,
        patch_existing=False,
        replace_media=True,
        replace_videos=False,
        status="pending_review",
        skip_company_update=True,
        created_by_id=resolve_created_by_id(args.created_by_id),
    )
    created = int(result.get("created_count") or 0)
    err = int(result.get("error_count") or 0)
    print(f"  created={created} updated={result.get('updated_count')} err={err}")
    if created or err:
        print(f"ERROR import: {result}", file=sys.stderr)
        return 1

    patch_typed(client, BENDING_CELL_ID)
    try:
        client._patch(
            f"robots/robots/{BENDING_CELL_ID}/",
            {
                "status": "pending_review",
                "name": "Robotic Bending Cell",
                "notes": row["notes"],
                "features": row["features"],
                "description": row["description"],
            },
        )
    except Exception as exc:
        print(f"  final patch warn: {exc}", file=sys.stderr)

    cm_ok, cm_fail = trigger_copy_media([BENDING_CELL_ID])
    print(f"copy-media ok={cm_ok} fail={cm_fail}")

    if args.verify_cdn:
        subprocess.check_call(
            [
                sys.executable,
                str(_RESEARCH_DIR / "verify_cdn_images.py"),
                "--company-id",
                str(COMPANY_ID),
            ],
            cwd=str(_RESEARCH_DIR),
        )

    if args.mark_done:
        subprocess.check_call(
            [
                sys.executable,
                str(_RESEARCH_DIR / "triage_content_queue.py"),
                "--mark-done",
                str(COMPANY_ID),
            ],
            cwd=str(_RESEARCH_DIR),
        )

    summary = {
        "enriched": [BENDING_CELL_ID],
        "rejected": rejected,
        "preview": str(out),
        "copy_media": {"ok": cm_ok, "fail": cm_fail},
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
