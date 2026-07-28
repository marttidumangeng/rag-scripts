"""Tests for web_extract helpers."""

from __future__ import annotations

import sys
from pathlib import Path

_RESEARCH_DIR = Path(__file__).resolve().parents[1]
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from schema import StagedRobot  # noqa: E402
from web_extract import (  # noqa: E402
    PageContent,
    build_image_candidates_for_pages,
    extract_image_urls,
    extract_specs_from_text,
    extract_youtube_ids,
    is_junk_image_url,
    rank_images,
    select_images_for_pages,
    robot_name_tokens,
    score_url_for_robot,
    select_confident_images,
    select_confident_videos,
    youtube_watch_url,
)


SAMPLE_HTML = """
<html><head>
<meta property="og:image" content="https://cdn.example.com/lumabot-hero.jpg" />
</head><body>
<img src="https://cdn.example.com/gallery-side.png" />
<a href="https://www.youtube.com/watch?v=dQw4v9WgXcQ">video</a>
<p>Payload up to 460 lbs and 20+ hours runtime.</p>
</body></html>
"""


def test_extract_images_and_youtube():
    images = extract_image_urls(SAMPLE_HTML, "https://example.com/product")
    assert "https://cdn.example.com/lumabot-hero.jpg" in images
    ids = extract_youtube_ids(SAMPLE_HTML)
    assert ids == ["dQw4v9WgXcQ"]
    assert youtube_watch_url(ids[0]) == "https://www.youtube.com/watch?v=dQw4v9WgXcQ"


def test_extract_specs():
    specs = extract_specs_from_text("Handles 460 lbs payload with 20+ hours runtime.")
    assert specs["payload_kg"] == round(460 * 0.453592, 1)
    assert "20" in str(specs.get("runtime", ""))


def test_robot_url_scoring():
    tokens = robot_name_tokens("Lumabot AMR", "Lumabot")
    assert score_url_for_robot("https://onwardrobotics.com/lumabot-amr/", tokens) > 0
    ranked = rank_images(
        [
            "https://cdn.example.com/logo.png",
            "https://cdn.example.com/lumabot-hero.jpg",
        ],
        tokens,
    )
    assert "lumabot" in ranked[0]


def test_estun_footer_icons_are_junk():
    assert is_junk_image_url("https://www.estun.com/skin/images/f-phone.png")
    assert is_junk_image_url("https://www.estun.com/button-icons/ArrowUp.png")
    assert is_junk_image_url("http://www.estun.com/assets/img/logo/asd-gzh.jpg")
    assert is_junk_image_url("http://www.estun.com/assets/img/dy.jpg")
    assert not is_junk_image_url("https://www.estun.com/uploads/20260521/robot.jpg")


def test_select_images_from_product_page_uploads():
    from web_extract import select_images_for_pages

    tokens = robot_name_tokens("iER8-720-MI-C", "iER8-720-MI-C")
    page = PageContent(
        url="https://www.estun.com/gjjjqr/356.html",
        html="",
        title="iER8-720-MI-C - cleanroom robot",
        text="Model iER8-720-MI-C payload 8kg",
        images=[
            "https://www.estun.com/skin/images/f-phone.png",
            "https://www.estun.com/uploads/20250903/robot-hero.png",
            "https://www.estun.com/uploads/20250903/robot-side.png",
        ],
    )
    hero, gallery = select_images_for_pages(
        [page],
        product_url=page.url,
        name="iER8-720-MI-C",
        model_name="iER8-720-MI-C",
        tokens=tokens,
    )
    assert hero == "https://www.estun.com/uploads/20250903/robot-hero.png"
    assert "f-phone" not in hero
    assert len(gallery) == 1


def test_build_image_candidates_for_pages_returns_scored_candidate_shape():
    page = PageContent(
        url="https://robots.example.com/products/lumabot",
        html="",
        title="Lumabot product page",
        text="Lumabot is an autonomous mobile robot.",
        images=[
            "https://cdn.example.com/lumabot-gallery.jpg",
            "https://cdn.example.com/lumabot-hero-image.jpg",
        ],
    )
    tokens = robot_name_tokens("Lumabot", "Lumabot")

    candidates = build_image_candidates_for_pages(
        [page],
        product_url=page.url,
        name="Lumabot",
        model_name="Lumabot",
        tokens=tokens,
        company_name="Example Robotics",
    )

    assert candidates
    assert candidates == sorted(
        candidates,
        key=lambda candidate: candidate["confidence_score"],
        reverse=True,
    )
    assert {
        "url",
        "source_page_url",
        "source_tier",
        "source_publisher",
        "source_domain",
        "media_class",
        "image_scope",
        "confidence_score",
        "confidence_breakdown",
        "match_reason",
        "rights_status",
        "confidence_level",
        "is_primary_eligible",
    }.issubset(candidates[0])
    assert candidates[0]["source_page_url"] == page.url
    assert candidates[0]["source_publisher"] == "robots.example.com"
    assert candidates[0]["rights_status"] == "review_required"
    staged = StagedRobot(name="Lumabot", images=candidates)
    assert staged.to_dict()["images"][0]["source_domain"] == "robots.example.com"


def test_build_image_candidates_for_pages_keeps_string_selector_compatibility():
    page = PageContent(
        url="https://www.estun.com/gjjjqr/356.html",
        html="",
        title="iER8-720-MI-C - cleanroom robot",
        text="Model iER8-720-MI-C payload 8kg",
        images=[
            "https://www.estun.com/uploads/20250903/robot-hero.png",
            "https://www.estun.com/uploads/20250903/robot-side.png",
        ],
    )
    tokens = robot_name_tokens("iER8-720-MI-C", "iER8-720-MI-C")

    candidates = build_image_candidates_for_pages(
        [page],
        product_url=page.url,
        name="iER8-720-MI-C",
        model_name="iER8-720-MI-C",
        tokens=tokens,
    )
    hero, gallery = select_images_for_pages(
        [page],
        product_url=page.url,
        name="iER8-720-MI-C",
        model_name="iER8-720-MI-C",
        tokens=tokens,
    )

    assert all(isinstance(candidate, dict) for candidate in candidates)
    assert [candidate["url"] for candidate in candidates] == [hero, *gallery]
    assert all(isinstance(url, str) for url in [hero, *gallery])


def test_digit_token_does_not_false_positive_in_hash_filename():
    tokens = robot_name_tokens("iER8-720-MI-C", "iER8-720-MI-C")
    from web_extract import score_image

    score = score_image(
        "https://en.estun.com/static/upload/image/20240531/1717108713836720.jpg",
        tokens,
    )
    assert score <= 0


def test_select_confident_images_requires_model_token():
    tokens = robot_name_tokens("iER3-400-SR", "iER3-400-SR")
    generic = [
        "https://www.estun.com/skin/images/f-phone.png",
        "https://www.estun.com/uploads/20260521/11bf220482e4802ae2dc9f00e3fb5101.jpg",
        "https://www.estun.com/uploads/ier3-400-sr-product.jpg",
    ]
    hero, gallery = select_confident_images(generic, tokens)
    assert hero == "https://www.estun.com/uploads/ier3-400-sr-product.jpg"
    assert "f-phone" not in hero


def test_select_confident_videos_skips_generic_intro():
    tokens = robot_name_tokens("iER3-400-SR", "iER3-400-SR")
    videos = [
        {
            "url": "https://www.youtube.com/watch?v=intro",
            "title": "ESTUN ROBOTICS INTRODUCTION",
            "description": "Company overview of all industrial robots",
        },
        {
            "url": "https://www.youtube.com/watch?v=model",
            "title": "iER3-400-SR SCARA robot demo",
            "description": "Payload 3kg reach 400mm",
        },
    ]
    picked = select_confident_videos(videos, tokens)
    assert len(picked) == 1
    assert "iER3" in picked[0]["title"]
