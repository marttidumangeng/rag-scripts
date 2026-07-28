"""Curate Bühler Group (company 1507) SORTEX / SPARK optical sorter fleet.

Sources: official buhlergroup.com PDPs + dam.buhlergroup.com brochures (2026-07-22).
Leave status pending_review. Never invent typed specs.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
from pathlib import Path
from typing import Any

import requests
from PIL import Image

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from api_client import ResearchApiClient
from load_env import load_research_env

load_research_env()

COMPANY_ID = 1507
COMPANY_SLUG = "buhler-group"
COMPANY_NAME = "Bühler Group"
COMPANY_WEBSITE = "https://www.buhlergroup.com/"
SWITZERLAND = 17
AVAILABLE = 11
# Existing taxonomy on R500 records: inspection + manufacturing + stationary.
USES = [7]
INDUSTRIES = [12]
MOVEMENT = [10]  # stationary
HUB = (
    "https://www.buhlergroup.com/content/buhlergroup/global/en/"
    "process-technologies/Optical-Sorting.html"
)
REPORT = _HERE / "staging" / "reports" / "buhler-1507-curated-report.json"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
    ),
    "Referer": "https://www.buhlergroup.com/",
}

# Exact TagCatalog names.
TAGS_RICE = [
    "Sorting",
    "Agriculture",
    "Food Handling",
    "Computer Vision",
    "Industrial",
    "Automation",
    "Inspection",
    "AI",
]
TAGS_GRAIN = [
    "Sorting",
    "Agriculture",
    "Food Handling",
    "Computer Vision",
    "Industrial",
    "Automation",
    "Inspection",
    "Industrial Inspection",
]
TAGS_AI = [
    "Sorting",
    "AI",
    "Agriculture",
    "Food Handling",
    "Computer Vision",
    "Industrial",
    "Automation",
    "Inspection",
]
TAGS_RECYCLE = [
    "Sorting",
    "Recycling",
    "Food Handling",
    "Computer Vision",
    "Industrial",
    "Automation",
    "Inspection",
    "Manufacturing",
]
TAGS_SPARK = [
    "Sorting",
    "Agriculture",
    "Food Handling",
    "Computer Vision",
    "Industrial",
    "Automation",
    "Inspection",
    "Manufacturing",
]

# OEM product heroes (Canto DAM paths / webProduct renditions).
IMG_R500 = (
    "https://dam.buhlergroup.com/rendition/1661738/-FPNG-TwebProduct_1x1-S800x800"
)
IMG_AI700 = (
    "https://www.buhlergroup.com/content/dam/Canto/OS/Sortex/"
    "OS_Sortex_AI700_Front_view.png"
)
IMG_H = (
    "https://www.buhlergroup.com/content/dam/Canto/DT/Sortex/"
    "DT_Sortex_H_right_angle_view_lights_on.png"
)
IMG_J = (
    "https://www.buhlergroup.com/content/dam/Canto/DT/Sortex/"
    "DT_Sortex_J_angled_view_five_chutes_lights_on.png"
)
IMG_S_CRYSTAL = (
    "https://dam.buhlergroup.com/rendition/"
    "321440a0c2e5490a9d32facf0b5df063/-FPNG-TwebProduct_1x1-S800x800"
)
IMG_S_ULTRA = (
    "https://dam.buhlergroup.com/rendition/"
    "e0fb5c36acfa4df2889e1f9e5708221c/-FPNG-TwebProduct_1x1-S800x800"
)
IMG_A_GLOW = (
    "https://dam.buhlergroup.com/rendition/"
    "455c87e03b8743bc8e790149ed741bc1/-FPNG-TwebProduct_1x1-S800x800"
)
IMG_A_LUMO = (
    "https://dam.buhlergroup.com/rendition/"
    "830d7c2b49954bd899a606481506f8ac/-FPNG-TwebProduct_1x1-S800x800"
)
IMG_SPARK = (
    "https://www.buhlergroup.com/content/dam/Canto/DT/Spark/"
    "DT_Spark_Pro_plus_front_view.jpg"
)

PDF_R500 = "https://dam.buhlergroup.com/asset/1688075/OS_R500_Brochure_web.pdf"
PDF_AI700 = (
    "https://dam.buhlergroup.com/asset/1678123/OS_AI700_Brochure_Update_web.pdf"
)
PDF_S_CRYSTAL = (
    "https://dam.buhlergroup.com/asset/b97777ebf69e4d1b91be32a0bb04d0a5/"
    "BSOL_212138_SORTEX_S_CrystalVision_print_brochure_v3.pdf"
)
PDF_S_ULTRA = (
    "https://dam.buhlergroup.com/asset/cf8472d060864cb78ccb0aec40250e2a/"
    "Brochure_DT_SO_SORTEX%20S%20UltraVision_BSSB.pdf"
)
PDF_A_GLOW = (
    "https://dam.buhlergroup.com/asset/c01c52af5ce140cbbdaf72fb01899400/"
    "DT_SORTEX-A_GlowVision_Brochure_EN.pdf"
)
PDF_A_LUMO = (
    "https://dam.buhlergroup.com/asset/7c5f8f148f77430394dbb94781c97d27/"
    "DT_SORTEX%20A%20LumoVision%20brochure_web.pdf"
)
PDF_SPARK = (
    "https://dam.buhlergroup.com/asset/1708803/"
    "OS_SPARK_Pro_brochure_update_Sep_2025_web.pdf"
)
PDF_J = "https://dam.buhlergroup.com/asset/9ff60842a8ce411cbe270b0c6c27e429"

URL_R500 = "https://www.buhlergroup.com/global/en/products/optical_sorter_sortexr500.html"
URL_AI700 = (
    "https://www.buhlergroup.com/global/en/products/optical_sorter_sortexai700.html"
)
URL_H = "https://www.buhlergroup.com/global/en/products/optical_sorter_sortexh.html"
URL_J = (
    "https://www.buhlergroup.com/global/en/products/"
    "optical_sorter_sortexjspectravision.html"
)
URL_S_CRYSTAL = (
    "https://www.buhlergroup.com/global/en/products/"
    "optical_sorter_sortexscrystalvision.html"
)
URL_S_ULTRA = (
    "https://www.buhlergroup.com/global/en/products/"
    "sortex_s_ultravisionopticalsorter.html"
)
URL_A_GLOW = (
    "https://www.buhlergroup.com/global/en/products/"
    "optical_sorter_sortexaglowvision.html"
)
URL_A_LUMO = (
    "https://www.buhlergroup.com/global/en/products/"
    "optical_sorter_sortexalumovision.html"
)
URL_SPARK = (
    "https://www.buhlergroup.com/global/en/products/optical_sorter_sparkpro.html"
)

# Public R500 product render shows six chutes → assign to R500 6 only.
# R500 5 is IMAGE TO-DO (no distinct 5-chute hero; hash-dedupe forbids reuse).
PRODUCTS: dict[int, dict[str, Any]] = {
    5068: {
        "name": "SORTEX R500 5",
        "model": "R500 5",
        "variant_code": "R500-5",
        "variant_label": "5-chute configuration",
        "url": URL_R500,
        "family_key": "buhler:sortex-r500",
        "family_name": "SORTEX R500",
        "family_url": URL_R500,
        "product_url_scope": "family",
        "image": None,
        "image_todo": (
            "Checked R500 PDP + brochure + Canto/DAM product render: the only "
            "public R500 machine photo shows six chutes and is assigned to "
            f"R500 6 (5069) via {IMG_R500}. No distinct 5-chute hero found."
        ),
        "tags": TAGS_RICE,
        "description": (
            "SORTEX R500 is Bühler's rice-specialist optical sorter for premium "
            "rice quality. The R500 5 configuration uses five chutes with "
            "rice-optimized optics, intelligent automation, and machine-learning "
            "modes for autonomous sorting with less operator intervention."
        ),
        "purpose": (
            "Premium rice optical sorting\n"
            "Color and foreign-matter removal in rice\n"
            "Rice yield and purity optimization"
        ),
        "features": (
            "Official SORTEX R500 brochure (BSOL Brochure R500 en 04 25) lists "
            "R500 5 technical details: unpacked weight 1,230 kg; width 2,771 mm; "
            "depth 1,342 mm; height 2,069 mm; typical air consumption 18.0 L/s; "
            "typical power 3.0 kW. Built for rice from lighting angles through "
            "defect segregation; Intelligent Automation self-adjusting modes; "
            "reject concentration improved by up to 18% versus previous SORTEX "
            "rice models. Autonomous operation reduces skilled-labor dependence."
        ),
        "typed": {
            "weight_kg": 1230.0,
            "weight": "1230 kg",
            "width_mm": 2771.0,
            "length_mm": 1342.0,
            "height_mm": 2069.0,
        },
        "sources": [URL_R500, PDF_R500, HUB],
        "dead": (
            "no distinct 5-chute product photo (six-chute render reserved for "
            "5069); no public OEM list price; dof N/A; payload_kg not cited"
        ),
    },
    5069: {
        "name": "SORTEX R500 6",
        "model": "R500 6",
        "variant_code": "R500-6",
        "variant_label": "6-chute configuration",
        "url": f"{URL_R500}#r500-6",
        "family_key": "buhler:sortex-r500",
        "family_name": "SORTEX R500",
        "family_url": URL_R500,
        "product_url_scope": "family",
        "image": IMG_R500,
        "tags": TAGS_RICE,
        "description": (
            "SORTEX R500 6 is the six-chute configuration of Bühler's "
            "rice-specialist optical sorter. It shares the R500 rice-optimized "
            "platform—autonomous modes, machine learning, and premium purity "
            "focus—with higher chute count versus the R500 5."
        ),
        "purpose": (
            "Premium rice optical sorting\n"
            "Higher-throughput rice purity sorting\n"
            "Color and foreign-matter removal in rice"
        ),
        "features": (
            "Official SORTEX R500 brochure lists R500 6 technical details: "
            "unpacked weight 1,270 kg; width 2,771 mm; depth 1,342 mm; height "
            "2,069 mm; typical air consumption 21.6 L/s; typical power 3.4 kW. "
            "Same rice-built optics and Intelligent Automation as the R500 "
            "family, with six-chute capacity for higher air/power draw versus "
            "R500 5. Reject concentration improved by up to 18% versus previous "
            "SORTEX rice models."
        ),
        "typed": {
            "weight_kg": 1270.0,
            "weight": "1270 kg",
            "width_mm": 2771.0,
            "length_mm": 1342.0,
            "height_mm": 2069.0,
        },
        "sources": [URL_R500, PDF_R500, HUB],
        "dead": (
            "no public single-SKU R500-6 PDP (shared R500 family page); "
            "no public OEM list price; dof not applicable to chute optical sorter; "
            "payload_kg not cited"
        ),
    },
    5070: {
        "name": "SORTEX AI700",
        "model": "AI700",
        "variant_code": "AI700",
        "variant_label": "Standard (1–7 modules)",
        "url": URL_AI700,
        "family_key": "buhler:sortex-ai700",
        "family_name": "SORTEX AI700",
        "family_url": URL_AI700,
        "product_url_scope": "exact_variant",
        "image": IMG_AI700,
        "tags": TAGS_AI,
        "description": (
            "SORTEX AI700 is Bühler's deep-learning optical sorter for food "
            "purity and yield. Trained on millions of labeled images, it targets "
            "hard impurity and allergen separation challenges—launch focus "
            "includes separating barley, wheat, and rye from oats—with "
            "out-of-the-box operation and real-time defect transparency."
        ),
        "purpose": (
            "AI-powered food impurity sorting\n"
            "Allergen separation in oats and grains\n"
            "Real-time defect monitoring for food safety"
        ),
        "features": (
            "Official AI700 brochure technical table covers modules 1–7 with "
            "shared depth door-open 2,323 mm and door-shut 1,776 mm, height "
            "2,010–2,088 mm, and weights from 550 kg (1 module) to 1,680 kg "
            "(7 modules)—no single SKU weight is typed because the public "
            "record is the multi-module family. Deep Learning AI modes, full-"
            "color cameras, high-intensity LED lighting, climate control, and "
            "optional remote access / Bühler Insights. Brochure claims +50% "
            "yield versus highest-performing traditional sorters on the oats "
            "launch application."
        ),
        "typed": {
            # Shared across all module columns (depth door shut). Module width,
            # weight, and height range disagree or are ranges — not typed.
            "length_mm": 1776.0,
        },
        "sources": [URL_AI700, PDF_AI700, HUB],
        "dead": (
            "weight_kg / height_mm / width_mm withheld—brochure is a "
            "multi-column family table (AI700 1–7) with non-agreeing width/"
            "weight and height stated as 2010–2088 mm; door-open depth 2323 mm "
            "is shared but kept in features to avoid conflating with width; "
            "no public list price; dof N/A; payload_kg not cited"
        ),
    },
    5071: {
        "name": "SORTEX H SpectraVision",
        "model": "H SpectraVision",
        "variant_code": "H-SpectraVision",
        "variant_label": "SpectraVision",
        "url": URL_H,
        "family_key": "buhler:sortex-h",
        "family_name": "SORTEX H SpectraVision",
        "family_url": URL_H,
        "product_url_scope": "exact_variant",
        "image": IMG_H,
        "tags": TAGS_GRAIN,
        "description": (
            "SORTEX H SpectraVision is Bühler's next-generation optical sorter "
            "with in-house full-color and InGaAs cameras, Merlin.Ai learning, "
            "and Industry 4.0 connectivity via Bühler Insights and the SORTEX "
            "Monitoring System. Applications include coffee, nuts, pulses, and "
            "wheat & rye."
        ),
        "purpose": (
            "High-performance grain and pulse optical sorting\n"
            "Coffee and nut defect removal\n"
            "Foreign-matter detection with InGaAs cameras"
        ),
        "features": (
            "Official H SpectraVision PDP: up to 50% higher reject "
            "concentrations versus prior generation; new full-color cameras for "
            "subtle color defects; InGaAs cameras for foreign matter; intelligent "
            "ejection, calibration, and tracking algorithms; pre-set product "
            "recipes and per-defect sensitivity; remote performance view and "
            "logged setup changes via Bühler Insights / SORTEX Monitoring. "
            "Brochure download is gated to sales request (no public PDF specs "
            "table on the PDP)."
        ),
        "typed": {},
        "sources": [URL_H, HUB],
        "dead": (
            "weight_kg, dimensions, throughput: public PDP has no numeric table; "
            "brochure is mailto-gated (sortexsales@buhlergroup.com); dof N/A; "
            "payload_kg not cited"
        ),
    },
    5072: {
        "name": "SPARK Pro",
        "model": "SPARK Pro",
        "variant_code": "SPARK-Pro",
        "variant_label": "Pro",
        "url": URL_SPARK,
        "family_key": "buhler:spark",
        "family_name": "SPARK Pro",
        "family_url": URL_SPARK,
        "product_url_scope": "exact_variant",
        "image": None,
        "image_todo": (
            "SPARK Pro PDP Canto asset DT_Spark_Pro_plus_front_view.jpg is labeled "
            "SPARK Pro+ on the chassis (sibling/plus variant). Fail-closed: not used "
            "as SPARK Pro primary. No exact 'SPARK Pro' (non-plus) product hero "
            "confirmed in this pass."
        ),
        "tags": TAGS_SPARK,
        "description": (
            "SPARK Pro is Bühler's affordable, easy-to-use optical sorter "
            "(SPARK line, not SORTEX-branded) for food safety and quality. It "
            "features a zero-spillage design, DynamoAI simple setup, dust "
            "extraction, and flexible sizing up to 10 chutes for grains, "
            "pulses, coffee, rice, spices, peanuts, and plastics."
        ),
        "purpose": (
            "Affordable multi-commodity optical sorting\n"
            "Grain, pulse, coffee, and rice purity sorting\n"
            "Plastic and spice optical sorting"
        ),
        "features": (
            "Official SPARK Pro PDP: available with up to 10 chutes; zero-"
            "spillage design to prevent floor losses; DynamoAI engine for "
            "simple set-up-and-go sorting; dust extraction concept for cleaner "
            "product; industrial testing and certification focus; multi-"
            "commodity coverage including grains, pulses, coffee, rice, spices, "
            "peanuts, and plastic sorting. September 2025 brochure hosted on "
            "dam.buhlergroup.com."
        ),
        "typed": {},
        "sources": [URL_SPARK, PDF_SPARK, HUB],
        "dead": (
            "exact SPARK Pro (non-plus) hero not confirmed — Pro+ chassis photo "
            "withheld; weight_kg and envelope dims: brochure PDF not fully parsed "
            "for a single-SKU numeric table in this pass; dof N/A; payload_kg not "
            "cited; chute count is a range (up to 10)"
        ),
    },
    5073: {
        "name": "SORTEX J SpectraVision",
        "model": "J SpectraVision",
        "variant_code": "J-SpectraVision",
        "variant_label": "SpectraVision",
        "url": URL_J,
        "family_key": "buhler:sortex-j",
        "family_name": "SORTEX J SpectraVision",
        "family_url": URL_J,
        "product_url_scope": "exact_variant",
        "image": IMG_J,
        "tags": TAGS_GRAIN,
        "description": (
            "SORTEX J SpectraVision sorts grains, seeds, and plastics with "
            "full-color cameras, remodeled lighting, standard InGaAs foreign-"
            "matter detection, and a slider-based UI. It targets purity, "
            "toxin/allergen-related foreign material, and higher reject "
            "concentrations with CE, NRTL, and NR-12 certification availability."
        ),
        "purpose": (
            "Grain and seed optical sorting\n"
            "Plastic electronic optical sorting\n"
            "Foreign-matter and subtle defect removal"
        ),
        "features": (
            "Official J SpectraVision PDP: up to 50% higher reject "
            "concentrations; in-house cameras with improved color spectral "
            "purity; standard InGaAs for foreign matter; intelligent sorting "
            "algorithms with product calibration/tracking; per-defect slider "
            "controls; Bühler Insights connectivity and SORTEX Monitoring. "
            "Product brochure asset on dam.buhlergroup.com (asset "
            "9ff60842a8ce411cbe270b0c6c27e429)."
        ),
        "typed": {},
        "sources": [URL_J, PDF_J, HUB],
        "dead": (
            "weight_kg / dims / throughput: no numeric table on public PDP; "
            "brochure asset URL lacks extractable filename in this pass; "
            "dof N/A; payload_kg not cited"
        ),
    },
    5074: {
        "name": "SORTEX S CrystalVision",
        "model": "S CrystalVision",
        "variant_code": "S-CrystalVision",
        "variant_label": "CrystalVision",
        "url": URL_S_CRYSTAL,
        "family_key": "buhler:sortex-s",
        "family_name": "SORTEX S",
        "family_url": URL_S_CRYSTAL,
        "product_url_scope": "exact_variant",
        "image": IMG_S_CRYSTAL,
        "tags": TAGS_RICE,
        "description": (
            "SORTEX S CrystalVision is a rice optical sorter focused on advanced "
            "foreign-matter removal—including frosted/abraded glass and white "
            "plastics—using deep-blue lighting, textured LEDs, Crosshair "
            "Targeting, and 78 ejectors per chute with up to six chute modules."
        ),
        "purpose": (
            "Rice foreign-matter removal including glass and white plastics\n"
            "Rice color, spot, and chalky defect sorting\n"
            "High-throughput rice purity sorting"
        ),
        "features": (
            "Official CrystalVision brochure module table (3–6 modules): depth "
            "1,372 mm and height 2,060 mm agree across all columns (typed); "
            "length 2,113 or 2,769 mm and weight 985–1,225 kg vary by module "
            "count so those are not typed. PDP: up to six chutes; patented feed "
            "system; 78 ejectors per chute; Intelligent Individual Defect "
            "Detection; SORTEX Monitoring / Bühler Insights connectivity."
        ),
        "typed": {
            "length_mm": 1372.0,  # OEM Depth — agrees all modules
            "height_mm": 2060.0,
        },
        "sources": [URL_S_CRYSTAL, PDF_S_CRYSTAL, HUB],
        "dead": (
            "weight_kg and length/width envelope withheld—multi-column module "
            "table disagrees (3–6 modules); no single t/h figure on CrystalVision "
            "PDP (UltraVision cites 18 t/h); dof N/A; payload_kg not cited"
        ),
    },
    5075: {
        "name": "SORTEX S UltraVision",
        "model": "S UltraVision",
        "variant_code": "S-UltraVision",
        "variant_label": "UltraVision",
        "url": URL_S_ULTRA,
        "family_key": "buhler:sortex-s",
        "family_name": "SORTEX S",
        "family_url": URL_S_ULTRA,
        "product_url_scope": "exact_variant",
        "image": IMG_S_ULTRA,
        "tags": TAGS_RICE,
        "description": (
            "SORTEX S UltraVision is Bühler's AI-enabled rice optical sorter for "
            "raw, parboiled, and steam varieties. The PDP states sorting up to "
            "18 t/h with up to 3 t/h per chute, ProSort simplified controls, and "
            "automatic detection adjustment for color defects and foreign "
            "materials including glass."
        ),
        "purpose": (
            "High-capacity rice optical sorting up to 18 t/h\n"
            "Raw, parboiled, and steam rice purity sorting\n"
            "Rice color defect and glass foreign-matter removal"
        ),
        "features": (
            "Official UltraVision PDP: sort up to 18 t/h; patented feeder with "
            "throughput per chute up to 3 t/h; ProSort OS (select variety, set "
            "defect sensitivity, start); automatic detection adjustment. Brochure "
            "module table (3–6): depth 1,372 mm and height 2,060 mm agree across "
            "columns (typed); length/weight vary by module (985–1,225 kg) and "
            "are not typed. Air note references 2.5 t/h per chute at stated test "
            "conditions."
        ),
        "typed": {
            "length_mm": 1372.0,
            "height_mm": 2060.0,
        },
        "sources": [URL_S_ULTRA, PDF_S_ULTRA, HUB],
        "dead": (
            "weight_kg and overall length withheld—multi-module table; "
            "no dedicated throughput_tph column (18 t/h kept in features); "
            "dof N/A; payload_kg not cited"
        ),
    },
    5076: {
        "name": "SORTEX A GlowVision",
        "model": "A GlowVision",
        "variant_code": "A-GlowVision",
        "variant_label": "GlowVision",
        "url": URL_A_GLOW,
        "family_key": "buhler:sortex-a",
        "family_name": "SORTEX A",
        "family_url": URL_A_GLOW,
        "product_url_scope": "exact_variant",
        "image": IMG_A_GLOW,
        "tags": TAGS_RECYCLE,
        "description": (
            "SORTEX A GlowVision is a 4-in-1 optical sorter for bottle-to-bottle "
            "PET recycling and food applications, combining color sorting, "
            "foreign-matter removal, polymer sorting, and loose-label reduction "
            "with simultaneous resorting for high reject concentration."
        ),
        "purpose": (
            "PET bottle-to-bottle recycling sorting\n"
            "Polymer and color sorting for plastics\n"
            "Foreign-matter and loose-label reduction"
        ),
        "features": (
            "Official GlowVision PDP/brochure: simultaneous resorting up to 40% "
            "reject concentration on the resorting channel; up to five chutes; "
            "broadband LED lighting; sealed optical/control cabinets rated up "
            "to IP5X; SORTEX Monitoring powered by Bühler Insights. Brochure "
            "module table (3–5 modules): width 2,387 mm, depth doors-shut "
            "1,708 mm, height 2,088 mm agree across modules (typed); unpacked "
            "weights 1,064 / 1,107 / 1,150 kg vary by module count (not typed)."
        ),
        "typed": {
            "width_mm": 2387.0,
            "length_mm": 1708.0,
            "height_mm": 2088.0,
        },
        "sources": [URL_A_GLOW, PDF_A_GLOW, HUB],
        "dead": (
            "weight_kg withheld—3/4/5 module weights disagree; dof N/A; "
            "payload_kg not cited"
        ),
    },
    5077: {
        "name": "SORTEX A LumoVision",
        "model": "A LumoVision",
        "variant_code": "A-LumoVision",
        "variant_label": "LumoVision",
        "url": URL_A_LUMO,
        "family_key": "buhler:sortex-a",
        "family_name": "SORTEX A",
        "family_url": URL_A_LUMO,
        "product_url_scope": "exact_variant",
        "image": IMG_A_LUMO,
        "tags": TAGS_AI,
        "description": (
            "SORTEX A LumoVision is a precision optical sorter for aflatoxin and "
            "visible-defect reduction in maize and peanuts, allergen removal from "
            "pulses, and fluorescent defect detection. Modular sizing handles up "
            "to twenty tons of product per hour per the PDP."
        ),
        "purpose": (
            "Aflatoxin and mycotoxin reduction in maize and nuts\n"
            "Allergen removal from pulses\n"
            "Fluorescent defect sorting in food commodities"
        ),
        "features": (
            "Official LumoVision PDP: up to 20 t/h capacity claim; up to five "
            "chutes; automated background adjustment; sealed cabinets up to "
            "IP5X; advanced mycotoxin inspection (brochure cites ~90% aflatoxin "
            "contamination-rate reduction in maize use-cases). Brochure module "
            "table (3–5): width 2,387 mm, depth doors-shut 1,708 mm, height "
            "2,088 mm agree (typed); weights 1,064 / 1,107 / 1,150 kg vary "
            "(not typed)."
        ),
        "typed": {
            "width_mm": 2387.0,
            "length_mm": 1708.0,
            "height_mm": 2088.0,
        },
        "sources": [URL_A_LUMO, PDF_A_LUMO, HUB],
        "dead": (
            "weight_kg withheld—multi-module table; dof N/A; payload_kg not cited"
        ),
    },
}


def payload(rid: int) -> dict[str, Any]:
    data = PRODUCTS[rid]
    notes = (
        f"[AI Research — Bühler curated full enrichment 2026-07-22] "
        f"OEM sources: {', '.join(data['sources'])}. "
        f"Dead searches: {data['dead']}."
    )
    if data.get("image_todo"):
        notes = (
            "[IMAGE TO-DO — no hero, deliberate]\n"
            f"{data['image_todo']}\n"
            "ACTION FOR TEAM: source a licensed exact-variant OEM product photo "
            "distinct from sibling/family heroes already used in this fleet.\n"
            "Do NOT substitute a sibling render, a family banner, or marketing/"
            "diagram art.\n"
            "---\n"
            + notes
        )
    body: dict[str, Any] = {
        "name": data["name"],
        "model_name": data["model"],
        "variant_code": data["variant_code"],
        "variant_label": data["variant_label"],
        "description": data["description"],
        "features": data["features"],
        "purpose": data["purpose"],
        "url": data["url"],
        "family_key": data["family_key"],
        "family_name": data["family_name"],
        "family_url": data["family_url"],
        "product_url_scope": data["product_url_scope"],
        "availability_status": AVAILABLE,
        "manufacturer_country_ref": SWITZERLAND,
        "manufacturer_countries": [SWITZERLAND],
        "uses": USES,
        "industries": INDUSTRIES,
        "movement_types": MOVEMENT,
        "tags": data["tags"],
        "information_source_urls": data["sources"],
        "notes": notes,
        "status": "pending_review",
        "categories": ["Industrial-Robot"],
    }
    if data.get("image"):
        body["image"] = data["image"]
        body["images"] = [data["image"]]
        body["s3_image"] = None
    else:
        body["image"] = None
        body["images"] = []
        body["s3_image"] = None
    body.update(data.get("typed") or {})
    return body


def scalar_payload(rid: int) -> dict[str, Any]:
    body = payload(rid)
    for key in ("image", "images", "s3_image"):
        body.pop(key, None)
    return body


def family_invariants() -> dict[str, list[int]]:
    groups: dict[str, list[int]] = {}
    for rid, data in PRODUCTS.items():
        groups.setdefault(data["family_key"], []).append(rid)
    return groups


def _admin_base() -> str:
    return os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/").replace(
        "/api/v1", ""
    )


def _internal_headers() -> dict[str, str]:
    secret = os.environ.get("INTERNAL_API_SECRET", "").strip()
    if not secret:
        raise RuntimeError("INTERNAL_API_SECRET missing")
    return {"X-Internal-Secret": secret}


def patch_company(client: ResearchApiClient) -> dict[str, Any]:
    return client._patch(
        f"companies/{COMPANY_ID}/",
        {
            "website": COMPANY_WEBSITE,
            "country_id": SWITZERLAND,
        },
    )


def clear_imageless_media(client: ResearchApiClient, rid: int) -> list[dict[str, int]]:
    """Bulk-import does not clear photos when images=[] — detach explicitly."""
    if PRODUCTS[rid].get("image"):
        return []
    removed: list[dict[str, int]] = []
    detail = client._get(f"robots/robots/{rid}/")
    headers = _internal_headers()
    admin = _admin_base()
    for photo in detail.get("photos") or []:
        response = requests.delete(
            f"{admin}/admin/robots/robot/content-queue/api/robot/"
            f"{rid}/photos/{photo['id']}/",
            headers=headers,
            timeout=60,
        )
        if not response.ok:
            raise RuntimeError(
                f"photo detach failed {rid}/{photo['id']}: "
                f"{response.status_code} {response.text[:200]}"
            )
        removed.append({"robot_id": rid, "photo_id": int(photo["id"])})
    client._patch(
        f"robots/robots/{rid}/",
        {"image": "", "s3_image": None, "status": "pending_review"},
    )
    return removed


def replace_media(client: ResearchApiClient, rid: int) -> dict[str, Any]:
    row = payload(rid)
    row.update(
        {
            "id": rid,
            "company_slug": COMPANY_SLUG,
            "company_name": COMPANY_NAME,
            "manufacturer_country_code": "CH",
            "manufacturer_country_codes": "CH",
            "video_urls": [],
        }
    )
    # Always request replace_media. Empty images + replace_media clears heroes
    # once server bulk_import_media supports the empty-clear path; until then
    # clear_imageless_media attempts admin detach (may 403 without staff session).
    result = client.bulk_import_robots(
        [row],
        update_existing=True,
        patch_existing=True,
        status="pending_review",
        skip_company_update=True,
        replace_media=True,
        replace_videos=True,
    )
    if not PRODUCTS[rid].get("image"):
        try:
            result["cleared_photos"] = clear_imageless_media(client, rid)
        except Exception as exc:  # noqa: BLE001
            result["clear_photos_error"] = str(exc)[:300]
    return result


def copy_media(rid: int) -> dict[str, Any]:
    if not PRODUCTS[rid].get("image"):
        return {"skipped": True, "reason": "no_image"}
    response = requests.post(
        f"{_admin_base()}/admin/robots/robot/content-queue/api/robot/"
        f"{rid}/copy-media/?force=1",
        headers=_internal_headers(),
        timeout=240,
    )
    response.raise_for_status()
    return response.json()


def verify_fleet(client: ResearchApiClient) -> dict[str, Any]:
    hashes: dict[str, int] = {}
    media: list[dict[str, Any]] = []
    for rid, data in PRODUCTS.items():
        robot = client._get(f"robots/robots/{rid}/")
        if robot.get("status") != "pending_review":
            raise RuntimeError(f"{rid} status drifted to {robot.get('status')}")
        if robot.get("family_key") != data["family_key"]:
            raise RuntimeError(f"{rid} family_key mismatch")
        if not (robot.get("tags") or []):
            raise RuntimeError(f"{rid} missing tags")
        avail = robot.get("availability_status")
        avail_id = avail.get("id") if isinstance(avail, dict) else avail
        if int(avail_id or 0) != AVAILABLE:
            raise RuntimeError(f"{rid} availability not Available: {avail}")
        for key, expected in (data.get("typed") or {}).items():
            if not isinstance(expected, (int, float)):
                continue
            actual = robot.get(key)
            if actual is None:
                raise RuntimeError(f"{rid} missing typed {key}")
            if abs(float(actual) - float(expected)) > 0.05:
                raise RuntimeError(f"{rid} typed {key}={actual} != {expected}")
        url = str(robot.get("s3_image") or robot.get("image") or "")
        if data.get("image"):
            if not url or "cdn.robotaigeek.com" not in url:
                raise RuntimeError(f"{rid} missing owned CDN image: {url}")
            resp = requests.get(url, headers=HEADERS, timeout=90)
            if resp.status_code != 200 or len(resp.content) < 8_000:
                raise RuntimeError(
                    f"{rid} CDN bad: {resp.status_code} {len(resp.content)}b"
                )
            magic = resp.content[:4]
            if not (
                resp.content[:3] == b"\xff\xd8\xff"
                or resp.content[:4] == b"\x89PNG"
                or magic == b"RIFF"
            ):
                raise RuntimeError(f"{rid} non-image magic {magic.hex()}")
            digest = hashlib.sha256(resp.content).hexdigest()
            if digest in hashes:
                raise RuntimeError(
                    f"{rid} image hash collides with {hashes[digest]}"
                )
            hashes[digest] = rid
            image = Image.open(io.BytesIO(resp.content))
            media.append(
                {
                    "id": rid,
                    "url": url,
                    "size": list(image.size),
                    "bytes": len(resp.content),
                    "sha256": digest,
                }
            )
        else:
            notes = str(robot.get("notes") or "")
            if "IMAGE TO-DO" not in notes:
                raise RuntimeError(f"{rid} imageless without IMAGE TO-DO note")
            media.append(
                {
                    "id": rid,
                    "url": url or None,
                    "image_todo": True,
                    "stale_media": bool(url or (robot.get("photos") or [])),
                }
            )
    company = client._get(f"companies/{COMPANY_ID}/")
    return {
        "company_website": company.get("website"),
        "company_country": company.get("country"),
        "media": media,
        "family_groups": family_invariants(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Curate Bühler company 1507")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--skip-media", action="store_true")
    args = parser.parse_args()

    client = ResearchApiClient()
    live = {
        int(r["id"]): r
        for r in client.list_robots_for_company(COMPANY_ID)
        if r.get("status") == "pending_review"
    }
    if set(live) != set(PRODUCTS):
        raise RuntimeError(
            f"pending set drift: missing={sorted(set(PRODUCTS)-set(live))} "
            f"unexpected={sorted(set(live)-set(PRODUCTS))}"
        )

    preview = {
        "company_id": COMPANY_ID,
        "mode": "apply" if args.apply else "dry-run",
        "company_website": COMPANY_WEBSITE,
        "switzerland_id": SWITZERLAND,
        "family_groups": family_invariants(),
        "products": {rid: payload(rid) for rid in PRODUCTS},
        "image_todo": [
            rid for rid, data in PRODUCTS.items() if not data.get("image")
        ],
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    if not args.apply:
        REPORT.write_text(
            json.dumps(preview, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(preview, indent=2, ensure_ascii=False))
        return 0

    company_result = patch_company(client)
    import_results: dict[int, Any] = {}
    copy_results: dict[int, Any] = {}
    for rid in PRODUCTS:
        import_results[rid] = replace_media(client, rid)
        if import_results[rid].get("error_count"):
            raise RuntimeError(f"import failed {rid}: {import_results[rid]}")
        client._patch(f"robots/robots/{rid}/", scalar_payload(rid))
        if not args.skip_media:
            copy_results[rid] = copy_media(rid)

    verified = verify_fleet(client) if not args.skip_media else {"skipped": True}
    preview.update(
        {
            "applied": True,
            "company_result": company_result,
            "import_results": import_results,
            "copy_media": copy_results,
            "verified": verified,
        }
    )
    REPORT.write_text(
        json.dumps(preview, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(preview, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
