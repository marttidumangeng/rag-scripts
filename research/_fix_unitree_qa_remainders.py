#!/usr/bin/env python3
"""Fix remaining Unitree QA: bad URLs + weak features/year from OEM pages."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from api_client import ResearchApiClient
from web_extract import WebFetcher, parse_page

# Curated English feature bullets from official Unitree product pages (plain HTTP).
# Kept short, model-specific, no promotional fluff beyond OEM claims.
CURATED = {
    40: {  # H1
        "url": "https://www.unitree.com/h1",
        "release_year": 2023,
        "features": (
            "Full-size humanoid platform for research and industry\n"
            "High degree-of-freedom limbs for dynamic walking and manipulation\n"
            "Developer-oriented SDK / secondary development support\n"
            "Modular compute and sensing for embodied-AI workloads"
        ),
        "purpose": "Full-size humanoid robot for research, development, and industrial exploration.",
    },
    126: {  # G1
        "url": "https://www.unitree.com/g1",
        "release_year": 2024,
        "features": (
            "Compact humanoid agent platform\n"
            "High-performance joint actuators for agile locomotion\n"
            "Expandable EDU configurations for research and training\n"
            "Designed for embodied AI avatar and humanoid application development"
        ),
        "purpose": "Compact humanoid robot for research, education, and embodied-AI development.",
    },
    44: {  # B2
        "url": "https://www.unitree.com/b2",
        "release_year": 2023,
        "features": (
            "Industrial quadruped for high-payload outdoor work\n"
            "Strong mobility on stairs, slopes, and rough terrain\n"
            "Long endurance for inspection and logistics tasks\n"
            "Expandable perception and compute payloads"
        ),
        "purpose": "Industrial quadruped robot for inspection, logistics, and outdoor mobility.",
    },
    42: {  # Go2
        "url": "https://www.unitree.com/go2",
        "release_year": 2023,
        "features": (
            "Consumer / research quadruped with 4D LiDAR sensing\n"
            "Multiple hardware tiers (Air / Pro / Edu)\n"
            "App and SDK control for education and development\n"
            "Compact form factor with agile gaits"
        ),
        "purpose": "Consumer and research quadruped robot for education, development, and exploration.",
    },
    282: {  # Laikago — legacy; no live PDP
        "url": "https://www.unitree.com/",
        "release_year": 2017,
        "features": (
            "Unitree's early research quadruped platform (legacy)\n"
            "Four-legged dynamic locomotion research platform\n"
            "Predecessor line to AlienGo / Go series"
        ),
        "purpose": "Legacy research quadruped from Unitree's early product line.",
        "notes_append": (
            "[IMAGE/URL NOTE — legacy model]\n"
            "No dedicated live product page found on unitree.com during 2026-07-18 enrich; "
            "URL left as company homepage. Confirm archive/datasheet if deeper specs needed."
        ),
    },
    348: {  # H2
        "url": "https://www.unitree.com/H2",
        "release_year": 2025,
        "features": (
            "Next-generation full-size humanoid platform\n"
            "Supports secondary development and system customization\n"
            "Aimed at industrial, commercial, and research deployments\n"
            "Companion configurations include EDU / PLUS / dual-arm variants"
        ),
        "purpose": "Full-size humanoid robot platform for industrial and research applications.",
    },
    601: {  # Unitree GD01
        "url": "https://www.unitree.com/",
        "features": (
            "Unitree GD01 product listing captured from company catalog signals\n"
            "Exact public English PDP not confirmed in this pass — verify on unitree.com"
        ),
        "notes_append": (
            "[URL/FEATURES TO-DO]\n"
            "Previously stored favicon.svg as source URL; cleared to homepage. "
            "Need dedicated GD01 product page before deeper specs."
        ),
    },
    660: {  # GD01 duplicate-ish
        "url": "https://www.unitree.com/",
        "notes_append": (
            "[URL/FEATURES TO-DO]\n"
            "Homepage-only source; features previously scraped from homepage chrome. "
            "Likely duplicate/overlap with Unitree GD01 (601) — review for merge."
        ),
    },
    5357: {  # B1
        "url": "https://www.unitree.com/b1",
        "release_year": 2021,
        "features": (
            "Industrial quadruped with deep waterproofing (IP68 class claims on OEM materials)\n"
            "High payload capacity for industrial outdoor work\n"
            "Designed for complex terrain and harsh weather\n"
            "Large-body platform for inspection and logistics payloads"
        ),
        "purpose": "Industrial waterproof quadruped for outdoor inspection and heavy-duty mobility.",
    },
}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    client = ResearchApiClient()

    # Spot-check key pages still fetch
    for url in (
        "https://www.unitree.com/h1",
        "https://www.unitree.com/g1",
        "https://www.unitree.com/b2",
        "https://www.unitree.com/go2",
        "https://www.unitree.com/H2",
        "https://www.unitree.com/b1",
    ):
        page = parse_page(WebFetcher(stealth=False), url, rendered=False)
        print(f"check {url} chars={len(page.text) if page else 0}")

    for rid, patch in CURATED.items():
        robot = client._get(f"robots/robots/{rid}/")
        existing_notes = robot.get("notes") or ""
        body = {
            k: v
            for k, v in patch.items()
            if k in {"url", "website_url", "features", "purpose", "release_year", "description"}
        }
        if "url" in body and "website_url" not in body:
            body["website_url"] = body["url"]
        note = patch.get("notes_append")
        if note and note not in existing_notes:
            body["notes"] = (note + "\n---\n" + existing_notes).strip() if existing_notes else note
        try:
            client._patch(f"robots/robots/{rid}/", body)
            print(f"patched {rid} {robot.get('name')} keys={sorted(body)}")
        except Exception as exc:
            print(f"FAIL {rid}: {exc}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
