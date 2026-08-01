"""Tests for the structured extraction ladder.

Every case here encodes a failure that actually happened in this pipeline, so
the suite doubles as a regression record:

  * '5G' becoming "5 mm of reach"          -> test_fpd_glass_generation_*
  * HS220 and HDR220-26 imported as two    -> test_split_alias / dedupe tests
  * controllers imported as robots         -> test_hyundai_config_excludes_*
  * a bare `(\\d+)\\s*kg` grabbing marketing copy -> test_spec_table_labels_govern
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from extractors.base import ExtractedProduct, SpecMapping, to_number  # noqa: E402
from extractors.manufacturer_api import (  # noqa: E402
    _walk_for_product_list,
    make_hyundai_config,
    split_alias,
)
from extractors.structured_html import JsonLdExtractor, SpecTableExtractor  # noqa: E402


# --------------------------------------------------------------------------
# alias splitting — the dual-naming trap
# --------------------------------------------------------------------------
@pytest.mark.parametrize("raw,name,alias", [
    ("HDR220-26(HS220)", "HDR220-26", "HS220"),
    ("HDR35-20 (UH035)", "HDR35-20", "UH035"),
    ("제품관리_HDF4-5(HH4)", "HDF4-5", "HH4"),      # CMS prefix stripped
    ("HH020", "HH020", ""),                          # no alias
    ("HC200/165L Series", "HC200/165L Series", ""),  # slash is not an alias
])
def test_split_alias(raw, name, alias):
    assert split_alias(raw) == (name, alias)


def test_alias_key_enables_cross_name_dedupe():
    """A record under the legacy name must match one under the current name."""
    p = ExtractedProduct(name="HDR35-20", alias="UH035", source_url="x")
    held = {"uh035"}  # what the catalogue already has, normalised
    assert p.key() not in held          # current name is genuinely new...
    assert p.alias_key() in held        # ...but the alias proves it is a dup


# --------------------------------------------------------------------------
# type-aware spec mapping — the "5 mm reach" bug
# --------------------------------------------------------------------------
def test_to_number_parses_glass_generation_happily():
    """Documents WHY the type guard is needed: '5G' is a perfectly good number."""
    assert to_number("5G") == 5.0
    assert to_number("1,425 mm") == 1425.0


def test_fpd_glass_generation_is_not_recorded_as_reach():
    cfg = make_hyundai_config()
    fpd_map = next(m for m in cfg["spec_mappings"] if m.name == "fpd")
    raw = {"prdTypeCd": "60010002", "prdBscSpec1": None, "prdBscSpec2": "5G",
           "prdBscSpec3": "Hi5a-C"}
    assert fpd_map.applies_to(raw)
    p = ExtractedProduct(name="HC1300B", source_url="x")
    fpd_map.apply(raw, p)
    assert p.reach_mm is None, "glass generation must never land in reach_mm"
    assert p.payload_kg is None
    assert p.extra["glass_generation"] == "5G"


def test_articulated_mapping_does_record_reach():
    cfg = make_hyundai_config()
    arm_map = next(m for m in cfg["spec_mappings"] if m.name == "articulated")
    raw = {"prdTypeCd": "60010001", "prdBscSpec1": "4", "prdBscSpec2": "581",
           "prdBscSpec3": "Hi7-N30", "prdDtlSpec2": "6", "prdDtlSpec3": "AC Servo"}
    assert arm_map.applies_to(raw)
    p = ExtractedProduct(name="HDF4-5", source_url="x")
    arm_map.apply(raw, p)
    assert (p.payload_kg, p.reach_mm, p.dof, p.drive) == (4.0, 581.0, 6, "AC Servo")


def test_mapping_selection_is_ordered_fpd_first():
    """FPD must be matched before the articulated rule, or it inherits reach."""
    cfg = make_hyundai_config()
    raw = {"prdTypeCd": "60010002", "prdBscSpec2": "8G"}
    chosen = next(m for m in cfg["spec_mappings"] if m.applies_to(raw))
    assert chosen.name == "fpd"


# --------------------------------------------------------------------------
# site config: robots only
# --------------------------------------------------------------------------
def test_hyundai_config_excludes_controllers_and_positioners():
    codes = {v["params"]["prdTypeCd"] for v in make_hyundai_config()["variants"]}
    assert codes == {"60010001", "60010002", "60010007"}
    assert "60010003" not in codes, "60010003 is controllers (Hi5a/Hi6), not robots"
    assert "60010004" not in codes, "60010004 is welding positioners, not robots"


# --------------------------------------------------------------------------
# envelope shape-matching
# --------------------------------------------------------------------------
@pytest.mark.parametrize("payload", [
    {"data": {"content": [{"prdNm": "A"}, {"prdNm": "B"}]}},
    {"results": [{"name": "A"}, {"name": "B"}]},
    {"props": {"pageProps": {"products": [{"title": "A"}, {"title": "B"}]}}},
])
def test_walk_finds_product_list_in_varied_envelopes(payload):
    rows = _walk_for_product_list(payload)
    assert rows and len(rows) == 2


def test_walk_ignores_lists_without_name_like_keys():
    assert _walk_for_product_list({"data": [{"x": 1, "y": 2}, {"x": 3, "y": 4}]}) is None


# --------------------------------------------------------------------------
# JSON-LD
# --------------------------------------------------------------------------
JSONLD_HTML = """
<html><head><script type="application/ld+json">
{"@context":"https://schema.org","@type":"Product","name":"Acme Arm 7",
 "image":"https://cdn.example.com/arm7.png",
 "additionalProperty":[
   {"@type":"PropertyValue","name":"Payload","value":"7 kg"},
   {"@type":"PropertyValue","name":"Reach","value":"911 mm"},
   {"@type":"PropertyValue","name":"Axes","value":"6"},
   {"@type":"PropertyValue","name":"Protection","value":"IP54"}]}
</script></head><body></body></html>
"""


def test_jsonld_reads_typed_specs():
    res = JsonLdExtractor().extract("https://example.com/arm7", JSONLD_HTML)
    assert len(res.products) == 1
    p = res.products[0]
    assert (p.name, p.payload_kg, p.reach_mm, p.dof) == ("Acme Arm 7", 7.0, 911.0, 6)
    assert p.extra["protection"] == "IP54"   # unmapped specs are kept, not dropped
    assert p.image_urls == ["https://cdn.example.com/arm7.png"]


def test_jsonld_declines_cleanly_when_no_product_node():
    html = '<script type="application/ld+json">{"@type":"Organization","name":"X"}</script>'
    res = JsonLdExtractor().extract("https://example.com", html)
    assert not res
    assert "no Product nodes" in res.declined_reason


# --------------------------------------------------------------------------
# spec tables
# --------------------------------------------------------------------------
HORIZONTAL_TABLE = """
<table>
 <tr><th>Model</th><th>RV-3FR</th><th>RV-7FR</th><th>RV-13FR</th></tr>
 <tr><td>Payload</td><td>3 kg</td><td>7 kg</td><td>13 kg</td></tr>
 <tr><td>Reach</td><td>642 mm</td><td>908 mm</td><td>1094 mm</td></tr>
 <tr><td>Axes</td><td>6</td><td>6</td><td>6</td></tr>
</table>
"""


def test_horizontal_table_yields_one_product_per_column():
    """This is the variant-family case: one page, every sibling model."""
    res = SpecTableExtractor().extract("https://example.com/melfa", HORIZONTAL_TABLE)
    names = {p.name for p in res.products}
    assert names == {"RV-3FR", "RV-7FR", "RV-13FR"}
    by = {p.name: p for p in res.products}
    assert (by["RV-3FR"].payload_kg, by["RV-3FR"].reach_mm) == (3.0, 642.0)
    assert (by["RV-13FR"].payload_kg, by["RV-13FR"].reach_mm) == (13.0, 1094.0)
    assert all(p.dof == 6 for p in res.products)


VERTICAL_TABLE = """
<table>
 <tr><th>Payload</th><td>20 kg</td></tr>
 <tr><th>Maximum reach</th><td>1 722 mm</td></tr>
 <tr><th>Repeatability</th><td>0.05 mm</td></tr>
</table>
"""


def test_vertical_table_reads_label_value_pairs():
    res = SpecTableExtractor().extract("https://example.com/p", VERTICAL_TABLE)
    assert len(res.products) == 1
    p = res.products[0]
    assert p.payload_kg == 20.0
    assert p.repeatability_mm == 0.05 if hasattr(p, "repeatability_mm") \
        else p.extra["repeatability_mm"] == 0.05


def test_spec_table_labels_govern_not_first_number_on_page():
    """The prose regex this replaces takes the FIRST '<n> kg' anywhere, so a
    marketing line poisons the payload. A labelled table cannot do that."""
    html = """
    <p>Our cell palletises up to 500 kg per hour for busy lines.</p>
    <table>
      <tr><th>Payload</th><td>12 kg</td></tr>
      <tr><th>Reach</th><td>1300 mm</td></tr>
    </table>"""
    res = SpecTableExtractor().extract("https://example.com/p", html)
    assert res.products[0].payload_kg == 12.0, "must read the labelled row, not the prose"


def test_table_without_recognisable_labels_declines():
    html = "<table><tr><th>Colour</th><td>Blue</td></tr><tr><th>SKU</th><td>X1</td></tr></table>"
    res = SpecTableExtractor().extract("https://example.com/p", html)
    assert not res
    assert "recognisable spec labels" in res.declined_reason
