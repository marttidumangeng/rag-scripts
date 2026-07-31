"""Hardening tests for manufacturer_gap_discovery (QA classes qa5–qa8).

Covers: harvest junk-name filtering (ISO country codes, <=3-char fragments,
non-English universities, Wikipedia robot-page titles), robot-candidate anchor
filtering (language switchers, nav lexicon, numeric ranges), charset-mojibake
repair, and the Yaskawa/Motoman alias matching against prod.
"""

from __future__ import annotations

from manufacturer_gap_discovery import (
    _baseline_name_variants,
    _decode_response,
    company_aliases,
    company_in_db,
    extract_robot_candidates,
    fix_mojibake,
    is_junk_company_name,
    merge_and_dedupe,
)


# ── qa5 final sweep: country codes + short fragments ─────────────────────────

def test_iso_country_codes_are_junk():
    for code in ("At", "Au", "Be", "Ca", "Cn", "Fr", "Jp", "Kr", "Tw", "Qa"):
        assert is_junk_company_name(code, "robolist"), code


def test_short_fragments_are_junk():
    for frag in ("cog", "cyn", "fbr", "hem", "mda", "pds", "see", "stm", "vex"):
        assert is_junk_company_name(frag, "robolist"), frag


def test_manual_seeds_exempt_from_length_rule():
    assert not is_junk_company_name("ABB", "manual_seed")


def test_normal_manufacturer_names_survive():
    for name in ("AUBO Robotics", "Boston Dynamics", "Franka Emika",
                 "Shenzhen Dobot", "Agile Robots"):
        assert not is_junk_company_name(name, "robolist"), name
        assert not is_junk_company_name(name, "wikipedia"), name


# ── qa: non-English universities ─────────────────────────────────────────────

def test_non_english_universities_are_junk():
    for name in (
        "Universität Bremen",
        "Technische Universität München",
        "Université de Montréal",
        "Universidad Politécnica de Madrid",
        "Universidade de São Paulo",
        "Delft University of Technology",
        "University of Tokyo",
    ):
        assert is_junk_company_name(name, "wikipedia"), name


def test_universal_robots_is_not_a_university():
    assert not is_junk_company_name("Universal Robots", "wikipedia")


# ── qa7/qa8: Wikipedia robot pages staged as manufacturers ───────────────────

def test_wikipedia_robot_titles_are_junk():
    for title in (
        "FEDOR",
        "MABEL",
        "Murata Boy and Murata Girl",
        "ZEUS robotic surgical system",
        "Honda P series",
    ):
        assert is_junk_company_name(title, "wikipedia"), title


def test_wiki_robot_heuristics_scoped_to_wikipedia_source():
    # Non-wikipedia sources are not subject to the title-shape heuristics
    assert not is_junk_company_name("FEDOR", "aparobot")


def test_merge_and_dedupe_drops_junk_names():
    harvests = {
        "robolist": {
            "at": {"name": "At"},
            "fbr": {"name": "fbr"},
            "acme": {"name": "Acme Robotics", "categories": ["cobot"]},
        },
        "wikipedia": {
            "fedor": {"name": "FEDOR"},
            "honda-p-series": {"name": "Honda P series"},
            "zeus": {"name": "ZEUS robotic surgical system"},
            "uni": {"name": "Universität Bremen"},
        },
    }
    baseline = {
        "company_index": set(),
        "robot_index": set(),
        "robot_global": set(),
        "website_index": set(),
    }
    gaps, _total = merge_and_dedupe(harvests, baseline)
    names = {g["name"] for g in gaps}
    assert names == {"Acme Robotics"}


# ── qa6/qa7: robot-candidate anchor filtering ────────────────────────────────

_HTML = """
<html><body>
<a href="/products/titan-x1">Titan X1 Robot</a>
<a href="/products/?lang=fr">franÃ§ais</a>
<a href="/products/?lang=tr">TÃ¼rkÃ§e</a>
<a href="/products/?lang=lv">Latviešu</a>
<a href="/products/?lang=uz">Oʻzbekcha</a>
<a href="/products/?lang=de">Deutsch</a>
<a href="/products/more">More</a>
<a href="/products/more2">MORE+</a>
<a href="/products/qv">Quick view</a>
<a href="/products/page/2">2</a>
<a href="/products/filter/light">1-7kg</a>
<a href="/products/filter/heavy">&gt;1000kg</a>
<a href="/products/robo-movel">RobÃ´ MÃ³vel</a>
</body></html>
"""


def test_extract_filters_language_nav_and_numeric_anchors():
    cands = extract_robot_candidates(
        _HTML, "https://example-robotics.com", "Example Robotics")
    names = {c["name"] for c in cands}
    assert "Titan X1 Robot" in names
    # language switchers (including mojibake forms, repaired then matched)
    for junk in ("français", "Türkçe", "Latviešu", "Oʻzbekcha", "Deutsch"):
        assert junk not in names, junk
    # nav lexicon + pagination/range fragments
    for junk in ("More", "MORE+", "Quick view", "2", "1-7kg", ">1000kg"):
        assert junk not in names, junk
    # mojibake product anchors are repaired, not dropped
    assert "Robô Móvel" in names


# ── qa8: charset mojibake repair ─────────────────────────────────────────────

def test_fix_mojibake_utf8_as_cp1252():
    assert fix_mojibake("franÃ§ais") == "français"
    assert fix_mojibake("TÃ¼rkÃ§e") == "Türkçe"


def test_fix_mojibake_gbk_as_latin1():
    fixed = fix_mojibake("TCHÎèÌ¨µ¹¹Ò"
                         "µç¶¯ºùÂ«")
    assert "Ã" not in fixed and "Â" not in fixed
    assert any("一" <= ch <= "鿿" for ch in fixed)  # decoded to CJK


def test_fix_mojibake_leaves_clean_text_alone():
    for text in ("Kärcher Robot", "Titan Arm", "Stäubli TX2-60", ""):
        assert fix_mojibake(text) == text


class _Resp:
    status_code = 200

    def __init__(self, content: bytes, header_encoding: str = "latin-1",
                 apparent_encoding: str = "utf-8"):
        self.content = content
        self.text = content.decode(header_encoding)
        self.apparent_encoding = apparent_encoding


def test_decode_response_uses_apparent_encoding_on_mojibake():
    content = "<html><a href='/products/x'>Robô français robot</a></html>".encode("utf-8")
    resp = _Resp(content)
    assert "Ã" in resp.text  # precondition: header decoding produced mojibake
    assert "Robô" in _decode_response(resp)


def test_decode_response_keeps_clean_pages():
    content = b"<html>plain ascii robots</html>"
    resp = _Resp(content)
    assert _decode_response(resp) == "<html>plain ascii robots</html>"


# ── item 5: Yaskawa / Motoman aliasing ───────────────────────────────────────

def test_electric_suffix_alias():
    assert "yaskawa" in company_aliases("YASKAWA Electric")
    assert "mitsubishi" in company_aliases("Mitsubishi Electric")


def test_yaskawa_and_motoman_match_prod():
    baseline = {
        "company_index": _baseline_name_variants("YASKAWA Electric Corporation"),
        "website_index": set(),
    }
    assert company_in_db("Yaskawa", "", baseline)
    assert company_in_db("Motoman", "", baseline)
    assert company_in_db("Yaskawa Motoman", "", baseline)
    assert not company_in_db("Fictional Robotics", "", baseline)
