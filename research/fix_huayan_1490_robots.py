"""Reconcile and safely enrich Huayan Robotics company 1490."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from api_client import ResearchApiClient
from huayan_1490_catalog import (
    CATALOG,
    EXISTING_ID_BY_MODEL,
    RETIREMENT_CANDIDATES,
    CatalogModel,
    normalize_model_code,
)

COMPANY_ID = 1490
COMPANY_SLUG = "huayan-robotics"
REPORT = Path(__file__).resolve().parent / "staging/reports/huayan-1490-full-enrichment.json"
IMAGE_LICENSE_NOTE = """[IMAGE TO-DO — no hero, deliberate]
Huayan publishes an exact official model image, but no reusable-media license or written republication permission was found.
ACTION FOR TEAM: Obtain written republication permission from Huayan Robotics before copying or hotlinking the image.
Do NOT substitute a sibling render, family banner, catalog crop, or dimensional drawing.
---"""
FAMILY_TEMPLATE_IDS = {
    "Elfin": 5295, "Elfin-Pro": 3670, "Elfin-Ex": 3683, "S": 3677,
    "Echo": 5302, "HY": 5302, "STAR": 5303, "Elfin-Li": 5295, "S-Li": 3677,
}
FAMILY_TAG_NAMES = {
    "Elfin": ("Cobot", "Industrial", "Industrial Automation", "Industrial Arm"),
    "Elfin-Pro": ("Cobot", "Industrial", "Industrial Automation", "Industrial Arm"),
    "Elfin-Ex": ("Cobot", "Industrial", "Industrial Automation", "Industrial Arm"),
    "S": ("Cobot", "Industrial", "Palletizing", "Industrial Arm"),
    "Echo": ("7-Axis", "Humanoid", "Research", "Robotic Arm"),
    "HY": ("7-Axis", "Humanoid", "Research", "Robotic Arm"),
    "STAR": ("AMR", "Autonomous", "Mobile Manipulator", "Robotic Arm"),
    "Elfin-Li": ("Cobot", "Industrial Automation", "Industrial Arm"),
    "S-Li": ("Cobot", "Industrial Automation", "Industrial Arm"),
}
RELATION_FIELDS = ("categories", "uses", "industries", "movement_types", "tags")
MEDIA_FIELDS = ("image", "images", "s3_image")
SOURCE_CONFLICTS = (
    {
        "model": "S20",
        "field": "repeatability_mm",
        "conflicting_values": [
            {
                "value": 0.03,
                "source": "https://www.huayan-robotics.com/s",
            },
            {
                "value": 0.05,
                "source": (
                    "https://www.huayan-robotics.net/"
                    "s-heavy-payload-collaborative-robot"
                ),
            },
        ],
        "selected_authoritative_value": 0.03,
        "selected_source": "https://www.huayan-robotics.com/s",
        "rationale": (
            "The current Chinese S-series table is the approved precedence source "
            "for conflicting model specifications."
        ),
    },
    {
        "model": "S40",
        "field": "reach_mm",
        "conflicting_values": [
            {
                "value": 2000,
                "source": "https://www.huayan-robotics.com/s",
            },
            {
                "value": 1800,
                "source": (
                    "https://www.huayan-robotics.net/"
                    "s-heavy-payload-collaborative-robot"
                ),
            },
        ],
        "selected_authoritative_value": 2000,
        "selected_source": "https://www.huayan-robotics.com/s",
        "rationale": (
            "The current Chinese S-series table is the approved precedence source "
            "for conflicting model specifications."
        ),
    },
    {
        "model": "S50",
        "field": "weight_kg",
        "conflicting_values": [
            {
                "value": 156,
                "source": "https://www.huayan-robotics.com/s",
            },
            {
                "value": 165,
                "source": (
                    "https://www.huayan-robotics.net/"
                    "s-heavy-payload-collaborative-robot"
                ),
            },
        ],
        "selected_authoritative_value": 156,
        "selected_source": "https://www.huayan-robotics.com/s",
        "rationale": (
            "The current Chinese S-series table is the approved precedence source "
            "for conflicting model specifications."
        ),
    },
)


@dataclass(frozen=True)
class Reconciliation:
    current_existing: tuple[tuple[dict[str, Any], CatalogModel], ...]
    missing: tuple[CatalogModel, ...]
    retirement_candidates: tuple[dict[str, Any], ...]
    unexpected: tuple[dict[str, Any], ...]


class PartialWriteError(RuntimeError):
    def __init__(
        self,
        robot_id: int,
        model: str,
        action: str,
        error: Exception,
    ) -> None:
        super().__init__(str(error))
        self.robot_id = robot_id
        self.model = model
        self.action = action
        self.original_error = str(error)

    def as_report_entry(self) -> dict[str, Any]:
        return {
            "id": self.robot_id,
            "model": self.model,
            "action": self.action,
            "failed_stage": "post_create_patch_or_verification",
            "error": self.original_error,
        }


def catalog_by_code() -> dict[str, CatalogModel]:
    return {normalize_model_code(row["model"]): row for row in CATALOG}


def _family_slug(family: str) -> str:
    return {
        "Elfin": "elfin", "Elfin-Pro": "elfin-pro", "Elfin-Ex": "elfin-ex",
        "S": "s-series", "Echo": "echo", "HY": "hy", "STAR": "star",
        "Elfin-Li": "elfin-li", "S-Li": "s-li",
    }[family]


def _display_name(model: CatalogModel) -> str:
    if model["family"] == "Elfin":
        return f"Elfin {model['model']}"
    if model["family"] == "Elfin-Ex":
        return f"Elfin-Ex {model['model']}"
    return model["model"]


def relation_ids(values: Any) -> list[int | str]:
    identifiers: list[int | str] = []
    for value in values or []:
        candidate = value.get("id") if isinstance(value, dict) else value
        if isinstance(candidate, int):
            identifiers.append(candidate)
        elif str(candidate).isdigit():
            identifiers.append(int(candidate))
        elif isinstance(candidate, str) and candidate.strip():
            identifiers.append(candidate.strip())
    return identifiers


def _robot_model(robot: dict[str, Any]) -> str:
    return str(robot.get("model_name") or robot.get("name") or "")


def _validate_known_ids(existing: list[dict[str, Any]]) -> None:
    by_id = {int(row["id"]): row for row in existing}
    expected_by_code = {
        normalize_model_code(model): (model, robot_id)
        for model, robot_id in EXISTING_ID_BY_MODEL.items()
    }
    for model, expected_id in EXISTING_ID_BY_MODEL.items():
        row = by_id.get(expected_id)
        if row and normalize_model_code(_robot_model(row)) != normalize_model_code(model):
            raise RuntimeError(
                f"known Huayan ID {expected_id} expected {model}, found {_robot_model(row)}"
            )
    found: set[int] = set()
    seen: dict[str, int] = {}
    for row in existing:
        code = normalize_model_code(_robot_model(row))
        expected = expected_by_code.get(code)
        if not expected:
            continue
        model, expected_id = expected
        actual_id = int(row["id"])
        if code in seen:
            raise RuntimeError(
                f"duplicate normalized current model {model}: {seen[code]} and {actual_id}"
            )
        seen[code] = actual_id
        if actual_id != expected_id:
            raise RuntimeError(
                f"known Huayan model {model} expected ID {expected_id}, found {actual_id}"
            )
        found.add(actual_id)
    missing = sorted(set(EXISTING_ID_BY_MODEL.values()) - found)
    if missing:
        raise RuntimeError(
            "known Huayan current model ID(s) missing: " + ", ".join(map(str, missing))
        )


def reconcile(existing: list[dict[str, Any]]) -> Reconciliation:
    _validate_known_ids(existing)
    models = catalog_by_code()
    matched: dict[str, tuple[dict[str, Any], CatalogModel]] = {}
    retirement: list[dict[str, Any]] = []
    unexpected: list[dict[str, Any]] = []
    for robot in existing:
        robot_id = int(robot["id"])
        if robot_id in RETIREMENT_CANDIDATES:
            retirement.append(robot)
            continue
        code = normalize_model_code(_robot_model(robot))
        model = models.get(code)
        if model is None:
            unexpected.append(robot)
        elif code in matched:
            raise RuntimeError(
                f"duplicate normalized current model {model['model']}: "
                f"{matched[code][0]['id']} and {robot_id}"
            )
        else:
            matched[code] = (robot, model)
    missing = tuple(
        row for row in CATALOG if normalize_model_code(row["model"]) not in matched
    )
    return Reconciliation(
        tuple(matched.values()), missing, tuple(retirement), tuple(unexpected)
    )


def _base_payload(model: CatalogModel, country_id: int) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": _display_name(model),
        "model_name": model["model"],
        "variant_code": model["model"],
        "variant_label": model["model"],
        "family_key": f"{COMPANY_SLUG}:{_family_slug(model['family'])}",
        "family_name": model["family"],
        "family_url": model["family_url"],
        "product_url_scope": "family",
        "url": model["family_url"],
        "description": model["description"],
        "purpose": model["purpose"],
        "features": model["features"],
        "availability_status": 11,
        "manufacturer_country_ref": country_id,
        "manufacturer_countries": [country_id],
        "information_source_urls": list(model["sources"]),
    }
    payload.update(model["typed"])
    return payload


def _detail_payload(
    model: CatalogModel,
    country_id: int,
    taxonomy: dict[str, list[int | str]],
) -> dict[str, Any]:
    tags = taxonomy.get("tags") or []
    if any(not isinstance(tag, str) or not tag.strip() for tag in tags):
        raise RuntimeError(f"{model['model']} tags must use catalog names, not IDs")
    payload = _base_payload(model, country_id)
    payload.update({field: list(taxonomy.get(field) or []) for field in RELATION_FIELDS})
    missing = [field for field in RELATION_FIELDS if not payload[field]]
    if missing:
        raise RuntimeError(f"{model['model']} taxonomy missing {', '.join(missing)}")
    return payload


def existing_patch(
    robot: dict[str, Any],
    model: CatalogModel,
    *,
    country_id: int,
    taxonomy: dict[str, list[int | str]] | None = None,
) -> dict[str, Any]:
    payload = _base_payload(model, country_id)
    payload.update({
        "status": robot.get("status"),
        "image": robot.get("image") or "",
        "images": list(robot.get("images") or []),
        "s3_image": robot.get("s3_image"),
    })
    for field in RELATION_FIELDS:
        if robot.get(field):
            payload[field] = relation_ids(robot[field])
    if taxonomy:
        payload.update({field: list(taxonomy.get(field) or []) for field in RELATION_FIELDS})
    return payload


def new_record(
    model: CatalogModel,
    *,
    country_id: int,
    taxonomy: dict[str, list[int | str]] | None = None,
) -> dict[str, Any]:
    payload = _base_payload(model, country_id)
    payload.update({
        "company": "Huayan Robotics", "company_id": COMPANY_ID,
        "status": "pending_review", "image": "", "images": [], "s3_image": None,
        "notes": IMAGE_LICENSE_NOTE,
    })
    if taxonomy:
        payload.update({field: list(taxonomy.get(field) or []) for field in RELATION_FIELDS})
    return payload


def validate_plan(plan: Reconciliation) -> None:
    if plan.unexpected:
        raise RuntimeError(
            "unexpected Huayan records: "
            + ", ".join(str(row.get("id")) for row in plan.unexpected)
        )
    if len(plan.retirement_candidates) != 3:
        raise RuntimeError(
            f"expected 3 retirement candidates, found {len(plan.retirement_candidates)}"
        )
    if len(plan.current_existing) + len(plan.missing) != 42:
        raise RuntimeError("current plus missing model count must equal 42")
    codes = [
        normalize_model_code(model["model"]) for _, model in plan.current_existing
    ] + [normalize_model_code(model["model"]) for model in plan.missing]
    if len(codes) != len(set(codes)):
        raise RuntimeError("duplicate normalized model code in reconciliation plan")


def media_blocked_models(plan: Reconciliation) -> list[str]:
    blocked = [
        model["model"]
        for robot, model in plan.current_existing
        if not _has_media(robot)
    ]
    blocked.extend(model["model"] for model in plan.missing)
    return blocked


def _has_media(robot: dict[str, Any]) -> bool:
    return any(
        robot.get(field)
        for field in ("image", "images", "s3_image", "photos")
    )


def licensing_note_evidence(plan: Reconciliation) -> dict[str, Any]:
    imageless = sorted(
        (
            (robot, model)
            for robot, model in plan.current_existing
            if not _has_media(robot)
        ),
        key=lambda pair: pair[1]["model"],
    )
    valid: list[str] = []
    invalid: list[dict[str, Any]] = []
    for robot, model in imageless:
        notes = str(robot.get("notes") or "")
        if IMAGE_LICENSE_NOTE in notes:
            valid.append(model["model"])
        else:
            invalid.append({
                "id": int(robot["id"]),
                "model": model["model"],
                "reason": "missing" if not notes.strip() else "invalid",
            })
    return {
        "imageless_current_models": [model["model"] for _, model in imageless],
        "valid_actionable_models": valid,
        "missing_or_invalid_models": [row["model"] for row in invalid],
        "missing_or_invalid_details": invalid,
    }


def fetch_company_details(client: ResearchApiClient) -> list[dict[str, Any]]:
    return [
        client._get(f"robots/robots/{int(row['id'])}/")
        for row in client.list_robots_for_company(COMPANY_ID)
    ]


def build_plan(client: ResearchApiClient) -> Reconciliation:
    plan = reconcile(fetch_company_details(client))
    validate_plan(plan)
    return plan


def resolve_china_id(client: ResearchApiClient) -> int:
    country_id = client.resolve_country_id("CN")
    if not country_id:
        raise RuntimeError("could not resolve manufacturer country CN")
    return int(country_id)


def resolve_family_tag_names(client: ResearchApiClient) -> dict[str, list[str]]:
    by_name = {
        str(tag.get("name") or "").casefold(): str(tag["name"])
        for tag in client.list_tags() if tag.get("name")
    }
    requested = sorted(
        {name for names in FAMILY_TAG_NAMES.values() for name in names},
        key=str.casefold,
    )
    missing = [name for name in requested if name.casefold() not in by_name]
    if missing:
        raise RuntimeError(
            "unresolved Huayan tag name(s): " + ", ".join(missing)
        )
    resolved: dict[str, list[str]] = {}
    for family, names in FAMILY_TAG_NAMES.items():
        resolved[family] = [
            by_name[name.casefold()] for name in names
        ]
    return resolved


def taxonomy_for_model(
    model: CatalogModel,
    details_by_id: dict[int, dict[str, Any]],
    tag_names: dict[str, list[str]],
) -> dict[str, list[int | str]]:
    exemplar_id = FAMILY_TEMPLATE_IDS[model["family"]]
    exemplar = details_by_id.get(exemplar_id)
    if exemplar is None:
        raise RuntimeError(f"taxonomy exemplar {exemplar_id} missing for {model['family']}")
    taxonomy = {
        field: relation_ids(exemplar.get(field))
        for field in ("categories", "uses", "industries", "movement_types")
    }
    taxonomy["tags"] = list(tag_names[model["family"]])
    missing = [field for field, values in taxonomy.items() if not values]
    if missing:
        raise RuntimeError(f"{model['family']} taxonomy missing {', '.join(missing)}")
    return taxonomy


def _field_id(value: Any) -> int | str | None:
    value = value.get("id") if isinstance(value, dict) else value
    return int(value) if str(value).isdigit() else value


def _source_urls(detail: dict[str, Any]) -> list[str]:
    values = detail.get("information_source_urls")
    if values is None:
        values = detail.get("information_sources")
    urls: list[str] = []
    for value in values or []:
        url = value.get("url") if isinstance(value, dict) else value
        if isinstance(url, str) and url.strip():
            urls.append(url.strip())
    return urls


def _video_urls(detail: dict[str, Any]) -> list[str]:
    return [
        str(video.get("url") if isinstance(video, dict) else video).strip()
        for video in detail.get("videos") or []
        if str(video.get("url") if isinstance(video, dict) else video).strip()
    ]


def _verify_catalog_videos(detail: dict[str, Any], model: CatalogModel) -> None:
    actual = _video_urls(detail)
    for url in model["videos"]:
        if actual.count(url) != 1:
            raise RuntimeError(
                f"{model['model']} official video verification failed for {url}"
            )


def verify_existing_videos_unchanged(
    before: list[dict[str, Any]],
    after: list[dict[str, Any]],
) -> None:
    before_by_id: dict[int, dict[str, Any]] = {}
    for row in before:
        if row.get("id") is None:
            raise RuntimeError("pre-existing video row has no stable ID")
        before_by_id[int(row["id"])] = row
    after_by_id = {
        int(row["id"]): row
        for row in after
        if row.get("id") is not None
    }
    if set(after_by_id) != set(before_by_id) or len(after) != len(before):
        raise RuntimeError("existing video row set changed")
    for video_id, row in before_by_id.items():
        if after_by_id.get(video_id) != row:
            raise RuntimeError(f"pre-existing video row changed: {video_id}")


def _verify_factual_detail(
    detail: dict[str, Any],
    model: CatalogModel,
    country_id: int,
    taxonomy: dict[str, list[int | str]],
    expected_status: str,
    *,
    require_catalog_videos: bool,
) -> None:
    robot_id = detail.get("id")
    if detail.get("status") != expected_status:
        raise RuntimeError(f"status invariant failed for {robot_id}")
    expected = _detail_payload(model, country_id, taxonomy)
    for field in (
        "name", "description", "features", "url", "model_name",
        "variant_code", "variant_label", "family_key",
        "family_name", "family_url", "product_url_scope",
    ):
        if detail.get(field) != expected[field]:
            raise RuntimeError(f"{model['model']} {field} verification failed")
    if detail.get("purpose") != expected["purpose"]:
        raise RuntimeError(f"{model['model']} purpose verification failed")
    if not set(model["sources"]).issubset(set(_source_urls(detail))):
        raise RuntimeError(f"{model['model']} sources verification failed")
    for field, value in model["typed"].items():
        if detail.get(field) != value:
            raise RuntimeError(
                f"{model['model']} post-patch typed field {field} verification failed"
            )
    if _field_id(detail.get("availability_status")) != 11:
        raise RuntimeError(f"{model['model']} availability verification failed")
    if _field_id(detail.get("manufacturer_country_ref")) != country_id:
        raise RuntimeError(f"{model['model']} country verification failed")
    if relation_ids(detail.get("manufacturer_countries")) != [country_id]:
        raise RuntimeError(f"{model['model']} country relation verification failed")
    for field in RELATION_FIELDS:
        if set(relation_ids(detail.get(field))) != set(relation_ids(expected[field])):
            raise RuntimeError(f"{model['model']} {field} relation verification failed")
    if require_catalog_videos:
        _verify_catalog_videos(detail, model)


def _verify_new_detail(
    detail: dict[str, Any],
    model: CatalogModel,
    country_id: int,
    taxonomy: dict[str, list[int | str]],
) -> None:
    robot_id = detail.get("id")
    _verify_factual_detail(
        detail,
        model,
        country_id,
        taxonomy,
        "pending_review",
        require_catalog_videos=True,
    )
    if any(detail.get(field) for field in MEDIA_FIELDS) or detail.get("photos"):
        raise RuntimeError(f"new model media invariant failed for {robot_id}")
    if detail.get("notes") != IMAGE_LICENSE_NOTE:
        raise RuntimeError(f"new model licensing note invariant failed for {robot_id}")


def apply_existing_record(
    client: ResearchApiClient,
    planned_robot: dict[str, Any],
    model: CatalogModel,
    *,
    country_id: int,
    taxonomy: dict[str, list[int | str]],
) -> dict[str, Any]:
    robot_id = int(planned_robot["id"])
    before = client._get(f"robots/robots/{robot_id}/")
    planned_status = planned_robot.get("status")
    if before.get("status") != planned_status:
        raise RuntimeError(f"status invariant failed for {robot_id}")
    before_media = {field: before.get(field) for field in MEDIA_FIELDS}
    before_videos = list(before.get("videos") or [])
    payload = _detail_payload(model, country_id, taxonomy)
    if not (
        before.get("image")
        or before.get("s3_image")
        or before.get("images")
        or before.get("photos")
    ) and IMAGE_LICENSE_NOTE not in str(before.get("notes") or ""):
        existing_notes = str(before.get("notes") or "").rstrip()
        payload["notes"] = (
            f"{existing_notes}\n\n{IMAGE_LICENSE_NOTE}"
            if existing_notes
            else IMAGE_LICENSE_NOTE
        )
    client._patch(f"robots/robots/{robot_id}/", payload)
    after = client._get(f"robots/robots/{robot_id}/")
    _verify_factual_detail(
        after,
        model,
        country_id,
        taxonomy,
        str(planned_status),
        require_catalog_videos=False,
    )
    if after.get("status") != planned_status:
        raise RuntimeError(f"status invariant failed after patch for {robot_id}")
    if {field: after.get(field) for field in MEDIA_FIELDS} != before_media:
        raise RuntimeError(f"media invariant failed after patch for {robot_id}")
    verify_existing_videos_unchanged(
        before_videos,
        list(after.get("videos") or []),
    )
    return after


def apply_new_record(
    client: ResearchApiClient,
    model: CatalogModel,
    *,
    country_id: int,
    taxonomy: dict[str, list[int | str]],
) -> dict[str, int | str]:
    payload = new_record(model, country_id=country_id, taxonomy=taxonomy)
    payload.update({
        "company_slug": COMPANY_SLUG, "company_name": "Huayan Robotics",
        "manufacturer_country_code": "CN", "manufacturer_country_codes": "CN",
        "video_urls": list(model["videos"]),
    })
    result = client.bulk_import_robots(
        [payload], update_existing=False, patch_existing=False,
        status="pending_review", skip_company_update=True,
        replace_media=False, replace_videos=False,
    )
    if result.get("error_count"):
        raise RuntimeError(f"bulk create failed for {model['model']}: {result}")
    applied = [
        row for row in result.get("results") or []
        if row.get("action") in {"created", "updated"} and row.get("id")
    ]
    if len(applied) != 1:
        raise RuntimeError(f"could not identify imported {model['model']}: {result}")
    robot_id = int(applied[0]["id"])
    action = str(applied[0]["action"])
    try:
        client._get(f"robots/robots/{robot_id}/")
        client._patch(
            f"robots/robots/{robot_id}/",
            _detail_payload(model, country_id, taxonomy),
        )
        verified = client._get(f"robots/robots/{robot_id}/")
        _verify_new_detail(verified, model, country_id, taxonomy)
    except Exception as exc:
        raise PartialWriteError(
            robot_id,
            model["model"],
            action,
            exc,
        ) from exc
    return {"id": robot_id, "action": action}


def apply_missing_model(
    client: ResearchApiClient,
    model: CatalogModel,
    *,
    country_id: int,
    taxonomy: dict[str, list[int | str]],
    report: dict[str, Any],
) -> dict[str, int | str]:
    try:
        applied = apply_new_record(
            client,
            model,
            country_id=country_id,
            taxonomy=taxonomy,
        )
    except PartialWriteError as exc:
        if exc.action == "created":
            report["partial_writes"].append(exc.as_report_entry())
        raise
    entry = {"id": int(applied["id"]), "model": model["model"]}
    key = "created" if applied["action"] == "created" else "create_race_updated"
    report[key].append(entry)
    return applied


def verify_final_current_records(
    plan: Reconciliation,
    *,
    country_id: int,
    taxonomy_by_family: dict[str, dict[str, list[int | str]]],
    expected_status_by_id: dict[int, str],
    expected_media_by_id: dict[int, dict[str, Any]],
) -> None:
    for detail, model in plan.current_existing:
        robot_id = int(detail["id"])
        taxonomy = taxonomy_by_family[model["family"]]
        if robot_id in expected_status_by_id:
            _verify_factual_detail(
                detail,
                model,
                country_id,
                taxonomy,
                expected_status_by_id[robot_id],
                require_catalog_videos=False,
            )
            actual_media = {
                field: detail.get(field) for field in MEDIA_FIELDS
            }
            if actual_media != expected_media_by_id[robot_id]:
                raise RuntimeError(
                    f"final media invariant failed for existing robot {robot_id}"
                )
        else:
            _verify_new_detail(detail, model, country_id, taxonomy)


def _planned_video_action(
    robot: dict[str, Any] | None,
    model: CatalogModel,
) -> dict[str, Any]:
    current_urls = _video_urls(robot or {})
    desired_urls = list(model["videos"])
    if not desired_urls:
        action = "none"
    elif robot is None:
        action = "create_with_catalog_videos"
    elif all(current_urls.count(url) == 1 for url in desired_urls):
        action = "no_change"
    else:
        action = "follow_up_no_safe_add_endpoint"
    return {
        "action": action,
        "requested_action": "add_video" if desired_urls else "none",
        "current_urls": current_urls,
        "desired_urls": desired_urls,
        "preserve_unrelated": True,
        "deduplicate": True,
        "replacement_allowed": False,
    }


def planned_patch_summaries(
    plan: Reconciliation,
    taxonomy_by_family: dict[str, dict[str, list[int | str]]],
) -> list[dict[str, Any]]:
    rows: list[tuple[dict[str, Any] | None, CatalogModel]] = [
        *plan.current_existing,
        *((None, model) for model in plan.missing),
    ]
    summaries: list[dict[str, Any]] = []
    for robot, model in rows:
        taxonomy = taxonomy_by_family[model["family"]]
        summaries.append({
            "id": int(robot["id"]) if robot else None,
            "model": model["model"],
            "operation": "patch" if robot else "create_then_patch",
            "status": str(robot.get("status")) if robot else "pending_review",
            "url": model["family_url"],
            "family": {
                "key": f"{COMPANY_SLUG}:{_family_slug(model['family'])}",
                "name": model["family"],
                "url": model["family_url"],
                "product_url_scope": "family",
            },
            "taxonomy": {
                "categories": list(taxonomy["categories"]),
                "uses": list(taxonomy["uses"]),
                "industries": list(taxonomy["industries"]),
                "movement_types": list(taxonomy["movement_types"]),
                "tag_names": list(taxonomy["tags"]),
            },
            "typed": dict(model["typed"]),
            "source_urls": list(model["sources"]),
            "video_action": _planned_video_action(robot, model),
            "media_excluded": True,
            "media_fields_in_patch": [],
        })
    return summaries


def build_report(
    plan: Reconciliation,
    details: list[dict[str, Any]],
    taxonomy_by_family: dict[str, dict[str, list[int | str]]],
    *,
    apply: bool,
) -> dict[str, Any]:
    blocked_models = media_blocked_models(plan)
    note_evidence = licensing_note_evidence(plan)
    planned_patches = planned_patch_summaries(plan, taxonomy_by_family)
    video_followups = [
        {
            "model": row["model"],
            "official_url": row["video_action"]["desired_urls"][0],
            "reason": "no safe non-destructive add endpoint",
        }
        for row in planned_patches
        if row["video_action"]["action"] == "follow_up_no_safe_add_endpoint"
    ]
    invalid_note_models = note_evidence["missing_or_invalid_models"]
    note_blocker = (
        "imageless current records missing/invalid actionable Huayan "
        "image-permission note: " + ", ".join(invalid_note_models)
        if invalid_note_models
        else ""
    )
    blockers = [note_blocker] if note_blocker and not apply else []
    report: dict[str, Any] = {
        "company_id": COMPANY_ID,
        "mode": "apply" if apply else "dry-run",
        "before_counts": dict(Counter(str(row.get("status")) for row in details)),
        "after_counts": {},
        "existing_updated": [],
        "created": [],
        "partial_writes": [],
        "create_race_updated": [],
        "retirement_candidates": sorted(RETIREMENT_CANDIDATES),
        "media_blocked": blocked_models,
        "licensing_note_evidence": note_evidence,
        "source_conflicts": list(SOURCE_CONFLICTS),
        "planned_patches": planned_patches,
        "video_followups": video_followups,
        "catalog_intent": {
            "known_original_records": len(EXISTING_ID_BY_MODEL),
            "catalog_additions": len(CATALOG) - len(EXISTING_ID_BY_MODEL),
            "catalog_total": len(CATALOG),
        },
        "blockers": blockers,
        "errors": list(blockers),
        "verified": {
            "current_models": len(plan.current_existing),
            "new_model_records": sum(
                1
                for robot, _ in plan.current_existing
                if int(robot["id"]) not in set(EXISTING_ID_BY_MODEL.values())
            ),
            "media_blocked": len(blocked_models),
            "licensing_notes_verified": len(
                note_evidence["valid_actionable_models"]
            ),
        },
    }
    if not apply:
        report["summary"] = {
            "existing_current": len(plan.current_existing),
            "missing_current": len(plan.missing),
            "retirement_candidates": len(plan.retirement_candidates),
            "unexpected": len(plan.unexpected),
            "planned_media_uploads": 0,
        }
    return report


def _write_report(report: dict[str, Any]) -> None:
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconcile Huayan Robotics company 1490")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    client = ResearchApiClient()
    details = fetch_company_details(client)
    plan = reconcile(details)
    validate_plan(plan)
    country_id = resolve_china_id(client)
    tag_names = resolve_family_tag_names(client)
    details_by_id = {int(row["id"]): row for row in details}
    expected_status_by_id = {
        int(robot["id"]): str(robot.get("status"))
        for robot, _ in plan.current_existing
    }
    expected_media_by_id = {
        int(robot["id"]): {
            field: robot.get(field) for field in MEDIA_FIELDS
        }
        for robot, _ in plan.current_existing
    }
    taxonomy = {
        family: taxonomy_for_model(
            next(model for model in CATALOG if model["family"] == family),
            details_by_id,
            tag_names,
        )
        for family in FAMILY_TEMPLATE_IDS
    }
    blocked_models = media_blocked_models(plan)
    unnoted_blockers = [
        model["model"]
        for robot, model in plan.current_existing
        if model["model"] in blocked_models
        and IMAGE_LICENSE_NOTE not in str(robot.get("notes") or "")
    ]
    if args.apply and unnoted_blockers:
        raise RuntimeError(
            "imageless records missing licensing blocker note: "
            + ", ".join(unnoted_blockers)
        )
    report = build_report(plan, details, taxonomy, apply=args.apply)
    if not args.apply:
        _write_report(report)
        return 1 if report["errors"] else 0
    if report["blockers"]:
        _write_report(report)
        return 1
    try:
        for robot, model in plan.current_existing:
            apply_existing_record(
                client, robot, model, country_id=country_id,
                taxonomy=taxonomy[model["family"]],
            )
            report["existing_updated"].append(int(robot["id"]))
        for model in plan.missing:
            live = reconcile(fetch_company_details(client))
            code = normalize_model_code(model["model"])
            if any(normalize_model_code(row["model"]) == code for _, row in live.current_existing):
                continue
            apply_missing_model(
                client, model, country_id=country_id,
                taxonomy=taxonomy[model["family"]],
                report=report,
            )
        after = fetch_company_details(client)
        after_plan = reconcile(after)
        validate_plan(after_plan)
        if len(after_plan.current_existing) != 42 or after_plan.missing:
            raise RuntimeError("post-apply catalog invariant failed")
        verify_final_current_records(
            after_plan,
            country_id=country_id,
            taxonomy_by_family=taxonomy,
            expected_status_by_id=expected_status_by_id,
            expected_media_by_id=expected_media_by_id,
        )
        report["after_counts"] = dict(Counter(str(row.get("status")) for row in after))
        report["media_blocked"] = media_blocked_models(after_plan)
    except Exception as exc:
        report["errors"].append(str(exc))
        _write_report(report)
        raise
    _write_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
