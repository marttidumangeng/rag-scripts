"""Regression tests for Yamaha company 1484 curated video cleanup."""

from __future__ import annotations

import io
import sys
from pathlib import Path
from typing import Any

from PIL import Image

RESEARCH_DIR = Path(__file__).resolve().parents[1]
if str(RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(RESEARCH_DIR))

import fix_yamaha_1484_robots as yamaha


class RecordingClient:
    def __init__(self) -> None:
        self.calls: list[tuple[list[dict[str, Any]], dict[str, Any]]] = []

    def bulk_import_robots(
        self, rows: list[dict[str, Any]], **kwargs: Any
    ) -> dict[str, Any]:
        self.calls.append((rows, kwargs))
        return {"error_count": 0, "updated_count": 1}


def test_xec_payload_has_only_official_yamaha_family_video() -> None:
    payload = yamaha.patch_payload(3520, "https://cdn.example/hero.png", "exact PDF")

    assert payload["video_urls"] == [
        {
            "url": "https://www.youtube.com/watch?v=spCY10jRA3g",
            "title": "【YK-X series】 Product Lineup and Application Introduction",
            "description": (
                "Official Yamaha Motor family overview covering the YK-X SCARA lineup; "
                "retained as family-level media because no exact-token YK-XEC video was found."
            ),
        }
    ]


def test_replace_robot_videos_uses_replace_flag_and_pending_status() -> None:
    client = RecordingClient()
    payload = yamaha.patch_payload(4757, "https://cdn.example/hero.png", "exact PDF")

    assert hasattr(yamaha, "replace_robot_videos")
    result = yamaha.replace_robot_videos(client, payload)

    assert result["error_count"] == 0
    assert client.calls == [
        (
            [
                {
                    "name": yamaha.PRODUCTS[4757]["official_name"],
                    "company_slug": "yamaha-motor-co-ltd-robotics-division",
                    "video_urls": payload["video_urls"],
                }
            ],
            {
                "update_existing": True,
                "patch_existing": True,
                "status": "pending_review",
                "skip_company_update": True,
                "replace_videos": True,
            },
        )
    ]


def test_upscale_product_render_preserves_alpha_and_reaches_hero_size() -> None:
    source = Image.new("RGBA", (230, 218), (255, 255, 255, 0))
    source.putpixel((115, 109), (12, 34, 56, 255))
    buffer = io.BytesIO()
    source.save(buffer, format="PNG")

    output = yamaha.upscale_product_render(buffer.getvalue())
    rendered = Image.open(io.BytesIO(output))

    assert rendered.format == "PNG"
    assert rendered.mode == "RGBA"
    assert max(rendered.size) >= 1_000
    assert rendered.getbbox() is not None


def test_yk1200_uses_exact_release_photo_instead_of_text_banner() -> None:
    assert yamaha.YK1200_IMAGE.endswith(
        "94545_0001-thumb-1000x618-256300.jpg"
    )
