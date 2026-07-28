"""Tests for YouTube metadata and tag suggestion."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_RESEARCH_DIR = Path(__file__).resolve().parents[1]
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from tag_suggest import TagCatalog  # noqa: E402
from youtube_metadata import enrich_video_list, extract_youtube_video_id, is_reject_robot_video_title  # noqa: E402


def test_extract_youtube_video_id():
    assert extract_youtube_video_id("https://www.youtube.com/watch?v=dQw4v9WgXcQ") == "dQw4v9WgXcQ"
    assert extract_youtube_video_id("https://youtu.be/abc12345678") == "abc12345678"


def test_reject_hash_uuid_wechat_titles():
    assert is_reject_robot_video_title("")
    assert is_reject_robot_video_title(
        "edd991e4f3def2a698c3b9f9ae8496d1 #人工智能 #ai #小鱼"
    )
    assert is_reject_robot_video_title("550e8400-e29b-41d4-a716-446655440000 demo")
    assert is_reject_robot_video_title("WeChat 20241219175819 #ai #robot")
    assert is_reject_robot_video_title(
        "#穿山甲机器人#AlphaRobotics#Panda#熊猫送餐机器人#餐宝#你好未来#送餐机器人#AI"
    )
    assert not is_reject_robot_video_title(
        "Our newest artificial intelligence robot-Alpha robotics-TImo"
    )
    assert not is_reject_robot_video_title(
        "Meet Panda, the Ultimate Delivery Robot by Alpha Robotics"
    )


@patch("youtube_metadata.fetch_youtube_metadata")
def test_enrich_skips_hash_title(mock_fetch):
    mock_fetch.return_value = {
        "url": "https://www.youtube.com/watch?v=NpYQVIj6bLs",
        "title": "edd991e4f3def2a698c3b9f9ae8496d1 #ai #小鱼",
        "description": "",
    }
    result = enrich_video_list(["https://www.youtube.com/watch?v=NpYQVIj6bLs"])
    assert result == []


@patch("youtube_metadata.fetch_youtube_metadata")
def test_enrich_video_list(mock_fetch):
    mock_fetch.return_value = {
        "url": "https://www.youtube.com/watch?v=dQw4v9WgXcQ",
        "title": "Demo Title",
        "description": "Demo description text",
    }
    result = enrich_video_list(["https://www.youtube.com/watch?v=dQw4v9WgXcQ"])
    assert len(result) == 1
    assert result[0]["title"] == "Demo Title"
    assert result[0]["description"] == "Demo description text"


def test_tag_catalog_suggest():
    catalog = TagCatalog(tags=[
        {"name": "AMR", "slug": "amr", "robots_count": 10},
        {"name": "Warehouse", "slug": "warehouse", "robots_count": 5},
        {"name": "Humanoid", "slug": "humanoid", "robots_count": 2},
    ])
    names = catalog.suggest(
        name="Lumabot AMR",
        description="Warehouse fulfillment autonomous mobile robot",
        movement_type_keys="wheeled",
        industry_keys="warehousing|logistics",
        max_tags=5,
    )
    assert "AMR" in names
    assert names[0] in ("AMR", "Warehouse")
