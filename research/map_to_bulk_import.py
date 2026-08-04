"""Map staging JSON records to bulk-import API row dicts."""

from __future__ import annotations

import re
from typing import Any

from schema import ImageCandidate, StagedRobot, normalize_image_candidates

AI_RESEARCH_PREFIX = "[AI Research]"


def _s(val: Any) -> str:
    if val is None:
        return ""
    s = str(val).strip()
    return "" if s.lower() in ("nan", "none") else s


def _join_sources(robot: StagedRobot) -> str:
    return "|".join(s.url for s in robot.sources if s.url)


def _strip_prefix(text: str) -> str:
    """Drop a leading '[AI Research]' the writer already added.

    This function re-adds the prefix below, so a staging writer that spells it
    out itself produced "[AI Research] [AI Research] Ingested from ...". Three
    writers do (including manufacturer_gap_discovery, the broad workflow), so
    the fix belongs here rather than in each of them.
    """
    stripped = text.lstrip()
    if stripped.startswith(AI_RESEARCH_PREFIX):
        return stripped[len(AI_RESEARCH_PREFIX):].lstrip()
    return text


def _build_notes(robot: StagedRobot) -> str:
    parts: list[str] = []
    if robot.notes:
        parts.append(_strip_prefix(robot.notes))
    if robot.research_notes:
        parts.append(_strip_prefix(robot.research_notes))
    source_urls = _join_sources(robot)
    if source_urls:
        parts.append(f"Sources: {source_urls.replace('|', ' | ')}")
    low_conf = [k for k, v in robot.confidence.items() if v == "low"]
    if low_conf:
        parts.append(f"Low confidence fields: {', '.join(low_conf)}")
    body = " | ".join(p for p in parts if p)
    if body:
        return f"{AI_RESEARCH_PREFIX} {body}"
    return AI_RESEARCH_PREFIX


def _list_to_pipe(values: list[str]) -> str:
    return "|".join(v.strip() for v in values if v and v.strip())


def _cited_release_year(robot: StagedRobot) -> int | None:
    """A release year imports only when its grounding citation line
    ('release_year=YYYY: ...') is staged in notes/research_notes — the citation
    rides into the robot's notes for audit. An uncited year (hallucination-prone
    page extraction, stale staging files) is dropped, not imported."""
    year = robot.release_year
    if not year:
        return None
    if f"release_year={year}:" in f"{robot.notes}\n{robot.research_notes}":
        return year
    return None


def staging_robot_to_bulk_import_row(robot: StagedRobot) -> dict[str, Any]:
    """Convert a StagedRobot to the dict expected by POST .../bulk-import/."""
    payload: dict[str, Any] = {
        "name": _s(robot.name),
        "company_slug": _s(robot.company_slug),
        "company_name": _s(robot.company_name),
        "model_name": _s(robot.model_name),
        "family_name": _s(robot.family_name),
        "family_key": _s(robot.family_key),
        "variant_code": _s(robot.variant_code),
        "variant_label": _s(robot.variant_label),
        "family_url": _s(robot.family_url),
        "product_url_scope": _s(robot.product_url_scope),
        "url": _s(robot.url),
        "image": _s(robot.image),
    }
    if robot.id is not None:
        payload["id"] = int(robot.id)
    payload.update({
        "description": _s(robot.description),
        "purpose": _s(robot.purpose),
        "features": _s(robot.features),
        "strengths": _s(robot.strengths),
        "weaknesses": _s(robot.weaknesses),
        "notes": _build_notes(robot),
        "availability_status_key": _s(robot.availability_status_key),
        "movement_type_keys": _s(robot.movement_type_keys),
        "industry_keys": _s(robot.industry_keys),
        "industries_other": _s(robot.industries_other),
        "use_keys": _s(robot.use_keys),
        "uses_other": _s(robot.uses_other),
        "category_slugs": _s(robot.category_slugs),
        "sub_category_slug": _s(robot.sub_category_slug),
        "tags": _s(robot.tags),
        "manufacturer_country_code": _s(robot.manufacturer_country_code),
        "manufacturer_country_codes": _s(robot.manufacturer_country_codes),
        "release_year": _cited_release_year(robot),
        "source_locale": _s(robot.source_locale) or "en",
        "price_range": _s(robot.price_range),
        "price_min": robot.price_min,
        "price_max": robot.price_max,
        "price_currency": _s(robot.price_currency),
        "price_notes": _s(robot.price_notes),
        "weight": _s(robot.weight),
        "weight_kg": robot.weight_kg,
        "height": _s(robot.height),
        "height_mm": robot.height_mm,
        "width": _s(robot.width),
        "width_mm": robot.width_mm,
        "length": _s(robot.length),
        "length_mm": robot.length_mm,
        "speed": robot.speed,
        "speed_ms": robot.speed_ms,
        "walking_speed": robot.walking_speed,
        "payload_kg": robot.payload_kg,
        "reach_mm": robot.reach_mm,
        "repeatability_mm": robot.repeatability_mm,
        "ip_rating": _s(robot.ip_rating),
        "operating_temp_min_c": _s(robot.operating_temp_min_c),
        "operating_temp_max_c": _s(robot.operating_temp_max_c),
        "dimensions_mm": _s(robot.dimensions_mm),
        "dof": robot.dof,
        "manipulation": _s(robot.manipulation),
        "battery_capacity": _s(robot.battery_capacity),
        "battery_wh": robot.battery_wh,
        "voltage": _s(robot.voltage),
        "runtime": _s(robot.runtime),
        "runtime_minutes": robot.runtime_minutes,
        "charging_type": _s(robot.charging_type),
        "charging_time": _s(robot.charging_time),
        "charging_time_minutes": robot.charging_time_minutes,
        "joint_torque": _s(robot.joint_torque),
        "joint_torque_nm": robot.joint_torque_nm,
        "torque_density": _s(robot.torque_density),
        "torque_density_nm_per_kg": robot.torque_density_nm_per_kg,
        "actuation_mechanism": _s(robot.actuation_mechanism),
        "computation": _s(robot.computation),
        "connectivity": _s(robot.connectivity),
        "software": _s(robot.software),
        "movement_engine": _s(robot.movement_engine),
        "environment": _s(robot.environment),
        "sensors": robot.sensors,
        "materials": robot.materials,
        "company_website": _s(robot.company_website),
        "company_hq_country_code": _s(robot.company_hq_country_code),
        "company_description": _s(robot.company_description),
    })

    # Extended-description narrative fields: include each when populated.
    for _narr in ("programming_interface", "safety_fencing", "mounting_options",
                  "deployment_context", "ecosystem_compatibility"):
        _val = _s(getattr(robot, _narr, ""))
        if _val:
            payload[_narr] = _val

    info_urls = _join_sources(robot)
    if info_urls:
        payload["information_source_urls"] = info_urls

    gallery: list[ImageCandidate] = normalize_image_candidates(list(robot.images))
    gallery_urls = {c.url for c in gallery}
    if robot.image and robot.image not in gallery_urls:
        gallery = [ImageCandidate(url=robot.image), *gallery]
    if gallery:
        payload["images"] = [c.to_dict() for c in gallery]

    if robot.video_urls:
        payload["video_urls"] = [v.to_dict() for v in robot.video_urls]

    return {k: v for k, v in payload.items() if v is not None and v != "" and v != []}


def staging_dict_to_bulk_import_row(data: dict[str, Any]) -> dict[str, Any]:
    return staging_robot_to_bulk_import_row(StagedRobot.from_dict(data))


def staging_robots_to_bulk_import_rows(
    records: list[dict[str, Any] | StagedRobot],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in records:
        if isinstance(record, StagedRobot):
            robot = record
        else:
            robot = StagedRobot.from_dict(record)
        row = staging_robot_to_bulk_import_row(robot)
        if row.get("name"):
            rows.append(row)
    return rows


def canonical_robot_key(name: str, company_slug: str = "") -> str:
    """Dedupe key within a staging batch."""
    slug = re.sub(r"[^a-z0-9]+", "-", (company_slug or "").lower()).strip("-")
    n = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return f"{slug}::{n}" if slug else n
