"""Greenfield workflow: discover new companies and dedupe robot catalogs."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from api_client import ResearchApiClient
from schema import StagedRobot

RESEARCH_DIR = Path(__file__).resolve().parent
SEEDS_FILE = RESEARCH_DIR / "seeds" / "companies.txt"
STAGING_ROBOTS = RESEARCH_DIR / "staging" / "robots"


def load_seed_companies(seeds_file: Path | None = None) -> list[str]:
    path = seeds_file or SEEDS_FILE
    if not path.exists():
        return []
    names: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            # Allow trailing inline comments: "Fanuc  # id=189"
            name = line.split("#", 1)[0].strip()
            if name:
                names.append(name)
    return names


def normalize_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def find_existing_company(
    name: str,
    client: ResearchApiClient | None = None,
) -> dict[str, Any] | None:
    client = client or ResearchApiClient()
    target = normalize_name(name)
    for hit in client.search_companies(name):
        if normalize_name(hit.get("name", "")) == target:
            return hit
    for existing in client.get_company_names():
        if normalize_name(existing) == target:
            results = client.search_companies(existing, page_size=1)
            if results:
                return results[0]
    return None


def list_existing_robot_names(company_id: int, client: ResearchApiClient | None = None) -> set[str]:
    client = client or ResearchApiClient()
    names: set[str] = set()
    for robot in client.list_robots_for_company(company_id):
        for field in ("name", "model_name"):
            val = robot.get(field)
            if val:
                names.add(normalize_name(str(val)))
    return names


def dedupe_staged_robots(
    staged_records: list[dict[str, Any]],
    company_id: int | None = None,
    client: ResearchApiClient | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Split staged robots into new vs skipped (already in DB).
    Returns (to_import, skipped).
    """
    client = client or ResearchApiClient()
    existing: set[str] = set()
    if company_id is not None:
        existing = list_existing_robot_names(company_id, client)

    to_import: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for record in staged_records:
        robot = StagedRobot.from_dict(record)
        keys = {normalize_name(robot.name)}
        if robot.model_name:
            keys.add(normalize_name(robot.model_name))
        if existing & keys:
            skipped.append({**record, "_skip_reason": "already_in_db"})
        else:
            to_import.append(record)

    return to_import, skipped


def load_staging_dir(company_slug: str) -> list[dict[str, Any]]:
    robot_dir = STAGING_ROBOTS / company_slug
    if not robot_dir.is_dir():
        return []
    records: list[dict[str, Any]] = []
    for path in sorted(robot_dir.glob("*.json")):
        records.append(json.loads(path.read_text(encoding="utf-8")))
    return records


def greenfield_dedupe_report(
    company_name: str,
    client: ResearchApiClient | None = None,
) -> dict[str, Any]:
    """Produce dedupe summary for a company before greenfield import."""
    client = client or ResearchApiClient()
    existing_company = find_existing_company(company_name, client)
    company_id = existing_company.get("id") if existing_company else None
    slug = (existing_company or {}).get("slug") or re.sub(
        r"[^a-z0-9]+", "-", company_name.lower()
    ).strip("-")

    staged = load_staging_dir(slug)
    to_import, skipped = dedupe_staged_robots(staged, company_id, client)

    return {
        "company_name": company_name,
        "company_exists": existing_company is not None,
        "company_id": company_id,
        "company_slug": slug,
        "staged_count": len(staged),
        "to_import_count": len(to_import),
        "skipped_count": len(skipped),
        "existing_robot_count": len(list_existing_robot_names(company_id, client)) if company_id else 0,
        "to_import": [r.get("name") for r in to_import],
        "skipped": [{"name": r.get("name"), "reason": r.get("_skip_reason")} for r in skipped],
    }
