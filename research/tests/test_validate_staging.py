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
