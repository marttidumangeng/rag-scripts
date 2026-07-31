"""Create Israel Aerospace Industries company; reassign + enrich Palladyne IAI SKUs.

Robots moved from Palladyne AI (1621):
  5675 Mini Harpy, 5672 HARPY, 5671 HAROP

Sources: https://www.iai.co.il/p/{mini-harpy,harpy,harop} (+ official brochures).
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
from web_extract import WebFetcher, parse_page

COMPANY_NAME = "Israel Aerospace Industries (IAI)"
COMPANY_SLUG = "israel-aerospace-industries"
COMPANY_WEBSITE = "https://www.iai.co.il"
IL_COUNTRY_ID = 9
PALLADYNE_ID = 1621

ROBOT_IDS = (5675, 5672, 5671)

URL = {
    "mini_harpy": f"{COMPANY_WEBSITE}/p/mini-harpy",
    "harpy": f"{COMPANY_WEBSITE}/p/harpy",
    "harop": f"{COMPANY_WEBSITE}/p/harop",
    "mini_brochure": f"{COMPANY_WEBSITE}/wp-content/uploads/2025/10/MSL-Mini-HARPY-Brochure.pdf",
    "harpy_brochure": f"{COMPANY_WEBSITE}/wp-content/uploads/2025/10/MSL-HARPY-NG-Brochure.pdf",
    "harop_brochure": f"{COMPANY_WEBSITE}/wp-content/uploads/2025/10/MSL-HAROP-Brochure.pdf",
}

# Palladyne-hosted product stills (OEM partnership pages) used only if IAI gallery
# yields no usable hero — still depict IAI airframes, not Palladyne branding art.
FALLBACK_IMG = {
    "mini_harpy": "https://www.palladyneai.com/wp-content/uploads/2026/06/MINI_HARPY_02-1.png",
    "harpy": "https://www.palladyneai.com/wp-content/uploads/2026/06/HARPY_02-2.png",
    "harop": "https://www.palladyneai.com/wp-content/uploads/2026/06/HAROP_03-1.png",
}

TAGS = "UAV|Drone|Aerial|Autonomous|Defense|Autonomous Flight|Military"
_AVAIL_IDS = {"available": 11, "announced": 10, "discontinued": 4}


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


def find_or_create_iai(client: ResearchApiClient) -> dict[str, Any]:
    for q in ("Israel Aerospace Industries", "IAI", COMPANY_NAME):
        hits = client.search_companies(q, page_size=20)
        for h in hits:
            name = (h.get("name") or "").lower()
            website = (h.get("website") or "").lower()
            if "israel aerospace" in name or "iai.co.il" in website:
                print(f"Found existing IAI company id={h['id']} name={h.get('name')}")
                return client._get(f"companies/{h['id']}/")
            if name.strip() in {"iai", "i.a.i."}:
                print(f"Found existing IAI company id={h['id']} name={h.get('name')}")
                return client._get(f"companies/{h['id']}/")
    print("Creating Israel Aerospace Industries (IAI)…")
    created = client.create_company(
        {
            "name": COMPANY_NAME,
            "slug": COMPANY_SLUG,
            "website": COMPANY_WEBSITE,
            "country_id": IL_COUNTRY_ID,
            "description": (
                "Israel Aerospace Industries (IAI) is Israel's major aerospace and "
                "defense company. Its Systems, Missiles & Space Group develops "
                "loitering munitions including HARPY, HAROP, and Mini HARPY."
            ),
            "source_locale": "en",
        }
    )
    print(f"Created company id={created.get('id')} slug={created.get('slug')}")
    return created


def pick_iai_hero(page_url: str, fallback: str) -> tuple[str, str]:
    """Return (image_url, note). Prefer iai.co.il gallery assets."""
    try:
        p = parse_page(WebFetcher(), page_url, rendered=False)
    except Exception as exc:
        print(f"WARN fetch {page_url}: {exc}", file=sys.stderr)
        return fallback, "fallback Palladyne-hosted IAI product still (IAI page scrape failed)"
    candidates: list[str] = []
    for img in p.images or []:
        u = img.get("url") if isinstance(img, dict) else str(img)
        if not u:
            continue
        ul = u.lower()
        if any(x in ul for x in ("logo", "icon", "favicon", "sprite", "arrow", "flag")):
            continue
        if "iai.co.il" in ul or "wp-content" in ul:
            candidates.append(u.split("?")[0])
    # Prefer larger product-looking paths
    scored = sorted(
        set(candidates),
        key=lambda u: (
            0 if any(t in u.lower() for t in ("harpy", "harop", "mini")) else 1,
            0 if u.lower().endswith((".png", ".jpg", ".jpeg", ".webp")) else 1,
            -len(u),
        ),
    )
    for u in scored[:8]:
        try:
            r = requests.get(
                u,
                timeout=45,
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Referer": COMPANY_WEBSITE + "/",
                },
            )
            if r.status_code != 200:
                continue
            body = r.content
            if not (
                body.startswith(b"\xff\xd8\xff")
                or body.startswith(b"\x89PNG")
                or (body[:4] == b"RIFF" and body[8:12] == b"WEBP")
            ):
                continue
            if len(body) < 20_000:
                continue
            md5 = hashlib.md5(body).hexdigest()
            print(f"  IAI hero candidate OK {u[:90]} md5={md5[:12]} bytes={len(body)}")
            return u, f"IAI gallery {u}"
        except Exception as exc:
            print(f"  skip {u[:80]}: {exc}", file=sys.stderr)
    # Validate fallback
    r = requests.get(
        fallback,
        timeout=45,
        headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.palladyneai.com/"},
    )
    r.raise_for_status()
    md5 = hashlib.md5(r.content).hexdigest()
    print(f"  Using fallback hero md5={md5[:12]} bytes={len(r.content)}")
    return fallback, "Palladyne-hosted IAI product still (IAI gallery empty/blocked)"


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
        time.sleep(0.2)
    return ok, fail


def build_fixes(heroes: dict[str, tuple[str, str]]) -> dict[int, dict[str, Any]]:
    mini_img, mini_note = heroes["mini_harpy"]
    harpy_img, harpy_note = heroes["harpy"]
    harop_img, harop_note = heroes["harop"]
    return {
        5675: {
            "name": "Mini HARPY",
            "model_name": "Mini HARPY",
            "variant_code": "Mini HARPY",
            "variant_label": "Mini HARPY",
            "url": URL["mini_harpy"],
            "family_key": "israel-aerospace-industries:mini-harpy",
            "family_name": "Mini HARPY",
            "family_url": URL["mini_harpy"],
            "product_url_scope": "exact_variant",
            "image": mini_img,
            "description": (
                "Mini HARPY is Israel Aerospace Industries' tactical loitering munition "
                "with a dual EO/IR and anti-radiation seeker for all-weather strike. "
                "Canister-launched from land or naval platforms, it can operate "
                "fully autonomously or with man-in-the-loop control against emitting "
                "and non-emitting targets."
            ),
            "purpose": (
                "Tactical loitering munition strike\n"
                "Suppression / destruction of enemy air defenses\n"
                "All-weather dual EO/IR and anti-radiation seek\n"
                "Land and naval canister-launched tactical fires"
            ),
            "features": (
                "OEM IAI Mini HARPY page (iai.co.il/p/mini-harpy): weight 50 kg; "
                "endurance ≥80 minutes; warhead 7 kg; operational range 100 km; "
                "dual EO/IR + anti-radiation seeker; canister launch (ground/naval); "
                "MITL or fully autonomous; abort/re-attack; shallow-to-vertical attack "
                "angles; battle damage assessment; electric propulsion (silent). "
                "World's only LM with dual EO/IR and AR seeker per IAI claim."
            ),
            "weight_kg": 50.0,
            "runtime_minutes": 80,
            "availability_status_key": "available",
            "movement_type_keys": "aerial|flying",
            "industry_keys": "defense|defence|military",
            "use_keys": "surveillance|reconnaissance",
            "category_slugs": "service-robots",
            "sub_category_slug": "military",
            "tags": TAGS,
            "manufacturer_country_code": "IL",
            "information_source_urls": [URL["mini_harpy"], URL["mini_brochure"]],
            "notes_force": (
                "[AI Research] Reassigned from Palladyne AI (1621) → IAI — product is "
                "IAI-made; Palladyne only listed it under IAI Partnership. Primary URL "
                f"set to {URL['mini_harpy']}. Hero: {mini_note}. Specs from IAI "
                "Technical Details table (50 kg / 80 min / 7 kg warhead / 100 km)."
            ),
            "source_note": URL["mini_harpy"],
            "deployment_context": (
                "Land and sea canister launch for tactical SEAD/DEAD and strike."
            ),
        },
        5672: {
            "name": "HARPY",
            "model_name": "HARPY",
            "variant_code": "HARPY",
            "variant_label": "HARPY",
            "url": URL["harpy"],
            "family_key": "israel-aerospace-industries:harpy",
            "family_name": "HARPY",
            "family_url": URL["harpy"],
            "product_url_scope": "exact_variant",
            "image": harpy_img,
            "description": (
                "HARPY is Israel Aerospace Industries' anti-radiation loitering "
                "munition for suppression and destruction of enemy air defenses "
                "(SEAD/DEAD). Combining UAV and missile characteristics, it can be "
                "launched without prior target coordinates and autonomously detect "
                "and strike radiating air-defense emitters."
            ),
            "purpose": (
                "Anti-radiation loitering munition (SEAD/DEAD)\n"
                "Suppression and destruction of enemy air defenses\n"
                "Autonomous emitter seek and strike\n"
                "Land and naval canister-launched deep strike"
            ),
            "features": (
                "OEM IAI HARPY page (iai.co.il/p/harpy): world's first / most "
                "operational anti-radiation loitering munition per IAI; fully "
                "autonomous; SEAD and DEAD missions; land/naval based; operational "
                "with several air forces; launched from ground or naval canisters "
                "for long-range safe-corridor creation; anti-radiation seeker with "
                "wide RF coverage; vertical strike angle capability. Extended "
                "endurance cited on partner materials (~9 hours) — not restated as "
                "a typed column without IAI brochure numeric confirmation in this "
                "pass. No public weight/payload on the HTML overview — left blank."
            ),
            "availability_status_key": "available",
            "movement_type_keys": "aerial|flying",
            "industry_keys": "defense|defence|military",
            "use_keys": "surveillance|reconnaissance",
            "category_slugs": "service-robots",
            "sub_category_slug": "military",
            "tags": TAGS,
            "manufacturer_country_code": "IL",
            "information_source_urls": [URL["harpy"], URL["harpy_brochure"]],
            "notes_force": (
                "[AI Research] Reassigned from Palladyne AI (1621) → IAI. Primary URL "
                f"{URL['harpy']}. Hero: {harpy_note}. Did not invent weight/range; "
                "brochure PDF available for a follow-up typed-spec pass."
            ),
            "source_note": URL["harpy"],
            "deployment_context": (
                "Ground-based or naval canister launch for SEAD/DEAD against A2AD."
            ),
        },
        5671: {
            "name": "HAROP",
            "model_name": "HAROP",
            "variant_code": "HAROP",
            "variant_label": "HAROP",
            "url": URL["harop"],
            "family_key": "israel-aerospace-industries:harop",
            "family_name": "HAROP",
            "family_url": URL["harop"],
            "product_url_scope": "exact_variant",
            "image": harop_img,
            "description": (
                "HAROP is Israel Aerospace Industries' long-range loitering munition "
                "that combines UAV and missile characteristics to hunt high-value "
                "targets — unmanned surface vessels, command posts, supply depots, "
                "tanks, and air-defense systems — with man-in-the-loop control and "
                "abort capability."
            ),
            "purpose": (
                "Long-range loitering munition strike\n"
                "High-value target hunt (land and naval)\n"
                "Man-in-the-loop precision attack with abort\n"
                "Standoff ISR-to-strike in one platform"
            ),
            "features": (
                "OEM IAI HAROP page (iai.co.il/p/harop): combat-proven standoff "
                "loitering attack weapon; canister launch; survey-and-strike; "
                "situational awareness and weapon in one package; EO seeker enables "
                "seek without prior intelligence; 9-hour endurance to locate, "
                "identify, plan attack route, and strike from shallow or steep dive; "
                "GNSS-jamming immunity; human-in-the-loop supervision with abort; "
                "truck or naval canister deployment. Typed runtime_minutes=540 from "
                "OEM '9-hour endurance' claim. No public weight on HTML overview."
            ),
            "runtime_minutes": 540,
            "availability_status_key": "available",
            "movement_type_keys": "aerial|flying",
            "industry_keys": "defense|defence|military",
            "use_keys": "surveillance|reconnaissance",
            "category_slugs": "service-robots",
            "sub_category_slug": "military",
            "tags": TAGS,
            "manufacturer_country_code": "IL",
            "information_source_urls": [URL["harop"], URL["harop_brochure"]],
            "notes_force": (
                "[AI Research] Reassigned from Palladyne AI (1621) → IAI. Primary URL "
                f"{URL['harop']}. Hero: {harop_note}. runtime_minutes=540 from OEM "
                "9-hour endurance statement."
            ),
            "source_note": URL["harop"],
            "deployment_context": (
                "Canisters on trucks or naval vessels; land and naval missions."
            ),
            "programming_interface": (
                "Remote human-in-the-loop mission control with abort capability "
                "(OEM HAROP overview)."
            ),
        },
    }


def build_row(
    fix: dict[str, Any],
    *,
    tags: str,
    company_slug: str,
    company_name: str,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "company_slug": company_slug,
        "company_name": company_name,
        "source_locale": "en",
    }
    skip = {"notes_force", "source_note", "images", "availability_status_key", "videos"}
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


def reassign(client: ResearchApiClient, rid: int, company_id: int) -> None:
    before = client._get(f"robots/robots/{rid}/")
    old = before.get("company_ref")
    old_id = old.get("id") if isinstance(old, dict) else old
    print(f"Reassign {rid}: company {old_id} -> {company_id} (sole owner)")
    client._patch(
        f"robots/robots/{rid}/",
        {"company_ref": company_id, "company_owner_ids": [company_id]},
    )
    after = client._get(f"robots/robots/{rid}/")
    new = after.get("company_ref")
    new_id = new.get("id") if isinstance(new, dict) else new
    owners = after.get("company_owner_ids") or after.get("company_owners")
    print(f"  after company_ref={new_id} owners={owners} name={after.get('name')}")
    if new_id != company_id:
        raise RuntimeError(f"reassign failed for {rid}: still company {new_id}")


def patch_typed(client: ResearchApiClient, rid: int, fix: dict[str, Any]) -> None:
    body: dict[str, Any] = {}
    for k in (
        "weight_kg",
        "runtime_minutes",
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
    ):
        if fix.get(k) not in (None, ""):
            body[k] = fix[k]
    avail = fix.get("availability_status_key")
    if avail:
        body["availability_status"] = _AVAIL_IDS.get(str(avail), avail)
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
            {
                "manufacturer_countries": [IL_COUNTRY_ID],
                "manufacturer_country_ref": IL_COUNTRY_ID,
            },
        )
        ok.append("manufacturer_countries")
    except Exception as exc:
        print(f"  patch fail {rid}.manufacturer_countries: {exc}", file=sys.stderr)
    if ok:
        print(f"  patched typed {rid}: {ok}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--copy-media", action="store_true")
    parser.add_argument("--verify-cdn", action="store_true")
    parser.add_argument("--mark-done-palladyne", action="store_true")
    parser.add_argument("--created-by-id", type=int, default=1)
    args = parser.parse_args()

    client = ResearchApiClient()
    catalog = TagCatalog.load(client=client)

    print("Selecting heroes…")
    heroes = {
        "mini_harpy": pick_iai_hero(URL["mini_harpy"], FALLBACK_IMG["mini_harpy"]),
        "harpy": pick_iai_hero(URL["harpy"], FALLBACK_IMG["harpy"]),
        "harop": pick_iai_hero(URL["harop"], FALLBACK_IMG["harop"]),
    }
    fixes = build_fixes(heroes)

    iai = find_or_create_iai(client) if args.apply else {"id": None, "slug": COMPANY_SLUG, "name": COMPANY_NAME}
    company_id = int(iai["id"]) if iai.get("id") else None
    company_slug = iai.get("slug") or COMPANY_SLUG
    company_name = iai.get("name") or COMPANY_NAME

    targets = []
    for rid, fix in fixes.items():
        tags = resolve_tags(catalog, str(fix.get("tags") or ""))
        row = build_row(fix, tags=tags, company_slug=company_slug, company_name=company_name)
        if len(row.get("features") or "") < 40 or not row.get("family_key") or not row.get("image"):
            print(f"ERROR incomplete {rid}", file=sys.stderr)
            return 1
        targets.append({"id": rid, "fix": fix, "row": row})
        print(f"  {rid} {fix['name']}: url={fix['url']} img={fix['image'][:70]}")

    preview = _RESEARCH_DIR / "staging" / "reports" / "iai-reassign-palladyne-preview.json"
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_text(
        json.dumps(
            {
                "company": {"id": company_id, "slug": company_slug, "name": company_name},
                "targets": [
                    {"id": t["id"], "name": t["fix"]["name"], "url": t["fix"]["url"], "image": t["fix"]["image"]}
                    for t in targets
                ],
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    if not args.apply:
        print(f"Preview: {preview}. Re-run with --apply --copy-media --verify-cdn --mark-done-palladyne")
        return 0

    assert company_id is not None

    # 1) Reassign first
    for t in targets:
        reassign(client, t["id"], company_id)

    # 2) Re-read and import under NEW company (rule 17)
    imported: list[int] = []
    for t in targets:
        rid = t["id"]
        after = client._get(f"robots/robots/{rid}/")
        cref = after.get("company_ref") or {}
        if (cref.get("id") if isinstance(cref, dict) else cref) != company_id:
            print(f"ERROR {rid} not on IAI after reassign", file=sys.stderr)
            return 1
        # Rebuild row with confirmed company name from API
        cname = cref.get("name") if isinstance(cref, dict) else company_name
        cslug = (cref.get("slug") if isinstance(cref, dict) else None) or company_slug
        tags = resolve_tags(catalog, str(t["fix"].get("tags") or ""))
        row = build_row(t["fix"], tags=tags, company_slug=cslug, company_name=cname)
        bulk = staging_dict_to_bulk_import_row(row)
        bulk["id"] = rid
        bulk["name"] = t["fix"]["name"]
        bulk["status"] = "pending_review"
        print(f"Importing {rid} {t['fix']['name']} under {cname}…", flush=True)
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
        if created != 0:
            print(f"ERROR {rid}: unexpected create {result}", file=sys.stderr)
            return 1
        if err:
            print(f"ERROR {rid}: import errors {result}", file=sys.stderr)
            return 1
        patch_typed(client, rid, t["fix"])
        if t["fix"].get("notes_force"):
            try:
                client._patch(f"robots/robots/{rid}/", {"notes": t["fix"]["notes_force"]})
            except Exception as exc:
                print(f"  notes fail {rid}: {exc}", file=sys.stderr)
        try:
            client._patch(
                f"robots/robots/{rid}/",
                {
                    "status": "pending_review",
                    "name": t["fix"]["name"],
                    "company_ref": company_id,
                    "company_owner_ids": [company_id],
                },
            )
        except Exception as exc:
            print(f"  final patch warn {rid}: {exc}", file=sys.stderr)
        imported.append(rid)

    if args.copy_media and imported:
        ok, fail = trigger_copy_media(imported)
        print(f"copy-media ok={ok} fail={fail}")
        for t in targets:
            if t["id"] in imported:
                patch_typed(client, t["id"], t["fix"])

    if args.verify_cdn and imported:
        subprocess.check_call(
            [
                sys.executable,
                str(_RESEARCH_DIR / "verify_cdn_images.py"),
                "--company-id",
                str(company_id),
            ],
            cwd=str(_RESEARCH_DIR),
        )

    if args.mark_done_palladyne:
        # Palladyne own products were enriched earlier; IAI SKUs now moved off.
        remaining = [
            r
            for r in client.list_robots_for_company(PALLADYNE_ID)
            if str(r.get("status") or "").lower() == "pending_review"
        ]
        print(f"Palladyne pending_review remaining: {len(remaining)}")
        subprocess.check_call(
            [
                sys.executable,
                str(_RESEARCH_DIR / "triage_content_queue.py"),
                "--mark-done",
                str(PALLADYNE_ID),
            ],
            cwd=str(_RESEARCH_DIR),
        )
        subprocess.check_call(
            [
                sys.executable,
                str(_RESEARCH_DIR / "triage_content_queue.py"),
                "--mark-done",
                str(company_id),
            ],
            cwd=str(_RESEARCH_DIR),
        )

    print(
        json.dumps(
            {
                "iai_company_id": company_id,
                "imported": imported,
                "preview": str(preview),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
