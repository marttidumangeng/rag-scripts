"""Fix Shenzhen Guanhong Automation (company 1419) content-queue enrichment.

OEM: https://www.szghrobot.com (company website also szghauto.com)
Sources: live EN PDPs under /products_details/*.html — Payload/Reach/DOF/Repeatability/Weight.

Issues addressed:
- feat=0 on all 18 pending robots
- Rename long marketing titles → SZGH model codes
- family_key guanhong:szgh-{b|g|h|hz|t}; CN country; Available(11)
- Keep OEM heroes from thefastimg portal CMS (already often on CDN)
- status stays pending_review

Requires prior scrape: python _scrape_guanhong_1419.py
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

COMPANY_ID = 1419
COMPANY_SLUG = "shenzhen-guanhong-automation-co-ltd"
COMPANY_NAME = "Shenzhen Guanhong Automation"
CN_COUNTRY_ID = 3  # filled at runtime from company if wrong
SCRAPE = _RESEARCH_DIR / "staging" / "reports" / "guanhong-1419-scrape.json"

TAGS_WELD = "Industrial|Industrial Arm|Welding|6-Axis"
TAGS_PALLET = "Industrial|Industrial Arm|Palletizing|4-Axis"
TAGS_GENERAL = "Industrial|Industrial Arm|6-Axis"

_AVAIL_IDS = {"available": 11}


def resolve_tags(catalog: TagCatalog, pipe: str) -> str:
    names = [n.strip() for n in pipe.split("|") if n.strip()]
    out: list[str] = []
    missing: list[str] = []
    for n in names:
        hit = catalog._by_name.get(n.lower())
        if hit:
            out.append(str(hit.get("name") or n))
        else:
            missing.append(n)
    if missing:
        print(f"WARN unresolved tags: {missing}", file=sys.stderr)
    return "|".join(out)


def tags_for(family_key: str, dof: int | None) -> str:
    if "szgh-h" in family_key or "szgh-hz" in family_key:
        return TAGS_WELD
    if "szgh-b" in family_key or "szgh-g" in family_key:
        return TAGS_PALLET
    if dof == 4:
        return TAGS_PALLET
    return TAGS_GENERAL


def purpose_from(apps: list[str], family_name: str) -> str:
    lines = []
    for a in apps:
        a = a.strip()
        if not a:
            continue
        # Drop warranty / controller noise
        if any(x in a.lower() for x in ("warranty", "controller", "display language", "technical service")):
            continue
        if a not in lines:
            lines.append(a)
        if len(lines) >= 6:
            break
    if not lines:
        if "Welding" in family_name:
            lines = ["Arc welding", "Metal fabrication welding"]
        elif "Pallet" in family_name:
            lines = ["Palletizing", "Material handling", "Parts transmission"]
        else:
            lines = ["Industrial articulated arm automation"]
    return "\n".join(lines)


def description_for(model: str, family_name: str, payload: float, reach: float, dof: int | None) -> str:
    axis = f"{dof}-axis " if dof else ""
    role = "welding" if "Welding" in family_name else (
        "palletizing/handling" if "Pallet" in family_name else "general automation"
    )
    return (
        f"{model} is a Shenzhen Guanhong Automation {axis}industrial robot in the "
        f"{family_name} line for {role}. OEM-rated payload {payload:g} kg and reach "
        f"{reach:g} mm (szghrobot.com product page)."
    )


def features_for(row: dict[str, Any]) -> str:
    parts = [
        f"OEM PDP {row['url']}: model {row['model_name']}; "
        f"payload {row['payload_kg']:g} kg; reach {row['reach_mm']:g} mm"
    ]
    if row.get("dof") is not None:
        parts.append(f"DOF {row['dof']}")
    if row.get("repeatability_mm") is not None:
        parts.append(f"repeatability ±{row['repeatability_mm']:g} mm")
    if row.get("weight_kg") is not None:
        parts.append(f"weight {row['weight_kg']:g} kg")
    apps = [a for a in (row.get("applications") or []) if a][:4]
    if apps:
        parts.append("applications: " + "; ".join(apps))
    parts.append("Warranty 2 years; lifelong technical service support (OEM claim).")
    return ". ".join(parts)


def trigger_copy_media(robot_ids: list[int]) -> tuple[int, int]:
    secret = os.environ.get("INTERNAL_API_SECRET") or ""
    api = (os.environ.get("ADMIN_BASE") or "https://ragadmin.robotaigeek.com").rstrip("/")
    if not secret:
        print("WARN: no INTERNAL_API_SECRET", file=sys.stderr)
        return 0, len(robot_ids)
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
        time.sleep(0.15)
    return ok, fail


def build_fix(row: dict[str, Any]) -> dict[str, Any]:
    fam = row["family_key"]
    dof = row.get("dof")
    apps = row.get("applications") or []
    return {
        "name": row["model_name"],
        "model_name": row["model_name"],
        "variant_code": row["model_name"],
        "variant_label": row["model_name"],
        "url": row["url"],
        "family_key": fam,
        "family_name": row["family_name"],
        "family_url": row.get("family_url") or row["url"],
        "product_url_scope": "exact_variant",
        "image": row.get("image") or row.get("existing_image") or "",
        "description": description_for(
            row["model_name"], row["family_name"], row["payload_kg"], row["reach_mm"], dof
        ),
        "purpose": purpose_from(apps, row["family_name"]),
        "features": features_for(row),
        "payload_kg": row["payload_kg"],
        "reach_mm": row["reach_mm"],
        "dof": dof,
        "repeatability_mm": row.get("repeatability_mm"),
        "weight_kg": row.get("weight_kg"),
        "availability_status_key": "available",
        "movement_type_keys": "stationary|fixed",
        "industry_keys": "manufacturing|industrial|metalworking",
        "use_keys": (
            "arc-welding|welding" if "Welding" in row["family_name"]
            else "material-handling|palletizing|intralogistics"
        ),
        "category_slugs": "industrial-robots",
        "sub_category_slug": "manufacturing-industrial",
        "tags": tags_for(fam, dof),
        "manufacturer_country_code": "CN",
        "information_source_urls": [row["url"]],
        "notes_force": (
            f"[AI Research] Renamed from {row.get('old_name')!r} → {row['model_name']}. "
            f"Specs scraped from OEM PDP {row['url']}. "
            f"family_key={fam}."
        ),
        "source_note": row["url"],
        "deployment_context": (
            "Factory floor industrial arm; ground / bracket / ceiling mounts where OEM lists them."
        ),
    }


def build_row(fix: dict[str, Any], *, tags: str) -> dict[str, Any]:
    row: dict[str, Any] = {
        "company_slug": COMPANY_SLUG,
        "company_name": COMPANY_NAME,
        "source_locale": "en",
    }
    skip = {"notes_force", "source_note", "images", "availability_status_key"}
    for k, v in fix.items():
        if k in skip or v is None or v == "":
            continue
        row[k] = v
    row["tags"] = tags
    row["notes"] = fix.get("notes_force") or ""
    row["research_notes"] = fix.get("source_note") or ""
    if fix.get("image"):
        row["images"] = [fix["image"]]
        row["image"] = fix["image"]
    row["availability_status_key"] = "available"
    return row


def patch_typed(client: ResearchApiClient, rid: int, fix: dict[str, Any], country_id: int) -> None:
    body: dict[str, Any] = {}
    for k in (
        "payload_kg",
        "reach_mm",
        "dof",
        "repeatability_mm",
        "weight_kg",
        "family_key",
        "family_name",
        "family_url",
        "model_name",
        "variant_code",
        "variant_label",
        "product_url_scope",
        "purpose",
        "deployment_context",
    ):
        if fix.get(k) not in (None, ""):
            body[k] = fix[k]
    body["availability_status"] = 11
    ok = []
    for k, v in body.items():
        try:
            client._patch(f"robots/robots/{rid}/", {k: v})
            ok.append(k)
        except Exception as exc:
            print(f"  patch fail {rid}.{k}: {exc}", file=sys.stderr)
    try:
        client._patch(
            f"robots/robots/{rid}/",
            {"manufacturer_countries": [country_id], "manufacturer_country_ref": country_id},
        )
        ok.append("manufacturer_countries")
    except Exception as exc:
        print(f"  patch fail {rid}.country: {exc}", file=sys.stderr)
    if ok:
        print(f"  patched typed {rid}: {ok}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--copy-media", action="store_true")
    parser.add_argument("--verify-cdn", action="store_true")
    parser.add_argument("--mark-done", action="store_true")
    parser.add_argument("--created-by-id", type=int, default=1)
    parser.add_argument("--only", type=int, nargs="*")
    args = parser.parse_args()

    if not SCRAPE.is_file():
        print(f"Missing {SCRAPE}; run _scrape_guanhong_1419.py first", file=sys.stderr)
        return 1
    scraped = json.loads(SCRAPE.read_text(encoding="utf-8"))
    scraped = [r for r in scraped if r.get("parse_ok")]
    if args.only:
        scraped = [r for r in scraped if int(r["id"]) in args.only]

    client = ResearchApiClient()
    catalog = TagCatalog.load(client=client)
    co = client._get(f"companies/{COMPANY_ID}/")
    country = co.get("country") or {}
    country_id = int(country.get("id") or CN_COUNTRY_ID)
    print(f"Company country_id={country_id} ({country.get('name')})")

    pending = {
        int(r["id"]): r
        for r in client.list_robots_for_company(COMPANY_ID)
        if str(r.get("status") or "").lower() == "pending_review"
    }

    targets = []
    for row in scraped:
        rid = int(row["id"])
        if rid not in pending:
            print(f"SKIP {rid}: not pending")
            continue
        fix = build_fix(row)
        if not fix.get("image"):
            print(f"ERROR {rid}: no image", file=sys.stderr)
            return 1
        tags = resolve_tags(catalog, fix["tags"])
        bulk_row = build_row(fix, tags=tags)
        targets.append({"id": rid, "fix": fix, "row": bulk_row})
        print(
            f"  {rid} {fix['name']}: pay={fix.get('payload_kg')} "
            f"reach={fix.get('reach_mm')} fam={fix['family_key']}"
        )

    preview = _RESEARCH_DIR / "staging" / "reports" / "guanhong-1419-fix-preview.json"
    preview.write_text(
        json.dumps(
            [{"id": t["id"], "name": t["fix"]["name"], "payload_kg": t["fix"].get("payload_kg"),
              "reach_mm": t["fix"].get("reach_mm"), "family_key": t["fix"]["family_key"],
              "url": t["fix"]["url"]} for t in targets],
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    if not targets:
        print("ERROR: no targets", file=sys.stderr)
        return 1
    if not args.apply:
        print(f"Preview {preview}. Re-run --apply --copy-media --verify-cdn --mark-done")
        return 0

    imported = []
    for t in targets:
        rid, fix, row = t["id"], t["fix"], t["row"]
        bulk = staging_dict_to_bulk_import_row(row)
        bulk["id"] = rid
        bulk["name"] = fix["name"]
        bulk["status"] = "pending_review"
        print(f"Importing {rid} {fix['name']}…", flush=True)
        result = client.bulk_import_robots(
            [bulk],
            update_existing=True,
            patch_existing=False,
            replace_media=True,
            replace_videos=True,
            status="pending_review",
            skip_company_update=True,
            created_by_id=resolve_created_by_id(args.created_by_id),
        )
        created = int(result.get("created_count") or 0)
        err = int(result.get("error_count") or 0)
        print(f"  created={created} updated={result.get('updated_count')} err={err}")
        if created or err:
            print(f"ERROR {rid}: {result}", file=sys.stderr)
            return 1
        patch_typed(client, rid, fix, country_id)
        try:
            client._patch(
                f"robots/robots/{rid}/",
                {"status": "pending_review", "name": fix["name"], "notes": fix["notes_force"]},
            )
        except Exception as exc:
            print(f"  final patch warn {rid}: {exc}", file=sys.stderr)
        imported.append(rid)

    if args.copy_media and imported:
        ok, fail = trigger_copy_media(imported)
        print(f"copy-media ok={ok} fail={fail}")
        for t in targets:
            if t["id"] in imported:
                patch_typed(client, t["id"], t["fix"], country_id)

    if args.verify_cdn and imported:
        subprocess.check_call(
            [sys.executable, str(_RESEARCH_DIR / "verify_cdn_images.py"),
             "--company-id", str(COMPANY_ID)],
            cwd=str(_RESEARCH_DIR),
        )

    if args.mark_done and imported:
        subprocess.check_call(
            [sys.executable, str(_RESEARCH_DIR / "triage_content_queue.py"),
             "--mark-done", str(COMPANY_ID)],
            cwd=str(_RESEARCH_DIR),
        )

    print(json.dumps({"imported": imported, "preview": str(preview)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
