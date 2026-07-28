"""Regression tests for Yamaha LCMR200 hero-image repair."""
from __future__ import annotations

import sys
from pathlib import Path

RESEARCH_DIR = Path(__file__).resolve().parents[1]
if str(RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(RESEARCH_DIR))

import fix_yamaha_lcmr200_images as yamaha_lcmr


def test_rights_restricted_catalog_renders_are_never_upload_targets() -> None:
    assert yamaha_lcmr.EXACT_TARGETS == {}
    assert yamaha_lcmr.HELD_NO_EXACT_IMAGE_IDS == {
        3325,
        3326,
        4385,
        4386,
        4387,
        4388,
        4389,
        4390,
        4391,
        4392,
        4393,
    }


def test_cad_catalog_renders_are_not_upload_targets() -> None:
    assert not hasattr(yamaha_lcmr, "CAD_CAPTURE_TARGETS")


def test_restricted_cad_cleanup_clears_media_and_adds_actionable_note() -> None:
    payload = yamaha_lcmr.restricted_cad_cleanup_payload(
        4386,
        "Existing curator note.",
    )

    assert payload["image"] == ""
    assert payload["images"] == []
    assert payload["s3_image"] is None
    assert payload["status"] == "pending_review"
    assert payload["notes"].startswith("[IMAGE TO-DO — no hero, deliberate]")
    assert "CADENAS" in payload["notes"]
    assert "written republication permission" in payload["notes"]
    assert payload["notes"].endswith("Existing curator note.")


def test_restricted_media_match_is_exact_to_robot() -> None:
    assert yamaha_lcmr.is_restricted_media_url(
        4386,
        "https://cdn.robotaigeek.com/robots/photos/lcmr200-f3-exact-cad-render.png",
    )
    assert not yamaha_lcmr.is_restricted_media_url(
        4386,
        "https://cdn.robotaigeek.com/robots/photos/lcmr200-f5-exact-cad-render.png",
    )


def test_cleanup_payload_does_not_duplicate_existing_todo_note() -> None:
    existing = yamaha_lcmr.restricted_cad_cleanup_payload(4386, "")["notes"]
    payload = yamaha_lcmr.restricted_cad_cleanup_payload(4386, existing)

    assert payload["notes"] == existing


def test_detach_only_mode_is_explicit() -> None:
    args = yamaha_lcmr.parse_args(["--apply", "--detach-only"])

    assert args.apply is True
    assert args.detach_only is True
