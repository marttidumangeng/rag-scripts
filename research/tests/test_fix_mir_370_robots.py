"""Regression tests for MiR company 370 catalog curation."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

RESEARCH_DIR = Path(__file__).resolve().parents[1]
if str(RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(RESEARCH_DIR))

import fix_mir_370_robots as mir


def test_identity_plan_keeps_canonical_mir_products() -> None:
    assert set(mir.PRODUCTS) == {4233, 4234, 4235, 4237, 2142, 2146, 2151}
    assert set(mir.REJECTS) == {4653, 4652, 4238, 4236}
    assert set(mir.REPARENT) == {3329, 3330}


def test_current_mir_specs_use_exact_oem_values() -> None:
    assert mir.PRODUCTS[2142]["typed"] == {
        "payload_kg": 250,
        "weight_kg": 94,
        "speed": 7.2,
        "length_mm": 800,
        "width_mm": 580,
        "height_mm": 300,
        "runtime_minutes": 780,
    }
    assert mir.PRODUCTS[2146]["typed"]["payload_kg"] == 600
    assert mir.PRODUCTS[2151]["typed"]["payload_kg"] == 1350


def test_media_is_blocked_without_republication_permission() -> None:
    for data in [*mir.PRODUCTS.values(), *mir.REPARENT.values()]:
        assert not data.get("image")
        assert "written permission" in data["notes"].lower()


def test_mir1000_duplicates_keep_published_record() -> None:
    assert "244" in mir.REJECTS[4236]
    assert "244" in mir.REJECTS[4653]


def test_mir1200_pallet_jack_has_exact_current_official_fields() -> None:
    data = mir.NEW_PRODUCTS["MiR1200 Pallet Jack"]

    assert data["name"] == "MiR1200 Pallet Jack"
    assert data["model_name"] == "MiR1200 Pallet Jack"
    assert data["variant_code"] == "MiR1200 Pallet Jack"
    assert data["url"] == (
        "https://mobile-industrial-robots.com/products/robots/"
        "mir1200-pallet-jack/"
    )
    assert data["family_key"] == (
        "mobile-industrial-robots:mir1200-pallet-jack"
    )
    assert data["family_name"] == "MiR1200 Pallet Jack"
    assert data["family_url"] == data["url"]
    assert data["product_url_scope"] == "exact_variant"
    assert data["availability_status"] == 11
    assert data["release_year"] == 2024
    assert data["category_slugs"] == "industrial-robots|mobile-robots"
    assert data["sub_category_slug"] == "logistics-warehouse"
    assert data["typed"] == {
        "payload_kg": 1200,
        "weight_kg": 750,
        "speed": 5.4,
        "length_mm": 1934,
        "width_mm": 820,
        "height_mm": 2120,
        "runtime_minutes": 600,
        "ip_rating": "IP52",
    }
    assert "AI-based perception" in data["features"]
    assert "driverless conveyance of heavy loads" in data["description"]
    assert data["purpose"] == (
        "Floor-to-floor pallet transport\n"
        "Finished-goods and raw-material movement\n"
        "Waste-disposal pallet movement"
    )
    assert data["sources"] == [
        data["url"],
        f"{data['url']}specifications",
        (
            "https://mobile-industrial-robots.com/blog/"
            "mir1200-pallet-jack-using-ai-to-revolutionize-pallet-handling"
        ),
        (
            "https://investors.teradyne.com/news-events/press-releases/"
            "detail/32/teradyne-robotics-to-bring-the-power-of-ai-to-"
            "robotics-with-nvidia"
        ),
    ]


def test_mir1200_create_only_dedupe_uses_exact_identity_and_model() -> None:
    assert len(mir.build_create_only_rows([])) == 1
    assert mir.build_create_only_rows(
        [
            {
                "name": "MiR1200 Pallet Jack",
                "model_name": "MiR1200 Pallet Jack",
            }
        ]
    )
    assert len(
        mir.build_create_only_rows(
            [{"name": "MiR1200", "model_name": "MiR1200"}]
        )
    ) == 1
    assert len(
        mir.build_create_only_rows(
            [
                {
                    "company_slug": "different-company",
                    "name": "MiR1200 Pallet Jack",
                    "model_name": "MiR1200 Pallet Jack",
                }
            ]
        )
    ) == 1


def test_every_nonempty_candidate_is_exact_model_specific_and_unique() -> None:
    retained = {
        **{f"mir:{robot_id}": data for robot_id, data in mir.PRODUCTS.items()},
        **{
            f"enabled:{robot_id}": data
            for robot_id, data in mir.REPARENT.items()
        },
        **{
            f"new:{model}": data
            for model, data in mir.NEW_PRODUCTS.items()
        },
    }
    urls: list[str] = []
    required = {
        "url",
        "rights_status",
        "source_page_url",
        "source_tier",
        "source_publisher",
        "image_scope",
        "media_class",
        "confidence_score",
        "match_reason",
        "description",
    }

    for label, data in retained.items():
        assert "images" in data, label
        for candidate in data["images"]:
            assert required <= set(candidate), label
            assert candidate["url"].startswith("https://"), label
            assert candidate["source_page_url"].startswith("https://"), label
            assert candidate["match_reason"], label
            assert candidate["description"], label
            assert candidate["image_scope"] == "exact_variant", label
            assert candidate["source_tier"] != "official_family", label
            assert candidate["media_class"] != "family_photo", label
            assert "sibling" not in candidate["match_reason"].lower(), label
            assert candidate["rights_status"] in {
                "permission_confirmed",
                "review_required",
                "restricted",
            }
            urls.append(candidate["url"])

    assert len(urls) == len(set(urls))


def test_enabled_products_stage_empty_candidates_with_actionable_search_notes() -> None:
    expected_sources = {
        3329: [
            "https://www.enabled-robotics.com/er-flex",
            "https://www.enabled-robotics.com/partnernetwork",
            "https://www.enabled-robotics.com/mobilecobots",
        ],
        3330: [
            "https://www.enabled-robotics.com/er-max",
            "https://www.enabled-robotics.com/partnernetwork",
            "https://www.enabled-robotics.com/mobilecobots",
        ],
    }

    for robot_id, sources in expected_sources.items():
        data = mir.REPARENT[robot_id]
        assert data["images"] == []
        search = data["image_candidate_search"]
        assert search["result"] == "no_exact_model_candidate_proven"
        assert search["source_pages"] == sources
        note = search["actionable_note"].lower()
        assert data["model_name"].lower() in note
        assert data["variant_code"].lower() in note
        assert "written approval" in note
        assert "exact-model" in note
        assert "sibling" in note


def test_mir500_commons_candidate_has_complete_cc_by_sa_attribution() -> None:
    candidate = mir.PRODUCTS[4235]["images"][0]

    assert candidate["url"] == (
        "https://upload.wikimedia.org/wikipedia/commons/0/0f/"
        "MiR_500_at_automatica_tradeshow_2018.jpg"
    )
    assert candidate["source_page_url"] == (
        "https://commons.wikimedia.org/wiki/"
        "File:MiR_500_at_automatica_tradeshow_2018.jpg"
    )
    assert candidate["rights_status"] == "permission_confirmed"
    assert candidate["source_tier"] == "reputable_third_party"
    assert candidate["source_publisher"] == (
        "Wikimedia Commons / Fernando Fandiño Oliver"
    )
    rights_note = candidate["description"]
    assert "Fernando Fandiño Oliver" in rights_note
    assert "CC BY-SA 4.0" in rights_note
    assert "https://creativecommons.org/licenses/by-sa/4.0" in rights_note
    assert "not an OEM-owned image" in rights_note
    assert "indicate changes" in rights_note
    assert "share alike" in rights_note.lower()


def test_unlicensed_official_and_press_images_require_review() -> None:
    candidates = [
        candidate
        for data in [
            *mir.PRODUCTS.values(),
            *mir.REPARENT.values(),
            *mir.NEW_PRODUCTS.values(),
        ]
        for candidate in data["images"]
        if "Wikimedia Commons" not in candidate["source_publisher"]
    ]

    assert candidates
    for candidate in candidates:
        assert candidate["rights_status"] == "review_required"
        assert candidate["confidence_score"] <= 69
        note = candidate["description"].lower()
        assert "written permission" in note or "written approval" in note


def test_apply_is_disabled_before_client_or_production_write(monkeypatch) -> None:
    class ForbiddenClient:
        def __init__(self) -> None:
            raise AssertionError("client must not be created for disabled apply")

    monkeypatch.setattr(mir, "ResearchApiClient", ForbiddenClient)

    with pytest.raises(SystemExit, match="production apply is disabled"):
        mir.main(["--apply"])


def test_dry_run_is_local_only_and_writes_valid_staging_json(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    report_path = tmp_path / "mir-report.json"
    staging_path = tmp_path / "mir1200-pallet-jack.json"
    identities_path = tmp_path / "mir-existing-identities.json"
    identities_path.write_text(
        json.dumps(
            {
                "snapshot_id": "test-mir-catalog-before-mir1200",
                "company_id": 370,
                "identities": [
                    {
                        "company_slug": "mobile-industrial-robots",
                        "name": "MiR250",
                        "model_name": "MiR250",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    class ForbiddenClient:
        def __init__(self) -> None:
            raise AssertionError("dry-run must not create an API client")

    monkeypatch.setattr(mir, "ResearchApiClient", ForbiddenClient)
    monkeypatch.setattr(mir, "REPORT", report_path)
    monkeypatch.setattr(mir, "MIR1200_STAGING", staging_path)
    monkeypatch.setattr(mir, "IDENTITIES_SNAPSHOT", identities_path)

    assert mir.main([]) == 0

    report = json.loads(report_path.read_text(encoding="utf-8"))
    staged = json.loads(staging_path.read_text(encoding="utf-8"))
    output = capsys.readouterr().out.lower()
    assert report["mode"] == "local-staging-dry-run"
    assert report["production_apply"] is False
    assert report["production_records_mutated"] is False
    assert report["mir1200"]["create_only"] is True
    assert report["mir1200"]["dedupe_snapshot_id"] == (
        "test-mir-catalog-before-mir1200"
    )
    assert report["mir1200"]["dedupe_result"] == "stage_create"
    assert len(report["candidate_mappings"]) == 10
    assert "Enabled Robotics candidate lists are intentionally empty" in (
        report["media_policy"]
    )
    assert staged["status"] == "pending_review"
    assert staged["name"] == "MiR1200 Pallet Jack"
    assert staged["import_metadata"] == {
        "mode": "create_only",
        "natural_key_fields": ["company_slug", "name", "model_name"],
        "natural_key": {
            "company_slug": "mobile-industrial-robots",
            "name": "MiR1200 Pallet Jack",
            "model_name": "MiR1200 Pallet Jack",
        },
        "dedupe_snapshot_id": "test-mir-catalog-before-mir1200",
    }
    assert staged["images"] == mir.NEW_PRODUCTS["MiR1200 Pallet Jack"]["images"]
    assert [source["url"] for source in staged["sources"]] == (
        mir.NEW_PRODUCTS["MiR1200 Pallet Jack"]["sources"]
    )
    assert "specifications" in staged["research_notes"]
    first_artifact = staging_path.read_bytes()

    assert mir.main([]) == 0
    assert staging_path.read_bytes() == first_artifact
    assert "local staging" in output
    assert "no production apply" in output


def test_main_skips_exact_snapshot_identity_and_removes_stale_create_artifact(
    monkeypatch, tmp_path: Path
) -> None:
    report_path = tmp_path / "mir-report.json"
    staging_path = tmp_path / "mir1200-pallet-jack.json"
    staging_path.write_text('{"stale": true}\n', encoding="utf-8")
    identities_path = tmp_path / "mir-existing-identities.json"
    identities_path.write_text(
        json.dumps(
            {
                "snapshot_id": "test-mir-catalog-with-mir1200",
                "company_id": 370,
                "identities": [
                    {
                        "company_slug": "mobile-industrial-robots",
                        "name": "MiR1200 Pallet Jack",
                        "model_name": "MiR1200 Pallet Jack",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(mir, "REPORT", report_path)
    monkeypatch.setattr(mir, "MIR1200_STAGING", staging_path)
    monkeypatch.setattr(mir, "IDENTITIES_SNAPSHOT", identities_path)
    monkeypatch.setattr(
        mir,
        "ResearchApiClient",
        lambda: (_ for _ in ()).throw(AssertionError("no API client")),
    )

    assert mir.main([]) == 0

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["mir1200"]["staged_rows"] == 0
    assert report["mir1200"]["dedupe_result"] == "skip_exact_existing"
    assert report["mir1200"]["dedupe_snapshot_id"] == (
        "test-mir-catalog-with-mir1200"
    )
    assert not staging_path.exists()


def test_main_fails_closed_when_local_identity_snapshot_is_missing(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(mir, "IDENTITIES_SNAPSHOT", tmp_path / "missing.json")
    monkeypatch.setattr(mir, "REPORT", tmp_path / "report.json")
    monkeypatch.setattr(mir, "MIR1200_STAGING", tmp_path / "robot.json")

    with pytest.raises(FileNotFoundError, match="identity snapshot"):
        mir.main([])


def test_identity_snapshot_rejects_rows_without_explicit_company_slug(
    tmp_path: Path,
) -> None:
    snapshot_path = tmp_path / "incomplete-identities.json"
    snapshot_path.write_text(
        json.dumps(
            {
                "snapshot_id": "incomplete-test-snapshot",
                "company_id": 370,
                "identities": [
                    {
                        "name": "MiR1200 Pallet Jack",
                        "model_name": "MiR1200 Pallet Jack",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match=r"identity snapshot row 0 missing required field\(s\): company_slug",
    ):
        mir.load_identity_snapshot(snapshot_path)
