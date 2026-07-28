"""Tests for Huayan candidate-only image staging."""
from __future__ import annotations

import io
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from PIL import Image

RESEARCH_DIR = Path(__file__).resolve().parents[1]
if str(RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(RESEARCH_DIR))

import stage_huayan_1490_image_candidates as stage


def _png(width: int = 12, height: int = 8) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(output, format="PNG")
    return output.getvalue()


class FakeResponse:
    def __init__(
        self,
        content: bytes,
        status_code: int = 200,
        *,
        url: str | None = None,
    ) -> None:
        self.content = content
        self.status_code = status_code
        self.url = url


def _production_rows(manifest: dict) -> list[dict]:
    return [
        {
            "id": entry["robot_id"],
            "name": entry["model"],
            "model_name": entry["model"],
            "status": "pending_review",
            "image": "",
            "images": [],
            "s3_image": None,
            "photos": [],
        }
        for entry in manifest["candidates"]
    ]


def test_manifest_has_exact_expected_26_ids_and_models() -> None:
    manifest = stage.load_manifest()

    assert {
        (entry["robot_id"], entry["model"])
        for entry in manifest["candidates"]
    } == set(stage.EXPECTED_ROBOTS.items())
    assert len(manifest["candidates"]) == 26


def test_manifest_uses_exact_backend_candidate_contract() -> None:
    manifest = stage.load_manifest()

    for entry in manifest["candidates"]:
        candidate = entry["candidate"]
        assert set(candidate) == set(stage.CANDIDATE_KEYS)
        assert candidate["source_tier"] == "official_exact"
        assert candidate["media_class"] == "official_render"
        assert candidate["image_scope"] == "exact_variant"
        assert candidate["rights_status"] == "review_required"
        assert isinstance(candidate["confidence_score"], int)
        assert 0 <= candidate["confidence_score"] <= 69
        assert candidate["match_reason"]


def test_future_bulk_rows_are_minimal_candidate_only_payloads() -> None:
    rows = stage.build_bulk_rows(stage.load_manifest())

    assert len(rows) == 26
    for row in rows:
        assert set(row) == {
            "id",
            "name",
            "company_id",
            "company_slug",
            "company_name",
            "images",
        }
        assert len(row["images"]) == 1
        assert set(row["images"][0]) == set(stage.CANDIDATE_KEYS)
        assert not (stage.FORBIDDEN_BULK_FIELDS & set(row))


def test_validate_rejects_duplicate_content_hashes() -> None:
    manifest = deepcopy(stage.load_manifest())
    for entry in manifest["candidates"]:
        entry["image_width_px"] = 12
        entry["image_height_px"] = 8
    production = _production_rows(manifest)

    report = stage.validate_manifest(
        manifest,
        production,
        fetch_image=lambda _url: FakeResponse(_png()),
    )

    assert report["valid"] is False
    assert report["staging_ready"] is False
    assert report["bulk_import_rows"] == []
    assert len(report["hash_collisions"]) == 1
    assert report["hash_count"] == 1


def test_validate_accepts_unique_images_and_matches_dimensions() -> None:
    manifest = stage.load_manifest()
    production = _production_rows(manifest)
    payload_by_url = {
        entry["candidate"]["url"]: _png(index + 10, index + 20)
        for index, entry in enumerate(manifest["candidates"])
    }
    adjusted = deepcopy(manifest)
    for entry in adjusted["candidates"]:
        with Image.open(io.BytesIO(payload_by_url[entry["candidate"]["url"]])) as image:
            entry["image_width_px"], entry["image_height_px"] = image.size

    report = stage.validate_manifest(
        adjusted,
        production,
        fetch_image=lambda url: FakeResponse(payload_by_url[url]),
        checked_production_endpoint="https://ragadmin.robotaigeek.com/api/v1/",
    )

    assert report["valid"] is True
    assert report["staging_ready"] is True
    assert report["checked_production_endpoint"] == (
        "https://ragadmin.robotaigeek.com/api/v1/"
    )
    assert report["confidence_score_range"] == {"min": 69, "max": 69}
    assert len(report["bulk_import_rows"]) == 26
    assert report["candidate_count"] == 26
    assert report["hash_count"] == 26
    assert report["failed_urls"] == []
    assert report["hash_collisions"] == []


@pytest.mark.parametrize(
    ("mutator", "expected_error"),
    [
        (
            lambda manifest: manifest["candidates"][0]["candidate"].update(
                {"url": "http://www.huayan-robotics.com/image.png"}
            ),
            "HTTPS",
        ),
        (
            lambda manifest: manifest["candidates"][0]["candidate"].update(
                {"rights_status": "official_source"}
            ),
            "review_required",
        ),
        (
            lambda manifest: manifest["candidates"][0]["candidate"].update(
                {"confidence_score": 70}
            ),
            "hard cap",
        ),
        (
            lambda manifest: manifest["candidates"][0]["candidate"].update(
                {"s3_image": "robots/copied.png"}
            ),
            "candidate keys",
        ),
    ],
)
def test_static_validation_fails_closed(mutator, expected_error: str) -> None:
    manifest = deepcopy(stage.load_manifest())
    mutator(manifest)

    errors = stage.validate_static_manifest(manifest)

    assert any(expected_error in error for error in errors)


def test_manual_exactness_caveats_cover_required_models() -> None:
    manifest = stage.load_manifest()
    caveated = {
        entry["model"]
        for entry in manifest["candidates"]
        if entry["manual_exactness_review"]
    }

    assert stage.REQUIRED_MANUAL_REVIEW_MODELS <= caveated


def test_production_validation_does_not_require_rights_fields() -> None:
    manifest = stage.load_manifest()

    result = stage.validate_production_rows(_production_rows(manifest), manifest)

    assert result["errors"] == []
    assert result["rights_status_serialized"] is False
    assert result["production_rights_workflow_ready"] is False


def test_production_validation_rejects_identity_status_or_media_drift() -> None:
    manifest = stage.load_manifest()
    rows = _production_rows(manifest)
    rows[0]["model_name"] = "Wrong model"
    rows[1]["status"] = "published"
    rows[2]["image"] = "https://cdn.example/image.png"

    result = stage.validate_production_rows(rows, manifest)

    assert any("identity" in error for error in result["errors"])
    assert any("status" in error for error in result["errors"])
    assert any("imageless" in error for error in result["errors"])


@pytest.mark.parametrize(
    "url",
    [
        "http://ragadmin.robotaigeek.com/api/v1/",
        "https://localhost:8000/api/v1/",
        "https://api-dev.robotaigeek.com/api/v1/",
        "https://staging.robotaigeek.com/api/v1/",
        "https://example.com/api/v1/",
    ],
)
def test_production_endpoint_rejects_nonproduction_urls_before_session(
    monkeypatch,
    url: str,
) -> None:
    monkeypatch.setattr(
        stage.requests,
        "Session",
        lambda: pytest.fail("session must not be created for unsafe endpoint"),
    )

    with pytest.raises(ValueError, match="production API endpoint"):
        stage.fetch_production_rows(base_url=url)


def test_production_endpoint_normalizes_exact_allowlisted_host() -> None:
    assert stage.normalize_production_endpoint(
        "https://RAGADMIN.robotaigeek.com/api/v1"
    ) == "https://ragadmin.robotaigeek.com/api/v1/"


def test_redirected_image_must_remain_https() -> None:
    manifest = stage.load_manifest()
    production = _production_rows(manifest)

    report = stage.validate_manifest(
        manifest,
        production,
        fetch_image=lambda url: FakeResponse(
            _png(280, 436),
            url=url.replace("https://", "http://"),
        ),
    )

    assert report["staging_ready"] is False
    assert report["bulk_import_rows"] == []
    assert any("redirected image URL must use HTTPS" in row["error"] for row in report["failed_urls"])


def test_cli_has_no_apply_mode() -> None:
    parser = stage.build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["--apply"])
