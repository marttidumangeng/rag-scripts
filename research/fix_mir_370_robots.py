"""Curate MiR (370), remove duplicates, and correct third-party ownership."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import requests

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from api_client import ResearchApiClient
from load_env import load_research_env
from youtube_metadata import enrich_video_list

load_research_env()

COMPANY_ID = 370
COMPANY_NAME = "Mobile Industrial Robots (MiR)"
COMPANY_SLUG = "mobile-industrial-robots"
REPORT = _HERE / "staging" / "reports" / "mir-370-curated-report.json"
MIR1200_STAGING = (
    _HERE
    / "staging"
    / "robots"
    / COMPANY_SLUG
    / "mir1200-pallet-jack.json"
)
IDENTITIES_SNAPSHOT = (
    _HERE
    / "staging"
    / "catalog-snapshots"
    / "mir-370-existing-identities.json"
)
IMAGE_TODO = (
    "[IMAGE TO-DO — no hero, deliberate]\n"
    "Exact official product imagery was found, but MiR/Teradyne terms do not "
    "grant third-party commercial catalog republication. Any existing pending "
    "media must be detached before approval rather than treating public "
    "availability as a license.\n"
    "ACTION FOR TEAM: obtain written permission from roboticspr@teradyne.com or "
    "source an independently licensed exact-model image.\n"
    "Do NOT substitute a sibling render, family banner, or design/spec sheet.\n---"
)
ENABLED_IMAGE_TODO = (
    "[IMAGE TO-DO — no hero, deliberate]\n"
    "Enabled Robotics states that copying website images requires its written "
    "approval. Any existing pending media must be detached before approval.\n"
    "ACTION FOR TEAM: request written permission from contact@enabled-robotics.com "
    "or source an independently licensed exact-model image.\n"
    "Do NOT substitute a sibling render, family banner, or design/spec sheet.\n---"
)


def _candidate(
    *,
    url: str,
    source_page_url: str,
    source_tier: str,
    source_publisher: str,
    media_class: str,
    image_scope: str,
    confidence_score: int,
    match_reason: str,
    rights_status: str,
    description: str,
) -> dict[str, Any]:
    return {
        "url": url,
        "source_page_url": source_page_url,
        "source_tier": source_tier,
        "source_publisher": source_publisher,
        "media_class": media_class,
        "image_scope": image_scope,
        "confidence_score": confidence_score,
        "match_reason": match_reason,
        "rights_status": rights_status,
        "description": description,
    }


MIR_REVIEW_NOTE = (
    "Official MiR/Teradyne product imagery; public availability is not a reuse "
    "license. Keep the asset external and review_required. Obtain written "
    "permission from MiR/Teradyne before commercial catalog republication."
)
def _product(
    *,
    name: str,
    model: str,
    url: str,
    family: str,
    description: str,
    features: str,
    purpose: str,
    typed: dict[str, Any],
    availability: int,
    sources: list[str],
    videos: list[str] | None = None,
    notes: str = "",
) -> dict[str, Any]:
    return {
        "name": name,
        "model_name": model,
        "variant_code": model,
        "url": url,
        "family_key": f"{COMPANY_SLUG}:{family}",
        "family_name": model,
        "family_url": url,
        "product_url_scope": "exact_variant",
        "description": description,
        "features": features,
        "purpose": purpose,
        "typed": typed,
        "availability_status": availability,
        "sources": sources,
        "videos": videos or [],
        "notes": f"{IMAGE_TODO}\n{notes}".rstrip(),
    }


PRODUCTS: dict[int, dict[str, Any]] = {
    4233: _product(
        name="MiR100",
        model="MiR100",
        url="https://mobile-industrial-robots.com/about/mir-history",
        family="mir100",
        description=(
            "MiR100 is a compact autonomous mobile robot for internal transport "
            "of loads up to 100 kg in factories, warehouses, and healthcare sites."
        ),
        features=(
            "100 kg deck payload; 1.5 m/s maximum speed; 890 × 580 × 352 mm; "
            "360-degree safety coverage; autonomous obstacle avoidance; optional "
            "standard or extended battery; compatible with MiR Fleet and top modules."
        ),
        purpose="Internal material transport\nCart and component movement",
        typed={
            "payload_kg": 100,
            "weight_kg": 76.3,
            "speed": 5.4,
            "length_mm": 890,
            "width_mm": 580,
            "height_mm": 352,
            "runtime_minutes": 540,
        },
        availability=4,
        sources=[
            "https://mobile-industrial-robots.com/about/mir-history",
            "https://24279054.fs1.hubspotusercontent-na1.net/hubfs/24279054/Resources/MiR/MiR100%20Specifications%202.57.pdf",
            "https://www.idec-fs.com/en/mir_news/endofsale-100/",
        ],
        videos=["https://www.youtube.com/watch?v=tVmVoDankzc"],
        notes="Sales ended December 2023; MiR250 is the documented successor.",
    ),
    4234: _product(
        name="MiR200",
        model="MiR200",
        url="https://mobile-industrial-robots.com/about/mir-history",
        family="mir200",
        description=(
            "MiR200 is a compact autonomous mobile robot developed for flexible "
            "transport of loads up to 200 kg in dynamic indoor environments."
        ),
        features=(
            "200 kg deck payload; 1.1 m/s maximum speed; 890 × 580 × 352 mm; "
            "10-hour operating time; autonomous mapping and navigation; safety "
            "laser scanners and obstacle detection; MiR Fleet compatibility."
        ),
        purpose="Internal material transport\nProduction-line replenishment",
        typed={
            "payload_kg": 200,
            "weight_kg": 70,
            "speed": 3.96,
            "length_mm": 890,
            "width_mm": 580,
            "height_mm": 352,
            "runtime_minutes": 600,
        },
        availability=4,
        sources=[
            "https://mobile-industrial-robots.com/about/mir-history",
            "https://howtorobot.com/sites/default/files/2021-02/MiR200%20_%20Mobile%20Industrial%20Robots.pdf",
            "https://idec-fs.com/mir_news/endofsale-200/",
        ],
        notes="Sales ended December 2021; MiR250 is the documented successor.",
    ),
    4235: _product(
        name="MiR500",
        model="MiR500",
        url=(
            "https://howtorobot.com/sites/default/files/2021-02/"
            "MiR500%20_%20Mobile%20Industrial%20Robots.pdf"
        ),
        family="mir500",
        description=(
            "MiR500 is a heavy-duty autonomous mobile robot for transporting "
            "pallets and industrial loads up to 500 kg."
        ),
        features=(
            "500 kg payload; 2.0 m/s maximum speed; 1350 × 910 × 320 mm; "
            "226 kg robot mass; up to 7 hours at maximum payload; IP21; "
            "autonomous navigation in dynamic industrial environments."
        ),
        purpose="Heavy-load transport\nPallet and material movement",
        typed={
            "payload_kg": 500,
            "weight_kg": 226,
            "speed": 7.2,
            "length_mm": 1350,
            "width_mm": 910,
            "height_mm": 320,
            "runtime_minutes": 420,
        },
        availability=3,
        sources=[
            "https://howtorobot.com/sites/default/files/2021-02/MiR500%20_%20Mobile%20Industrial%20Robots.pdf",
            "https://mobile-industrial-robots.com/about/mir-history",
        ],
        videos=["https://www.youtube.com/watch?v=VUnFL9P8Z_E"],
        notes=(
            "Legacy model absent from the current sales catalog; no public OEM "
            "end-of-sale notice was found, so availability remains Released."
        ),
    ),
    4237: _product(
        name="MiR250 Hook",
        model="MiR250 Hook",
        url="https://mobile-industrial-robots.com/products/applications/mir250-hook",
        family="mir250",
        description=(
            "MiR250 Hook combines the MiR250 AMR with an autonomous tow hook to "
            "collect and move carts through manufacturing and logistics facilities."
        ),
        features=(
            "Up to 500 kg towing capacity at 1% incline and 300 kg at 5%; "
            "2.0 m/s maximum speed; adjustable hook height; automatic cart pickup; "
            "10-hour operating time; MiR Fleet compatibility."
        ),
        purpose="Autonomous cart towing\nMaterial-train transport",
        typed={
            "payload_kg": 500,
            "weight_kg": 188,
            "speed": 7.2,
            "length_mm": 1130,
            "width_mm": 580,
            "height_mm": 645,
            "runtime_minutes": 600,
        },
        availability=11,
        sources=[
            "https://mobile-industrial-robots.com/products/applications/mir250-hook",
            "https://mobile-industrial-robots.com/about/mir-history",
        ],
        notes=(
            "Dimensions are the minimum configured envelope; OEM range is "
            "1130–1220 × 580 × 645–895 mm. Typed payload is the 1% incline maximum. "
            "Exact official image candidate (2000×1248): "
            "https://a.storyblok.com/f/230581/2000x1248/55feb0d3c2/"
            "mir250hook-transparent.png — visible on the exact MiR250 Hook PDP, "
            "but Teradyne grants no commercial republication right. Corroborating "
            "article with two MiR-credited exact photos: "
            "https://www.automatedwarehouseonline.com/"
            "mir-launches-new-improved-mir250-hook-solution-for-autonomous-cart-towing/ "
            "— Automated Warehouse/WTWH provides no reuse license; request written "
            "permission before copying either article image."
        ),
    ),
    2142: _product(
        name="MiR250",
        model="MiR250",
        url="https://mobile-industrial-robots.com/products/robots/mir250",
        family="mir250",
        description=(
            "MiR250 is a compact autonomous mobile robot for transporting small "
            "and medium loads in dynamic industrial and logistics environments."
        ),
        features=(
            "250 kg payload; 2.0 m/s maximum speed; 800 × 580 × 300 mm; "
            "94 kg robot mass; up to 13 hours at maximum payload; IP21; "
            "replaceable lithium-ion battery; 12 certified safety functions."
        ),
        purpose="Internal material transport\nCart, pallet, and component movement",
        typed={
            "payload_kg": 250,
            "weight_kg": 94,
            "speed": 7.2,
            "length_mm": 800,
            "width_mm": 580,
            "height_mm": 300,
            "runtime_minutes": 780,
        },
        availability=11,
        sources=[
            "https://mobile-industrial-robots.com/products/robots/mir250",
            "https://mobile-industrial-robots.com/products/robots/mir250/specifications",
        ],
        videos=["https://www.youtube.com/watch?v=grGWLKxZH9o"],
    ),
    2146: _product(
        name="MiR600",
        model="MiR600",
        url="https://mobile-industrial-robots.com/products/robots/mir600",
        family="mir600",
        description=(
            "MiR600 is an IP52-rated autonomous mobile robot for transporting "
            "heavy loads and pallets up to 600 kg in demanding industrial sites."
        ),
        features=(
            "600 kg payload; 2.0 m/s maximum speed; 1350 × 910 × 322 mm; "
            "240 kg robot mass; 8.5 hours at maximum payload; IP52; "
            "lithium-ion battery; TÜV-evaluated safety functions."
        ),
        purpose="Heavy-load transport\nPallet and material movement",
        typed={
            "payload_kg": 600,
            "weight_kg": 240,
            "speed": 7.2,
            "length_mm": 1350,
            "width_mm": 910,
            "height_mm": 322,
            "runtime_minutes": 510,
        },
        availability=11,
        sources=[
            "https://mobile-industrial-robots.com/products/robots/mir600",
            "https://mobile-industrial-robots.com/products/robots/mir600/specifications",
        ],
        videos=["https://www.youtube.com/watch?v=tcCwobduJeE"],
    ),
    2151: _product(
        name="MiR1350",
        model="MiR1350",
        url="https://mobile-industrial-robots.com/products/robots/mir1350",
        family="mir1350",
        description=(
            "MiR1350 is MiR's highest-capacity deck-load AMR for autonomous "
            "transport of pallets and industrial loads up to 1,350 kg."
        ),
        features=(
            "1350 kg payload; 1.2 m/s maximum speed; 1350 × 910 × 322 mm; "
            "244 kg robot mass; 6 hours 45 minutes at maximum payload; IP52; "
            "lithium-ion battery; TÜV-evaluated safety functions."
        ),
        purpose="Very-heavy-load transport\nPallet and material movement",
        typed={
            "payload_kg": 1350,
            "weight_kg": 244,
            "speed": 4.32,
            "length_mm": 1350,
            "width_mm": 910,
            "height_mm": 322,
            "runtime_minutes": 405,
        },
        availability=11,
        sources=[
            "https://mobile-industrial-robots.com/products/robots/mir1350",
            "https://mobile-industrial-robots.com/products/robots/mir1350/specifications",
        ],
        videos=["https://www.youtube.com/watch?v=tcCwobduJeE"],
    ),
}

NEW_PRODUCTS: dict[str, dict[str, Any]] = {
    "MiR1200 Pallet Jack": {
        **_product(
            name="MiR1200 Pallet Jack",
            model="MiR1200 Pallet Jack",
            url=(
                "https://mobile-industrial-robots.com/products/robots/"
                "mir1200-pallet-jack/"
            ),
            family="mir1200-pallet-jack",
            description=(
                "MiR1200 Pallet Jack is an autonomous mobile robot for automated "
                "driverless conveyance of heavy loads, including floor-to-floor "
                "transport of EU pallets weighing up to 1,200 kg."
            ),
            features=(
                "1,200 kg maximum payload; 1.5 m/s maximum speed; "
                "1,934 × 820 × 2,120 mm; 750 kg robot mass; up to 10 hours "
                "active operation at maximum payload; IP52; AI-based perception "
                "for pallet detection; five 3D cameras, 3D lidar, three SICK "
                "safety laser scanners, and an ultrasonic pallet sensor."
            ),
            purpose=(
                "Floor-to-floor pallet transport\n"
                "Finished-goods and raw-material movement\n"
                "Waste-disposal pallet movement"
            ),
            typed={
                "payload_kg": 1200,
                "weight_kg": 750,
                "speed": 5.4,
                "length_mm": 1934,
                "width_mm": 820,
                "height_mm": 2120,
                "runtime_minutes": 600,
                "ip_rating": "IP52",
            },
            availability=11,
            sources=[
                (
                    "https://mobile-industrial-robots.com/products/robots/"
                    "mir1200-pallet-jack/"
                ),
                (
                    "https://mobile-industrial-robots.com/products/robots/"
                    "mir1200-pallet-jack/specifications"
                ),
                (
                    "https://mobile-industrial-robots.com/blog/"
                    "mir1200-pallet-jack-using-ai-to-revolutionize-pallet-handling"
                ),
                (
                    "https://investors.teradyne.com/news-events/press-releases/"
                    "detail/32/teradyne-robotics-to-bring-the-power-of-ai-to-"
                    "robotics-with-nvidia"
                ),
            ],
            notes=(
                "Launched 19 March 2024. Current official specification page "
                "states up to 10 hours active operation with maximum payload; "
                "the overview page's quick-facts block currently states 8 hours."
            ),
        ),
        "release_year": 2024,
        "category_slugs": "industrial-robots|mobile-robots",
        "sub_category_slug": "logistics-warehouse",
    }
}

REJECTS: dict[int, str] = {
    4653: "duplicate: MiR1000; keep published canonical record 244",
    4236: "duplicate: MiR1000; keep published canonical record 244",
    4652: "duplicate: MiR500; keep canonical pending record 4235",
    4238: (
        "invalid_configuration_name: no OEM MiR500 Shelf Carrier product; "
        "MiR500 used MiR Shelf Lift, while MiR Shelf Carrier 250 is a distinct "
        "MiR250 application"
    ),
}

REPARENT: dict[int, dict[str, Any]] = {
    3329: {
        "name": "ER-FLEX (MC250)",
        "model_name": "ER-FLEX",
        "variant_code": "MC250",
        "url": "https://www.enabled-robotics.com/er-flex",
        "family_key": "enabled-robotics:er-flex",
        "family_name": "ER-FLEX",
        "family_url": "https://www.enabled-robotics.com/er-flex",
        "description": (
            "ER-FLEX is an Enabled Robotics mobile collaborative robot family "
            "combining a MiR250 base with Universal Robots arms for flexible "
            "industrial manipulation and transport."
        ),
        "features": (
            "MiR250 mobile base; multiple Universal Robots arm options; integrated "
            "vision and safety system; autonomous navigation; mobile manipulation; "
            "variant-dependent arm and transport payloads."
        ),
        "purpose": "Mobile manipulation\nMachine tending\nAssembly and pick-and-place",
        "typed": {
            "speed": 7.2,
            "length_mm": 800,
            "width_mm": 580,
        },
        "availability_status": 11,
        "sources": [
            "https://www.enabled-robotics.com/er-flex",
            "https://www.enabled-robotics.com/partnernetwork",
        ],
        "videos": [],
        "notes": (
            f"{ENABLED_IMAGE_TODO}\nMC250 is the former MiR-marketplace name. "
            "Complete weight and payload vary by selected arm, so the stale "
            "universal 161 kg value was removed."
        ),
    },
    3330: {
        "name": "ER-MAX (MC600)",
        "model_name": "ER-MAX",
        "variant_code": "MC600",
        "url": "https://www.enabled-robotics.com/er-max",
        "family_key": "enabled-robotics:er-max",
        "family_name": "ER-MAX",
        "family_url": "https://www.enabled-robotics.com/er-max",
        "description": (
            "ER-MAX is an Enabled Robotics mobile collaborative robot that "
            "combines a MiR600 AMR with a UR20 or UR30 arm for autonomous "
            "heavy-duty mobile manipulation."
        ),
        "features": (
            "380 kg transport payload; UR20 or UR30 arm; 2.0 m/s maximum speed; "
            "1350 × 910 × 926 mm excluding arm; 460 kg system mass; integrated "
            "vision and safety; approximately four hours operating time."
        ),
        "purpose": "Heavy mobile manipulation\nMachine tending\nMaterial handling",
        "typed": {
            "payload_kg": 380,
            "weight_kg": 460,
            "speed": 7.2,
            "length_mm": 1350,
            "width_mm": 910,
            "height_mm": 926,
            "runtime_minutes": 240,
        },
        "availability_status": 11,
        "sources": [
            "https://www.enabled-robotics.com/er-max",
            "https://mobile-industrial-robots.com/news-center/new-mobile-collaborative-robot-combines-high-payload-autonomous-mobility-and-precision-robotics-arm-to-drive-industrial-automation-to-new-heights",
        ],
        "videos": ["https://www.youtube.com/watch?v=clQUM0-fJUc"],
        "notes": (
            f"{ENABLED_IMAGE_TODO}\nLaunched as MC600 in November 2024 and now "
            "marketed by its manufacturer as ER-MAX."
        ),
    },
}

PRODUCTS[4233]["images"] = [
    _candidate(
        url=(
            "https://a.storyblok.com/f/230581/297x168/80677dde67/"
            "mir100.png"
        ),
        source_page_url="https://mobile-industrial-robots.com/about/mir-history",
        source_tier="official_exact",
        source_publisher="Mobile Industrial Robots (MiR)",
        media_class="official_render",
        image_scope="exact_variant",
        confidence_score=69,
        match_reason="MiR history page labels this asset MiR100.",
        rights_status="review_required",
        description=MIR_REVIEW_NOTE,
    )
]
PRODUCTS[4234]["images"] = [
    _candidate(
        url=(
            "https://a.storyblok.com/f/230581/297x168/d97a53105e/"
            "mir200.png"
        ),
        source_page_url="https://mobile-industrial-robots.com/about/mir-history",
        source_tier="official_exact",
        source_publisher="Mobile Industrial Robots (MiR)",
        media_class="official_render",
        image_scope="exact_variant",
        confidence_score=69,
        match_reason="MiR history page labels this asset MiR200.",
        rights_status="review_required",
        description=MIR_REVIEW_NOTE,
    )
]
PRODUCTS[4235]["images"] = [
    _candidate(
        url=(
            "https://upload.wikimedia.org/wikipedia/commons/0/0f/"
            "MiR_500_at_automatica_tradeshow_2018.jpg"
        ),
        source_page_url=(
            "https://commons.wikimedia.org/wiki/"
            "File:MiR_500_at_automatica_tradeshow_2018.jpg"
        ),
        source_tier="reputable_third_party",
        source_publisher="Wikimedia Commons / Fernando Fandiño Oliver",
        media_class="product_photo",
        image_scope="exact_variant",
        confidence_score=90,
        match_reason=(
            "Commons file title, description, and visible trade-show robot "
            "identify the exact MiR500 model."
        ),
        rights_status="permission_confirmed",
        description=(
            "Photo by Fernando Fandiño Oliver, own work, licensed CC BY-SA 4.0 "
            "(https://creativecommons.org/licenses/by-sa/4.0). Attribute the "
            "author, link the Commons source and license, indicate changes, and "
            "share alike when adapting. This is not an OEM-owned image."
        ),
    )
]
PRODUCTS[4237]["images"] = [
    _candidate(
        url=(
            "https://a.storyblok.com/f/230581/791x612/970dd590ab/"
            "mir250-hook.png"
        ),
        source_page_url=(
            "https://mobile-industrial-robots.com/products/applications/"
            "mir250-hook"
        ),
        source_tier="official_exact",
        source_publisher="Mobile Industrial Robots (MiR)",
        media_class="official_render",
        image_scope="exact_variant",
        confidence_score=69,
        match_reason="Exact MiR250 Hook product-page social image.",
        rights_status="review_required",
        description=MIR_REVIEW_NOTE,
    )
]
PRODUCTS[2142]["images"] = [
    _candidate(
        url=(
            "https://a.storyblok.com/f/230581/672x421/2ae31882e5/"
            "mir250-fallbackteaser.png"
        ),
        source_page_url=(
            "https://mobile-industrial-robots.com/products/robots/mir250"
        ),
        source_tier="official_exact",
        source_publisher="Mobile Industrial Robots (MiR)",
        media_class="official_render",
        image_scope="exact_variant",
        confidence_score=69,
        match_reason="Exact MiR250 official product-page social image.",
        rights_status="review_required",
        description=MIR_REVIEW_NOTE,
    )
]
PRODUCTS[2146]["images"] = [
    _candidate(
        url=(
            "https://a.storyblok.com/f/230581/672x421/347d9337e1/"
            "mir600-fallbackteaser.png"
        ),
        source_page_url=(
            "https://mobile-industrial-robots.com/products/robots/mir600/"
        ),
        source_tier="official_exact",
        source_publisher="Mobile Industrial Robots (MiR)",
        media_class="official_render",
        image_scope="exact_variant",
        confidence_score=69,
        match_reason="Exact MiR600 official product-page social image.",
        rights_status="review_required",
        description=MIR_REVIEW_NOTE,
    )
]
PRODUCTS[2151]["images"] = [
    _candidate(
        url=(
            "https://a.storyblok.com/f/230581/672x421/bdb745e5ae/"
            "mir1350-fallbackteaser.png"
        ),
        source_page_url=(
            "https://mobile-industrial-robots.com/products/robots/mir1350/"
        ),
        source_tier="official_exact",
        source_publisher="Mobile Industrial Robots (MiR)",
        media_class="official_render",
        image_scope="exact_variant",
        confidence_score=69,
        match_reason="Exact MiR1350 official product-page social image.",
        rights_status="review_required",
        description=MIR_REVIEW_NOTE,
    )
]
NEW_PRODUCTS["MiR1200 Pallet Jack"]["images"] = [
    _candidate(
        url=(
            "https://a.storyblok.com/f/230581/1764x1920/13ab49ff91/"
            "mir1200-palletjack-transparent.png"
        ),
        source_page_url=NEW_PRODUCTS["MiR1200 Pallet Jack"]["url"],
        source_tier="official_exact",
        source_publisher="Mobile Industrial Robots (MiR)",
        media_class="official_render",
        image_scope="exact_variant",
        confidence_score=69,
        match_reason=(
            "Exact MiR1200 Pallet Jack official product-page social image."
        ),
        rights_status="review_required",
        description=MIR_REVIEW_NOTE,
    )
]
REPARENT[3329]["images"] = []
REPARENT[3329]["image_candidate_search"] = {
    "result": "no_exact_model_candidate_proven",
    "source_pages": [
        "https://www.enabled-robotics.com/er-flex",
        "https://www.enabled-robotics.com/partnernetwork",
        "https://www.enabled-robotics.com/mobilecobots",
    ],
    "actionable_note": (
        "Documented search confirmed ER-FLEX is also known as MC250, but the "
        "current official page presents multiple arm-specific ER-FLEX variants "
        "and family/group imagery. No image was provable as the exact retained "
        "ER-FLEX (MC250) record without choosing a sibling configuration. Keep "
        "the candidate list empty; request written approval for an exact-model "
        "asset from Enabled Robotics before republication."
    ),
}
REPARENT[3330]["images"] = []
REPARENT[3330]["image_candidate_search"] = {
    "result": "no_exact_model_candidate_proven",
    "source_pages": [
        "https://www.enabled-robotics.com/er-max",
        "https://www.enabled-robotics.com/partnernetwork",
        "https://www.enabled-robotics.com/mobilecobots",
    ],
    "actionable_note": (
        "Documented search confirmed ER-MAX is also known as MC600, but the "
        "current official page presents separate ER-MAX 600-20 and 600-30 "
        "configurations. No image was provable as the exact retained ER-MAX "
        "(MC600) record without choosing a sibling configuration. Keep the "
        "candidate list empty; request written approval for an exact-model "
        "asset from Enabled Robotics before republication."
    ),
}


def _base_payload(
    data: dict[str, Any],
    *,
    enabled: bool = False,
    clear_media: bool = True,
) -> dict[str, Any]:
    payload = {
        "name": data["name"],
        "model_name": data["model_name"],
        "variant_code": data["variant_code"],
        "description": data["description"],
        "features": data["features"],
        "purpose": data["purpose"],
        "url": data["url"],
        "family_key": data["family_key"],
        "family_name": data["family_name"],
        "family_url": data["family_url"],
        "product_url_scope": "exact_variant",
        "availability_status": data["availability_status"],
        "manufacturer_country_ref": 58,
        "manufacturer_countries": [58],
        "uses": [16, 62, 74, 32],
        "industries": [11, 12],
        "movement_types": [4],
        "tags": (
            ["AMR", "Autonomous", "Collaborative Robot", "Industrial"]
            if enabled
            else ["AMR", "Autonomous", "Industrial", "Warehouse Automation"]
        ),
        "information_source_urls": data["sources"],
        "notes": data["notes"],
        "status": "pending_review",
    }
    if clear_media:
        payload.update(
            {"image": "", "images": list(data.get("images") or []), "s3_image": None}
        )
    payload.update(data["typed"])
    return payload


def _new_product_staging_payload(
    data: dict[str, Any],
    *,
    dedupe_snapshot_id: str = "explicit-existing-identities",
) -> dict[str, Any]:
    return {
        "import_metadata": {
            "mode": "create_only",
            "natural_key_fields": ["company_slug", "name", "model_name"],
            "natural_key": {
                "company_slug": COMPANY_SLUG,
                "name": data["name"],
                "model_name": data["model_name"],
            },
            "dedupe_snapshot_id": dedupe_snapshot_id,
        },
        "name": data["name"],
        "company_slug": COMPANY_SLUG,
        "company_name": COMPANY_NAME,
        "model_name": data["model_name"],
        "variant_code": data["variant_code"],
        "family_name": data["family_name"],
        "family_key": data["family_key"],
        "family_url": data["family_url"],
        "product_url_scope": data["product_url_scope"],
        "manufacturer_country_code": "DK",
        "manufacturer_country_codes": "DK",
        "image": "",
        "images": list(data["images"]),
        "url": data["url"],
        "description": data["description"],
        "purpose": data["purpose"],
        "features": data["features"],
        "notes": data["notes"],
        "availability_status": data["availability_status"],
        "category_slugs": data["category_slugs"],
        "sub_category_slug": data["sub_category_slug"],
        "tags": "AMR|Autonomous|Industrial|Warehouse Automation|Pallet Transport",
        "release_year": data["release_year"],
        "sources": [
            {"url": url, "type": "website"} for url in data["sources"]
        ],
        "information_source_urls": list(data["sources"]),
        "research_notes": (
            "All numeric fields are sourced from the current official MiR1200 "
            "Pallet Jack specifications page listed in sources. Release year and "
            "AI feature details are sourced from the official MiR launch article "
            "and Teradyne press release. Local create-only staging; no production apply."
        ),
        "status": "pending_review",
        **data["typed"],
    }


def build_create_only_rows(
    existing_rows: list[dict[str, Any]],
    *,
    dedupe_snapshot_id: str = "explicit-existing-identities",
) -> list[dict[str, Any]]:
    """Stage MiR1200 only when exact name and model identity are absent."""
    data = NEW_PRODUCTS["MiR1200 Pallet Jack"]
    identity = (
        COMPANY_SLUG,
        data["name"].strip(),
        data["model_name"].strip(),
    )
    existing_identities: set[tuple[str, str, str]] = set()
    for row in existing_rows:
        if not isinstance(row, dict):
            continue
        existing_identity = tuple(
            str(row.get(field) or "").strip()
            for field in ("company_slug", "name", "model_name")
        )
        if all(existing_identity):
            existing_identities.add(existing_identity)
    if identity in existing_identities:
        return []
    return [
        _new_product_staging_payload(
            data,
            dedupe_snapshot_id=dedupe_snapshot_id,
        )
    ]


def load_identity_snapshot(path: Path) -> tuple[list[dict[str, Any]], str]:
    """Load the required local catalog identity snapshot and fail closed."""
    if not path.is_file():
        raise FileNotFoundError(f"local identity snapshot not found: {path}")
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    if snapshot.get("company_id") != COMPANY_ID:
        raise ValueError(f"identity snapshot company_id must be {COMPANY_ID}")
    snapshot_id = str(snapshot.get("snapshot_id") or "").strip()
    if not snapshot_id:
        raise ValueError("identity snapshot_id is required")
    identities = snapshot.get("identities")
    if not isinstance(identities, list):
        raise ValueError("identity snapshot identities must be a list")
    required_fields = ("company_slug", "name", "model_name")
    for index, row in enumerate(identities):
        if not isinstance(row, dict):
            raise ValueError(f"identity snapshot row {index} must be an object")
        missing = [
            field
            for field in required_fields
            if not str(row.get(field) or "").strip()
        ]
        if missing:
            raise ValueError(
                f"identity snapshot row {index} missing required field(s): "
                f"{', '.join(missing)}"
            )
    return identities, snapshot_id


def _candidate_mappings() -> list[dict[str, Any]]:
    mappings = [
        {
            "record": f"MiR existing ID {robot_id}",
            "model": data["model_name"],
            "candidates": data["images"],
        }
        for robot_id, data in sorted(PRODUCTS.items())
    ]
    mappings.extend(
        {
            "record": f"Enabled Robotics existing ID {robot_id}",
            "model": data["model_name"],
            "candidates": data["images"],
            "empty_candidate_search": data.get("image_candidate_search"),
        }
        for robot_id, data in sorted(REPARENT.items())
    )
    mappings.extend(
        {
            "record": "MiR create-only staging",
            "model": model,
            "candidates": data["images"],
        }
        for model, data in sorted(NEW_PRODUCTS.items())
    )
    return mappings


def _admin_base() -> str:
    return os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/").replace(
        "/api/v1", ""
    )


def detach_photos(
    client: ResearchApiClient, robot_ids: set[int]
) -> tuple[list[dict[str, int]], set[int]]:
    session_id = os.environ.get("ADMIN_SESSION_ID", "").strip()
    removed = []
    blocked: set[int] = set()
    for rid in sorted(robot_ids):
        detail = client._get(f"robots/robots/{rid}/")
        photos = detail.get("photos") or []
        if photos and not session_id:
            blocked.add(rid)
            continue
        for photo in photos:
            response = requests.delete(
                f"{_admin_base()}/admin/robots/robot/content-queue/api/robot/"
                f"{rid}/photos/{photo['id']}/",
                cookies={"sessionid": session_id},
                timeout=60,
            )
            if not response.ok:
                raise RuntimeError(
                    f"photo detach failed {rid}/{photo['id']}: "
                    f"{response.status_code} {response.text[:200]}"
                )
            removed.append({"robot_id": rid, "photo_id": int(photo["id"])})
    return removed, blocked


def replace_videos(
    client: ResearchApiClient,
    rid: int,
    data: dict[str, Any],
    *,
    company_name: str,
    company_slug: str,
) -> dict[str, Any]:
    row = {
        "id": rid,
        "name": data["name"],
        "company_name": company_name,
        "company_slug": company_slug,
        "manufacturer_country_code": "DK",
        "manufacturer_country_codes": "DK",
        "video_urls": enrich_video_list(data["videos"]),
    }
    return client.bulk_import_robots(
        [row],
        update_existing=True,
        patch_existing=True,
        status="pending_review",
        skip_company_update=True,
        replace_videos=True,
    )


def ensure_enabled_company(client: ResearchApiClient) -> int:
    matches = client.search_companies("Enabled Robotics", page_size=20)
    exact = [row for row in matches if row.get("name") == "Enabled Robotics"]
    if not exact:
        first_id = sorted(REPARENT)[0]
        client._patch(
            f"robots/robots/{first_id}/",
            {"company": "Enabled Robotics"},
        )
        matches = client.search_companies("Enabled Robotics", page_size=20)
        exact = [row for row in matches if row.get("name") == "Enabled Robotics"]
        if not exact:
            try:
                exact = [client.get_company("enabled-robotics")]
            except Exception:
                exact = []
    if len(exact) != 1:
        raise RuntimeError(f"Enabled Robotics company resolution failed: {exact}")
    company_id = int(exact[0]["id"])
    client.patch_company(
        company_id,
        {
            "slug": "enabled-robotics",
            "website": "https://www.enabled-robotics.com/",
            "country_id": 58,
            "short_description": (
                "Danish manufacturer of mobile collaborative robot systems "
                "combining AMRs, robot arms, vision, safety, and fleet software."
            ),
            "description": (
                "Enabled Robotics develops mobile collaborative robots for "
                "industrial manipulation and transport. Its ER-FLEX and ER-MAX "
                "systems integrate MiR mobile bases with Universal Robots arms."
            ),
            "sources": (
                "https://www.enabled-robotics.com/\n"
                "https://www.enabled-robotics.com/er-flex\n"
                "https://www.enabled-robotics.com/er-max"
            ),
        },
    )
    return company_id


def apply_reparent(
    client: ResearchApiClient,
    enabled_company_id: int,
    media_detach_blocked: set[int],
) -> list[int]:
    for rid, data in REPARENT.items():
        replace_videos(
            client,
            rid,
            data,
            company_name="Enabled Robotics",
            company_slug="enabled-robotics",
        )
        client._patch(
            f"robots/robots/{rid}/",
            {
                "company": "Enabled Robotics",
                "company_owner_ids": [enabled_company_id],
                **_base_payload(
                    data,
                    enabled=True,
                    clear_media=rid not in media_detach_blocked,
                ),
            },
        )
    return sorted(REPARENT)


def reject_invalid(client: ResearchApiClient) -> list[int]:
    for rid, reason in REJECTS.items():
        client._patch(
            f"robots/robots/{rid}/",
            {
                "status": "rejected",
                "rejection_reason": reason,
                "notes": f"[CURATED FULL 2026-07-21] {reason}",
            },
        )
    return sorted(REJECTS)


def verify(
    client: ResearchApiClient,
    enabled_company_id: int,
    media_detach_blocked: set[int],
) -> dict[str, Any]:
    rows = client.list_robots_for_company(COMPANY_ID)
    pending = {int(row["id"]): row for row in rows if row.get("status") == "pending_review"}
    if set(pending) != set(PRODUCTS):
        raise RuntimeError(f"MiR pending mismatch: {sorted(pending)}")
    for rid in PRODUCTS:
        detail = client._get(f"robots/robots/{rid}/")
        if (
            rid not in media_detach_blocked
            and (detail.get("image") or detail.get("s3_image") or detail.get("photos"))
        ):
            raise RuntimeError(f"restricted MiR media remains attached to {rid}")
        if not detail.get("family_key"):
            raise RuntimeError(f"missing family_key on {rid}")
    for rid in REPARENT:
        detail = client._get(f"robots/robots/{rid}/")
        owners = {int(owner["id"]) for owner in detail.get("company_owners") or []}
        if owners != {enabled_company_id}:
            raise RuntimeError(f"Enabled ownership mismatch {rid}: {owners}")
        if (
            rid not in media_detach_blocked
            and (detail.get("image") or detail.get("s3_image") or detail.get("photos"))
        ):
            raise RuntimeError(f"restricted Enabled media remains attached to {rid}")
    return {
        "mir_pending_ids": sorted(pending),
        "mir_rejected_ids": sorted(REJECTS),
        "enabled_company_id": enabled_company_id,
        "enabled_pending_ids": sorted(REPARENT),
        "image_permission_holds": sorted(set(PRODUCTS) | set(REPARENT)),
        "media_detach_blocked_ids": sorted(media_detach_blocked),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Curate MiR company 370")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--existing-identities",
        type=Path,
        default=IDENTITIES_SNAPSHOT,
        help="Required local/read-only MiR identity snapshot for create-only dedupe",
    )
    args = parser.parse_args(argv)
    if args.apply:
        raise SystemExit(
            "production apply is disabled for Image Rights Review Task 3; "
            "this script writes local staging artifacts only"
        )

    existing_identities, snapshot_id = load_identity_snapshot(
        args.existing_identities
    )
    staged_rows = build_create_only_rows(
        existing_identities,
        dedupe_snapshot_id=snapshot_id,
    )
    report: dict[str, Any] = {
        "company_id": COMPANY_ID,
        "mode": "local-staging-dry-run",
        "production_apply": False,
        "production_records_mutated": False,
        "products": sorted(PRODUCTS),
        "rejects": REJECTS,
        "reparent": sorted(REPARENT),
        "mir1200": {
            "model": "MiR1200 Pallet Jack",
            "create_only": True,
            "dedupe_identity_fields": ["company_slug", "name", "model_name"],
            "dedupe_snapshot_id": snapshot_id,
            "dedupe_result": (
                "stage_create" if staged_rows else "skip_exact_existing"
            ),
            "staged_rows": len(staged_rows),
            "staging_file": str(MIR1200_STAGING),
            "status": "pending_review",
            "source_urls": NEW_PRODUCTS["MiR1200 Pallet Jack"]["sources"],
        },
        "candidate_mappings": _candidate_mappings(),
        "media_policy": (
            "Candidates remain external. MiR/Teradyne assets are review_required "
            "pending written permission; the MiR500 Wikimedia Commons candidate "
            "is permission_confirmed under CC BY-SA 4.0. Enabled Robotics "
            "candidate lists are intentionally empty because no exact retained-"
            "model image was proven without selecting a sibling configuration."
        ),
        "no_production_apply_note": (
            "Local staging only. No production endpoint was called and no "
            "production record, image, or media object was mutated."
        ),
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    MIR1200_STAGING.parent.mkdir(parents=True, exist_ok=True)
    if staged_rows:
        MIR1200_STAGING.write_text(
            json.dumps(staged_rows[0], indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    elif MIR1200_STAGING.exists():
        MIR1200_STAGING.unlink()
    REPORT.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print("LOCAL STAGING ONLY — NO PRODUCTION APPLY")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
