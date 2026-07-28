"""Tests for Huayan company 1490 reconciliation and payloads."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RESEARCH_DIR = Path(__file__).resolve().parents[1]
if str(RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(RESEARCH_DIR))

from fix_huayan_1490_robots import (
    catalog_by_code,
    existing_patch,
    new_record,
    reconcile,
    validate_plan,
)
import fix_huayan_1490_robots as huayan


CURRENT_EXISTING = {
    5205: ("S30", "published"),
    5295: ("E03", "published"),
    5296: ("E05-L", "published"),
    5297: ("E05", "published"),
    5298: ("E10-L", "published"),
    5299: ("E10", "published"),
    5300: ("E12", "published"),
    5301: ("E15", "pending_review"),
    3687: ("E15F", "pending_review"),
    3686: ("E12F", "pending_review"),
    3685: ("E10F-L", "pending_review"),
    3684: ("E10F", "pending_review"),
    3683: ("E05F", "pending_review"),
    3682: ("S60", "pending_review"),
    3681: ("S50", "pending_review"),
    3680: ("S40", "pending_review"),
    3677: ("S20", "pending_review"),
    3676: ("E15-Pro", "pending_review"),
    3675: ("E12-Pro", "pending_review"),
    3674: ("E10L-Pro", "pending_review"),
    3673: ("E10-Pro", "pending_review"),
    3672: ("E05L-Pro", "pending_review"),
    3671: ("E05-Pro", "pending_review"),
    3670: ("E03-Pro", "pending_review"),
}


def load_existing_fixture() -> list[dict]:
    rows = [
        {
            "id": robot_id,
            "name": model,
            "model_name": model,
            "status": status,
            "image": f"https://cdn.example/{robot_id}.png",
            "images": [f"https://cdn.example/{robot_id}.png"],
            "s3_image": f"https://cdn.example/{robot_id}.png",
            "notes": "",
        }
        for robot_id, (model, status) in CURRENT_EXISTING.items()
    ]
    rows.extend(
        [
            {"id": 3679, "name": "S-35", "model_name": "S-35", "status": "pending_review"},
            {
                "id": 5302,
                "name": "Echo 7-Axis Humanoid Arm Series",
                "model_name": "Echo 7-Axis Humanoid Arm Series",
                "status": "published",
            },
            {
                "id": 5303,
                "name": "STAR Mobile Manipulator",
                "model_name": "STAR Mobile Manipulator",
                "status": "published",
            },
        ]
    )
    return rows


def test_reconcile_finds_24_current_18_missing_and_3_retirement_candidates() -> None:
    plan = reconcile(load_existing_fixture())
    assert len(plan.current_existing) == 24
    assert len(plan.missing) == 18
    assert {row["id"] for row in plan.retirement_candidates} == {3679, 5302, 5303}
    assert plan.unexpected == ()


def test_media_blocked_includes_imageless_existing_and_missing_models() -> None:
    rows = load_existing_fixture()
    e03 = next(row for row in rows if row["model_name"] == "E03")
    e03.update({"image": "", "images": [], "s3_image": None, "photos": []})

    blocked = huayan.media_blocked_models(reconcile(rows))

    assert "E03" in blocked
    assert "Echo 3" in blocked
    assert len(blocked) == 19


def test_dry_run_licensing_note_counts_are_evidence_based() -> None:
    rows = load_existing_fixture()
    e10l = next(row for row in rows if row["model_name"] == "E10L-Pro")
    e10l["videos"] = [{
        "id": 9001,
        "url": catalog_by_code()["e10lpro"]["videos"][0],
    }]
    notes_by_model = {
        "E03": huayan.IMAGE_LICENSE_NOTE,
        "E05": "",
        "E10": "Image permission should be requested someday.",
    }
    for row in rows:
        if row["model_name"] in notes_by_model:
            row.update({
                "image": "",
                "images": [],
                "s3_image": None,
                "photos": [],
                "notes": notes_by_model[row["model_name"]],
            })
    plan = reconcile(rows)
    taxonomy = {
        family: {
            "categories": [1],
            "uses": [2],
            "industries": [3],
            "movement_types": [4],
            "tags": ["Cobot"],
        }
        for family in huayan.FAMILY_TEMPLATE_IDS
    }

    report = huayan.build_report(plan, rows, taxonomy, apply=False)

    evidence = report["licensing_note_evidence"]
    assert evidence["imageless_current_models"] == ["E03", "E05", "E10"]
    assert evidence["valid_actionable_models"] == ["E03"]
    assert evidence["missing_or_invalid_models"] == ["E05", "E10"]
    assert evidence["missing_or_invalid_details"] == [
        {"id": 5297, "model": "E05", "reason": "missing"},
        {"id": 5299, "model": "E10", "reason": "invalid"},
    ]
    assert report["verified"]["licensing_notes_verified"] == 1
    assert report["blockers"] == [
        "imageless current records missing/invalid actionable Huayan "
        "image-permission note: E05, E10"
    ]
    assert report["errors"] == report["blockers"]


def test_dry_run_warns_for_missing_existing_video_without_blocking() -> None:
    rows = load_existing_fixture()
    plan = reconcile(rows)
    taxonomy = {
        family: {
            "categories": [1],
            "uses": [2],
            "industries": [3],
            "movement_types": [4],
            "tags": ["Cobot"],
        }
        for family in huayan.FAMILY_TEMPLATE_IDS
    }

    report = huayan.build_report(plan, rows, taxonomy, apply=False)
    e10l = next(
        row for row in report["planned_patches"] if row["model"] == "E10L-Pro"
    )

    assert e10l["video_action"]["action"] == "follow_up_no_safe_add_endpoint"
    assert e10l["video_action"]["requested_action"] == "add_video"
    assert e10l["video_action"]["replacement_allowed"] is False
    assert report["video_followups"] == [
        {
            "model": "E10L-Pro",
            "official_url": catalog_by_code()["e10lpro"]["videos"][0],
            "reason": "no safe non-destructive add endpoint",
        }
    ]
    assert report["blockers"] == []
    assert report["errors"] == []


def test_reconcile_fails_closed_when_known_model_is_on_wrong_id() -> None:
    rows = load_existing_fixture()
    e03 = next(row for row in rows if row["model_name"] == "E03")
    e03["id"] = 9999

    with pytest.raises(RuntimeError, match=r"E03.*expected ID 5295.*found 9999"):
        reconcile(rows)


def test_reconcile_fails_closed_when_known_id_has_wrong_model() -> None:
    rows = load_existing_fixture()
    e03 = next(row for row in rows if row["id"] == 5295)
    e03["name"] = "E05"
    e03["model_name"] = "E05"

    with pytest.raises(RuntimeError, match=r"ID 5295.*expected E03.*found E05"):
        reconcile(rows)


def test_existing_patch_preserves_status_and_media() -> None:
    robot = load_existing_fixture()[0]
    payload = existing_patch(robot, catalog_by_code()["s30"], country_id=45)
    assert payload["status"] == robot["status"]
    assert payload["image"] == robot["image"]
    assert payload["images"] == robot["images"]
    assert payload["s3_image"] == robot["s3_image"]


def test_new_record_is_pending_imageless_and_has_license_note() -> None:
    payload = new_record(catalog_by_code()["echo3"], country_id=45)
    assert payload["status"] == "pending_review"
    assert payload["image"] == ""
    assert payload["images"] == []
    assert payload["s3_image"] is None
    assert payload["notes"].startswith("[IMAGE TO-DO — no hero, deliberate]")
    assert "written republication permission" in payload["notes"]


def test_new_record_uses_catalog_tag_names_and_no_media_urls() -> None:
    taxonomy = {
        "categories": [1],
        "uses": [2],
        "industries": [3],
        "movement_types": [4],
        "tags": ["Cobot", "Robot Arm"],
    }

    payload = new_record(
        catalog_by_code()["e03li"],
        country_id=45,
        taxonomy=taxonomy,
    )

    assert payload["tags"] == ["Cobot", "Robot Arm"]
    assert all(isinstance(tag, str) for tag in payload["tags"])
    assert payload["image"] == ""
    assert payload["images"] == []
    assert payload["s3_image"] is None
    for typed_field in (
        "payload_kg",
        "weight_kg",
        "reach_mm",
        "repeatability_mm",
        "dof",
        "speed",
        "runtime_minutes",
    ):
        assert typed_field not in payload


def test_payload_has_family_availability_sources_and_distinct_purpose() -> None:
    payload = new_record(catalog_by_code()["e15"], country_id=45)
    assert payload["family_key"] == "huayan-robotics:elfin"
    assert payload["family_name"] == "Elfin"
    assert payload["product_url_scope"] == "family"
    assert payload["availability_status"] == 11
    assert payload["manufacturer_country_ref"] == 45
    assert payload["information_source_urls"]
    assert payload["purpose"] != payload["description"]
    assert payload["payload_kg"] == 18
    assert payload["url"] == "https://www.huayan-robotics.net/elfin-collaborative-robot"
    assert "website_url" not in payload


def test_dry_run_report_reflects_live_state_and_catalog_intent() -> None:
    rows = load_existing_fixture()
    e10l_existing = next(row for row in rows if row["model_name"] == "E10L-Pro")
    e10l_existing["videos"] = [{
        "id": 9001,
        "url": catalog_by_code()["e10lpro"]["videos"][0],
    }]
    initial = reconcile(rows)
    for robot_id, model in enumerate(initial.missing, start=6000):
        row = new_record(model, country_id=45)
        row["id"] = robot_id
        row["videos"] = [{"id": robot_id + 1000, "url": url} for url in model["videos"]]
        rows.append(row)
    live_plan = reconcile(rows)
    taxonomy = {
        family: {
            "categories": [1],
            "uses": [2],
            "industries": [3],
            "movement_types": [4],
            "tags": ["Cobot"],
        }
        for family in huayan.FAMILY_TEMPLATE_IDS
    }

    report = huayan.build_report(
        live_plan,
        rows,
        taxonomy,
        apply=False,
    )

    assert report["summary"]["existing_current"] == 42
    assert report["summary"]["missing_current"] == 0
    assert report["catalog_intent"] == {
        "known_original_records": 24,
        "catalog_additions": 18,
        "catalog_total": 42,
    }
    assert len(report["planned_patches"]) == 42
    e10l = next(
        row for row in report["planned_patches"] if row["model"] == "E10L-Pro"
    )
    assert e10l["url"] == catalog_by_code()["e10lpro"]["family_url"]
    assert e10l["status"] == "pending_review"
    assert e10l["family"]["key"] == "huayan-robotics:elfin-pro"
    assert e10l["taxonomy"]["tag_names"] == ["Cobot"]
    assert e10l["typed"]["payload_kg"] == 10
    assert e10l["source_urls"]
    assert e10l["video_action"]["desired_urls"]
    assert e10l["media_excluded"] is True
    assert report["verified"]["licensing_notes_verified"] == 18
    assert report["licensing_note_evidence"]["valid_actionable_models"] == sorted(
        model["model"] for model in initial.missing
    )
    assert report["licensing_note_evidence"]["missing_or_invalid_models"] == []
    assert report["blockers"] == []


def test_source_conflicts_are_auditable_and_use_chinese_precedence() -> None:
    conflicts = huayan.SOURCE_CONFLICTS

    assert {row["model"] for row in conflicts} == {"S20", "S40", "S50"}
    assert all(row["selected_source"] == "https://www.huayan-robotics.com/s" for row in conflicts)
    assert all("current Chinese" in row["rationale"] for row in conflicts)
    assert next(row for row in conflicts if row["model"] == "S20")[
        "selected_authoritative_value"
    ] == 0.03
    assert next(row for row in conflicts if row["model"] == "S40")[
        "selected_authoritative_value"
    ] == 2000
    assert next(row for row in conflicts if row["model"] == "S50")[
        "selected_authoritative_value"
    ] == 156


def test_validate_plan_rejects_duplicate_records() -> None:
    plan = reconcile(load_existing_fixture())
    validate_plan(plan)
    duplicate = load_existing_fixture() + [
        {"id": 9999, "name": "E15", "model_name": "E15", "status": "pending_review"}
    ]
    with pytest.raises(RuntimeError, match="duplicate"):
        reconcile(duplicate)
