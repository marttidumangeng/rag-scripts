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
    ManufacturerAPIExtractor,
    _attr_lookup,
    _drop_shared_images,
    _walk_for_product_list,
    make_hyundai_config,
    make_nachi_config,
    make_techman_config,
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


# --------------------------------------------------------------------------
# Navigation must not be mistaken for a catalogue.
#
# Live failure (2026-08-03): Zoox's __NEXT_DATA__ produced four "products" —
# "How To Ride", "Know Your Ride", "Support", "Where to Ride" — because the
# walker matched any list of dicts carrying a name-ish key. Since a structured
# hit SHORT-CIRCUITS link mining, this did not add noise, it REPLACED the
# result the old path would have produced. Caught 8 companies into a 595-company
# run.
# --------------------------------------------------------------------------
def test_navigation_menu_is_not_a_product_list():
    nav = {"props": {"pageProps": {"nav": [
        {"title": "How To Ride", "href": "/how-to-ride"},
        {"title": "Know Your Ride", "href": "/know"},
        {"title": "Support", "href": "/support"},
    ]}}}
    assert _walk_for_product_list(nav) is None


def test_breadcrumb_shape_is_not_a_product_list():
    crumbs = {"data": [{"name": "Home", "url": "/"},
                       {"name": "Products", "url": "/products"}]}
    assert _walk_for_product_list(crumbs) is None


def test_list_with_product_fields_survives_the_nav_filter():
    """A record carrying a product-shaped key is a catalogue even when it also
    has a url — many real product feeds include a link."""
    feed = {"data": {"items": [
        {"name": "Arm 5", "url": "/p/arm5", "payload_kg": 5, "image": "a.png"},
        {"name": "Arm 7", "url": "/p/arm7", "payload_kg": 7, "image": "b.png"},
    ]}}
    rows = _walk_for_product_list(feed)
    assert rows and len(rows) == 2


# --------------------------------------------------------------------------
# Nachi — WooCommerce attribute arrays
#
# Nachi types its specs as `attributes: [{name, terms:[{name}]}]`, which a
# flat field-name mapping cannot see at all. Its product feed also mixes 5
# controllers in with the 62 robots.
# --------------------------------------------------------------------------
NACHI_ROBOT = {
    "name": "MZ35S",
    "images": [{"src": "https://n.example.com/mz35s.png"}],
    "attributes": [
        {"name": "Reach", "terms": [{"name": "1882"}]},
        {"name": "Payload", "terms": [{"name": "35"}]},
        {"name": "Application", "terms": [{"name": "Dispensing"}, {"name": "Palletizing"}]},
        {"name": "Mount", "terms": [{"name": "Floor"}]},
    ],
}
NACHI_CONTROLLER = {
    "name": "CFDQ Controller",
    "images": [{"src": "https://n.example.com/cfdq.png"}],
    # A controller carries the same attribute array shape, minus payload.
    "attributes": [{"name": "Mount", "terms": [{"name": "Floor"}]}],
}


def _run(rows, cfg):
    return ManufacturerAPIExtractor()._rows_to_products(
        rows, page_url="https://n.example.com/", mappings=cfg.get("spec_mappings") or [],
        image_url_template=cfg.get("image_url_template"), label="", cfg=cfg)


def test_attr_lookup_flattens_woocommerce_terms():
    flat = _attr_lookup(NACHI_ROBOT, make_nachi_config())
    assert flat["payload"] == "35"
    assert flat["reach"] == "1882"
    assert flat["application"] == "Dispensing, Palletizing"


def test_nachi_reads_specs_out_of_the_attribute_array():
    p = _run([NACHI_ROBOT], make_nachi_config())[0]
    assert (p.payload_kg, p.reach_mm) == (35.0, 1882.0)
    # Applications are captured at extraction time, not re-derived from prose
    # later: uses/industries must be filled from data we already hold.
    assert p.extra["applications"] == "Dispensing, Palletizing"
    assert p.extra["mounting"] == "Floor"


def test_nachi_drops_controllers_via_missing_payload():
    """The 5 controllers are exactly the rows with no payload attribute, so the
    requirement doubles as the discriminator — no name blocklist to go stale."""
    out = _run([NACHI_ROBOT, NACHI_CONTROLLER], make_nachi_config())
    assert [p.name for p in out] == ["MZ35S"]


def test_attribute_value_never_overwrites_a_mapped_field():
    """A flat mapping is the more specific source; attributes only fill gaps."""
    cfg = dict(make_nachi_config())
    cfg["spec_mappings"] = [SpecMapping(name="x", applies_to=lambda r: True,
                                        payload_field="true_payload")]
    row = dict(NACHI_ROBOT, true_payload="35.5")
    assert _run([row], cfg)[0].payload_kg == 35.5


# --------------------------------------------------------------------------
# Shared images
#
# Nachi's feed has several models pointing at the same *basename*
# (robotproductspage.ai_.png) under different upload folders — those are
# genuinely different files and must be KEPT. Only a repeated full URL is a
# real collision, and it is correct for at most one of its claimants.
# --------------------------------------------------------------------------
def test_shared_image_url_is_dropped_from_every_claimant():
    a = ExtractedProduct(name="A", source_url="x", image_urls=["http://c/shared.png"])
    b = ExtractedProduct(name="B", source_url="x",
                         image_urls=["http://c/shared.png", "http://c/b.png"])
    assert _drop_shared_images([a, b]) == 2
    assert a.image_urls == []
    assert b.image_urls == ["http://c/b.png"]


def test_same_basename_under_different_paths_is_not_shared():
    a = ExtractedProduct(name="A", source_url="x", image_urls=["http://c/2023/07/p.png"])
    b = ExtractedProduct(name="B", source_url="x", image_urls=["http://c/2025/07/p.png"])
    assert _drop_shared_images([a, b]) == 0
    assert a.image_urls and b.image_urls


# --------------------------------------------------------------------------
# Techman
# --------------------------------------------------------------------------
TECHMAN_ROW = {
    "name": "TM5 - 700", "reach": 746, "payload": 6, "weight": 22, "ipiv": 54,
    "typeName": "Regular", "feature": "Small Size, Big Capabilities",
    "images": ["https://tm.example.com/tm5700.png"],
    "applicationCategories": [{"name": "Assembly"}, {"name": "Inspection"},
                              {"name": "Assembly"}],
}


def test_techman_normalises_the_spaced_hyphen_in_display_names():
    """The API prints 'TM5 - 700'; every datasheet says 'TM5-700'. Importing the
    spaced form would create a robot no search or dedupe key can match."""
    assert _run([TECHMAN_ROW], make_techman_config())[0].name == "TM5-700"


def test_techman_reads_typed_specs_and_applications():
    p = _run([TECHMAN_ROW], make_techman_config())[0]
    assert (p.payload_kg, p.reach_mm, p.dof) == (6.0, 746.0, 6)
    assert p.extra["ip_rating"] == 54
    assert p.extra["applications"] == "Assembly, Inspection"   # deduped, ordered
    assert p.image_urls == ["https://tm.example.com/tm5700.png"]


def test_techman_sends_the_content_language_header():
    """Without it the endpoint answers 406 — which looks exactly like a bot
    block and would otherwise trigger a pointless Playwright escalation."""
    assert make_techman_config()["extra_headers"] == {"Content-Language": "en"}


def test_constants_do_not_overwrite_a_value_the_source_supplied():
    cfg = dict(make_techman_config())
    cfg["spec_mappings"] = [SpecMapping(name="x", applies_to=lambda r: True,
                                        dof_field="axes")]
    p = _run([dict(TECHMAN_ROW, axes="7")], cfg)[0]
    assert p.dof == 7, "a declared constant is a fallback, not an override"


def test_hyundai_rows_still_match_after_nav_filter():
    """The registered path must be unaffected by the nav discriminator."""
    rows = [{"prdNm": "HDF4-5(HH4)", "prdTypeCd": "60010001", "prdBscSpec1": "4"},
            {"prdNm": "HDF7-9(HH7)", "prdTypeCd": "60010001", "prdBscSpec1": "7"}]
    assert _walk_for_product_list({"data": {"content": rows}}) is not None


# --------------------------------------------------------------------------
# DOF stated in copy but not typed as a field.
#
# Nachi's attribute array has no axis count, but the marketing sentence states
# it. An UNANCHORED `(\d)-axis` search over the same text matches "J2-axis
# encoder connector protector" and reported 6-axis arms as 1- and 7-axis, so
# the match must be anchored to the product's own name.
# --------------------------------------------------------------------------
def test_dof_is_read_from_copy_when_anchored_to_the_product_name():
    row = dict(NACHI_ROBOT, short_description=(
        "<p>The MZ35S is a high-performance 6-axis industrial robot designed "
        "for versatility.</p>"))
    assert _run([row], make_nachi_config())[0].dof == 6


def test_dof_ignores_axis_mentions_not_about_this_product():
    row = dict(NACHI_ROBOT, short_description=(
        "<p>When selecting option OP-P6-016 (J2-axis encoder connector "
        "protector), the rating decreases.</p>"))
    assert _run([row], make_nachi_config())[0].dof is None


def test_dof_from_text_never_overrides_a_typed_value():
    cfg = dict(make_nachi_config())
    cfg["spec_mappings"] = [SpecMapping(name="x", applies_to=lambda r: True,
                                        dof_field="axes")]
    row = dict(NACHI_ROBOT, axes="4",
               short_description="The MZ35S is a 6-axis industrial robot.")
    assert _run([row], cfg)[0].dof == 4, "a typed field outranks prose"
