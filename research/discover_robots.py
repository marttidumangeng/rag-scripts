"""
Discover new robots from a company website and write staging JSON for bulk import.

Unlike `auto robots` (which enriches robots already in the DB), this script
crawls the company site to FIND new robots that don't exist yet, then stages
them for import.

Usage:
  # Dry run — discover, show what would be created
  python discover_robots.py --company-id 1372

  # Provide known product page URLs to seed the crawl
  python discover_robots.py --company-id 1372 \\
    --seed-urls "https://www.365robot.sg/robot-waiter/,https://www.365robot.sg/robot-promoter/"

  # JS-heavy site (renders with Playwright)
  python discover_robots.py --company-id 1372 --playwright

  # Discover + import in one step
  python discover_robots.py --company-id 1372 --apply --created-by-id 1 --status pending_review

  # Local dev server
  python discover_robots.py --company-id 1372 --local --apply --created-by-id 1
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any
import urllib.parse
from urllib.parse import urlparse

# Ensure UTF-8 output on Windows (robot/company names may contain non-ASCII chars)
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Load env before importing anything else
import sys as _sys
from load_env import load_research_env
load_research_env(local="--local" in _sys.argv)

from api_client import ResearchApiClient
from evidence_store import EvidenceStore
from product_url_search import is_weak_product_url, search_product_url_for_robot
from release_year_lookup import citation_line, lookup_release_year
from schema import SourceRef, StagedRobot
from slug_utils import slugify_company_name
from web_extract import (
    PageContent,
    WebFetcher,
    build_image_candidates_for_pages,
    confirm_target_on_page,
    discover_sitemap_urls,
    extract_image_urls,
    extract_specs_from_text,
    normalize_url,
    parse_page,
    robot_name_tokens,
    same_site,
    select_hero_from_candidates,
)

from google import genai
from google.genai import types

RESEARCH_DIR = Path(__file__).resolve().parent
STAGING_ROBOTS = RESEARCH_DIR / "staging" / "robots"

_GEMINI_MODEL = "models/gemini-2.5-flash"

# URL path segments that strongly suggest a product/robot page
_PRODUCT_SIGNALS = re.compile(
    r"/(robot|amr|agv|fmr|bot|cobot|drone|arm|manipulator|"
    r"delivery|service|greeter|receptionist|promoter|waiter|"
    r"forklift|inspection|patrol|cleaning|disinfect|product|solution)s?[/-]",
    re.I,
)
_SKIP_SIGNALS = re.compile(
    # cases/case-studies/applications: deployment stories, not product pages —
    # they carry install-site nicknames instead of product names (Qin Feng
    # 2026-08-03: a /cases/ page yielded "Old Treasure Little Yellow Man", a
    # literal translation of the Chinese nickname for a robot that already
    # existed under its real model code).
    r"/(blog|news|press|career|about|contact|privacy|cookie|"
    r"cases?|case-stud(?:y|ies)|success-stor(?:y|ies)|"
    r"login|register|faq|glossary|tag|category|search|page)/",
    re.I,
)

_EXTRACT_SYSTEM = """\
You are a robotics product catalog assistant for RobotAIGeek, a trusted robotics \
intelligence platform. Given a web page's title, URL, and text content, extract \
ALL distinct robot products mentioned on this page.

A single page may describe multiple variants (e.g. Model A, Model B, Model C).
Treat each variant as a separate robot.

DO NOT extract products that are clearly NOT robots: conventional standalone
machinery (press brakes, grinders, levelers, CNC machines, laser/plasma cutters,
conveyors, decoilers, punching machines, storage racks), spare parts/accessories
sold alone (grippers, controllers, sensors, batteries), or generic vehicles.
A robotic CELL built around a robot arm counts as a robot. When a product is
borderline, include it but set "is_robot" honestly.

Return a JSON array. Each element must have:
  - "is_robot": true when this is a robot/robotic system; false when it is
    conventional machinery, a component, or software-only (boolean, required)
  - "non_robot_reason": when is_robot is false, one short factual phrase quoting
    what makes it a non-robot (string or "")
  - "name": the robot's full commercial name in ENGLISH (string, required).
    If the page names the product in Japanese/Chinese/Korean, translate or
    romanize it, keeping model codes verbatim (e.g. "Mujin パレットシャトル PS1500A"
    -> "Mujin Pallet Shuttle PS1500A"). Never return a name containing CJK characters.
  - "model_name": model/SKU code if different from name (string or "")
  - "purpose": one short phrase for the robot's primary purpose, e.g.
    "Warehouse order fulfillment" (string or "")
  - "features": 2-5 key features as short phrases joined by newlines, only from
    page content (string or "")
  - "release_year": 4-digit year the robot launched IF the page states it (int or null)
  - "availability": one of "available", "pre_order", "coming_soon", "discontinued",
    or "" when the page doesn't say
  - "price_min" / "price_max": numeric price in the page's currency if shown
    (numbers or null; a single price goes in both)
  - "price_currency": ISO code or symbol when a price is shown (string or "")
  - "source_locale": language of the page text, e.g. "en", "zh-CN", "ja", "de"
  - "movement_types": array from ["wheeled","legged","aerial","tracked","stationary","swimming","other"]
  - "sub_category": single slug from ["personal-assistants","service-hospitality","personal-mobility",
    "retail-customer-engagement","learning","logistics-warehouse","agriculture","companionship",
    "manufacturing-industrial","cleaning-facilities","security","healthcare","military"]
  - "uses": array from ["assembly","cleaning","entertainment","exploration","other","palletizing",
    "pick-and-place","research","surgery","cooking","delivery","guiding","helping","inspection",
    "inventory","monitoring","patrol","picking","reception","remote","sanitizing","scanning",
    "transport","education"]
  - "industries": array from ["defence","others","research","space","agriculture","airports",
    "cleaning","construction","education","healthcare","homes","hotels","logistics",
    "manufacturing","restaurants","retail","security"]
  Taxonomy fields: only use values from the lists; empty array/"" when genuinely uncertain.
  These five narrative fields feed the extended (long-form) description; return each
  ONLY when the page states it, "" otherwise — never invent (see no-hallucination rule):
  - "programming_interface": how the robot is programmed/taught (e.g. "Drag-and-drop
    tablet UI, no coding" or "UR Script / Polyscope 5"). Max 120 chars.
  - "safety_fencing": whether a safety fence/cage is required (e.g. "Not required in
    collaborative mode" or "Full perimeter fencing required"). Max 120 chars.
  - "mounting_options": supported mounting orientations (e.g. "Floor, wall, ceiling,
    inverted"). Max 80 chars.
  - "deployment_context": typical installation/deployment time or effort (e.g.
    "Operational within a single shift"). Max 120 chars.
  - "ecosystem_compatibility": certified accessories, partner ecosystem, or integration
    standards (e.g. "300+ UR+ certified accessories", "ROS 2 compatible"). Max 150 chars.
  - "specs": object with any of these keys the page STATES (omit keys not stated;
    convert units: lbs->kg, mph->m/s, hours->minutes):
    {"weight_kg": num, "payload_kg": num, "reach_mm": num, "speed_ms": num,
     "dof": int, "battery_wh": num, "runtime_minutes": int,
     "charging_time_minutes": int, "ip_rating": "IP54", "dimensions_mm": "LxWxH"}
  - "tags": array of 3-6 tags chosen ONLY from the ALLOWED TAGS list appended to
    the page content below; [] when none fit
  - "categories": array of 1-3 slugs chosen ONLY from the ALLOWED CATEGORIES list
    appended below; [] when none fit
  - "description": English description of what the robot does, following the
    CONTENT-BRIEF STYLE rules below (string or "")
  - "is_robot_page": true if this page is about a physical robot product, false otherwise

CONTENT-BRIEF STYLE for "description" (all are hard requirements):
1. FIRST SENTENCE: must name the robot, the company, and the robot type in a
   single clause, stated as fact.
2. LENGTH SCALES WITH THE PAGE'S FACTS: if the page only establishes what the
   robot is, who makes it, and what it does, write 2-3 sentences. Only when
   the page also states things like a launch year, a concrete differentiator
   (spec, capability, design choice), or deployment/availability evidence may
   you write up to 120-180 words in short paragraphs. Never pad a thin page
   into a long text.
3. Voice: third-person present tense only. Never imperative ("Achieve...",
   "Discover..."). Never first-person. No rhetorical questions, no opening
   with industry pain points.
4. Banned words: advanced, innovative, cutting-edge, state-of-the-art,
   high-performance, enhanced, next-generation, revolutionary, seamless,
   robust, powerful, versatile, sophisticated, exceptional, superior, premier.
5. Banned moves: "represents the company's vision", "has evolved through
   multiple iterations", any claim about company strategy or mission unless
   it appears verbatim on the page.
6. No hallucination: use ONLY information present in the page content — no
   outside knowledge about this robot, even if you recognize it. Facts the
   page doesn't state are UNKNOWN; write less rather than inventing.

If the page is NOT about a physical robot product (e.g. it's a blog, about page,
careers, contact, news), return: [{"is_robot_page": false}]

COMPONENTS ARE NOT ROBOTS. Also return [{"is_robot_page": false}] for pages about:
actuators/servo motors (e.g. DYNAMIXEL), sensors, cameras, controllers, motor
drivers, batteries, chargers, wheels, frames, software/SDKs, spare parts, and
simple grippers. Exception: complete robots, robotic arms/manipulators, mobile
platforms, drones, and standalone multi-DOF dexterous robot hands DO count.

Respond ONLY with a valid JSON array. No markdown fences, no extra text.

Examples:
[
  {"name": "365HotelBot - W", "model_name": "365HotelBot-W", "description": "365HotelBot-W is a wheeled delivery robot from 365 Robot for hotel room service. It rides elevators autonomously, phones guests on arrival, and navigates corridors with LiDAR. Launched in 2023, it is deployed in hotels across Southeast Asia.", "purpose": "Hotel room-service delivery", "features": "Elevator integration\\nLiDAR navigation\\nGuest phone notification", "release_year": 2023, "availability": "available", "price_min": null, "price_max": null, "price_currency": "", "source_locale": "en", "movement_types": ["wheeled"], "sub_category": "service-hospitality", "uses": ["delivery"], "industries": ["hotels"], "is_robot_page": true},
  {"name": "365HotelBot - S", "model_name": "365HotelBot-S", "description": "365HotelBot-S is a compact delivery robot from 365 Robot for smaller hotels. It squeezes through corridors as narrow as 80 cm using the same elevator-integrated navigation as the W model.", "purpose": "Compact hotel amenity delivery", "features": "80 cm corridor clearance\\nElevator integration", "release_year": null, "availability": "available", "price_min": null, "price_max": null, "price_currency": "", "source_locale": "en", "movement_types": ["wheeled"], "sub_category": "service-hospitality", "uses": ["delivery"], "industries": ["hotels"], "is_robot_page": true}
]
"""

# Deterministic non-robot backstop (2026-08-04). The prompt's is_robot /
# is_robot_page instructions explicitly exclude controllers, software, and
# components — and the model STILL returned is_robot=true for an entire
# "Robot Controller GRC Series" catalogue (NexAIoT: 15 controllers, gateways,
# a teach pendant, an API library and an HMI staged as robots; the category
# title contains "Robot", which is apparently all it takes). Third incident
# of an instruction-only gate failing. This veto reads the TYPE PHRASE the
# extractor itself asserts as fact (the name + the mandated first sentence
# "X is a <type> from <company>") — a claim we can regex, not a judgement we
# have to trust. A strong physical-robot phrase anywhere overrides the veto,
# so "NexMOV AMR is an Autonomous Mobile Robot..." survives while
# "GRC V100 is a robot controller..." does not.
_COMPONENT_VETO_RE = re.compile(
    r"\b(robot |motion )?controllers?\b|\bgateways?\b|\bteach(ing)? pendants?\b"
    r"|\bpendants?\b|\bsoftware\b|\bsdk\b|\bapi\b|\blibrar(y|ies)\b"
    r"|\bhmi\b|\bhuman.machine interface\b|\bconfiguration tool\b"
    r"|\bindustrial pc\b|\bpanel pc\b|\brpa\b|\brobotic process automation\b"
    r"|\bi/?o module\b|\bservo (drives?|motors?)\b|\bactuators?\b"
    r"|\bgrippers?\b|\bmaster stack\b|\bcontrol platform\b"
    # Conventional-machinery vocabulary (2026-08-06 draft-lane sweep found 30
    # of these already imported: woodworking lines, packaging machines, PLCs).
    # Deliberately NO bare 'cnc' — real machine-tending robots mention CNC.
    r"|\bproduction line\b|\bpress brake\b|\bbending machine\b"
    r"|\bengraving machine\b|\bedge band(er|ing)\b|\bwoodworking\b"
    r"|\bsheet metal machine\b|\blathe\b|\bmilling machine\b"
    r"|\b(packaging|filling|sealing|drilling|saw) machine\b"
    r"|\bplc\b|\bcamera payload\b|\bisr payload\b"
    # Digital goods: 3D-print file shops sell STL/PDF downloads for building
    # STATIC props, not robots. Droid Division (company 1829, 2026-08-09) put
    # three Futurama/Star-Wars fan replicas in the queue at GBP 22 each — the
    # page literally says "Listing is NOT a physical item/prop. It is FILES
    # for 3D PRINTING at home".
    r"|\bstl file|\b3d[- ]print(?:ing|able|ed)? (?:file|set|kit|plan)"
    r"|\bdownloadable (?:pdf|file|plan)|\bprint files\b|\bdigital (?:product|download)"
    r"|\bnot a physical item\b|\bpapercraft\b|\bcosplay\b|\bprop replica\b",
    re.IGNORECASE,
)

# WooCommerce/Etsy listing chrome swallowed into the product NAME: a shop's
# archive markup glues the rating and price onto the title, and an "add to
# cart" button label can be captured as the name outright. Real examples from
# company 1829: "Cal Robot Rated 5.00 out of 5 £ 22.00", "Select options".
_SHOP_CHROME_NAME_RE = re.compile(
    r"rated\s+[\d.]+\s+out of\s+\d"
    r"|\b(?:select options|add to (?:basket|cart)|read more|buy now|out of stock)\b"
    r"|[£$€]\s?\d",
    re.IGNORECASE,
)
_STRONG_ROBOT_RE = re.compile(
    r"\b(autonomous mobile robot|amr|agv|robot(ic)? arm|articulated robot"
    r"|scara|delta robot|parallel robot|cobot|collaborative robot|humanoid"
    r"|quadruped|hexapod|exoskeleton|mobile robot|welding robot"
    r"|palletiz\w+ robot|robot palletizer|palletizer|inspection robot"
    r"|cleaning robot|delivery robot|service robot|surgical robot"
    r"|test automation robot|robotic cell|drone|uav|robot(ic)? hand)\b",
    re.IGNORECASE,
)


# Robot-TYPE vocabulary for the generic-name check below. Deliberately a
# SEPARATE set from _GENERIC_NAME_WORDS (which feeds dedupe identity): a name
# made ENTIRELY of type words + generic words is a category shell, but a type
# word alongside a brand token ("Agilex AMR") is fine.
_TYPE_ONLY_WORDS = frozenset({
    "delta", "scara", "cobot", "co", "amr", "agv", "arm", "arms", "humanoid",
    "industrial", "collaborative", "mobile", "autonomous", "welding",
    "palletizing", "picking", "sorting", "inspection", "cleaning", "delivery",
    "service", "smart", "intelligent", "speed", "high", "ultra", "axis",
    "dual", "single", "compact", "heavy", "light", "duty", "purpose",
})

# Rows extracted from news/exhibition coverage rather than a product page.
# QKM 2026-08-05: "HS-1540 Robot ... was showcased at the fair" — a real-ish
# model code with no product page behind it, unverifiable as staged.
_NEWS_DERIVED_RE = re.compile(
    r"\b(?:was |were |first )?(?:showcased|unveiled|exhibited|debuted|premiered)\s+at\b",
    re.IGNORECASE,
)


_URL_SLUG_NOISE = frozenset({
    "product", "products", "detail", "details", "index", "html", "htm", "php",
    "asp", "aspx", "en", "cn", "tw", "de", "jp", "page", "item", "goods",
    "shop", "store", "view", "id", "www", "com", "solution", "solutions",
})


def name_disagrees_with_url(name: str, url: str) -> bool:
    """True when the extracted name shares NOTHING with its own product URL.

    WHY (2026-08-09, Wuxi Wanlv 1828): the extractor named three real products
    after the site's NAV CATEGORY — "Agriculture & Photovoltaic",
    "Fishery & Photovoltaic", "Ground Projects" — while the URLs said
    `.../solar-panel-cleaning-robot-wls-7-lm/`. Every downstream step then
    searched for a category label, found nothing, and left ten fields blank:
    Martti saw "promising entries with a lot of data missing", but the real
    defect was the NAME, and every enrichment call spent on those rows was
    wasted before it started. A product page's slug essentially always carries
    the model or product words; zero overlap means we grabbed a breadcrumb.

    Conservative: returns False whenever either side has no distinctive tokens
    (opaque numeric slugs, /product/12345) rather than guessing.
    """
    slug = re.split(r"[?#]", (url or ""))[0].rstrip("/").rsplit("/", 1)[-1]
    slug_tokens = {
        t for t in re.split(r"[^a-z0-9]+", slug.lower())
        if len(t) > 1 and not t.isdigit() and t not in _URL_SLUG_NOISE
    }
    name_tokens = {
        t for t in re.split(r"[^a-z0-9]+", (name or "").lower())
        if len(t) > 1 and t not in _URL_SLUG_NOISE and t not in _GENERIC_NAME_WORDS
    }
    if not slug_tokens or not name_tokens:
        return False
    if slug_tokens & name_tokens:
        return False
    # Model codes vary slightly between name and slug ("UR10e" vs `ur10-robot`,
    # "HH7E" vs `hh7`), so exact token equality is too strict — a containment
    # match on either side counts as agreement. >=3 chars so "a"/"x" can't
    # match everything.
    for n_tok in name_tokens:
        for s_tok in slug_tokens:
            if len(n_tok) >= 3 and len(s_tok) >= 3 and (n_tok in s_tok or s_tok in n_tok):
                return False
    return True


def _clean_features(features, name: str = "", model_name: str = "") -> str:
    """Deterministic feature cleanup; never fails the caller."""
    try:
        from features_gen import clean_feature_lines
        return clean_feature_lines(str(features or ""), name=name, model_name=model_name)
    except Exception:  # noqa: BLE001 — cleanup is a bonus, never a blocker
        return str(features or "")


# A manufacturer's own URL taxonomy is the most reliable "is this a robot"
# signal we have — vendors file products honestly even when the marketing copy
# talks about robotics. Orbbec (company 1799, 2026-08-11) put THIRTEEN depth
# cameras, a 2D LiDAR and two camera-computer modules into the queue; two
# reached To Review at score 96, because AI verification checks fidelity to the
# source page and never asks whether the product is a robot.
_COMPONENT_URL_RE = re.compile(
    r"/products?/[^/]*("
    r"stereo[-_]?vision|structured[-_]?light|depth[-_]?camera|camera[-_]computer"
    r"|3d[-_]?camera|rgbd?[-_]?camera|vision[-_]?(sensor|camera|system)"
    r"|lidar|lazer|laser[-_]scanner|tof[-_]|time[-_]of[-_]flight"
    r"|imu\b|encoder|servo[-_]?(motor|drive)|reducer|gearbox|harmonic[-_]drive"
    r"|controller|gateway|teach[-_]pendant|power[-_]supply"
    r"|computer[-_]on[-_]modules?|com[-_]express|single[-_]board|motherboard"
    r"|industrial[-_]?pcs?|edge[-_](server|computer)|accelerator"
    r"|end[-_]effector|gripper|actuator"
    r")", re.IGNORECASE)

# The same vocabulary as it appears in a product's own first sentence.
_SENSOR_TYPE_RE = re.compile(
    r"\b(depth (and rgb |)camera|rgbd camera|stereo (vision |)camera"
    r"|structured[- ]light camera|3d camera|time[- ]of[- ]flight (camera|sensor)"
    r"|lidar( sensor| scanner|)|laser scanner|vision sensor|camera[- ]computer"
    r"|imu|inertial measurement unit|depth sensor)\b", re.IGNORECASE)


def component_veto(name: str, description: str, url: str = "") -> str:
    """Return the offending phrase when a staged item is not a catalogable
    robot product; '' when it reads as one. Three deterministic checks:

    1. Generic-only name — every token is category vocabulary ("Delta Robot",
       "Co-robot") and there is no model code. These are series/marketing
       shells that duplicate the properly-named rows next to them.
    2. News/exhibition derivation — "was showcased at ..." descriptions come
       from coverage pages, not product pages.
    3. Component/software type phrase — the extractor's own first sentence
       says controller/gateway/software/etc. A strong physical-robot phrase
       overrides ONLY this check (a "Delta Robot" shell must not be saved by
       'delta robot' also being a strong-robot phrase).
    """
    first_sentence = (description or "").split(".")[0]
    scope = f"{name or ''} {first_sentence}"
    # URL taxonomy first: it is the vendor's own classification and survives
    # marketing copy that name/description checks fall for. Checked BEFORE the
    # strong-robot override, because "for robotics" appears in the blurb of
    # every component sold into this market.
    if url:
        u = _COMPONENT_URL_RE.search(url)
        if u:
            return f"component product path ({u.group(1).lower()!r})"
    m = _SENSOR_TYPE_RE.search(scope)
    if m:
        return f"sensor/vision component ({m.group(0).lower()!r})"
    # Shop-listing chrome in the NAME means we scraped an archive tile, not a
    # product page — the row is unusable whatever it turns out to be.
    chrome = _SHOP_CHROME_NAME_RE.search(name or "")
    if chrome:
        return f"shop-listing chrome in name ({chrome.group(0)!r})"
    if not _model_code_set(name or ""):
        toks = [t for t in re.split(r"[^a-z0-9]+", (name or "").lower()) if t]
        if toks and all(t in _GENERIC_NAME_WORDS or t in _TYPE_ONLY_WORDS for t in toks):
            return f"generic-only name {name!r}"
    # Only when the WHOLE description is a thin blurb: a rich product-page
    # description may legitimately cite a trade-fair debut as launch evidence,
    # but "X is a robot from Y. It was showcased at Z." is coverage, not catalog.
    sentences = [s for s in (description or "").split(".") if s.strip()]
    if len(sentences) <= 2:
        m = _NEWS_DERIVED_RE.search(description or "")
        if m:
            return m.group(0)
    if _STRONG_ROBOT_RE.search(scope):
        return ""
    m = _COMPONENT_VETO_RE.search(scope)
    return m.group(0) if m else ""


# Content-brief style checks (mirrors robots/description_gen.py on the server) —
# LLMs don't always follow prompt rules, so violations are logged for review
# rather than trusted silently
_BANNED_WORDS_RE = re.compile(
    r"\b(advanced|innovative|cutting[- ]edge|state[- ]of[- ]the[- ]art|"
    r"high[- ]performance|enhanced|next[- ]generation|revolutionary|seamless|"
    r"robust|powerful|versatile|sophisticated|exceptional|superior|premier)\b",
    re.IGNORECASE,
)
_BANNED_MOVES_RE = re.compile(
    r"represents the company['’]?s vision|has evolved through multiple iterations",
    re.IGNORECASE,
)


def _brief_violations(name: str, description: str) -> list[str]:
    if not description:
        return []
    problems = []
    if len(description) < 80:
        problems.append(f"description below brief minimum ({len(description)} < 80 chars)")
    elif len(description.split()) > 220:
        problems.append(f"description above brief maximum ({len(description.split())} > 220 words)")
    banned = sorted({m.lower() for m in _BANNED_WORDS_RE.findall(description)})
    if banned:
        problems.append(f"banned promotional word(s): {', '.join(banned)}")
    if _BANNED_MOVES_RE.search(description):
        problems.append("banned template phrase")
    first = description[:250].lower()
    name_token = name.split()[0].lower() if name.split() else ""
    if name_token and name_token not in first:
        problems.append("first sentence does not name the robot")
    return problems


# Backwards-compatible alias (older call sites / reports refer to Track A)
_track_a_violations = _brief_violations


# ---------------------------------------------------------------------------
# URL discovery
# ---------------------------------------------------------------------------

def _slug_word_count(url: str) -> int:
    """Number of hyphen-separated words in the last path segment."""
    slug = urlparse(url).path.strip("/").split("/")[-1]
    return len([w for w in slug.split("-") if w])


def _score_url_as_product(url: str, *, strict: bool = False) -> int:
    """Score a URL for likelihood of being a dedicated robot product page.

    strict=True applies tighter filters to exclude blog/case-study URLs that
    happen to mention robots but aren't a product page (--product-pages-only).
    """
    path = urlparse(url).path.lower()
    if _SKIP_SIGNALS.search("/" + path.strip("/")):
        return -10
    score = 0
    if _PRODUCT_SIGNALS.search("/" + path.strip("/")):
        score += 8
    # Depth heuristic: product pages are usually 1-2 levels deep
    depth = len([p for p in path.split("/") if p])
    if depth == 1:
        score += 3
    elif depth == 2:
        score += 1
    elif depth >= 4:
        score -= 3
    # Extensions / static assets
    if re.search(r"\.(pdf|zip|png|jpg|svg|css|js)$", path):
        return -10
    # Strict mode: long slugs are almost always blog/case-study pages, not product pages.
    # e.g. /robot-restaurant-singapore-japanese-dining/ (5 words) → blog
    #      /hotel-room-delivery-service-robot/ (5 words) → product (has product signal)
    # Penalise if slug is long AND no strong product signal.
    if strict:
        words = _slug_word_count(url)
        if words > 5:
            score -= 20  # definitely a blog post
        elif words > 4 and score < 8:
            score -= 10  # long-ish slug without a product keyword
    return score


def discover_product_urls(
    fetcher: WebFetcher,
    website: str,
    seed_urls: list[str],
    *,
    use_playwright: bool = False,
    strict: bool = False,
    limit: int = 60,
) -> list[str]:
    """Return candidate product page URLs from sitemap, homepage links, and seeds.

    strict=True (--product-pages-only) filters out long blog/case-study URLs.
    """
    parsed = urlparse(website)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    netloc = parsed.netloc

    seen: set[str] = set()
    candidates: list[str] = []

    def add(url: str) -> None:
        url = normalize_url(url, origin)
        if url and url not in seen and same_site(url, netloc):
            seen.add(url)
            candidates.append(url)

    # 1. Seed URLs have highest priority
    for u in seed_urls:
        add(u)

    # 2. Sitemap
    for u in discover_sitemap_urls(fetcher, origin, limit=200):
        add(u)

    # 3. Homepage links
    homepage = parse_page(fetcher, origin, rendered=use_playwright)
    if homepage:
        for href in re.findall(r'href=["\']([^"\'#?][^"\']*)["\']', homepage.html):
            add(href if href.startswith("http") else f"{origin.rstrip('/')}/{href.lstrip('/')}")

    # Score and filter
    scored = [((_score_url_as_product(u, strict=strict), -i), u) for i, u in enumerate(candidates)]
    scored.sort(key=lambda x: x[0], reverse=True)

    # Seed URLs always included first regardless of score
    result = list(seed_urls[:])
    for (score, _), url in scored:
        if url not in result:
            if score >= 0:
                result.append(url)
    return result[:limit]


# ---------------------------------------------------------------------------
# Per-page robot extraction via Gemini
# ---------------------------------------------------------------------------

def _gemini_client():
    # Metered via spend_guard (daily budget); v1beta: thinking_config is not
    # accepted on v1 (400 INVALID_ARGUMENT) — matches product_url_search.py /
    # robot_auto_research.py.
    import spend_guard
    return spend_guard.client(http_options={"api_version": "v1beta"})


class GeminiBudgetExhausted(RuntimeError):
    """Raised when this process hits its GEMINI_CALL_BUDGET — abort, don't keep burning quota."""


_gemini_calls = 0


def _check_gemini_budget() -> None:
    """Per-process call cap (env GEMINI_CALL_BUDGET, 0/unset = unlimited). Guards against
    loops/stuck runs silently eating API quota — each company runs in its own process,
    so the budget is effectively per-company."""
    global _gemini_calls
    budget = int(os.environ.get("GEMINI_CALL_BUDGET", "0") or 0)
    _gemini_calls += 1
    if budget and _gemini_calls > budget:
        raise GeminiBudgetExhausted(f"GEMINI_CALL_BUDGET={budget} exhausted ({_gemini_calls} calls)")


def extract_robots_from_page(page: PageContent, company_name: str,
                             allowed_tags: list[str] | None = None,
                             allowed_categories: list[str] | None = None) -> list[dict[str, Any]]:
    """Use Gemini to extract robot product info from a page. Returns list of robot dicts."""
    # Chrome-stripped copy, not page.text: a prefix of the full text is navigation on
    # nav-heavy sites (avinc.com's mega-menu runs ~9k chars, pushing every product fact
    # past the cutoff — that is how AeroVironment's ROV got described as a flying robot).
    # main_text is far shorter than text, so a larger budget still cuts tokens.
    text_snippet = (page.main_text or page.text or "")[:6000]
    tags_block = ""
    if allowed_tags:
        tags_block = "\n\nALLOWED TAGS: " + ", ".join(allowed_tags[:300])
    user_msg = (
        f"Company: {company_name}\n"
        f"Page URL: {page.url}\n"
        f"Page title: {page.title}\n"
        f"Meta description: {page.meta_description}\n\n"
        f"Page text (truncated):\n{text_snippet}"
        f"{tags_block}"
    )

    _check_gemini_budget()
    client = _gemini_client()
    response = client.models.generate_content(
        model=_GEMINI_MODEL,
        contents=f"{_EXTRACT_SYSTEM}\n\n{user_msg}",
        config=types.GenerateContentConfig(
            temperature=0.0,
            max_output_tokens=4096,
            # Without this, 2.5-flash can burn its whole output budget on hidden
            # reasoning and return nothing (see robot_auto_research.py YouTube search).
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )

    text = (response.text or "").strip()
    # Strip markdown fences if present
    text = re.sub(r"^```[a-z]*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Try to extract first [...] block
        m = re.search(r"\[[\s\S]*?\]", text)
        if not m:
            return []
        try:
            data = json.loads(m.group())
        except json.JSONDecodeError:
            return []

    if not isinstance(data, list):
        return []
    if data and data[0].get("is_robot_page") is False:
        return []

    robots = []
    for item in data:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name or not item.get("is_robot_page", True):
            continue
        description = str(item.get("description") or "").strip()
        # Deterministic backstop on the model's own type phrase — the
        # is_robot_page flag lies on component pages (see component_veto).
        veto = component_veto(name, description, getattr(page, "url", "") or "")
        if veto:
            print(f"    -- '{name}' type-phrase veto ({veto!r}), skipping")
            continue
        for problem in _track_a_violations(name, description):
            print(f"    [style] {name}: {problem}")
        robots.append({
            "name": name,
            "model_name": str(item.get("model_name") or "").strip(),
            "description": description,
            "url": page.url,
            "images": page.images,
            # extended extraction fields — consumed by _write_staging
            "purpose": item.get("purpose"),
            # Free cleanup of scraper artifacts (page H1 glued to the first
            # bullet, space-before-punctuation). AI verification cannot catch
            # these — the text is faithful to the source, just not editorially
            # clean — so a human was deleting them by hand (robot 6446).
            "features": _clean_features(
                item.get("features"), name, str(item.get("model_name") or "")
            ),
            "release_year": item.get("release_year"),
            "availability": item.get("availability"),
            "price_min": item.get("price_min"),
            "price_max": item.get("price_max"),
            "price_currency": item.get("price_currency"),
            "source_locale": item.get("source_locale"),
            "movement_types": item.get("movement_types"),
            "sub_category": item.get("sub_category"),
            "uses": item.get("uses"),
            "industries": item.get("industries"),
            "programming_interface": item.get("programming_interface"),
            "safety_fencing": item.get("safety_fencing"),
            "mounting_options": item.get("mounting_options"),
            "deployment_context": item.get("deployment_context"),
            "ecosystem_compatibility": item.get("ecosystem_compatibility"),
            "specs": item.get("specs"),
            "tags": item.get("tags"),
            "categories": item.get("categories"),
        })
    return robots


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def _normalize(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _model_code_set(name: str) -> frozenset[str]:
    """The digit-bearing tokens of a product name — its language-independent core.

    "Aktives Schulter-Exoskelett S700", "Active Shoulder Exoskeleton S700",
    "S700 Schulter-Exoskelett", "exoIQ S700" and "S700" all reduce to {s700}:
    the marketing words around a model code vary per page and per locale, the
    code does not. Tokens without a digit ("exoiq", "shoulder") are excluded —
    they're branding/description, not identity.
    """
    # Split on WHITESPACE, not hyphens: a hyphenated model string is ONE code.
    # Hyphen-splitting reduced 'QF-GJ-J-DL-1400-10-4/5' to {1400}, making every
    # DL/YT/MD/H variant of the 1400 series "the same product" — 5+ real
    # variants were skipped at discovery on Hu Nan Qin Feng (2026-08-03),
    # directly violating the variants-are-separate-rows policy.
    tokens = re.split(r"\s+", (name or "").lower())

    def _is_code(t: str) -> bool:
        t = re.sub(r"[^a-z0-9]", "", t)
        if not t or not any(c.isdigit() for c in t):
            return False  # no digits = branding/description word
        if t.isdigit() and len(t) < 3:
            return False  # bare small numbers ("2", "24") are counts, not codes
        return True

    return frozenset(
        re.sub(r"[^a-z0-9]", "", t) for t in tokens if _is_code(t)
    )


# Tokens that make a same-code name a DIFFERENT product (a variant), not a
# re-phrasing. Variants are deliberately separate catalog rows (Option A family
# policy: models and variants shown separately) — the dedupe below must never
# collapse them. Digit-bearing qualifiers (V2, MK2, R2) are already distinct
# model codes; this list covers the digit-less ones.
_VARIANT_QUALIFIERS = frozenset({
    "pro", "plus", "max", "mini", "lite", "ultra", "neo", "evo", "air",
    "xl", "xs", "se", "ng", "gen", "mk", "mkii", "cobot", "edu", "kit",
    "sp", "dw", "mi", "sr", "hd", "st", "lr", "ex", "w",
})


def _variant_tokens(name: str) -> frozenset[str]:
    tokens = re.split(r"[^a-z0-9]+", (name or "").lower())
    return frozenset(t for t in tokens if t in _VARIANT_QUALIFIERS)


# Category/descriptor vocabulary (EN + the DE/EN mix real OEM sites use) that
# never identifies a product. Only consulted for names WITHOUT a model code:
# "DEXTER Robotic Surgery System" / "DEXTER" / "Dexter Robotic System" must
# reduce to the same brand core {dexter} (Distalmotion, 2026-08-03: one product
# became 6 rows because code-based dedupe had nothing to key on).
_GENERIC_NAME_WORDS = frozenset({
    "robot", "robots", "robotic", "robotics", "system", "systems", "series",
    "platform", "solution", "solutions", "machine", "machines", "surgery",
    "surgical", "medical", "active", "aktives", "aktive", "soft",
    "exoskeleton", "exoskeletons", "exoskelett", "exoskelette",
    "shoulder", "schulter", "back", "support", "console", "cart", "patient",
    "surgeon", "edition", "version", "model", "type", "the", "and", "for",
})


def _identity_core(name: str) -> frozenset[str]:
    """The tokens that identify a product: model codes when present, else the
    brand words left after stripping generic vocabulary and variant qualifiers.
    Empty = name carries no identity (pure category words) — no core dedupe."""
    codes = _model_code_set(name)
    if codes:
        return codes
    tokens = re.split(r"[^a-z0-9]+", (name or "").lower())
    return frozenset(
        t for t in tokens
        if t and t not in _GENERIC_NAME_WORDS and t not in _VARIANT_QUALIFIERS and len(t) > 1
    )


def _already_exists(name: str, existing_names: set[str],
                    existing_code_variants: dict[frozenset[str], set[frozenset[str]]] | None = None) -> bool:
    if _normalize(name) in existing_names:
        return True
    # Cross-locale/cross-phrasing duplicate: same model-code core AND same
    # variant qualifiers as a robot we already have. Without this, a bilingual
    # site yields one robot per page TITLE, not per product — exoIQ
    # (2026-08-03): 3 real products became 24 robots ("S700 Shoulder
    # Exoskeleton", "S700 Schulter-Exoskelett", "exoIQ S700", "S700"...).
    # VARIANTS ARE NOT DUPLICATES: "S700 Pro" differs from "S700" by a
    # qualifier token, is a separate product, and stays a separate row —
    # only names with the same code AND the same qualifier set are collapsed.
    if existing_code_variants:
        core = _identity_core(name)
        if core and _variant_tokens(name) in existing_code_variants.get(core, set()):
            return True
    return False


# ---------------------------------------------------------------------------
# Staging writer
# ---------------------------------------------------------------------------

# Site chrome, never product photos: theme assets and banner/hero filenames
# (e.g. mujin.co.jp /wp-content/themes/mujin/assets/jp/img/top_catch.png).
_CHROME_IMAGE_RE = re.compile(
    r"/wp-content/themes/|/(?:[a-z0-9_-]*(?:banner|hero|top_catch|_catch|logo|favicon|og[-_]image|"
    r"partners?|clients?|sponsors?|brands?|"
    # event/booth/team photos are people shots, not product images
    r"show|expo|fair|booth|conference|event|team|award|default|placeholder|profile|flag|icon)[a-z0-9_-]*)\.(?:png|jpe?g|webp|svg)$"
    # site-wide og/social cards named like 'robotis_og.png' / 'site-og.jpg'
    r"|[-_]og\.(?:png|jpe?g|webp)$"
    # video-player thumbnails are stills, not product photos (the video itself
    # is captured separately via the embed URL)
    r"|//img\.youtube\.com/|//i\.ytimg\.com/|vimeocdn\.com/",
    re.I,
)

# WordPress/CDN size-variant suffixes: photo-300x191.png, photo-scaled.jpg,
# photo-scaled-e1666727076134.jpg are all the SAME asset.
_WP_VARIANT_RE = re.compile(r"(-\d{2,4}x\d{2,4}|-scaled(?:-e\d+)?|-e\d{8,})(?=\.\w{3,4}$)", re.I)

# Shopify size variants: photo_490x.jpg, photo_490x@2x.jpg, photo_70x.progressive.webp.jpg,
# photo_1024x1024.jpg are all the SAME asset (Shopify appends _<W>[x<H>] and an @Nx DPR).
# Without this a Shopify gallery collapses to ONE asset served at 6 sizes while *looking*
# like 6 photos — seen on Makeblock, where mBot2/mTiny each staged 6 images that were one
# render at _490x/_490x@2x/_70x/...
_SHOPIFY_VARIANT_RE = re.compile(r"_(\d{2,4})x(\d{2,4})?(?:@([23])x)?(?=[._]|$)", re.I)
# Shopify also stacks pseudo-extensions: photo_490x.progressive.webp.jpg
_EXT_CHAIN_RE = re.compile(r"(?:\.(?:progressive|webp|avif|jpe?g|png|gif))+$", re.I)

# Webflow responsive variants: photo-p-500.webp, photo-p-1080.png — same asset.
# (RobCo's site-wide render staged as 6 "photos" that were one image at -p-108/160/200/...)
_WEBFLOW_VARIANT_RE = re.compile(r"-p-(\d{2,4})(?=\.\w{3,4}$|$)", re.I)

# PATH-prefix transforms: the resize lives in the directory, not the filename —
# /cdn/w_330/photo.jpg is a 330px render of /uploads/photo.jpg (Saab Seaeye).
# Suffix-based keys can't see these, so one asset staged twice (SR20: hi-res-2.png
# from both /uploads/ and /cdn/w_330/). Only collapsed WITHIN one robot's list —
# keying globally on the bare filename could merge unrelated same-named assets.
_CDN_WIDTH_PATH_RE = re.compile(r"/cdn/[whq]_(\d{2,4})/", re.I)


def _img_url(x: object) -> str:
    """A staged `images[]` entry is either a candidate dict ({'url': ...}) or a
    plain URL string — `image` (the hero) is always a string. Normalise both."""
    if isinstance(x, dict):
        return str(x.get("url") or "")
    return str(x or "")


def _unquote_stable(s: str, limit: int = 3) -> str:
    """Percent-decode until stable. Webflow serves the -p-<width> variants of an
    asset DOUBLE-encoded ("Elegante%2520Elise" vs "Elegante%20Elise"), so without
    this the same render compares as two assets and never collapses."""
    for _ in range(limit):
        d = urllib.parse.unquote(s)
        if d == s:
            break
        s = d
    return s


def _image_base_key(u: object) -> str:
    """Identity of the underlying asset, ignoring CDN size/format transforms.

    Key only — never use for fetching; the stored URL must stay encoded.
    """
    b = _img_url(u).split("?")[0]  # drop ?v= / ?width= cache-busters
    b = _unquote_stable(b)         # normalise single/double percent-encoding
    b = b.split("/m/")[0]          # Storyblok transform path
    b = _WP_VARIANT_RE.sub("", b)
    b = _SHOPIFY_VARIANT_RE.sub("", b)
    b = _WEBFLOW_VARIANT_RE.sub("", b)
    b = _EXT_CHAIN_RE.sub("", b)
    return re.sub(r"\.\w{3,4}$", "", b)

_CJK_NAME_RE = re.compile(
    "[぀-ヿ"   # Hiragana + Katakana
    "㐀-䶿"    # CJK Extension A
    "一-鿿"    # CJK Unified Ideographs
    "豈-﫿"    # CJK Compatibility Ideographs
    "가-힯]"   # Hangul Syllables
)


_TAG_CATALOG = None


def _tag_catalog():
    """Load the tag catalog once per process (one API call), never per robot."""
    global _TAG_CATALOG
    if _TAG_CATALOG is None:
        from tag_suggest import TagCatalog
        _TAG_CATALOG = TagCatalog.load()
    return _TAG_CATALOG


def _catalog_tag_names() -> list[str]:
    """Tag names from the catalog API (loaded once per process)."""
    try:
        cat = _tag_catalog()
        return [str(t.get("name") or "").strip() for t in cat.tags if t.get("name")]
    except Exception:
        return []


_CATEGORY_SLUGS = None


def _catalog_category_slugs() -> list[str]:
    """Category slugs the model may choose from (loaded once per process).

    Intersected with `robot_categories.CANONICAL_CATEGORY_SLUGS` rather than
    offered raw. The live table held 191 rows on 2026-07-31, 135 of them unused
    and many near-duplicates of each other ("Ground Robot" / "Ground / Ground
    Robot" / "Grounded"; "aerial" / "drone" / "uav"). Handing that list to a
    classifier guarantees the duplicates keep getting picked, which is how they
    stay alive. The intersection also means the model can only name rows that
    already exist, so the importer never has to create one.
    """
    global _CATEGORY_SLUGS
    if _CATEGORY_SLUGS is None:
        from robot_categories import CANONICAL_CATEGORY_SLUGS
        try:
            from api_client import ResearchApiClient
            c = ResearchApiClient()
            slugs, page = [], 1
            while True:
                d = c._get("categories/", params={"page": page, "page_size": 100})
                items = d.get("results", []) if isinstance(d, dict) else d
                slugs += [i.get("slug") for i in items if isinstance(i, dict) and i.get("slug")]
                if not (isinstance(d, dict) and d.get("next")):
                    break
                page += 1
            _CATEGORY_SLUGS = [s for s in slugs if s in CANONICAL_CATEGORY_SLUGS]
        except Exception:
            # Offline/API failure must not mean "no categories at all" — the
            # vocabulary is a constant, and every slug in it exists on prod.
            _CATEGORY_SLUGS = sorted(CANONICAL_CATEGORY_SLUGS)
    return _CATEGORY_SLUGS


def _youtube_title(url: str) -> str:
    """Video title via YouTube oEmbed — free, no API key. Best-effort."""
    try:
        import requests as _rq
        r = _rq.get("https://www.youtube.com/oembed",
                    params={"url": url, "format": "json"}, timeout=8)
        if r.status_code == 200:
            return str(r.json().get("title") or "")[:255]
    except Exception:
        pass
    return ""


def _dedupe_cdn_transforms(urls: list[str]) -> list[str]:
    """Collapse image variants to one URL per underlying asset:
    - Storyblok `/m/<transform>` suffixes (prefer the largest transform)
    - WordPress `-WxH` / `-scaled` / `-eNNN` size variants (prefer the original/largest)
    - Shopify `_WxH` / `@2x` DPR variants (prefer the original/largest)
    """
    def rank(u: str) -> int:
        if "/m/20x0" in u:  # lazy-load placeholder, 20px wide
            return 0
        m = re.search(r"/m/(\d+)x(\d+)", u)
        if m:
            return int(m.group(1)) * max(int(m.group(2)), 1)
        if "/m/" in u:  # smart/filters transform at original size
            return 500_000
        m = re.search(r"-(\d{2,4})x(\d{2,4})(?=\.\w{3,4}$)", u)
        if m:  # WP thumbnail: rank by area
            return int(m.group(1)) * int(m.group(2))
        if re.search(r"-scaled(?:-e\d+)?(?=\.\w{3,4}$)", u, re.I):
            return 3_000_000  # WP 'scaled' = full-size render of a huge original
        m = _SHOPIFY_VARIANT_RE.search(u)
        if m:  # Shopify: rank by rendered width (w * DPR); always below a plain original
            w = int(m.group(1)) * int(m.group(3) or 1)
            h = int(m.group(2) or w)
            return min(w * h, 2_000_000)
        m = _WEBFLOW_VARIANT_RE.search(u)
        if m:  # Webflow -p-<width>: rank by width, still below a plain original
            return min(int(m.group(1)) * 1_000, 2_000_000)
        m = _CDN_WIDTH_PATH_RE.search(u)
        if m:  # /cdn/w_330/ path transform: rank by width, below a plain original
            return min(int(m.group(1)) * 1_000, 2_000_000)
        return 2_500_000  # plain original filename
    def base_key(u: str) -> str:
        # Within ONE robot's list a repeated filename is the same asset served from
        # a transform path (/cdn/w_330/x.jpg vs /uploads/x.jpg), so key on the
        # filename once a path-transform is in play. Never do this globally.
        k = _image_base_key(u)
        if _CDN_WIDTH_PATH_RE.search(u):
            return k.rsplit("/", 1)[-1]
        return k

    best: dict[str, str] = {}
    order: list[str] = []
    # First pass keyed as above; second pass collapses an original that only
    # differs from a transform by directory (keys: full path vs bare filename).
    for u in urls:
        base = base_key(u)
        if base not in best:
            order.append(base)
            best[base] = u
        elif rank(u) > rank(best[base]):
            best[base] = u
    out = [best[b] for b in order]

    # Second pass: drop a PATH-TRANSFORM url when a better-ranked sibling with the
    # same filename exists (its original, or a wider render). Restricted to urls
    # that actually carry a transform — collapsing on bare filename unconditionally
    # would merge unrelated same-named assets (/uploads/2023/hero.jpg vs .../2024/).
    def _name(u: str) -> str:
        return _image_base_key(u).rsplit("/", 1)[-1]

    final: list[str] = []
    for u in out:
        if _CDN_WIDTH_PATH_RE.search(u) and any(
            v is not u and _name(v) == _name(u) and rank(v) > rank(u) for v in out
        ):
            continue
        final.append(u)
    return final


def _demote_cross_page_images(
    staged_files: list[Path],
    image_pages: dict[str, set[str]],
    *,
    min_pages: int = 2,
) -> dict[str, int]:
    """Drop site-furniture images from staged robots, order-independently.

    An asset that appears on 2+ DIFFERENT product pages is a site-wide graphic
    (nav banner, concept render, style frame, marketing tile), not any one robot's
    product photo. The in-loop `image_usage` guard only counts robots staged
    EARLIER, so the first claimants keep the generic asset — RobCo shipped its
    site-wide humanoid "Concept-Robot" render as the hero of several 5-axis arms
    that way. This runs after the crawl, when every page has been seen, so the
    threshold applies to every robot equally.

    Deliberately no "keep something" fallback: a robot left with zero images gets
    the `missing_image` flag, which is the honest signal. A wrong hero is worse
    than none (see the >=4-photos rule: correct beats padded).
    """
    shared = {k for k, pages in image_pages.items() if len(pages) >= min_pages}
    stats = {"files": 0, "dropped": 0, "emptied": 0, "hero_repicked": 0}
    if not shared:
        return stats
    for fp in staged_files:
        try:
            d = json.loads(Path(fp).read_text(encoding="utf-8"))
        except Exception:
            continue
        before = list(d.get("images") or [])
        kept = [u for u in before if _image_base_key(u) not in shared]
        if len(kept) == len(before):
            continue
        stats["files"] += 1
        stats["dropped"] += len(before) - len(kept)
        d["images"] = kept
        if d.get("image") and _image_base_key(d["image"]) in shared:
            # `image` is a plain URL string even though `images[]` holds candidate dicts.
            d["image"] = _img_url(kept[0]) if kept else ""
            stats["hero_repicked"] += 1
        if not kept:
            stats["emptied"] += 1
            print(f"        !! {d.get('name')}: all images were site-wide assets "
                  f"(each on >={min_pages} pages) — left with none, expect missing_image")
        Path(fp).write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
    return stats


def _write_staging(
    robot: dict[str, Any],
    company_slug: str,
    company_name: str,
    country_code: str,
    *,
    company_website: str = "",
    image_usage: dict[str, int] | None = None,
    shared_page: bool = False,
    source_pages: list[PageContent] | None = None,
) -> Path:
    name = robot["name"]
    robot_slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    images = [u for u in robot.get("images", []) if not _CHROME_IMAGE_RE.search(u)]
    # An image already staged for 2+ earlier robots this run is a shared page
    # banner/graphic, not this robot's product photo — drop it.
    if image_usage is not None:
        images = [u for u in images if image_usage.get(u, 0) < 2]
    images = _dedupe_cdn_transforms(images)
    tokens = robot_name_tokens(name, robot.get("model_name") or "")
    if shared_page:
        # Multiple robots share this page: an image belongs to THIS robot only when
        # its filename carries one of the robot's model tokens (e.g. 'rmp-401' vs
        # 'rmp-lite-220'). Token-less images (siblings' photos, event shots) are
        # dropped rather than cross-attributed — no image beats the wrong image.
        images = [u for u in images
                  if any(tok and tok in u.lower() for tok in tokens)]
    product_url = robot.get("url") or ""
    if is_weak_product_url(product_url, company_website, tokens):
        searched = search_product_url_for_robot(
            name,
            company_name,
            model_name=robot.get("model_name") or "",
            company_website=company_website,
        )
        # Search results bypass the crawl-time URL filter — apply it here too.
        # Serper happily returns /about/, /news/, /cases/ pages as "the product
        # URL", and Qin Feng (2026-08-03) got a whole shadow product series
        # extracted from its About page's company-history section that way.
        if searched and _SKIP_SIGNALS.search(searched):
            print(f"        search returned non-product page, discarded: {searched}")
            searched = None
        if searched:
            product_url = searched
            print(f"        product URL via search: {searched}")
    pages_for_images = [
        PageContent(
            url=page.url,
            html=page.html,
            text=page.text,
            title=page.title,
            meta_description=page.meta_description,
            images=[image_url for image_url in page.images if image_url in images],
            video_urls=page.video_urls,
        )
        for page in (source_pages or [])
    ]
    if not pages_for_images and images:
        pages_for_images = [
            PageContent(
                url=product_url,
                html="",
                text=f"{name} {robot.get('model_name') or ''}",
                title=name,
                images=images,
            )
        ]
    image_candidates = build_image_candidates_for_pages(
        pages_for_images,
        product_url=product_url,
        name=name,
        model_name=robot.get("model_name") or "",
        tokens=tokens,
        company_name=company_name,
    )
    hero_image = select_hero_from_candidates(image_candidates)
    if image_usage is not None:
        for u in {candidate["url"] for candidate in image_candidates}:
            if u:
                image_usage[u] = image_usage.get(u, 0) + 1

    def _keys(vals: object) -> str:
        return "|".join(v.strip() for v in vals if isinstance(v, str) and v.strip()) \
            if isinstance(vals, list) else ""

    _avail_map = {"available": "released", "pre_order": "pre_order",
                  "coming_soon": "coming_soon", "discontinued": "discontinued"}
    _price_min, _price_max = robot.get("price_min"), robot.get("price_max")

    # The extractor returns [] for categories whenever nothing in the allowed
    # list "fits", which is most of the time — derive from the taxonomy it DID
    # return rather than staging a robot that lands flagged "No category".
    from robot_categories import derive_category_slugs

    category_slugs = _keys(robot.get("categories")) or derive_category_slugs(
        name=name,
        text=" ".join(str(robot.get(f) or "") for f in ("description", "purpose", "features")),
        movement_type_keys=_keys(robot.get("movement_types")),
        sub_category_slug=(robot.get("sub_category") or "").strip(),
        use_keys=_keys(robot.get("uses")),
        industry_keys=_keys(robot.get("industries")),
        fallback="other",
    )

    staged = StagedRobot(
        name=name,
        model_name=robot.get("model_name") or "",
        company_slug=company_slug,
        company_name=company_name,
        manufacturer_country_code=country_code,
        url=product_url,
        description=robot.get("description") or "",
        purpose=(robot.get("purpose") or "")[:200],
        features=(robot.get("features") or "")[:1500],
        # release_year is filled by the grounded lookup below, never from page
        # extraction — the extractor invents years despite the "IF the page
        # states it" prompt rule (refresh years, the current year).
        availability_status_key=_avail_map.get(str(robot.get("availability") or "").strip(), ""),
        price_min=float(_price_min) if isinstance(_price_min, (int, float)) else None,
        price_max=float(_price_max) if isinstance(_price_max, (int, float)) else None,
        price_currency=(robot.get("price_currency") or "")[:10],
        # Platform supports en/zh-CN/zh-HK only; our extracted text is English,
        # so any other detected page language (ko/ja/de/...) stages as en.
        source_locale=(lambda loc: loc if loc in ("en", "zh-CN", "zh-TW", "zh-HK") else "en")(
            (robot.get("source_locale") or "en").strip()),
        category_slugs=category_slugs,
        movement_type_keys=_keys(robot.get("movement_types")),
        sub_category_slug=(robot.get("sub_category") or "").strip(),
        use_keys=_keys(robot.get("uses")),
        industry_keys=_keys(robot.get("industries")),
        # Extended-description narrative fields (blank unless the page stated them).
        programming_interface=(robot.get("programming_interface") or "")[:120],
        safety_fencing=(robot.get("safety_fencing") or "")[:120],
        mounting_options=(robot.get("mounting_options") or "")[:80],
        deployment_context=(robot.get("deployment_context") or "")[:120],
        ecosystem_compatibility=(robot.get("ecosystem_compatibility") or "")[:150],
        image=hero_image,
        images=image_candidates,
        # Fills `company.country` on import when the Company row is blank
        # (views.py company-enrichment block), so the whole manufacturer is
        # fixed by the first robot staged rather than one robot at a time.
        company_hq_country_code=country_code,
        sources=[SourceRef(url=product_url, type="website")] if product_url else [],
    )
    # Specs: Gemini-extracted (page spec tables) first, then heuristic page-text fallback
    _SPEC_KEYS = {"weight_kg", "payload_kg", "reach_mm", "speed_ms", "dof", "battery_wh",
                  "runtime_minutes", "charging_time_minutes", "ip_rating", "dimensions_mm"}
    gem_specs = robot.get("specs") if isinstance(robot.get("specs"), dict) else {}
    merged_specs = {**(robot.get("_page_specs") or {}), **gem_specs}
    for key, val in merged_specs.items():
        if key in _SPEC_KEYS and hasattr(staged, key) and not getattr(staged, key, None):
            try:
                setattr(staged, key, val)
            except Exception:
                continue

    # Tags: Gemini picks from the catalog list (constrained); keyword suggester retired
    gem_tags = robot.get("tags")
    if isinstance(gem_tags, list):
        clean = [t.strip() for t in gem_tags if isinstance(t, str) and 0 < len(t.strip()) <= 40]
        staged.tags = "|".join(dict.fromkeys(clean))[:500]

    # Release year: only a search-grounded year with a citation is staged, and the
    # citation goes into research_notes (-> robot notes on import) for human audit.
    # An uncited year is dropped rather than imported: a wrong staged year also
    # blocks the enrichment pass, which only looks up years the DB doesn't have.
    year_hit = None
    try:
        _check_gemini_budget()
        year_hit = lookup_release_year(
            name, company_name, model_name=robot.get("model_name") or "")
    except GeminiBudgetExhausted:
        pass  # budget spent: stage without a year instead of failing the robot
    except Exception:
        year_hit = None
    if year_hit:
        staged.release_year = year_hit["year"]
        staged.confidence["release_year"] = year_hit["confidence"]
        staged.research_notes = (
            (staged.research_notes + "\n" if staged.research_notes else "")
            + citation_line(year_hit)
        )
        print(f"        release year: {year_hit['year']} [{year_hit['confidence']}]")
    elif robot.get("release_year"):
        print(f"        release year {robot['release_year']} from page extraction "
              "dropped (no grounding citation)")

    # Videos: YouTube embeds from the robot's own page (single-robot pages only —
    # videos can't be token-matched to siblings on shared pages)
    vid_urls = robot.get("_page_videos") or []
    if vid_urls and not staged.video_urls:
        from schema import VideoRef
        staged.video_urls = [VideoRef(url=u, title=_youtube_title(u)) for u in vid_urls[:3]]

    # HARD RULE (Martti, 2026-08-03): Discovery must never emit a robot with
    # blank features. When the extractor found none, GENERATE distinct feature
    # bullets from the description — never a literal copy, which the server's
    # `features_duplicates_description` flag forbids (a naive copy shipped for
    # a few hours on 2026-08-03 and immediately produced that flag on Edge
    # Medical). features_gen verifies distinctness with the server's own
    # checker; '' -> the import gate holds the row.
    if not (staged.features or "").strip():
        from features_gen import features_from_text
        staged.features = features_from_text(staged.name, staged.description or "")

    out_dir = STAGING_ROBOTS / company_slug
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{robot_slug}.json"
    out_path.write_text(
        json.dumps(staged.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return out_path


# ---------------------------------------------------------------------------
# Main discovery workflow
# ---------------------------------------------------------------------------

def discover_robots_for_company(
    company_id: int,
    *,
    client: ResearchApiClient | None = None,
    seed_urls: list[str] | None = None,
    use_playwright: bool | None = None,
    use_stealth: bool = False,
    use_apify: bool | None = None,
    skip_existing: bool = True,
    product_pages_only: bool = False,
    max_per_page: int = 0,
    gemini_delay: float = 1.0,
    url_limit: int = 60,
) -> dict[str, Any]:
    """
    Crawl company website, discover new robots, write staging JSON.

    product_pages_only: filter out long blog/case-study URLs before fetching.
    max_per_page: if a page yields more than this many robots, skip it (it's a
                  listing page showing the full catalog, not a dedicated product page).
                  0 = no limit.
    use_playwright: None (default) = take it from RESEARCH_USE_PLAYWRIGHT, which is
                  what the nightly VM sets. Pass True/False to override explicitly.
    """
    # Previously this defaulted to False and never consulted the environment, so
    # the nightly discovery stage ran plain `requests` on a box with Chromium
    # installed — RESEARCH_USE_PLAYWRIGHT was only ever read by
    # robot_auto_research.py (the ENRICHMENT stage). Against a JS-rendered
    # catalogue (axios/Next.js) discovery therefore saw a placeholder shell and
    # moved on, which is a large part of why JS-storefront OEMs are so
    # under-covered. Explicit True/False from a caller or --playwright still wins.
    if use_playwright is None:
        use_playwright = os.environ.get("RESEARCH_USE_PLAYWRIGHT", "").lower() in ("1", "true", "yes")

    client = client or ResearchApiClient()
    company = client.get_company(company_id)
    company_name = str(company.get("name") or "")
    company_slug = slugify_company_name(company.get("slug") or company.get("name") or "")
    website = str(company.get("website") or "")
    country_code = ""
    if company.get("country"):
        country_code = str(company["country"].get("code") or "")

    if not website:
        return {"ok": False, "error": f"Company id={company_id} has no website set"}

    if not country_code:
        # Free, offline, and correct for every manufacturer on a ccTLD — the
        # alternative is staging a whole company's robots with the
        # error-severity "No country" flag. Anything less certain is left to
        # `resolve_pending_company_gaps`, which fixes the Company row itself.
        from company_country_resolve import country_from_domain

        country_code = country_from_domain(website)
        if country_code:
            print(f"Country         : {country_code} (from domain — company row is blank)")

    print(f"\nCompany         : {company_name} (id={company_id})")
    print(f"Website         : {website}")
    print(f"Playwright      : {use_playwright}")
    print(f"Product pages only: {product_pages_only}")
    if max_per_page:
        print(f"Max robots/page : {max_per_page}")

    # Existing DB robots for dedup — by normalized name AND by (model-code core,
    # variant qualifiers) so cross-locale re-phrasings collapse while variants
    # stay separate rows (see _already_exists).
    existing_names: set[str] = set()
    existing_code_variants: dict[frozenset[str], set[frozenset[str]]] = {}
    if skip_existing:
        for r in client.list_robots_for_company(company_id):
            for field in ("name", "model_name"):
                v = r.get(field)
                if v:
                    existing_names.add(_normalize(str(v)))
                    core = _identity_core(str(v))
                    if core:
                        existing_code_variants.setdefault(core, set()).add(_variant_tokens(str(v)))
        print(f"Existing : {len(existing_names)} robots already in DB")

    fetcher = WebFetcher(timeout=30, stealth=use_stealth, apify_fallback=use_apify)
    evidence = EvidenceStore(company_slug)

    # Discover candidate URLs
    print("\nDiscovering product URLs...")
    urls = discover_product_urls(
        fetcher, website, seed_urls or [],
        use_playwright=use_playwright,
        strict=product_pages_only,
        limit=url_limit,
    )
    print(f"Candidates: {len(urls)} URLs to check")
    print(f"Evidence   : {evidence.relative_root}")

    # Bot-walled URL discovery: sitemap + homepage crawl found (almost) nothing the
    # seeds didn't already provide. Crawl the whole site through Apify's
    # website-content-crawler instead — real Firefox + rotating proxy — and feed the
    # returned pages straight into the same extraction loop below.
    pre_fetched: dict[str, PageContent] = {}
    if fetcher.apify_fallback and len(urls) <= len(seed_urls or []):
        from apify_fetch import apify_enabled, wcc_crawl_site
        from web_extract import page_from_html
        if apify_enabled():
            print("Sparse crawl — falling back to Apify website-content-crawler site crawl...")
            for item in wcc_crawl_site(website, max_pages=url_limit):
                page_url = normalize_url(str(item.get("url") or ""))
                if not page_url or _SKIP_SIGNALS.search(urlparse(page_url).path):
                    continue
                page = page_from_html(page_url, item.get("html") or "")
                if page is None and (item.get("text") or "").strip():
                    # No saved HTML (rare) — text-only page still allows name/spec
                    # extraction, just no image/video mining.
                    meta = item.get("metadata") or {}
                    page = PageContent(
                        url=page_url, html="", text=str(item.get("text") or ""),
                        title=str(meta.get("title") or ""),
                        meta_description=str(meta.get("description") or ""),
                    )
                if page is not None:
                    pre_fetched[page_url] = page
                    evidence.save_page(
                        page_url,
                        html=page.html or "",
                        text=page.text or "",
                        title=page.title or "",
                        source="apify_wcc",
                    )
            urls = list(dict.fromkeys(urls + list(pre_fetched)))
            print(f"Apify crawl: {len(pre_fetched)} pages fetched, {len(urls)} total candidates")

    discovered: list[dict[str, Any]] = []
    skipped_existing: list[str] = []
    skipped_target_not_found: list[str] = []
    errors: list[str] = []
    staged_files: list[str] = []
    checked_urls: set[str] = set()
    image_usage: dict[str, int] = {}  # image URL -> robots staged with it this run
    # asset identity -> set of pages it appeared on; feeds the cross-page demotion
    # post-pass (site-wide graphics show up on every product page).
    image_pages: dict[str, set[str]] = {}
    budget_exhausted = False

    for i, url in enumerate(urls, 1):
        if url in checked_urls:
            continue
        checked_urls.add(url)

        print(f"\n  [{i}/{len(urls)}] {url}")

        page = pre_fetched.get(url) or parse_page(fetcher, url, rendered=use_playwright)
        if not page:
            print("        -- fetch failed, skipping")
            errors.append(f"fetch failed: {url}")
            continue

        if url not in pre_fetched:
            evidence.save_page(
                url,
                html=page.html or "",
                text=page.text or "",
                title=page.title or "",
                source="playwright" if use_playwright else "fetch",
            )

        for _img in (page.images or []):
            image_pages.setdefault(_image_base_key(_img), set()).add(url)

        _page_specs = extract_specs_from_text(page.text or "")
        _yt_re = re.compile(r"(?:https?:)?//(?:www\.)?(?:youtube\.com/(?:watch\?v=|embed/)|youtu\.be/)([\w-]{6,20})")
        _page_videos = [f"https://www.youtube.com/watch?v={vid}"
                        for vid in dict.fromkeys(_yt_re.findall(page.html or ""))][:3]
        try:
            robots = extract_robots_from_page(page, company_name, allowed_tags=_catalog_tag_names(), allowed_categories=_catalog_category_slugs())
        except GeminiBudgetExhausted as exc:
            print(f"        !! {exc} — aborting discovery for this company")
            errors.append(str(exc))
            budget_exhausted = True
            break
        except Exception as exc:
            # The DAILY budget (spend_guard) must stop the crawl exactly like the
            # per-process budget above — without this it fell into the generic
            # handler below and kept walking every remaining URL, failing each
            # one (no spend, but wasted crawl time and a noisy log).
            from spend_guard import SpendBudgetExceeded
            if isinstance(exc, SpendBudgetExceeded):
                print(f"        !! {exc} — aborting discovery for this company")
                errors.append(str(exc))
                budget_exhausted = True
                break
            print(f"        -- Gemini error: {exc}")
            errors.append(f"gemini error on {url}: {exc}")
            if gemini_delay:
                time.sleep(gemini_delay)
            continue

        evidence.save_extract(url, robots or [], extractor="gemini_discover")

        if not robots:
            print("        -- not a robot product page")
            if gemini_delay:
                time.sleep(gemini_delay)
            continue

        if max_per_page and len(robots) > max_per_page:
            print(f"        -- {len(robots)} robots found (>{max_per_page}), looks like a listing page, skipping")
            if gemini_delay:
                time.sleep(gemini_delay)
            continue

        for robot in robots:
            name = robot["name"]
            model_name = str(robot.get("model_name") or "").strip()
            # Non-robots never get staged, so they can never be imported —
            # discovery is the cheapest place to stop a press brake from ever
            # costing a review slot + remediation passes (the 2026-07-31 batch
            # put 19 sheet-metal machines in To Review as "robots").
            if robot.get("is_robot") is False:
                why = str(robot.get("non_robot_reason") or "conventional machinery")[:120]
                print(f"        -- '{name}' NOT a robot ({why}), skipping")
                errors.append(f"non_robot skipped: {name} ({why})")
                continue
            # Deterministic backstop: the model claims is_robot=true, but its
            # own type phrase says otherwise (see component_veto docstring).
            veto = component_veto(name, str(robot.get("description") or ""),
                                  str(robot.get("url") or url or ""))
            if veto:
                print(f"        -- '{name}' type-phrase veto ({veto!r}), skipping")
                errors.append(f"component veto skipped: {name} ({veto})")
                continue
            # A name that shares nothing with its own product URL is a nav
            # breadcrumb, not a product name — importing it guarantees wasted
            # enrichment spend on a row nothing can research.
            if name_disagrees_with_url(name, str(robot.get("url") or "")):
                print(f"        -- '{name}' does not match its product URL, skipping")
                errors.append(f"name/url mismatch skipped: {name}")
                continue
            if _CJK_NAME_RE.search(name):
                # Prompt asks for English/romanized names; if CJK still leaks through,
                # skip rather than import a name the site can't render for EN visitors.
                print(f"        -- '{name}' has CJK name despite prompt, skipping")
                errors.append(f"cjk name skipped: {name}")
                continue
            if _already_exists(name, existing_names, existing_code_variants):
                print(f"        -- '{name}' already exists (name or model-code match), skipping")
                skipped_existing.append(name)
                continue

            # Fail closed: do not stage a robot Gemini inferred if the name/model
            # is not visibly present on this page (nav/footer/sibling hallucinations).
            if not confirm_target_on_page(name, model_name, page):
                detail = f"name/model not found on page text/title/url for {url}"
                print(f"        -- '{name}' target_not_found, skipping")
                evidence.note_target_not_found(url, name, detail=detail)
                skipped_target_not_found.append(name)
                errors.append(f"target_not_found: {name} @ {url}")
                continue

            # Variant extracted from a sibling's page (SM300-SP found on /sm300-ng/):
            # when a DIFFERENT crawl candidate URL carries this robot's own slug,
            # that page is its true product URL.
            if len(robots) > 1:
                _slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
                for cand in urls:
                    if cand != url and _slug and _slug in cand.lower().replace("_", "-"):
                        robot["url"] = cand
                        print(f"        (variant URL: {cand[:70]})")
                        break
            robot["_page_specs"] = _page_specs
            robot["_page_videos"] = _page_videos if len(robots) == 1 else []
            path = _write_staging(robot, company_slug, company_name, country_code,
                                  company_website=website, image_usage=image_usage,
                                  shared_page=(len(robots) > 1),
                                  source_pages=[page])
            print(f"        OK staged '{name}' -- {path.name}")
            evidence.link_robot(url, name, staging_file=str(path))
            discovered.append({"name": name, "url": url, "staging_file": str(path)})
            staged_files.append(str(path))
            existing_names.add(_normalize(name))  # prevent duplicates across pages
            _core = _identity_core(name)
            if _core:
                # ...including cross-locale re-phrasings (variants stay distinct)
                existing_code_variants.setdefault(_core, set()).add(_variant_tokens(name))

        if gemini_delay:
            time.sleep(gemini_delay)

    evidence_root = evidence.finish(
        company_id=company_id,
        discovered=len(discovered),
        skipped_existing=len(skipped_existing),
        skipped_target_not_found=len(skipped_target_not_found),
        errors=len(errors),
        budget_exhausted=budget_exhausted,
        website=website,
    )
    _demote = _demote_cross_page_images([Path(f) for f in staged_files], image_pages)
    if _demote["dropped"]:
        print(f"\nCross-page image demotion: dropped {_demote['dropped']} site-wide asset(s) "
              f"from {_demote['files']} robot(s); {_demote['hero_repicked']} hero(es) re-picked, "
              f"{_demote['emptied']} left with no image")

    print(
        f"\nDiscovery complete: {len(discovered)} new, "
        f"{len(skipped_existing)} skipped existing, "
        f"{len(skipped_target_not_found)} target_not_found, "
        f"{len(errors)} errors"
    )
    print(f"Evidence saved → {evidence_root}")
    summary = {
        # An aborted crawl is not a successful discovery — callers gate
        # auto-import and exit codes on this.
        "ok": not budget_exhausted,
        "company_id": company_id,
        "company_slug": company_slug,
        "discovered": discovered,
        "skipped_existing": skipped_existing,
        "skipped_target_not_found": skipped_target_not_found,
        "errors": errors,
        "staged_files": staged_files,
        "evidence_dir": evidence.relative_root,
        "evidence_run_id": evidence.run_id,
    }
    if budget_exhausted:
        summary["error"] = (
            "Gemini budget exhausted — discovery aborted early; "
            f"{len(discovered)} robot(s) staged before the abort were NOT imported"
        )
    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Discover new robots from a company website and stage them for import"
    )
    p.add_argument("--company-id", type=int, required=True, help="Company ID to crawl")
    p.add_argument(
        "--seed-urls",
        default="",
        help="Comma-separated product page URLs to prioritize (optional)",
    )
    p.add_argument("--playwright", action="store_true", help="Render JS pages with Playwright")
    p.add_argument(
        "--apify",
        action="store_true",
        help="Bot-wall escape hatch: fetch blocked pages via Apify website-content-crawler; "
             "crawls the whole site through Apify when URL discovery itself is blocked (needs APIFY_API_KEY)",
    )
    p.add_argument("--apply", action="store_true", help="Import staged robots via bulk-import API")
    p.add_argument("--local", action="store_true", help="Use *_LOCAL env vars to target local dev server")
    p.add_argument("--created-by-id", type=int, default=0, help="User ID for created_by field")
    p.add_argument("--status", default="pending_review", help="Robot status on import (default: pending_review)")
    p.add_argument("--delay", type=float, default=1.0, help="Seconds between Gemini calls (default: 1.0)")
    p.add_argument("--url-limit", type=int, default=60, help="Max candidate URLs to check (default: 60)")
    p.add_argument("--include-existing", action="store_true", help="Don't skip robots already in DB")
    p.add_argument(
        "--product-pages-only",
        action="store_true",
        help="Skip blog/case-study URLs with long slugs; only process dedicated product pages",
    )
    p.add_argument(
        "--max-per-page",
        type=int,
        default=0,
        help="Skip pages that yield more than N robots (listing pages). 0=no limit (default: 0)",
    )
    p.add_argument(
        "--enrich",
        action="store_true",
        help="After importing, run the enrichment pipeline to fill specs, images, movement types, etc. Requires --apply.",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    client = ResearchApiClient()

    seed_urls = [u.strip() for u in args.seed_urls.split(",") if u.strip()] if args.seed_urls else []

    result = discover_robots_for_company(
        args.company_id,
        client=client,
        seed_urls=seed_urls,
        use_playwright=args.playwright,
        use_apify=args.apify or None,
        skip_existing=not args.include_existing,
        product_pages_only=args.product_pages_only,
        max_per_page=args.max_per_page,
        gemini_delay=args.delay,
        url_limit=args.url_limit,
    )

    if not result.get("ok"):
        print(f"\nERROR: {result.get('error')}", file=sys.stderr)
        sys.exit(1)

    discovered = result["discovered"]
    if not discovered:
        print("\nNo new robots discovered.")
        return

    print(f"\nStaged {len(discovered)} robots in: staging/robots/{result['company_slug']}/")

    if not args.apply:
        print("\nRun with --apply to import.")
        return

    # Import via bulk-import — only the files this run staged, never whatever
    # else is sitting in the persistent staging dir.
    from import_staging import import_staging
    staged_paths = [Path(p) for p in result.get("staged_files", []) if Path(p).is_file()]
    if not staged_paths:
        print("\nNo importable staged files — skipping import.")
        return
    print("\nImporting staged robots...")
    import_result = import_staging(
        staged_paths,
        client=client,
        patch=True,
        status=args.status,
        dry_run=False,
        created_by_id=args.created_by_id or None,
        # Discovery stages SKELETONS (name/url/description/image). Importing
        # them raw creates unapprovable To Review shells that busiest-first
        # remediation never reaches (robot 6717, 2026-08-02). Run --enrich, or
        # set IMPORT_ALLOW_SKELETONS=1 for a deliberate raw import.
        block_skeletons=True,
    )
    created = import_result.get("created_count", 0)
    updated = import_result.get("updated_count", 0)
    errs = import_result.get("error_count", 0)
    print(f"\nImport complete: {created} created, {updated} updated, {errs} errors")

    if args.enrich and (created + updated) > 0:
        print("\nEnriching newly imported robots (specs, images, movement types, categories)...")
        from robot_auto_research import research_robots_for_company
        enrich_result = research_robots_for_company(
            args.company_id,
            client=client,
            only_missing=True,
            use_playwright=args.playwright or None,
        )
        enriched = enrich_result.get("robots_researched", 0)
        enrich_errs = enrich_result.get("errors", [])
        print(f"Enrichment complete: {enriched} robots updated, {len(enrich_errs)} errors")
        if enrich_errs:
            for e in enrich_errs:
                print(f"  - {e}")

    if errs:
        # Some rows failed to import — exit nonzero so schedulers see the failure.
        sys.exit(1)


if __name__ == "__main__":
    main()
