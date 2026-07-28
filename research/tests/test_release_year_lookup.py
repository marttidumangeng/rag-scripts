"""Tests for release-year lookup parsing — a bad parse must never invent a year."""

from release_year_lookup import _parse_lookup_response, citation_line


def test_valid_high_confidence():
    result = _parse_lookup_response(
        '{"year": 2023, "source_url": "https://oem.com/press/launch", '
        '"evidence": "Press release dated 2023-10-05 announces the E2 launch", '
        '"is_specific_model": true}'
    )
    assert result == {
        "year": 2023,
        "source_url": "https://oem.com/press/launch",
        "evidence": "Press release dated 2023-10-05 announces the E2 launch",
        "confidence": "high",
    }


def test_medium_when_not_specific_model():
    result = _parse_lookup_response(
        '{"year": 2021, "source_url": "https://x.com", "evidence": "launch coverage", '
        '"is_specific_model": false}'
    )
    assert result["confidence"] == "medium"


def test_medium_when_no_source_url():
    result = _parse_lookup_response(
        '{"year": 2021, "source_url": "", "evidence": "news article", "is_specific_model": true}'
    )
    assert result["confidence"] == "medium"


def test_null_year_rejected():
    assert _parse_lookup_response('{"year": null, "source_url": "", "evidence": "unknown"}') is None


def test_out_of_range_year_rejected():
    assert _parse_lookup_response('{"year": 1830, "source_url": "u", "evidence": "e"}') is None
    assert _parse_lookup_response('{"year": 2093, "source_url": "u", "evidence": "e"}') is None


def test_year_without_evidence_rejected():
    assert _parse_lookup_response('{"year": 2020, "source_url": "https://x.com", "evidence": ""}') is None


def test_string_year_coerced():
    result = _parse_lookup_response(
        '{"year": "2019", "source_url": "https://x.com", "evidence": "datasheet", "is_specific_model": true}'
    )
    assert result["year"] == 2019


def test_markdown_fenced_json_parsed():
    result = _parse_lookup_response(
        '```json\n{"year": 2022, "source_url": "https://x.com", "evidence": "press", '
        '"is_specific_model": true}\n```'
    )
    assert result["year"] == 2022


def test_garbage_rejected():
    assert _parse_lookup_response("") is None
    assert _parse_lookup_response("The robot launched in 2021.") is None
    assert _parse_lookup_response('{"year": true, "evidence": "x"}') is None


def test_citation_line_with_source_url():
    line = citation_line({
        "year": 2023,
        "evidence": "Press release dated 2023-10-05 announces the E2 launch",
        "source_url": "https://oem.com/press/launch",
    })
    assert line == (
        "release_year=2023: Press release dated 2023-10-05 announces the E2 launch "
        "(https://oem.com/press/launch)"
    )


def test_citation_line_without_source_url():
    line = citation_line({"year": 2021, "evidence": "launch coverage", "source_url": ""})
    assert line == "release_year=2021: launch coverage"
