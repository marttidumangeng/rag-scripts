"""Tests for Huayan company 1490 apply workflow invariants."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RESEARCH_DIR = Path(__file__).resolve().parents[1]
if str(RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(RESEARCH_DIR))
TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from fix_huayan_1490_robots import (
    apply_existing_record,
    apply_new_record,
    catalog_by_code,
    new_record,
    reconcile,
    relation_ids,
)
import fix_huayan_1490_robots as huayan
from test_fix_huayan_1490_reconciliation import load_existing_fixture


TAXONOMY = {
    "categories": [1],
    "uses": [2],
    "industries": [3],
    "movement_types": [4],
    "tags": ["Cobot"],
}


class FakeClient:
    def __init__(self, detail: dict, *, corrupt_after_patch: str | None = None) -> None:
        self.detail = detail
        self.corrupt_after_patch = corrupt_after_patch
        self.patches: list[tuple[str, dict]] = []

    def _get(self, path: str) -> dict:
        return dict(self.detail)

    def _patch(self, path: str, data: dict) -> dict:
        self.patches.append((path, data))
        self.detail.update(data)
        if self.corrupt_after_patch:
            self.detail[self.corrupt_after_patch] = "wrong"
        return dict(self.detail)


class FakeCreateClient:
    def __init__(
        self,
        *,
        action: str = "created",
        fail_patch: bool = False,
        corrupt_after_patch: str | None = None,
    ) -> None:
        self.action = action
        self.fail_patch = fail_patch
        self.corrupt_after_patch = corrupt_after_patch
        self.patches: list[tuple[str, dict]] = []
        self.detail = {
            "id": 6001,
            "model_name": "Echo 3",
            "status": "pending_review",
            "image": "",
            "images": [],
            "s3_image": None,
            "photos": [],
        }

    def bulk_import_robots(self, rows: list[dict], **kwargs: object) -> dict:
        self.detail["notes"] = rows[0]["notes"]
        self.detail["videos"] = [
            {"id": index, "url": url}
            for index, url in enumerate(rows[0].get("video_urls") or [], start=1)
        ]
        return {
            "error_count": 0,
            "results": [{"id": 6001, "action": self.action}],
        }

    def _get(self, path: str) -> dict:
        return dict(self.detail)

    def _patch(self, path: str, data: dict) -> dict:
        self.patches.append((path, dict(data)))
        if self.fail_patch:
            raise RuntimeError("detail patch rejected")
        self.detail.update(data)
        self.detail["availability_status"] = {"id": data["availability_status"]}
        self.detail["manufacturer_country_ref"] = {
            "id": data["manufacturer_country_ref"]
        }
        self.detail["manufacturer_countries"] = [
            {"id": value} for value in data["manufacturer_countries"]
        ]
        for field in ("categories", "uses", "industries", "movement_types"):
            self.detail[field] = [
                {"id": value} if isinstance(value, int) else value
                for value in data[field]
            ]
        if self.corrupt_after_patch:
            self.detail[self.corrupt_after_patch] = "wrong"
        return dict(self.detail)


class FakeVideoClient(FakeClient):
    def __init__(self, detail: dict) -> None:
        super().__init__(detail)
        self.bulk_calls: list[tuple[list[dict], dict]] = []

    def bulk_import_robots(self, rows: list[dict], **kwargs: object) -> dict:
        self.bulk_calls.append((rows, kwargs))
        self.detail["videos"] = [
            {
                "id": index,
                "url": item["url"] if isinstance(item, dict) else item,
                "title": item.get("title", "") if isinstance(item, dict) else "",
                "description": (
                    item.get("description", "") if isinstance(item, dict) else ""
                ),
            }
            for index, item in enumerate(rows[0]["video_urls"], start=1)
        ]
        return {
            "error_count": 0,
            "results": [{"id": self.detail["id"], "action": "updated"}],
        }


def test_second_reconcile_has_no_missing_models() -> None:
    initial = load_existing_fixture()
    plan = reconcile(initial)
    rows = list(initial)
    for offset, model in enumerate(plan.missing, start=6000):
        row = new_record(model, country_id=45)
        row["id"] = offset
        rows.append(row)
    after = reconcile(rows)
    assert len(after.current_existing) == 42
    assert after.missing == ()


def test_apply_refuses_status_drift_before_patch() -> None:
    planned = load_existing_fixture()[-4]
    assert planned["status"] == "pending_review"
    client = FakeClient({**planned, "status": "published"})
    with pytest.raises(RuntimeError, match="status invariant"):
        apply_existing_record(
            client,
            planned,
            catalog_by_code()["e03pro"],
            country_id=45,
            taxonomy=TAXONOMY,
        )
    assert client.patches == []


def test_apply_does_not_patch_media_fields() -> None:
    planned = load_existing_fixture()[0]
    client = FakeClient(dict(planned))
    apply_existing_record(
        client,
        planned,
        catalog_by_code()["s30"],
        country_id=45,
        taxonomy=TAXONOMY,
    )
    assert client.patches
    patched_fields = set().union(*(payload for _, payload in client.patches))
    assert not ({"image", "images", "s3_image"} & patched_fields)


def test_imageless_existing_record_gets_actionable_license_note() -> None:
    planned = {
        **load_existing_fixture()[7],
        "image": "",
        "images": [],
        "s3_image": None,
        "photos": [],
        "notes": "Existing research note",
    }
    client = FakeClient(dict(planned))
    apply_existing_record(
        client,
        planned,
        catalog_by_code()["e15"],
        country_id=45,
        taxonomy=TAXONOMY,
    )
    assert client.detail["notes"].startswith("Existing research note")
    assert "[IMAGE TO-DO — no hero, deliberate]" in client.detail["notes"]


def test_existing_apply_fails_when_factual_verification_mismatches() -> None:
    planned = load_existing_fixture()[0]
    client = FakeClient(dict(planned), corrupt_after_patch="purpose")

    with pytest.raises(RuntimeError, match="purpose verification failed"):
        apply_existing_record(
            client,
            planned,
            catalog_by_code()["s30"],
            country_id=45,
            taxonomy=TAXONOMY,
        )


@pytest.mark.parametrize("field", ["name", "description", "features", "url"])
def test_existing_apply_verifies_canonical_text_and_official_url(field: str) -> None:
    planned = load_existing_fixture()[0]
    client = FakeClient(dict(planned), corrupt_after_patch=field)

    with pytest.raises(RuntimeError, match=rf"{field} verification failed"):
        apply_existing_record(
            client,
            planned,
            catalog_by_code()["s30"],
            country_id=45,
            taxonomy=TAXONOMY,
        )


def test_existing_catalog_video_is_preserved_while_factual_patch_continues() -> None:
    planned = next(
        row for row in load_existing_fixture() if row["model_name"] == "E10L-Pro"
    )
    unrelated = "https://www.youtube.com/watch?v=keep-valid"
    client = FakeVideoClient(
        {
            **planned,
            "videos": [
                {
                    "id": 77,
                    "url": unrelated,
                    "title": "Keep valid",
                    "description": "Existing unrelated valid video",
                }
            ],
        }
    )
    model = catalog_by_code()["e10lpro"]

    before_videos = list(client.detail["videos"])
    result = apply_existing_record(
        client,
        planned,
        model,
        country_id=45,
        taxonomy=TAXONOMY,
    )

    assert client.bulk_calls == []
    assert len(client.patches) == 1
    assert client.patches[0][1]["url"] == model["family_url"]
    assert client.detail["videos"] == before_videos
    assert result["videos"] == before_videos


def test_existing_video_verification_requires_all_rows_unchanged() -> None:
    before = [
        {
            "id": 77,
            "url": "https://www.youtube.com/watch?v=keep-valid",
            "title": "Keep valid",
            "description": "Existing unrelated valid video",
            "is_primary": True,
            "order": 0,
            "created_by": "curator",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-02T00:00:00Z",
        }
    ]
    huayan.verify_existing_videos_unchanged(before, list(before))

    mutated = [{**before[0], "order": 1}]
    with pytest.raises(RuntimeError, match="pre-existing video row changed"):
        huayan.verify_existing_videos_unchanged(before, mutated)
    with pytest.raises(RuntimeError, match="video row set changed"):
        huayan.verify_existing_videos_unchanged(before, [])


def test_final_verification_checks_existing_factual_fields() -> None:
    planned = load_existing_fixture()[0]
    model = catalog_by_code()["s30"]
    client = FakeClient(dict(planned))
    applied = apply_existing_record(
        client,
        planned,
        model,
        country_id=45,
        taxonomy=TAXONOMY,
    )
    applied["purpose"] = "wrong"
    final_plan = huayan.Reconciliation(((applied, model),), (), (), ())

    with pytest.raises(RuntimeError, match="purpose verification failed"):
        huayan.verify_final_current_records(
            final_plan,
            country_id=45,
            taxonomy_by_family={"S": TAXONOMY},
            expected_status_by_id={int(planned["id"]): str(planned["status"])},
            expected_media_by_id={
                int(planned["id"]): {
                    field: planned.get(field)
                    for field in ("image", "images", "s3_image")
                }
            },
        )


def test_relation_ids_accepts_serialized_relations() -> None:
    assert relation_ids([{"id": 4, "name": "A"}, 5, "6", {"name": "missing"}]) == [
        4,
        5,
        6,
    ]


def test_new_record_is_detail_patched_then_get_verified() -> None:
    client = FakeCreateClient()
    model = catalog_by_code()["echo3"]
    taxonomy = {
        "categories": [1],
        "uses": [2],
        "industries": [3],
        "movement_types": [4],
        "tags": ["7-Axis", "Robot Arm"],
    }

    result = apply_new_record(
        client,
        model,
        country_id=45,
        taxonomy=taxonomy,
    )

    assert result == {"id": 6001, "action": "created"}
    assert len(client.patches) == 1
    path, payload = client.patches[0]
    assert path == "robots/robots/6001/"
    assert payload["payload_kg"] == 3
    assert payload["reach_mm"] == 555
    assert payload["dof"] == 7
    assert payload["family_key"] == "huayan-robotics:echo"
    assert payload["availability_status"] == 11
    assert payload["tags"] == ["7-Axis", "Robot Arm"]
    assert not ({"image", "images", "s3_image", "photos"} & set(payload))


def test_new_record_imports_and_verifies_exact_catalog_video_once() -> None:
    client = FakeCreateClient()
    model = catalog_by_code()["e10lpro"]

    apply_new_record(
        client,
        model,
        country_id=45,
        taxonomy=TAXONOMY,
    )

    assert [video["url"] for video in client.detail["videos"]] == model["videos"]


def test_new_record_post_create_patch_failure_is_not_success() -> None:
    client = FakeCreateClient(fail_patch=True)

    with pytest.raises(RuntimeError, match="detail patch rejected"):
        apply_new_record(
            client,
            catalog_by_code()["echo3"],
            country_id=45,
            taxonomy={
                "categories": [1],
                "uses": [2],
                "industries": [3],
                "movement_types": [4],
                "tags": ["7-Axis"],
            },
        )


@pytest.mark.parametrize("field", ["name", "description", "features", "url"])
def test_new_record_verifies_canonical_text_and_official_url(field: str) -> None:
    client = FakeCreateClient(corrupt_after_patch=field)

    with pytest.raises(RuntimeError, match=rf"{field} verification failed"):
        apply_new_record(
            client,
            catalog_by_code()["echo3"],
            country_id=45,
            taxonomy={
                "categories": [1],
                "uses": [2],
                "industries": [3],
                "movement_types": [4],
                "tags": ["7-Axis"],
            },
        )


def test_partial_create_is_reported_with_id_and_not_as_created() -> None:
    client = FakeCreateClient(fail_patch=True)
    report = {"created": [], "partial_writes": []}

    with pytest.raises(RuntimeError, match="detail patch rejected"):
        huayan.apply_missing_model(
            client,
            catalog_by_code()["echo3"],
            country_id=45,
            taxonomy={
                "categories": [1],
                "uses": [2],
                "industries": [3],
                "movement_types": [4],
                "tags": ["7-Axis"],
            },
            report=report,
        )

    assert report["created"] == []
    assert report["partial_writes"] == [
        {
            "id": 6001,
            "model": "Echo 3",
            "action": "created",
            "failed_stage": "post_create_patch_or_verification",
            "error": "detail patch rejected",
        }
    ]


def test_new_record_retry_accepts_bulk_import_updated_action_idempotently() -> None:
    client = FakeCreateClient(action="updated")

    result = apply_new_record(
        client,
        catalog_by_code()["echo3"],
        country_id=45,
        taxonomy={
            "categories": [1],
            "uses": [2],
            "industries": [3],
            "movement_types": [4],
            "tags": ["7-Axis"],
        },
    )

    assert result == {"id": 6001, "action": "updated"}
    assert len(client.patches) == 1
