"""Unit tests for validate_staging."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_RESEARCH_DIR = Path(__file__).resolve().parents[1]
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from validate_staging import validate_company, validate_robot, validate_robot_batch  # noqa: E402

VALID_ROBOT = {
    "name": "Go2",
    "company_slug": "unitree-robotics",
    "description": "Quadruped",
    "sources": [{"url": "https://www.unitree.com/go2"}],
}

VALID_COMPANY = {
    "id": 1,
    "name": "Unitree Robotics",
    "description": "Robotics company",
    "website": "https://www.unitree.com",
    "sources": [{"url": "https://www.unitree.com/about"}],
}


def test_validate_robot_ok():
    result = validate_robot(VALID_ROBOT)
    assert result.ok
    assert not result.errors()


def test_validate_robot_missing_name():
    result = validate_robot({**VALID_ROBOT, "name": ""})
    assert not result.ok
    assert any(i.field == "name" for i in result.errors())


def test_validate_robot_missing_sources():
    result = validate_robot({**VALID_ROBOT, "sources": []})
    assert not result.ok


def test_validate_robot_invalid_source_url():
    result = validate_robot({**VALID_ROBOT, "sources": [{"url": "not-a-url"}]})
    assert not result.ok


def test_validate_robot_warnings_for_missing_image():
    result = validate_robot(VALID_ROBOT)
    assert any(i.field == "image" for i in result.warnings())


def test_uncited_release_year_warns_that_it_will_be_dropped():
    # Tally 2026-10-14: 'release_year=2017 = first deployment' is not the
    # 'release_year=YYYY:' citation the importer needs, so the year was dropped.
    result = validate_robot({
        **VALID_ROBOT, "release_year": 2017,
        "research_notes": "release_year=2017 = first commercial deployment",
    })
    warning = next(i for i in result.warnings() if i.field == "release_year")
    assert "will NOT be imported" in warning.message
    assert "release_year=2017:" in warning.message


def test_cited_release_year_has_no_warning():
    result = validate_robot({
        **VALID_ROBOT, "release_year": 2020,
        "research_notes": "release_year=2020: The Spoon, 2020-01-06 (https://thespoon.tech/x)",
    })
    assert not any(i.field == "release_year" for i in result.warnings())


def test_citation_for_another_year_still_warns():
    result = validate_robot({
        **VALID_ROBOT, "release_year": 2025,
        "notes": "release_year=2021: launch coverage (https://x.com)",
    })
    assert any(i.field == "release_year" for i in result.warnings())


def test_no_release_year_no_warning():
    result = validate_robot(VALID_ROBOT)
    assert not any(i.field == "release_year" for i in result.warnings())


def test_validate_company_ok():
    result = validate_company(VALID_COMPANY)
    assert result.ok


def test_validate_company_missing_sources():
    result = validate_company({**VALID_COMPANY, "sources": []})
    assert not result.ok


def test_validate_batch_rejects_duplicates():
    result = validate_robot_batch([VALID_ROBOT, VALID_ROBOT])
    assert not result.ok
    assert any("duplicate" in i.field for i in result.errors())
