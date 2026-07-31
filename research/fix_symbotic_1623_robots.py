"""Fix Symbotic (company 1623) content-queue enrichment.

OEM: https://www.symbotic.com
Sources: SymMicro micro-fulfillment page + robots / distribution pages.

Issues addressed:
- SymMicro had no photo/features/tags/taxonomy
- Hero = official Symbotic warehouse system render (SymMicro-specific PDP has no
  product-only still; rejected stock shopping photos and sibling SymBot fleet as
  primary when they would mislabel the SKU — system render depicts the Symbotic
  automation system SymMicro adapts for retail back-of-store)
- Fill description/features/purpose from OEM SymMicro page claims
- US manufacturer country; logistics-warehouse; Available FK 11
- status stays pending_review
"""
from __future__ import annotations

import argparse
import hashlib
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

COMPANY_ID = 1623
COMPANY_SLUG = "symbotic"
COMPANY_NAME = "Symbotic"
COMPANY_WEBSITE = "https://www.symbotic.com"
US = "US"
US_COUNTRY_ID = 20

URL = {
    "symmicro": f"{COMPANY_WEBSITE}/solutions/symmicro/",
    "robots": f"{COMPANY_WEBSITE}/solutions/robots/",
    "distribution": f"{COMPANY_WEBSITE}/solutions/distribution-solution/",
}

IMG = {
    # Official system render from Symbotic CDN (www host; Referer required).
    "symmicro": (
        f"{COMPANY_WEBSITE}/wp-content/uploads/2025/10/System-Render_0937_cc.jpg"
    ),
}

EXPECTED_MD5 = {
    "symmicro": "2159b0ff4507519a65e8e9fd33e25796",
}

TAGS = (
    "AMR|Warehouse Automation|Warehouse|Logistics|Autonomous|"
    "Industrial|Material Handling|Wheeled"
)

_AVAIL_IDS = {"available": 11, "announced": 10, "discontinued": 4}


def verify_hero(name: str, url: str) -> str:
    r = requests.get(
        url,
        timeout=45,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": COMPANY_WEBSITE + "/",
        },
    )
    r.raise_for_status()
    body = r.content
    if not body.startswith(b"\xff\xd8\xff"):
        raise RuntimeError(f"{name}: not JPEG magic={body[:8]!r} len={len(body)}")
    md5 = hashlib.md5(body).hexdigest()
    expected = EXPECTED_MD5.get(name, "")
    if expected and md5 != expected:
        raise RuntimeError(f"{name}: md5 {md5} != {expected}")
    return md5


def trigger_copy_media(robot_ids: list[int]) -> tuple[int, int]:
    secret = os.environ.get("INTERNAL_API_SECRET") or ""
    api = (os.environ.get("ADMIN_BASE") or "https://ragadmin.robotaigeek.com").rstrip("/")
    if not secret:
        print("WARN: no INTERNAL_API_SECRET for copy-media", file=sys.stderr)
        return 0, len(robot_ids)
    ok = fail = 0
    for rid in robot_ids:
        url = f"{api}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/"
        try:
            resp = requests.post(
                url, headers={"X-Internal-Secret": secret}, timeout=120
            )
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


ROBOT_FIXES: dict[int, dict[str, Any]] = {
    5686: {
        "name": "SymMicro",
        "model_name": "SymMicro",
        "variant_code": "SymMicro",
        "variant_label": "SymMicro",
        "url": URL["symmicro"],
        "family_key": "symbotic:symmicro",
        "family_name": "SymMicro",
        "family_url": URL["symmicro"],
        "product_url_scope": "family",
        "image": IMG["symmicro"],
        "description": (
            "SymMicro is Symbotic's micro-fulfillment solution that adapts the company's "
            "warehouse automation technology for retail back-of-store spaces. It turns "
            "local store inventory areas into digitized fulfillment cells so retailers "
            "can automate e-commerce pickup, clear aisles of picking trolleys, and "
            "support omnichannel shopping with near-touchless DC-to-consumer operations."
        ),
        "purpose": (
            "Retail back-of-store micro-fulfillment\n"
            "Automated e-commerce order picking and in-store pickup\n"
            "Digitized small-goods inventory management\n"
            "Omnichannel grocery and retail fulfillment"
        ),
        "features": (
            "OEM SymMicro page: 550 picks per hour per station; up to 5× productivity "
            "improvement vs manual travel-order picking; converts back-of-store space "
            "into inventory management and fulfillment; fully digitized inventory in a "
            "secured robotic system; reduces substitutes via accurate available stock; "
            "pairs with Symbotic distribution-center solutions for near-touchless "
            "DC-to-consumer flow; clears retail aisles of online-order trolleys and "
            "personnel; supports any inventory of small goods beyond grocery retail. "
            "No OEM-published payload/weight/dims for the SymMicro cell on the product "
            "page — typed columns left blank."
        ),
        "availability_status_key": "available",
        "movement_type_keys": "wheeled|mobile",
        "industry_keys": "retail|food-beverage|fmcg|logistics|industrial|commercial",
        "use_keys": "logistics|material-handling|warehousing|intralogistics",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "logistics-warehouse",
        "tags": TAGS,
        "manufacturer_country_code": US,
        "information_source_urls": [URL["symmicro"], URL["robots"], URL["distribution"]],
        "notes_force": (
            "[AI Research] Enriched from https://www.symbotic.com/solutions/symmicro/. "
            "Hero = System-Render_0937_cc.jpg (official Symbotic system overview). "
            "SymMicro PDP has no model-only product still — rejected iStock shopping "
            "photos. SymBot fleet photos belong to the SymBots product line "
            "(/solutions/robots/), not this SymMicro SKU. No OEM typed specs "
            "(payload/weight/dims) on SymMicro page. Claim '550 picks/hr/station' and "
            "'5× productivity' cited from OEM marketing copy only."
        ),
        "source_note": URL["symmicro"],
        "deployment_context": (
            "Retail and grocery back-of-store micro-fulfillment cells; pairs with "
            "Symbotic distribution-center automation for omnichannel supply chains."
        ),
        "programming_interface": (
            "Symbotic AI & software stack for digitized inventory, sequenced "
            "retrieval, and station-based picking (OEM does not publish a public "
            "programming SDK on the SymMicro page)."
        ),
        "ecosystem_compatibility": (
            "Designed to work with Symbotic distribution / DC solutions and SymBot "
            "robotic inventory automation."
        ),
    },
}


def build_row(fix: dict[str, Any], *, tags: str) -> dict[str, Any]:
    row: dict[str, Any] = {
        "company_slug": COMPANY_SLUG,
        "company_name": COMPANY_NAME,
        "source_locale": "en",
    }
    skip = {"videos", "notes_force", "source_note", "images", "availability_status_key"}
    for k, v in fix.items():
        if k in skip or v is None or v == "":
            continue
        row[k] = v
    row["tags"] = tags
    if fix.get("notes_force"):
        row["notes"] = fix["notes_force"]
    if fix.get("source_note"):
        row["research_notes"] = fix["source_note"]
    if fix.get("image"):
        row["images"] = [fix["image"]]
        row["image"] = fix["image"]
    row["availability_status_key"] = fix.get("availability_status_key") or "available"
    return row


def patch_typed(client: ResearchApiClient, rid: int, fix: dict[str, Any]) -> None:
    body: dict[str, Any] = {}
    for k in (
        "family_key",
        "family_name",
        "family_url",
        "model_name",
        "variant_code",
        "variant_label",
        "product_url_scope",
        "purpose",
        "deployment_context",
        "programming_interface",
        "ecosystem_compatibility",
    ):
        if fix.get(k) not in (None, ""):
            body[k] = fix[k]
    avail_key = fix.get("availability_status_key")
    if avail_key:
        body["availability_status"] = _AVAIL_IDS.get(str(avail_key), avail_key)
    ok_keys: list[str] = []
    for k, v in body.items():
        try:
            client._patch(f"robots/robots/{rid}/", {k: v})
            ok_keys.append(k)
        except Exception as exc:
            print(f"  patch fail {rid}.{k}: {exc}", file=sys.stderr)
    try:
        client._patch(
            f"robots/robots/{rid}/",
            {
                "manufacturer_countries": [US_COUNTRY_ID],
                "manufacturer_country_ref": US_COUNTRY_ID,
            },
        )
        ok_keys.append("manufacturer_countries")
    except Exception as exc:
        print(f"  patch fail {rid}.manufacturer_countries: {exc}", file=sys.stderr)
    if ok_keys:
        print(f"  patched typed {rid}: {ok_keys}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix Symbotic company 1623")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--copy-media", action="store_true")
    parser.add_argument("--verify-cdn", action="store_true")
    parser.add_argument("--mark-done", action="store_true")
    parser.add_argument("--skip-hero-check", action="store_true")
    parser.add_argument("--created-by-id", type=int, default=1)
    args = parser.parse_args()

    client = ResearchApiClient()
    catalog = TagCatalog.load(client=client)
    all_robots = {
        int(r["id"]): r
        for r in client.list_robots_for_company(COMPANY_ID)
        if str(r.get("status") or "").lower() == "pending_review"
    }

    if not args.skip_hero_check:
        print("Verifying OEM hero hashes…")
        for name, url in IMG.items():
            md5 = verify_hero(name, url)
            print(f"  OK {name} md5={md5}")

    targets: list[dict[str, Any]] = []
    for rid, fix in ROBOT_FIXES.items():
        robot = all_robots.get(rid)
        if not robot:
            print(f"SKIP {rid}: not pending_review / not found")
            continue
        tags = resolve_tags(catalog, str(fix.get("tags") or ""))
        row = build_row(fix, tags=tags)
        if len(row.get("features") or "") < 40 or not row.get("family_key") or not row.get("image"):
            print(f"ERROR {rid}: incomplete row", file=sys.stderr)
            return 1
        targets.append({"id": rid, "name": row["name"], "row": row, "fix": fix})
        print(f"  {rid} {row['name']}: fam={row.get('family_key')} url={row.get('url')}")

    preview = _RESEARCH_DIR / "staging" / "reports" / "symbotic-1623-fix-preview.json"
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_text(
        json.dumps(
            {"targets": [{"id": t["id"], "name": t["name"], "url": t["row"].get("url"),
                          "image": t["row"].get("image")} for t in targets]},
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
        print(f"Preview: {preview}. Re-run with --apply --copy-media --verify-cdn --mark-done")
        return 0

    imported: list[int] = []
    for t in targets:
        rid, row, fix = t["id"], t["row"], t["fix"]
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
        print(f"  bulk-import created={created} updated={result.get('updated_count')} err={err}")
        if created != 0 or err:
            print(f"ERROR {rid}: {result}", file=sys.stderr)
            return 1
        patch_typed(client, rid, fix)
        if fix.get("notes_force"):
            try:
                client._patch(f"robots/robots/{rid}/", {"notes": fix["notes_force"]})
            except Exception as exc:
                print(f"  notes fail {rid}: {exc}", file=sys.stderr)
        try:
            client._patch(
                f"robots/robots/{rid}/",
                {"status": "pending_review", "name": fix["name"]},
            )
        except Exception as exc:
            print(f"  status/name warn {rid}: {exc}", file=sys.stderr)
        imported.append(rid)

    if args.copy_media and imported:
        ok, fail = trigger_copy_media(imported)
        print(f"copy-media ok={ok} fail={fail}")
        for t in targets:
            if t["id"] in imported:
                patch_typed(client, t["id"], t["fix"])

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
