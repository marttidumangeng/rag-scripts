"""Apply en.estun.com catalog URLs/images to all Estun staging robots (no Gemini)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from load_env import load_research_env  # noqa: E402

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient  # noqa: E402
from estun_english_catalog import (  # noqa: E402
    ESTUN_ENGLISH_LIST_URLS,
    derive_estun_family_metadata,
    lookup_estun_english_entry,
)
from import_staging import import_staging, resolve_created_by_id  # noqa: E402
from robot_auto_research import resolve_company_slug, slugify_robot_name  # noqa: E402

RESEARCH_DIR = _RESEARCH_DIR
COMPANY_ID = 220


def apply_catalog_to_staging(company_id: int = COMPANY_ID) -> dict:
    client = ResearchApiClient()
    company = client.get_company(company_id)
    slug = resolve_company_slug(str(company.get("name") or ""), company.get("slug"))
    staging_dir = RESEARCH_DIR / "staging" / "robots" / slug
    robots = client.list_robots_for_company(company_id)

    matched = 0
    missed: list[str] = []
    updated_files: list[str] = []

    for robot in robots:
        name = robot.get("name") or ""
        entry = lookup_estun_english_entry(name, robot.get("model_name") or name)
        family = derive_estun_family_metadata(name)
        if entry:
            # Prefer family from matched catalog name + list key
            family = derive_estun_family_metadata(
                name,
                list_key=str(entry.get("list_key") or ""),
            )
            # Overlay catalog-enriched family when present
            for k in ("family_key", "family_name", "variant_code", "product_url_scope"):
                if entry.get(k):
                    family[k] = entry[k]
        else:
            missed.append(name)

        fname = staging_dir / f"{slugify_robot_name(name)}.json"
        # Prefer live DB fields so validation/patch keep existing description/url.
        data: dict = {
            "name": name,
            "company_slug": slug,
            "company_name": company.get("name") or "Estun Robotics",
            "model_name": robot.get("model_name") or name,
            "description": (robot.get("description") or "").strip()
            or f"Estun industrial robot model {name}.",
            "purpose": (robot.get("purpose") or "").strip(),
            "url": (robot.get("url") or "").strip(),
        }
        if robot.get("id") is not None:
            data["id"] = robot["id"]

        data.update(family)
        data["family_url"] = ""

        source_url = ""
        if entry:
            data["url"] = entry["url"]
            hero = entry.get("image") or ""
            data["image"] = hero
            candidate = entry.get("image_candidate")
            if isinstance(candidate, dict) and candidate.get("url"):
                data["images"] = [candidate]
            else:
                data["images"] = [hero] if hero else []
            source_url = entry["url"]
            data["research_notes"] = (
                "Auto-researched from Estun English catalog list pages: "
                + ", ".join(ESTUN_ENGLISH_LIST_URLS)
                + f". Catalog model: {entry.get('name', name)}. "
                + f"Family key: {family.get('family_key', '')}."
            )
            matched += 1
        else:
            source_url = data["url"] or (company.get("website") or "https://en.estun.com/")
            data["research_notes"] = (
                f"Family metadata derived from name ({family.get('family_key', '')}). "
                "No English catalog match for hero image."
            ).strip()

        data["sources"] = [{"url": source_url, "type": "website"}]

        fname.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        updated_files.append(fname.name)

    return {
        "ok": True,
        "company_id": company_id,
        "company_slug": slug,
        "matched": matched,
        "missed": missed,
        "updated_files": sorted(set(updated_files)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply Estun English catalog to staging + import")
    parser.add_argument("--company-id", type=int, default=COMPANY_ID)
    parser.add_argument("--local", action="store_true", help="Target local dev API (*_LOCAL env vars)")
    parser.add_argument("--apply-import", action="store_true")
    parser.add_argument(
        "--force-overwrite",
        action="store_true",
        help="Use full update (not patch) so url/image/sources replace bad prod values",
    )
    parser.add_argument(
        "--replace-media",
        action="store_true",
        help="Wipe existing photos (escape hatch). Default: Phase-1 non-destructive upsert.",
    )
    parser.add_argument(
        "--family-only",
        action="store_true",
        help="Import even when catalog match is 0 (family metadata for all staged files).",
    )
    parser.add_argument("--created-by-id", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=5)
    args = parser.parse_args()

    # Ensure catalog rebuild picks up stealth fetcher after code edits.
    from estun_english_catalog import build_estun_english_catalog

    build_estun_english_catalog.cache_clear()

    result = apply_catalog_to_staging(args.company_id)
    print(json.dumps({k: v for k, v in result.items() if k != "updated_files"}, indent=2))
    if result.get("missed"):
        print("missed:", ", ".join(result["missed"]).encode("utf-8", "replace").decode("utf-8"))

    should_import = args.apply_import and (
        result.get("matched", 0) > 0 or args.family_only
    )
    if should_import:
        slug = result["company_slug"]
        imp = import_staging(
            RESEARCH_DIR / "staging" / "robots" / slug,
            patch=not args.force_overwrite,
            force_overwrite=args.force_overwrite,
            status="pending_review",
            dry_run=False,
            created_by_id=resolve_created_by_id(args.created_by_id),
            replace_media=bool(args.replace_media),
            batch_size=args.batch_size,
            skip_company_update=True,
        )
        print(json.dumps(imp, indent=2))
        if not imp.get("ok"):
            return 1
        if args.local:
            _copy_media_local(slug)
    return 0


def _copy_media_local(company_slug: str) -> None:
    """After local import, mirror external URLs to /media/ so admin avoids hotlink proxies."""
    import os
    import sys

    server_dir = RESEARCH_DIR.parents[1] / "robotaigeek-server"
    if str(server_dir) not in sys.path:
        sys.path.insert(0, str(server_dir))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
    import django

    django.setup()
    from common.models import Company
    from robots.background import copy_media_for_robot
    from robots.models import Robot

    company = Company.objects.filter(slug=company_slug).first()
    if not company:
        print(f"local copy-media: company not found ({company_slug})", flush=True)
        return
    ok = fail = 0
    for robot in Robot.objects.filter(company_ref=company).order_by("id"):
        if copy_media_for_robot(robot.id):
            ok += 1
        else:
            fail += 1
    print(f"local copy-media: ok={ok} fail={fail}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
