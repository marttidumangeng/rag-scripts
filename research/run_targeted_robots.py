"""One-off targeted re-enrich + import for a named subset of company robots."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from api_client import ResearchApiClient
from import_staging import (
    _import_batch_with_retry,
    load_json_robots,
    resolve_created_by_id,
    staging_robots_to_bulk_import_rows,
)
from robot_auto_research import (
    RESEARCH_DIR,
    RobotAutoResearcher,
    _merge_staged,
    _robot_api_to_staged,
    resolve_company_slug,
    robot_name_tokens,
)
from validate_staging import validate_robot, validate_robot_batch
from web_extract import score_image

TARGET_NAMES_DEFAULT = [
    "iER6-600-SR",
    "iER6-500-SR",
    "iER50-2700",
    "iER50-1200-SR",
    "iER420-3300",
    "iER350-3300",
    "iER350-3200",
    "iER35-1810",
    "iER30-2700",
    "iER3-500-SR",
    "iER3-400-SR",
    "iER280-3200",
    "iER270-3100-DW",
    "iER270-2700",
    "iER220-3100",
    "iER220-3100-DW",
    "iER220-2700",
    "iER220-2650",
    "iER20-850-SR-UNO",
    "iER20-800-SR-HI",
]


def enrich_robots(
    company_id: int,
    names: list[str],
    *,
    refresh_media: bool,
    refresh_website_url: bool,
) -> dict:
    client = ResearchApiClient()
    company = client.get_company(company_id)
    company_slug = resolve_company_slug(str(company.get("name") or ""), company.get("slug"))
    company_name = str(company.get("name") or "")
    website = str(company.get("website") or "")

    staged_company_path = RESEARCH_DIR / "staging" / "companies" / f"{company_slug}.json"
    manufacturer_cc = ""
    if staged_company_path.is_file():
        staged_co = json.loads(staged_company_path.read_text(encoding="utf-8"))
        website = staged_co.get("website") or website
        manufacturer_cc = staged_co.get("country_code") or ""

    name_set = {n.strip() for n in names if n.strip()}
    all_robots = client.list_robots_for_company(company_id)
    robots = [r for r in all_robots if r.get("name") in name_set]
    found = {r.get("name") for r in robots}
    missing = sorted(name_set - found)

    force_fields: set[str] = set()
    if refresh_media:
        force_fields.update({"image", "images", "video_urls"})
    if refresh_website_url:
        force_fields.add("url")

    researcher = RobotAutoResearcher()
    from evidence_store import EvidenceStore, sweep_company_evidence

    evidence = EvidenceStore(company_slug, pipeline="enrich")
    print(f"Evidence   : {evidence.relative_root}", flush=True)
    results: list[dict] = []
    errors: list[str] = []
    blocked_hero_urls: set[str] = set()

    for idx, robot in enumerate(robots, 1):
        rname = robot.get("name") or f"id={robot.get('id')}"
        print(f"  [{idx}/{len(robots)}] Researching: {rname} ...", flush=True)
        try:
            researched = researcher.research_robot(
                robot,
                company_slug=company_slug,
                company_name=company_name,
                company_website=website,
                manufacturer_country_code=manufacturer_cc,
                trust_stored_url="url" not in force_fields,
                blocked_hero_urls=blocked_hero_urls,
                evidence=evidence,
            )
            if researched is None:
                print(f"         skipped — target_not_found", flush=True)
                errors.append(f"target_not_found: {rname}")
                continue
            if researched.image and score_image(
                researched.image,
                robot_name_tokens(researched.name, researched.model_name),
            ) < 16:
                blocked_hero_urls.add(researched.image)
            base = _robot_api_to_staged(robot, company_slug, company_name)
            researched = _merge_staged(base, researched, force_fields=frozenset(force_fields))
            validation = validate_robot(researched)
            path = researcher.write_staging_file(researched, company_slug)
            print(
                f"         url={researched.url[:60] if researched.url else 'none'}",
                flush=True,
            )
            print(
                f"         image={'YES' if researched.image else 'none'} "
                f"+{len(researched.images)} gallery",
                flush=True,
            )
            results.append(
                {
                    "robot_id": robot.get("id"),
                    "name": researched.name,
                    "url": researched.url,
                    "image": researched.image,
                    "staging_file": str(path),
                    "validation_ok": validation.ok,
                }
            )
        except Exception as exc:
            print(f"         ERROR: {exc}", flush=True)
            errors.append(f"{rname}: {exc}")

    evidence.finish(
        company_id=company_id,
        robots_researched=len(results),
        errors=len(errors),
    )
    sweep = sweep_company_evidence(company_slug)
    print(f"Evidence saved → {evidence.relative_root}", flush=True)

    return {
        "ok": not errors,
        "company_id": company_id,
        "company_slug": company_slug,
        "requested": len(name_set),
        "matched": len(robots),
        "missing_names": missing,
        "results": results,
        "errors": errors,
        "evidence_dir": evidence.relative_root,
        "evidence_run_id": evidence.run_id,
        "evidence_sweep": sweep,
    }


def import_robots(
    company_slug: str,
    names: list[str],
    *,
    created_by_id: int | None,
    batch_size: int,
) -> dict:
    client = ResearchApiClient()
    created_by_id = resolve_created_by_id(created_by_id)
    staging_dir = RESEARCH_DIR / "staging" / "robots" / company_slug
    name_set = {n.strip() for n in names if n.strip()}

    records = []
    used_files: list[str] = []
    for fpath in sorted(staging_dir.glob("*.json")):
        for rec in load_json_robots(fpath):
            if rec.get("name") in name_set:
                records.append(rec)
                used_files.append(str(fpath.name))

    if not records:
        return {"ok": False, "errors": ["No staging records matched target names"]}

    validation = validate_robot_batch(records)
    if not validation.ok:
        return {
            "ok": False,
            "errors": [f"{i.field}: {i.message}" for i in validation.errors()],
        }

    rows = staging_robots_to_bulk_import_rows(records)
    totals = {"created_count": 0, "updated_count": 0, "skipped_count": 0, "error_count": 0}
    all_results: list[dict] = []

    for start in range(0, len(rows), batch_size):
        batch = rows[start : start + batch_size]
        data = _import_batch_with_retry(
            client,
            batch,
            patch=True,
            status="pending_review",
            skip_company_update=True,
            created_by_id=created_by_id,
            replace_media=True,
        )
        for key in totals:
            totals[key] += data.get(key, 0)
        all_results.extend(data.get("results", []))

    return {
        "ok": totals["error_count"] == 0,
        "files": sorted(set(used_files)),
        "robot_count": len(rows),
        **totals,
        "results": all_results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Targeted robot re-enrich + import")
    parser.add_argument("--company-id", type=int, required=True)
    parser.add_argument("--created-by-id", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=5)
    parser.add_argument("--names", nargs="*", default=TARGET_NAMES_DEFAULT)
    parser.add_argument("--enrich-only", action="store_true")
    parser.add_argument("--import-only", action="store_true")
    parser.add_argument("--no-refresh-media", action="store_true")
    parser.add_argument("--no-refresh-website-url", action="store_true")
    args = parser.parse_args()

    refresh_media = not args.no_refresh_media
    refresh_website_url = not args.no_refresh_website_url
    company_slug = ""

    if not args.import_only:
        enrich = enrich_robots(
            args.company_id,
            args.names,
            refresh_media=refresh_media,
            refresh_website_url=refresh_website_url,
        )
        print(json.dumps(enrich, indent=2))
        if not enrich.get("ok"):
            return 1
        company_slug = enrich["company_slug"]
        if enrich.get("missing_names"):
            print("WARNING: names not found in DB:", enrich["missing_names"], file=sys.stderr)

    if not args.enrich_only:
        if not company_slug:
            client = ResearchApiClient()
            company = client.get_company(args.company_id)
            company_slug = resolve_company_slug(str(company.get("name") or ""), company.get("slug"))
        imp = import_robots(
            company_slug,
            args.names,
            created_by_id=args.created_by_id,
            batch_size=args.batch_size,
        )
        print(json.dumps(imp, indent=2))
        if not imp.get("ok"):
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
