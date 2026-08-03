"""Regression tests for the two spec-corruption guards (2026-08-01).

Incident: 61 HD Hyundai robots were imported at 04:59 with specs read from the
manufacturer's own product API. Between 12:30 and 13:13 an enrichment pass
rewrote 10 of them with numbers scraped from page prose:

    HX500        reach 2,704 mm -> 68
    HDX400L-30   400 kg/3,056 mm -> 300 kg/56 mm   (300 kg is HDX300L-30's payload)
    HH012A       12 kg/1,425 mm -> 20 kg/1,742 mm
    YS100A       reach 2,239 mm -> 239

Two independent causes, one test module each half:

  1. `_PAYLOAD_KG_RE` was a bare ``(\\d+)\\s*kg`` — first match anywhere on the
     page won, with no requirement that the number be labelled. The
     `extract_specs_from_text` docstring claimed the patterns "only fire when
     the spec label is present near the number", which was true of reach and
     weight but not payload.
  2. Page-scraped values were allowed to REPLACE populated specs. A catalogue
     page legitimately lists many payloads, so no regex can disambiguate it —
     the value must simply not be allowed to overwrite known-good data.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from web_extract import extract_specs_from_text  # noqa: E402


# ---------------------------------------------------------------------------
# Guard 1: payload must be labelled
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("text,expected", [
    # The exact failure mode: an unlabelled number in marketing copy.
    ("Our cell palletises up to 500 kg per hour for busy lines.", None),
    ("The controller cabinet weighs 68 kg and ships separately.", None),
    ("Handles trays up to 30 kg without additional tooling.", None),
    # Legitimate, labelled payloads still extract — both word orders.
    ("Payload: 12 kg", 12.0),
    ("Payload 4 kg / Reach 581 mm", 4.0),
    ("A 25 kg payload robot for heavy handling.", 25.0),
    ("Load capacity 400 kg", 400.0),
    ("Rated load 150 kg", 150.0),
    ("Maximum payload 7 kg", 7.0),
])
def test_payload_requires_a_label(text, expected):
    assert extract_specs_from_text(text).get("payload_kg") == expected


def test_reach_was_already_label_guarded_and_stays_so():
    """Reach was never the bug — this pins the behaviour so a future edit to
    the shared pattern block cannot silently loosen it."""
    assert extract_specs_from_text("The base is 581 mm across.").get("reach_mm") is None
    assert extract_specs_from_text("Reach 581 mm").get("reach_mm") == 581.0


def test_catalogue_page_remains_ambiguous_by_nature():
    """A page listing every model in a family legitimately contains several
    labelled payloads. No regex can pick the right one, which is precisely why
    guard 2 (never overwrite a populated spec) is the load-bearing fix rather
    than a nicety."""
    page = ("HDX300L-30 payload 300 kg reach 3056 mm  "
            "HDX400-25 payload 400 kg reach 2500 mm")
    got = extract_specs_from_text(page)
    assert got.get("payload_kg") == 300.0   # first labelled hit, not necessarily correct
    assert got.get("reach_mm") == 3056.0


# ---------------------------------------------------------------------------
# Guard 2: scraped specs may fill blanks, never overwrite — and "absent" is
# not "blank". Mirrors the filter applied in RobotAutoResearcher.research_robot.
# ---------------------------------------------------------------------------
def apply_guard(specs: dict, robot: dict) -> tuple[dict, list, list]:
    kept, unknown = [], []
    out = dict(specs)
    for k in list(out):
        if k not in robot:
            unknown.append(k)
            out.pop(k)
        elif robot.get(k) not in (None, "", [], {}):
            kept.append(k)
            out.pop(k)
    return out, sorted(kept), sorted(unknown)


def test_populated_spec_is_never_overwritten():
    """The incident in one assertion: a good API-sourced reach survives a
    scraped one."""
    specs = {"payload_kg": 300.0, "reach_mm": 56.0}          # scraped, wrong
    robot = {"payload_kg": 400.0, "reach_mm": 3056.0}        # from the maker's API
    out, kept, _ = apply_guard(specs, robot)
    assert out == {}
    assert kept == ["payload_kg", "reach_mm"]


def test_blank_spec_is_still_filled():
    """The guard must not block genuine enrichment of empty fields."""
    specs = {"payload_kg": 12.0, "reach_mm": 1300.0}
    robot = {"payload_kg": None, "reach_mm": ""}
    out, kept, unknown = apply_guard(specs, robot)
    assert out == {"payload_kg": 12.0, "reach_mm": 1300.0}
    assert kept == [] and unknown == []


def test_absent_key_is_not_treated_as_blank():
    """The lite serializer omits every spec field. If a caller hands over a
    robot dict without them, 'not supplied' must not be read as 'empty' — that
    inference is how a scraped guess replaces a value nobody checked."""
    specs = {"payload_kg": 999.0}
    robot = {"name": "X"}                                    # no spec keys at all
    out, kept, unknown = apply_guard(specs, robot)
    assert out == {}, "must not write a spec when the current value is unknown"
    assert unknown == ["payload_kg"]
    assert kept == []


def test_mixed_case_partitions_correctly():
    specs = {"payload_kg": 1.0, "reach_mm": 2.0, "dof": 6}
    robot = {"payload_kg": 400.0, "reach_mm": None}          # dof key absent
    out, kept, unknown = apply_guard(specs, robot)
    assert out == {"reach_mm": 2.0}      # only the genuinely-blank one is filled
    assert kept == ["payload_kg"]
    assert unknown == ["dof"]
