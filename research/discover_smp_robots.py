"""Curated SMP Robotics (212) soft enrich — S-series UGVs.

OEM: https://www.smprobotics.com / products_autonomous_ugv/
Shared S-series chassis specs (2021 table): 4–6 km/h, 1420×780×1750 mm,
110 kg, up to 24 km range, IP65.

Pending (13) + soft-fill published Argus S5.2 (5250) + Bird Control (5252).

Usage:
  python discover_smp_robots.py --apply
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import requests

_RESEARCH = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient
from import_staging import import_staging, resolve_created_by_id

COMPANY_SLUG = "smp-robotics"
COMPANY_NAME = "SMP Robotics"
US_ID = 20
AVAILABLE = 11

# Shared S-series platform (OEM products_autonomous_ugv 2021 table)
PLATFORM = {
    "speed": 6.0,  # 4–6 km/h cited; store upper cruise
    "length_mm": 1420,
    "width_mm": 780,
    "height_mm": 1750,
    "weight_kg": 110.0,
}

FAM_S5 = {
    "family_key": "smp:s5-argus",
    "family_name": "Argus S5",
    "family_url": "https://smprobotics.com/security_robot/security-patrol-robot/",
}
FAM_S2 = {
    "family_key": "smp:s2-gas-monitor",
    "family_name": "S2 Gas / Air Monitor",
    "family_url": "https://smprobotics.com/products_autonomous_ugv/area-and-perimeter-gas-monitoring-robot/",
}
FAM_S3 = {
    "family_key": "smp:s3-inspector",
    "family_name": "S3 Inspector",
    "family_url": "https://smprobotics.com/products_autonomous_ugv/electrical-substation-inspection-robot/",
}
FAM_S4 = {
    "family_key": "smp:s4-bird",
    "family_name": "S4 Bird Control",
    "family_url": "https://smprobotics.com/products_autonomous_ugv/bird-control-robot/",
}
FAM_S6 = {
    "family_key": "smp:s6-gas-leak",
    "family_name": "S6 Gas Leak",
    "family_url": "https://smprobotics.com/products_autonomous_ugv/gas-leak-inspection-robot/",
}
FAM_S7 = {
    "family_key": "smp:s7-delivery",
    "family_name": "S7 Delivery",
    "family_url": "https://smprobotics.com/products_autonomous_ugv/autonomous-delivery-robot/",
}
FAM_S8 = {
    "family_key": "smp:s8-mosquito",
    "family_name": "S8 Mosquito Control",
    "family_url": "https://smprobotics.com/products_autonomous_ugv/mosquito-control-robot/",
}
FAM_S11 = {
    "family_key": "smp:s11-telepresence",
    "family_name": "S11 Telepresence",
    "family_url": "https://smprobotics.com/products_autonomous_ugv/virtual-telepresence-robot/",
}

PRODUCTS: list[dict[str, Any]] = [
    # --- published soft-fill ---
    {
        "id": 5250,
        "published": True,
        "name": "Argus S5.2",
        "model_name": "Argus S5.2",
        "variant_code": "S5.2",
        "variant_label": "S5.2",
        "url": "https://smprobotics.com/products_autonomous_ugv/security-patrol-robot/",
        **FAM_S5,
        "product_url_scope": "exact_variant",
        "purpose": (
            "Outdoor autonomous security patrol\n"
            "360° mobile video surveillance with PTZ tracking"
        ),
        "description": (
            "Argus S5.2 is SMP Robotics' affordable outdoor autonomous security patrol "
            "UGV for well-maintained sites. Six panoramic cameras plus an HD PTZ enable "
            "360° surveillance and person tracking, with ONVIF VMS integration and "
            "automatic docking."
        ),
        "features": (
            "OEM smprobotics.com S5.2: six panoramic cameras + HD PTZ (track ~50 m); "
            "face highlighting; optional thermal PTZ sibling; flashing lights; mic/"
            "intercom; group patrol route sharing; ONVIF (Genetec/Milestone/Avigilon); "
            "auto docking. S-series platform: 4–6 km/h, ~24 km range, 1420×780×1750 mm, "
            "~110 kg, IP65, −20…+45 °C (OEM 2021 table)."
        ),
        "use_keys": "patrol|security|surveillance",
        "industry_keys": "security|civil-security-emergency",
        "category_slugs": "Security",
        "movement_keys": "wheeled",
        "tags": ["SMP", "Argus", "S5", "Security", "Patrol", "UGV", "USA"],
        "sources": [
            {
                "url": "https://smprobotics.com/products_autonomous_ugv/security-patrol-robot/",
                "type": "website",
                "title": "OEM Argus S5.2",
            },
            {
                "url": "https://smprobotics.com/products_autonomous_ugv/",
                "type": "website",
                "title": "OEM S-series hub",
            },
        ],
    },
    {
        "id": 5252,
        "published": True,
        "name": "Bird Control Robot",
        "model_name": "S4 Bird Control",
        "variant_code": "S4",
        "variant_label": "Bird Control",
        "url": "https://smprobotics.com/products_autonomous_ugv/bird-control-robot/",
        **FAM_S4,
        "product_url_scope": "exact_variant",
        "purpose": (
            "Wildlife and bird deterrence on outdoor sites\n"
            "Mobile scare/patrol for agriculture and coastal facilities"
        ),
        "description": (
            "The Bird Control Robot (S4) is SMP Robotics' autonomous UGV configured for "
            "bird and animal deterrence in agriculture and coastal facilities, using the "
            "shared S-series outdoor mobile platform."
        ),
        "features": (
            "OEM smprobotics.com bird-control-robot (S4): autonomous outdoor UGV for "
            "wildlife deterrence; shared S-series chassis (4–6 km/h, ~110 kg, "
            "1420×780×1750 mm, IP65, auto dock). Soft: deterrent payload details vary "
            "by option; MSRP not typed on OEM page."
        ),
        "use_keys": "patrol|agriculture|monitoring",
        "industry_keys": "agriculture|security",
        "category_slugs": "Agricultural-Robots|Security",
        "movement_keys": "wheeled",
        "tags": ["SMP", "S4", "Bird Control", "Agriculture", "UGV", "USA"],
        "sources": [
            {
                "url": "https://smprobotics.com/products_autonomous_ugv/bird-control-robot/",
                "type": "website",
                "title": "OEM Bird Control",
            },
            {
                "url": "https://smprobotics.com/products_autonomous_ugv/",
                "type": "website",
                "title": "OEM S-series hub",
            },
        ],
    },
    # --- pending ---
    {
        "id": 5257,
        "name": "S5 HD Security Robot",
        "model_name": "Argus S5 HD",
        "variant_code": "S5-HD",
        "variant_label": "HD",
        "url": "https://smprobotics.com/security_robot/security-patrol-robot/patrolling_restricted_areas/",
        **FAM_S5,
        "product_url_scope": "exact_variant",
        "purpose": (
            "Daytime HD panoramic patrol of restricted areas\n"
            "360° high-resolution outdoor video surveillance"
        ),
        "description": (
            "The S5 HD Security Robot is an Argus S5 configuration with six HD 1080p "
            "panoramic cameras for well-lit or daytime-heavy restricted-area patrols on "
            "SMP's outdoor wheeled UGV platform."
        ),
        "features": (
            "OEM patrolling_restricted_areas: S5 HD with six HD panoramic cameras for "
            "360° ultra-high-res view; best for well-lit/daytime sites; shared Argus "
            "S5 / S-series platform (4–6 km/h, ~110 kg, 1420×780×1750 mm, IP65, auto "
            "dock, ONVIF). Soft: exact camera model codes vary by year."
        ),
        "use_keys": "patrol|security|surveillance",
        "industry_keys": "security|civil-security-emergency",
        "category_slugs": "Security",
        "movement_keys": "wheeled",
        "tags": ["SMP", "Argus", "S5", "HD", "Security", "Patrol", "USA"],
        "sources": [
            {
                "url": "https://smprobotics.com/security_robot/security-patrol-robot/patrolling_restricted_areas/",
                "type": "website",
                "title": "OEM S5 HD",
            },
            {
                "url": "https://smprobotics.com/security_robot/security-patrol-robot/",
                "type": "website",
                "title": "OEM Argus hub",
            },
        ],
    },
    {
        "id": 5259,
        "name": "S5 PTZ Security Robot",
        "model_name": "Argus S5 PTZ",
        "variant_code": "S5-PTZ",
        "variant_label": "PTZ",
        "url": "https://smprobotics.com/security_robot/security-patrol-robot/rapid_deployment_surveillance_system/",
        **FAM_S5,
        "product_url_scope": "exact_variant",
        "purpose": (
            "Long-range PTZ tracking during autonomous patrol\n"
            "Face and human detection for restricted sites"
        ),
        "description": (
            "The S5 PTZ Security Robot adds an operated PTZ zoom camera (~28× class) to "
            "the Argus S5 panoramic suite for long-distance human tracking and face "
            "detection on the shared SMP outdoor UGV chassis."
        ),
        "features": (
            "OEM S5 PTZ IS: six panoramic cameras + PTZ with ~28× zoom; auto or manual "
            "track; face detection at distance; shared S-series platform specs "
            "(4–6 km/h, ~110 kg, 1420×780×1750 mm, IP65). Soft: rapid-deployment page "
            "is the config hub URL retained from queue."
        ),
        "use_keys": "patrol|security|surveillance",
        "industry_keys": "security|civil-security-emergency",
        "category_slugs": "Security",
        "movement_keys": "wheeled",
        "tags": ["SMP", "Argus", "S5", "PTZ", "Security", "Patrol", "USA"],
        "sources": [
            {
                "url": "https://smprobotics.com/security_robot/security-patrol-robot/rapid_deployment_surveillance_system/",
                "type": "website",
                "title": "OEM S5 PTZ / rapid deploy",
            },
            {
                "url": "https://smprobotics.com/products_autonomous_ugv/security-patrol-robot/",
                "type": "website",
                "title": "OEM S5.2 PTZ notes",
            },
        ],
    },
    {
        "id": 5260,
        "name": "S5 Thermal Security Robot",
        "model_name": "Argus S5 Thermal",
        "variant_code": "S5-IR",
        "variant_label": "Thermal",
        "url": "https://smprobotics.com/security_robot/thermal-security-robot/",
        **FAM_S5,
        "product_url_scope": "exact_variant",
        "purpose": (
            "Night and low-light perimeter patrol with thermal PTZ\n"
            "Human detection without site lighting"
        ),
        "description": (
            "The S5 Thermal (IR) Security Robot is the Argus S5 dual-spectrum "
            "configuration with optical zoom plus uncooled thermal PTZ for night "
            "patrols on unlit perimeters."
        ),
        "features": (
            "OEM thermal-security-robot: dual-spectrum PTZ (optical + thermal IR); "
            "detect humans hundreds of yards day/night without lighting; panoramic "
            "suite retained; night route markers for dark segments; S-series platform "
            "(4–6 km/h, ~110 kg, IP65, 1420×780×1750 mm)."
        ),
        "use_keys": "patrol|security|surveillance",
        "industry_keys": "security|civil-security-emergency|energy",
        "category_slugs": "Security",
        "movement_keys": "wheeled",
        "tags": ["SMP", "Argus", "S5", "Thermal", "IR", "Security", "USA"],
        "sources": [
            {
                "url": "https://smprobotics.com/security_robot/thermal-security-robot/",
                "type": "website",
                "title": "OEM S5 Thermal",
            },
            {
                "url": "https://smprobotics.com/security_robot/security-patrol-robot/",
                "type": "website",
                "title": "OEM Argus hub",
            },
        ],
    },
    {
        "id": 5258,
        "name": "S5 Perimeter Control Robot",
        "model_name": "Argus S5 Perimeter",
        "variant_code": "S5-Perimeter",
        "variant_label": "Perimeter",
        "url": "https://smprobotics.com/security_robot/security-patrol-robot/perimeter_control_robot/",
        **FAM_S5,
        "product_url_scope": "exact_variant",
        "purpose": (
            "Perimeter patrol under harsh mixed lighting\n"
            "Wide-dynamic-range panoramic surveillance"
        ),
        "description": (
            "The S5 Perimeter Control Robot is an Argus S5 AI configuration tuned for "
            "challenging lighting (tree shade, uneven night lighting) with "
            "high-sensitivity wide-dynamic-range panoramic cameras."
        ),
        "features": (
            "OEM perimeter_control_robot: high-sensitivity WDR panoramic cameras for "
            "~15–20 yd monitoring in harsh light; Argus S5 outdoor UGV platform "
            "(4–6 km/h, ~110 kg, 1420×780×1750 mm, IP65, auto dock). Soft: sibling of "
            "HD/PTZ/Thermal camera packages."
        ),
        "use_keys": "patrol|security|surveillance",
        "industry_keys": "security|civil-security-emergency",
        "category_slugs": "Security",
        "movement_keys": "wheeled",
        "tags": ["SMP", "Argus", "S5", "Perimeter", "Security", "USA"],
        "sources": [
            {
                "url": "https://smprobotics.com/security_robot/security-patrol-robot/perimeter_control_robot/",
                "type": "website",
                "title": "OEM Perimeter Control",
            },
            {
                "url": "https://smprobotics.com/security_robot/security-patrol-robot/",
                "type": "website",
                "title": "OEM Argus hub",
            },
        ],
    },
    {
        "id": 5263,
        "name": "Solar Powered Security Robot",
        "model_name": "Argus S5 Solar",
        "variant_code": "S5-Solar",
        "variant_label": "Solar",
        "url": "https://smprobotics.com/products_autonomous_ugv/solar-powered-security-robot/",
        **FAM_S5,
        "product_url_scope": "exact_variant",
        "purpose": (
            "Off-grid outdoor video surveillance with solar top-up\n"
            "Long-dwell security patrol without grid power"
        ),
        "description": (
            "The Solar Powered Security Robot (S5 S) adds solar panels to the Argus S5 "
            "platform so continuous video monitoring can run with reduced dependence on "
            "external power grids at remote sites."
        ),
        "features": (
            "OEM solar-powered-security-robot (S5 S): solar panels for continuous "
            "monitoring without grid cabling; shared S-series chassis (4–6 km/h, "
            "~110 kg, 1420×780×1750 mm, IP65). Soft: panel wattage / duty cycle not "
            "typed on page scrape."
        ),
        "use_keys": "patrol|security|surveillance|monitoring",
        "industry_keys": "security|energy",
        "category_slugs": "Security",
        "movement_keys": "wheeled",
        "tags": ["SMP", "Argus", "S5", "Solar", "Security", "Off-grid", "USA"],
        "sources": [
            {
                "url": "https://smprobotics.com/products_autonomous_ugv/solar-powered-security-robot/",
                "type": "website",
                "title": "OEM Solar Security",
            },
            {
                "url": "https://smprobotics.com/products_autonomous_ugv/",
                "type": "website",
                "title": "OEM S-series hub",
            },
        ],
    },
    {
        "id": 5262,
        "name": "Smart House Security Robot",
        "model_name": "Argus S5 Smart House",
        "variant_code": "S5-SmartHouse",
        "variant_label": "Smart House",
        "url": "https://smprobotics.com/products_autonomous_ugv/smart-house-security-robot/",
        **FAM_S5,
        "product_url_scope": "exact_variant",
        "purpose": (
            "24/7 autonomous patrol of private estates\n"
            "Residential and smart-home outdoor security"
        ),
        "description": (
            "The Smart House Security Robot is the Argus S5 configuration positioned for "
            "round-the-clock patrolling and protection of private residences and estates."
        ),
        "features": (
            "OEM smart-house-security-robot: Argus S5 for private areas / smart home; "
            "panoramic + PTZ class surveillance; S-series platform (4–6 km/h, ~110 kg, "
            "1420×780×1750 mm, IP65, auto dock). Soft: consumer MSRP not listed."
        ),
        "use_keys": "patrol|security|surveillance",
        "industry_keys": "security",
        "category_slugs": "Security",
        "movement_keys": "wheeled",
        "tags": ["SMP", "Argus", "S5", "Smart House", "Residential", "Security", "USA"],
        "sources": [
            {
                "url": "https://smprobotics.com/products_autonomous_ugv/smart-house-security-robot/",
                "type": "website",
                "title": "OEM Smart House",
            },
            {
                "url": "https://smprobotics.com/security_robot/security-patrol-robot/",
                "type": "website",
                "title": "OEM Argus hub",
            },
        ],
    },
    {
        "id": 5254,
        "name": "Mobile ALPR Robot",
        "model_name": "Argus S5 ALPR",
        "variant_code": "S5-ALPR",
        "variant_label": "ALPR",
        "url": "https://smprobotics.com/products_autonomous_ugv/automatic-license-plate-recognition-mobile-system/",
        **FAM_S5,
        "product_url_scope": "exact_variant",
        "purpose": (
            "Mobile automatic license plate recognition on patrol\n"
            "Parking-lot security and plate inventory"
        ),
        "description": (
            "The Mobile ALPR Robot is an Argus S5 configuration with automatic license "
            "plate recognition for parking lots and vehicle areas, combining ALPR cameras "
            "with panoramic security surveillance."
        ),
        "features": (
            "OEM ALPR mobile system: S5 ALPR reads plates while patrolling at pedestrian "
            "speed; dual-side reading; panoramic security cameras; obstacle avoidance; "
            "S-series platform (4–6 km/h, ~110 kg, 1420×780×1750 mm, IP65). Soft: ALPR "
            "vendor module SKU not typed."
        ),
        "use_keys": "patrol|security|surveillance|monitoring",
        "industry_keys": "security|logistics",
        "category_slugs": "Security",
        "movement_keys": "wheeled",
        "tags": ["SMP", "Argus", "S5", "ALPR", "Parking", "Security", "USA"],
        "sources": [
            {
                "url": "https://smprobotics.com/products_autonomous_ugv/automatic-license-plate-recognition-mobile-system/",
                "type": "website",
                "title": "OEM Mobile ALPR",
            },
            {
                "url": "https://smprobotics.com/products_autonomous_ugv/",
                "type": "website",
                "title": "OEM S-series hub",
            },
        ],
    },
    {
        "id": 5261,
        "name": "S6.3 Gas Leak Detection Robot",
        "model_name": "S6.3 Gas Leak",
        "variant_code": "S6.3",
        "variant_label": "S6.3",
        "url": "https://smprobotics.com/products_autonomous_ugv/gas-leak-inspection-robot/",
        **FAM_S6,
        "product_url_scope": "exact_variant",
        "purpose": (
            "Autonomous laser methane leak inspection\n"
            "Outdoor oil and gas facility route scanning"
        ),
        "description": (
            "The S6.3 Gas Leak Detection Robot autonomously inspects outdoor "
            "petrochemical equipment with a remote laser methane detector plus "
            "visible/IR cameras on the SMP S-series UGV chassis."
        ),
        "features": (
            "OEM gas-leak-inspection-robot (S6.3): pan-tilt dual camera (visible+IR) + "
            "remote laser methane detector; programmed stop points; alarm on leak; "
            "related A6 OMD for underground corridors. S-series platform (4–6 km/h, "
            "~110 kg, 1420×780×1750 mm, IP65). Soft: detector brand/model not typed."
        ),
        "use_keys": "inspection|monitoring|patrol",
        "industry_keys": "oil-gas|energy|security",
        "category_slugs": "Security",
        "movement_keys": "wheeled",
        "tags": ["SMP", "S6", "Gas Leak", "Methane", "Oil Gas", "Inspection", "USA"],
        "sources": [
            {
                "url": "https://smprobotics.com/products_autonomous_ugv/gas-leak-inspection-robot/",
                "type": "website",
                "title": "OEM S6.3 Gas Leak",
            },
            {
                "url": "https://smprobotics.com/products_autonomous_ugv/",
                "type": "website",
                "title": "OEM S-series hub",
            },
        ],
    },
    {
        "id": 5256,
        "name": "Multi-Gas Monitoring Robot",
        "model_name": "S2 Multi-Gas",
        "variant_code": "S2-MultiGas",
        "variant_label": "Multi-Gas",
        "url": "https://smprobotics.com/products_autonomous_ugv/area-and-perimeter-gas-monitoring-robot/",
        **FAM_S2,
        "product_url_scope": "exact_variant",
        "purpose": (
            "Perimeter and area multi-gas hazard monitoring\n"
            "Mobile industrial air-quality surveillance"
        ),
        "description": (
            "The Multi-Gas Monitoring Robot is SMP's S2-class outdoor UGV configured for "
            "area and perimeter multi-gas / hazmat surveillance, replacing multiple "
            "fixed monitoring stations on large sites."
        ),
        "features": (
            "OEM area-and-perimeter-gas-monitoring-robot (S2 family): configurable gas/"
            "dust/hazard sensors on shared S-series chassis (4–6 km/h, ~110 kg, "
            "1420×780×1750 mm, IP65). Soft: exact sensor suite SKUs option-dependent."
        ),
        "use_keys": "monitoring|inspection|patrol",
        "industry_keys": "oil-gas|energy|manufacturing|security",
        "category_slugs": "Security",
        "movement_keys": "wheeled",
        "tags": ["SMP", "S2", "Multi-Gas", "Monitoring", "ESG", "UGV", "USA"],
        "sources": [
            {
                "url": "https://smprobotics.com/products_autonomous_ugv/area-and-perimeter-gas-monitoring-robot/",
                "type": "website",
                "title": "OEM Multi-Gas",
            },
            {
                "url": "https://smprobotics.com/products_autonomous_ugv/air-quality-monitoring-robot/",
                "type": "website",
                "title": "OEM S2 Air Quality sibling",
            },
        ],
    },
    {
        "id": 5253,
        "name": "Inspector Series",
        "model_name": "S3 Inspector",
        "variant_code": "S3",
        "variant_label": "Inspector",
        "url": "https://smprobotics.com/products_autonomous_ugv/electrical-substation-inspection-robot/",
        **FAM_S3,
        "product_url_scope": "exact_variant",
        "purpose": (
            "Automated thermal inspection of outdoor electrical equipment\n"
            "High-voltage substation route scanning"
        ),
        "description": (
            "The Inspector Series (S3) is SMP Robotics' thermal imaging inspection UGV "
            "for high-voltage substations and outdoor electrical equipment on the shared "
            "S-series platform."
        ),
        "features": (
            "OEM electrical-substation-inspection-robot (S3): infrared thermal inspection "
            "of HV/industrial equipment; autonomous route stops; S-series platform "
            "(4–6 km/h, ~110 kg, 1420×780×1750 mm, IP65). Soft: camera resolution/"
            "sensitivity not typed on hub page."
        ),
        "use_keys": "inspection|monitoring|patrol",
        "industry_keys": "energy|oil-gas|security",
        "category_slugs": "Security",
        "movement_keys": "wheeled",
        "tags": ["SMP", "S3", "Inspector", "Thermal", "Substation", "Energy", "USA"],
        "sources": [
            {
                "url": "https://smprobotics.com/products_autonomous_ugv/electrical-substation-inspection-robot/",
                "type": "website",
                "title": "OEM S3 Inspector",
            },
            {
                "url": "https://smprobotics.com/products_autonomous_ugv/",
                "type": "website",
                "title": "OEM S-series hub",
            },
        ],
    },
    {
        "id": 5251,
        "name": "Autonomous Delivery Robot",
        "model_name": "S7 Delivery",
        "variant_code": "S7",
        "variant_label": "Delivery",
        "url": "https://smprobotics.com/products_autonomous_ugv/autonomous-delivery-robot/",
        **FAM_S7,
        "product_url_scope": "exact_variant",
        "purpose": (
            "Self-driving small-parcel delivery on industrial sites\n"
            "Locked-compartment outdoor logistics with optional surveillance"
        ),
        "description": (
            "The Autonomous Delivery Robot (S7) is SMP's AGV-style outdoor UGV for "
            "industrial logistics and automated material handling, carrying small parcels "
            "in a locked compartment on the shared S-series chassis."
        ),
        "features": (
            "OEM autonomous-delivery-robot (S7): AGV/logistics UGV; locked parcel "
            "compartment; can combine with surveillance options; S-series platform "
            "(4–6 km/h, ~110 kg, 1420×780×1750 mm, IP65, auto dock). Soft: cargo volume/"
            "payload kg not typed on page scrape."
        ),
        "use_keys": "delivery|transport|logistics|patrol",
        "industry_keys": "logistics|manufacturing|security",
        "category_slugs": "Delivery-Robots|Security",
        "movement_keys": "wheeled",
        "tags": ["SMP", "S7", "Delivery", "AGV", "Logistics", "UGV", "USA"],
        "sources": [
            {
                "url": "https://smprobotics.com/products_autonomous_ugv/autonomous-delivery-robot/",
                "type": "website",
                "title": "OEM S7 Delivery",
            },
            {
                "url": "https://smprobotics.com/products_autonomous_ugv/",
                "type": "website",
                "title": "OEM S-series hub",
            },
        ],
    },
    {
        "id": 5255,
        "name": "Mosquito Control Robot",
        "model_name": "S8 Mosquito Control",
        "variant_code": "S8",
        "variant_label": "Mosquito",
        "url": "https://smprobotics.com/products_autonomous_ugv/mosquito-control-robot/",
        **FAM_S8,
        "product_url_scope": "exact_variant",
        "purpose": (
            "Mobile mosquito control with onboard propane trap\n"
            "Outdoor pest reduction on industrial and campus sites"
        ),
        "description": (
            "The Mosquito Control Robot (S8) carries a propane mosquito trap on SMP's "
            "autonomous outdoor UGV to clear designated areas of disease-carrying insects."
        ),
        "features": (
            "OEM mosquito-control-robot (S8): mobile propane mosquito trap on S-series "
            "chassis (4–6 km/h, ~110 kg, 1420×780×1750 mm, IP65). Soft: trap capacity/"
            "coverage radius not typed on page scrape."
        ),
        "use_keys": "agriculture|monitoring|patrol",
        "industry_keys": "agriculture|security",
        "category_slugs": "Agricultural-Robots",
        "movement_keys": "wheeled",
        "tags": ["SMP", "S8", "Mosquito", "Pest Control", "Agriculture", "UGV", "USA"],
        "sources": [
            {
                "url": "https://smprobotics.com/products_autonomous_ugv/mosquito-control-robot/",
                "type": "website",
                "title": "OEM Mosquito Control",
            },
            {
                "url": "https://smprobotics.com/application_autonomus_mobile_robots/",
                "type": "website",
                "title": "OEM applications hub",
            },
        ],
    },
    {
        "id": 5264,
        "name": "Virtual Telepresence Robot",
        "model_name": "S11 Telepresence",
        "variant_code": "S11",
        "variant_label": "Telepresence",
        "url": "https://smprobotics.com/products_autonomous_ugv/virtual-telepresence-robot/",
        **FAM_S11,
        "product_url_scope": "exact_variant",
        "purpose": (
            "Outdoor virtual telepresence with live video and audio\n"
            "Remote site presence and virtual tourism"
        ),
        "description": (
            "The Virtual Telepresence Robot (S11) enables remote presence with live video "
            "and audio on SMP's outdoor autonomous UGV platform for virtual tourism and "
            "remote inspection."
        ),
        "features": (
            "OEM virtual-telepresence-robot (S11): live video/audio remote presence; "
            "outdoor telepresence / virtual tourism use cases; S-series platform "
            "(4–6 km/h, ~110 kg, 1420×780×1750 mm, IP65). Soft: camera FOV / bitrate "
            "not typed on page scrape."
        ),
        "use_keys": "surveillance|monitoring|patrol",
        "industry_keys": "security|research",
        "category_slugs": "Telepresence-Robots",
        "movement_keys": "wheeled",
        "tags": ["SMP", "S11", "Telepresence", "Remote Presence", "UGV", "USA"],
        "sources": [
            {
                "url": "https://smprobotics.com/products_autonomous_ugv/virtual-telepresence-robot/",
                "type": "website",
                "title": "OEM S11 Telepresence",
            },
            {
                "url": "https://smprobotics.com/products_autonomous_ugv/",
                "type": "website",
                "title": "OEM S-series hub",
            },
        ],
    },
]


def taxonomy_ids(client: ResearchApiClient) -> dict[str, dict[str, int]]:
    def idx(path: str) -> dict[str, int]:
        rows = client._get(path)
        return {
            (r.get("key") or "").lower(): int(r["id"])
            for r in rows
            if r.get("key") and r.get("id")
        }

    return {
        "uses": idx("robots/uses/"),
        "industries": idx("robots/industries/"),
        "movement": idx("robots/movement-types/"),
    }


def map_keys(tax: dict[str, dict[str, int]], group: str, keys: str) -> list[int]:
    out = []
    for k in keys.split("|"):
        kid = tax[group].get(k.strip().lower())
        if kid:
            out.append(kid)
        else:
            print(f"  warn missing {group}={k}")
    return out


def force_en(client: ResearchApiClient, rid: int, row: dict[str, Any]) -> None:
    sync = {
        "updates": [
            {
                "id": rid,
                "locale": loc,
                "source_hash": f"smp-en-{rid}-20260720-{loc}",
                "translated_fields": {
                    "description": row.get("description") or "",
                    "features": row.get("features") or "",
                    "purpose": row.get("purpose") or "",
                    "name": row.get("name") or "",
                },
            }
            for loc in ("zh-CN", "zh-TW")
        ]
    }
    try:
        resp = client._session.post(
            client._url("robots/robots/translation-sync/?force=1"),
            json=sync,
            timeout=60,
        )
        print(f"  translation-sync {rid}: {resp.status_code}")
    except requests.RequestException as e:
        print(f"  translation-sync warn {rid}: {e}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--local", action="store_true")
    args = ap.parse_args()
    if not args.apply:
        print("dry-run: pass --apply to write")
        for p in PRODUCTS:
            flag = "PUB" if p.get("published") else "PEND"
            print(f"  {flag} {p['id']} {p['name']} fam={p['family_key']}")
        return 0

    client = ResearchApiClient()
    tax = taxonomy_ids(client)
    staging = _RESEARCH / "staging" / "robots" / "smp-robotics"
    staging.mkdir(parents=True, exist_ok=True)

    for spec in PRODUCTS:
        existing = client._get(f"robots/robots/{spec['id']}/")
        img = existing.get("image") or existing.get("s3_image") or ""
        notes = (
            f"[AI Research] SMP enrich 2026-07-20: US; family {spec['family_key']}; "
            f"S-series platform specs from OEM 2021 table; Available."
        )
        info_urls = [s["url"] for s in spec["sources"]]
        status = existing.get("status") or "pending_review"
        if not spec.get("published"):
            status = "pending_review"
        row = {
            "id": spec["id"],
            "name": spec["name"],
            "model_name": spec["model_name"],
            "variant_code": spec["variant_code"],
            "variant_label": spec["variant_label"],
            "company_slug": COMPANY_SLUG,
            "company_name": COMPANY_NAME,
            "manufacturer_country_code": "US",
            "manufacturer_country_codes": "US",
            "description": spec["description"],
            "purpose": spec["purpose"],
            "features": spec["features"],
            "url": spec["url"],
            "image": img,
            "images": [img] if img else [],
            "source_locale": "en",
            "availability_status": AVAILABLE,
            "family_key": spec["family_key"],
            "family_name": spec["family_name"],
            "family_url": spec["family_url"],
            "product_url_scope": spec["product_url_scope"],
            "movement_type_keys": spec["movement_keys"],
            "category_slugs": spec["category_slugs"],
            "use_keys": spec["use_keys"],
            "industry_keys": spec["industry_keys"],
            "tags": spec["tags"],
            "notes": notes,
            "research_notes": notes,
            "sources": spec["sources"],
            "information_source_urls": info_urls,
            **PLATFORM,
        }
        path = staging / f"{spec['variant_code'].lower().replace('.', '')}.json"
        path.write_text(json.dumps(row, indent=2, ensure_ascii=False), encoding="utf-8")
        print("staged", path.name)
        print(
            "import",
            spec["id"],
            import_staging(
                path,
                dry_run=False,
                patch=True,
                force_overwrite=True,
                replace_media=False,
                status=status if spec.get("published") else "pending_review",
                created_by_id=resolve_created_by_id(1),
                skip_company_update=True,
            ),
        )
        body: dict[str, Any] = {
            "name": spec["name"],
            "manufacturer_countries": [US_ID],
            "manufacturer_country_ref": US_ID,
            "availability_status": AVAILABLE,
            "description": spec["description"],
            "features": spec["features"],
            "purpose": spec["purpose"],
            "url": spec["url"],
            "information_source_urls": info_urls,
            "family_key": spec["family_key"],
            "family_name": spec["family_name"],
            "family_url": spec["family_url"],
            "model_name": spec["model_name"],
            "variant_code": spec["variant_code"],
            "variant_label": spec["variant_label"],
            "product_url_scope": spec["product_url_scope"],
            "notes": notes,
            "tags": spec["tags"],
            "uses": map_keys(tax, "uses", spec["use_keys"]),
            "industries": map_keys(tax, "industries", spec["industry_keys"]),
            "movement_types": map_keys(tax, "movement", spec["movement_keys"]),
            **PLATFORM,
        }
        try:
            client._patch(f"robots/robots/{spec['id']}/", body)
            print("patch OK", spec["id"])
        except Exception as e:
            print("patch FAIL", spec["id"], e)
            slim = {
                k: body[k]
                for k in (
                    "manufacturer_countries",
                    "manufacturer_country_ref",
                    "availability_status",
                    "description",
                    "features",
                    "purpose",
                    "url",
                    "information_source_urls",
                    "family_key",
                    "family_name",
                    "family_url",
                    "notes",
                    "speed",
                    "length_mm",
                    "width_mm",
                    "height_mm",
                    "weight_kg",
                )
                if k in body
            }
            try:
                client._patch(f"robots/robots/{spec['id']}/", slim)
                print("slim patch OK", spec["id"])
            except Exception as e2:
                print("slim FAIL", spec["id"], e2)
        force_en(client, spec["id"], row)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
