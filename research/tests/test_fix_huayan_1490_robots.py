"""Tests for Huayan Robotics company 1490's static catalog contract."""

from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path

RESEARCH_DIR = Path(__file__).resolve().parents[1]
if str(RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(RESEARCH_DIR))

import fix_huayan_1490_robots as huayan
import huayan_1490_catalog as catalog


class PartialTagCatalogClient:
    def list_tags(self) -> list[dict]:
        return [
            {"id": 1, "name": name}
            for names in huayan.FAMILY_TAG_NAMES.values()
            for name in names
            if name != "Industrial Arm"
        ]


def test_fixer_uses_only_the_authoritative_catalog_contract() -> None:
    assert huayan.CATALOG is catalog.CATALOG
    assert huayan.EXISTING_ID_BY_MODEL is catalog.EXISTING_ID_BY_MODEL
    assert not hasattr(huayan, "CURRENT_MODELS")
    assert not hasattr(huayan, "validate_catalog")


def test_payload_builders_copy_catalog_without_mutating_it() -> None:
    model = deepcopy(huayan.catalog_by_code()["e03"])

    payload = huayan.new_record(model, country_id=45)

    assert model == huayan.catalog_by_code()["e03"]
    assert payload["model_name"] == "E03"


def test_tag_resolution_fails_closed_with_exact_missing_names() -> None:
    try:
        huayan.resolve_family_tag_names(PartialTagCatalogClient())
    except RuntimeError as exc:
        assert str(exc) == "unresolved Huayan tag name(s): Industrial Arm"
    else:
        raise AssertionError("partial tag resolution must fail closed")
