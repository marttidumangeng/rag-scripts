"""Unit tests for map_to_bulk_import."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_RESEARCH_DIR = Path(__file__).resolve().parents[1]
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from map_to_bulk_import import (  # noqa: E402
    AI_RESEARCH_PREFIX,
    canonical_robot_key,
    staging_dict_to_bulk_import_row,
    staging_robot_to_bulk_import_row,
    staging_robots_to_bulk_import_rows,
)
from schema import ImageCandidate, StagedRobot, SourceRef  # noqa: E402


SAMPLE = {
    "name": "Go2",
    "model_name": "Go2",
    "company_name": "Unitree Robotics",
    "company_slug": "unitree-robotics",
    "manufacturer_country_code": "CN",
    "url": "https://www.unitree.com/go2",
    "image": "https://www.unitree.com/images/go2.jpg",
    "description": "Quadruped robot",
    "purpose": "Research and delivery",
    "movement_type_keys": "legged",
    "industry_keys": "research",
    "sub_category_slug": "personal-assistants",
    "price_min": 1600,
    "price_max": 2800,
    "price_currency": "USD",
    "weight_kg": 15,
    "sensors": ["lidar", "depth camera"],
    "materials": ["aluminum"],
    "sources": [{"url": "https://www.unitree.com/go2", "type": "website"}],
    "research_notes": "Price from product page",
}


def test_staging_to_bulk_import_row_core_fields():
    row = staging_dict_to_bulk_import_row(SAMPLE)
    assert row["name"] == "Go2"
    assert row["company_slug"] == "unitree-robotics"
    assert row["manufacturer_country_code"] == "CN"
    assert row["price_min"] == 1600
    assert row["sensors"] == ["lidar", "depth camera"]
    assert row["information_source_urls"] == "https://www.unitree.com/go2"


def test_family_metadata_round_trips_to_bulk_import_row():
    family_fields = {
        "family_name": "Go Series",
        "family_key": "unitree-robotics:go-series",
        "variant_code": "Go2-W",
        "variant_label": "Wheeled inspection variant",
        "family_url": "https://www.unitree.com/go-series",
        "product_url_scope": "exact_variant",
    }

    robot = StagedRobot.from_dict({**SAMPLE, **family_fields})
    staged = robot.to_dict()
    row = staging_robot_to_bulk_import_row(robot)

    for key, value in family_fields.items():
        assert staged[key] == value
        assert row[key] == value


def test_notes_prefixed_with_ai_research():
    row = staging_dict_to_bulk_import_row(SAMPLE)
    assert row["notes"].startswith(AI_RESEARCH_PREFIX)
    assert "Price from product page" in row["notes"]
    assert "https://www.unitree.com/go2" in row["notes"]


def test_empty_fields_omitted():
    row = staging_dict_to_bulk_import_row({"name": "X", "company_slug": "x", "sources": [{"url": "https://example.com"}]})
    assert "description" not in row
    assert "price_min" not in row


def test_batch_conversion():
    rows = staging_robots_to_bulk_import_rows([SAMPLE, {"name": "", "company_slug": "x"}])
    assert len(rows) == 1


def test_canonical_robot_key():
    assert canonical_robot_key("Go2", "unitree-robotics") == "unitree-robotics::go2"


def test_uncited_release_year_dropped():
    row = staging_dict_to_bulk_import_row({**SAMPLE, "release_year": 2023})
    assert "release_year" not in row


def test_cited_release_year_kept_with_citation_in_notes():
    row = staging_dict_to_bulk_import_row({
        **SAMPLE,
        "release_year": 2023,
        "research_notes": "release_year=2023: Press release dated 2023-10-05 (https://oem.com/press)",
    })
    assert row["release_year"] == 2023
    assert "release_year=2023:" in row["notes"]


def test_release_year_citation_must_match_year():
    # A citation for a different year doesn't legitimize the staged year
    row = staging_dict_to_bulk_import_row({
        **SAMPLE,
        "release_year": 2025,
        "research_notes": "release_year=2021: launch coverage (https://x.com)",
    })
    assert "release_year" not in row


def test_images_and_videos_in_payload():
    row = staging_dict_to_bulk_import_row({
        **SAMPLE,
        "images": ["https://example.com/a.jpg", "https://example.com/b.jpg"],
        "video_urls": ["https://www.youtube.com/watch?v=abc"],
    })
    assert row["image"] == "https://www.unitree.com/images/go2.jpg"
    assert len(row["images"]) == 3
    assert all(isinstance(item, dict) and "url" in item for item in row["images"])
    assert row["images"][0]["url"] == "https://www.unitree.com/images/go2.jpg"
    assert "youtube.com" in row["video_urls"][0]["url"]
    robot = StagedRobot.from_dict({
        **SAMPLE,
        "sources": ["https://example.com/spec.pdf"],
    })
    row = staging_dict_to_bulk_import_row(robot.to_dict())
    assert "example.com" in row.get("information_source_urls", "")


def test_image_candidate_string_round_trip():
    row = staging_dict_to_bulk_import_row({
        **SAMPLE,
        "images": ["https://example.com/a.jpg", "https://example.com/b.jpg"],
    })
    urls = [item["url"] for item in row["images"]]
    assert "https://example.com/a.jpg" in urls
    assert "https://example.com/b.jpg" in urls
    assert all(set(item.keys()) == {"url"} for item in row["images"] if item["url"].startswith("https://example.com"))


def test_image_candidate_object_metadata_preserved():
    candidate = {
        "url": "https://example.com/product.jpg",
        "source_page_url": "https://example.com/go2",
        "source_tier": "official_exact",
        "source_publisher": "example.com",
        "media_class": "product_photo",
        "image_scope": "exact_variant",
        "confidence_score": 88,
        "confidence_breakdown": {"identity_match": 40, "source_authority": 25},
        "match_reason": "Exact product page hero",
        "rights_status": "official_source",
        "content_hash": "abc123",
        "retrieved_at": "2026-07-15T08:00:00Z",
    }
    row = staging_dict_to_bulk_import_row({
        **SAMPLE,
        "image": "",
        "images": [candidate],
    })
    assert row["image"] == "https://example.com/product.jpg"
    assert len(row["images"]) == 1
    payload_candidate = row["images"][0]
    assert payload_candidate["url"] == candidate["url"]
    assert payload_candidate["source_page_url"] == candidate["source_page_url"]
    assert payload_candidate["confidence_score"] == 88
    assert payload_candidate["confidence_breakdown"]["identity_match"] == 40
    assert payload_candidate["rights_status"] == "official_source"


def test_mixed_string_and_object_images():
    structured = {
        "url": "https://example.com/structured.jpg",
        "source_tier": "official_exact",
        "confidence_score": 82,
        "media_class": "product_photo",
        "image_scope": "exact_variant",
        "rights_status": "official_source",
    }
    row = staging_dict_to_bulk_import_row({
        **SAMPLE,
        "image": "",
        "images": ["https://example.com/plain.jpg", structured],
    })
    by_url = {item["url"]: item for item in row["images"]}
    assert set(by_url) == {
        "https://example.com/plain.jpg",
        "https://example.com/structured.jpg",
    }
    assert by_url["https://example.com/plain.jpg"] == {"url": "https://example.com/plain.jpg"}
    assert by_url["https://example.com/structured.jpg"]["confidence_score"] == 82


def test_staged_robot_from_dict_normalizes_image_candidates():
    robot = StagedRobot.from_dict({
        "name": "Go2",
        "images": [
            "https://example.com/a.jpg",
            {
                "url": "https://example.com/b.jpg",
                "source_tier": "official_exact",
                "confidence_score": 90,
            },
        ],
    })
    assert len(robot.images) == 2
    assert all(isinstance(c, ImageCandidate) for c in robot.images)
    assert robot.images[0].url == "https://example.com/a.jpg"
    assert robot.images[1].source_tier == "official_exact"
    assert robot.images[1].confidence_score == 90


def test_staged_robot_direct_construction_string_images():
    robot = StagedRobot(
        name="Go2",
        company_slug="unitree-robotics",
        images=["https://a.jpg"],
    )
    assert len(robot.images) == 1
    assert isinstance(robot.images[0], ImageCandidate)
    assert robot.images[0].url == "https://a.jpg"
    assert robot.image == ""

    serialized = robot.to_dict()
    assert len(serialized["images"]) == 1
    assert serialized["images"][0] == {"url": "https://a.jpg"}
    assert serialized["image"] == ""

    row = staging_robot_to_bulk_import_row(robot)
    assert "image" not in row
    assert row["images"] == [{"url": "https://a.jpg"}]


def test_confidence_breakdown_empty_dict_round_trip():
    candidate = ImageCandidate(
        url="https://example.com/x.jpg",
        confidence_breakdown={},
    )
    assert candidate.to_dict()["confidence_breakdown"] == {}


def test_hero_from_candidates_when_image_blank():
    row = staging_dict_to_bulk_import_row({
        "name": "Go2",
        "company_slug": "unitree-robotics",
        "images": [
            {
                "url": "https://example.com/low.jpg",
                "confidence_score": 55,
                "media_class": "product_photo",
                "image_scope": "exact_variant",
                "rights_status": "official_source",
            },
            {
                "url": "https://example.com/hero.jpg",
                "confidence_score": 88,
                "media_class": "product_photo",
                "image_scope": "exact_variant",
                "rights_status": "official_source",
                "source_tier": "official_exact",
            },
        ],
        "sources": [{"url": "https://example.com/go2"}],
    })
    assert row["image"] == "https://example.com/hero.jpg"
    image_urls = [item["url"] for item in row["images"]]
    assert "https://example.com/hero.jpg" in image_urls
    assert "https://example.com/low.jpg" in image_urls


def test_hero_official_render_when_primary_eligible():
    row = staging_dict_to_bulk_import_row({
        "name": "Go2",
        "company_slug": "unitree-robotics",
        "images": [
            {
                "url": "https://example.com/render.png",
                "confidence_score": 82,
                "media_class": "official_render",
                "image_scope": "exact_variant",
                "rights_status": "official_source",
                "source_tier": "official_exact",
            },
        ],
        "sources": [{"url": "https://example.com/go2"}],
    })
    assert row["image"] == "https://example.com/render.png"


def test_hero_blank_when_only_technical_drawing():
    row = staging_dict_to_bulk_import_row({
        "name": "Go2",
        "company_slug": "unitree-robotics",
        "images": [
            {
                "url": "https://example.com/drawing.png",
                "confidence_score": 75,
                "media_class": "technical_drawing",
                "image_scope": "exact_variant",
                "rights_status": "official_source",
                "source_tier": "official_exact",
            },
        ],
        "sources": [{"url": "https://example.com/go2"}],
    })
    assert "image" not in row
    assert row["images"][0]["url"] == "https://example.com/drawing.png"


def test_hero_blank_when_only_non_reject_not_primary_eligible():
    row = staging_dict_to_bulk_import_row({
        "name": "Go2",
        "company_slug": "unitree-robotics",
        "images": [
            {
                "url": "https://example.com/low.jpg",
                "confidence_score": 55,
                "media_class": "product_photo",
                "image_scope": "exact_variant",
                "rights_status": "official_source",
            },
        ],
        "sources": [{"url": "https://example.com/go2"}],
    })
    assert "image" not in row
    assert row["images"][0]["url"] == "https://example.com/low.jpg"


# --------------------------------------------------------------------------
# The notes prefix is added HERE, so a writer that also spells it out produced
# "[AI Research] [AI Research] Ingested from ...". Three staging writers do,
# including manufacturer_gap_discovery, so every robot they imported carries
# the doubled prefix in its notes.
# --------------------------------------------------------------------------
def test_notes_prefix_is_not_doubled_when_the_writer_supplied_it():
    row = staging_dict_to_bulk_import_row({
        "name": "TM12",
        "company_slug": "techman-robot",
        "research_notes": "[AI Research] Ingested from Techman Robot's own product JSON API.",
        "sources": [{"url": "https://www.tm-robot.com"}],
    })
    assert row["notes"].count("[AI Research]") == 1
    assert row["notes"].startswith("[AI Research] Ingested from Techman")


def test_notes_prefix_is_still_added_when_the_writer_omitted_it():
    row = staging_dict_to_bulk_import_row({
        "name": "TM12",
        "company_slug": "techman-robot",
        "research_notes": "Ingested from the manufacturer API.",
        "sources": [{"url": "https://www.tm-robot.com"}],
    })
    assert row["notes"].startswith("[AI Research] Ingested from the manufacturer API.")


def test_prefix_inside_the_body_is_left_alone():
    """Only a LEADING prefix is redundant; one quoted mid-sentence is content."""
    row = staging_dict_to_bulk_import_row({
        "name": "TM12",
        "company_slug": "techman-robot",
        "research_notes": "Supersedes the earlier [AI Research] note.",
        "sources": [{"url": "https://www.tm-robot.com"}],
    })
    assert row["notes"].count("[AI Research]") == 2
