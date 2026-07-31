"""Batch-import all remaining QA-certified gap-discovery companies.

Continuation of the manual per-company import process used for the first 5
companies (Segway Navimow, AGILOX, Movu, Ambi, Wingtra) on 2026-07-30. Runs
unattended per explicit user instruction (overrides the normal
stage-one-review-one rule, since imports land as reversible pending_review
records and the ledger prevents duplicate imports).

Per company:
  1. Skip if already in staged_import.json's import_ledger.
  2. Re-check against CURRENT prod (not just the discovery-time baseline) by
     exact normalized-name match — catches companies created since the
     baseline was dumped. Does NOT catch brand/subsidiary overlaps like
     Navimow-vs-Segway; those still need a human's periodic sanity pass.
  3. Re-filter robot leads through the same junk regexes used during QA
     (defence in depth in case anything slipped through).
  4. Light-enrich each surviving robot from its product URL: og:description,
     validated og:image, purpose fallback derived from the company's own
     harvested category (never fabricated).
  5. Dry-run via import_staging(); on success, apply(); record the ledger
     entry. On any failure, log and move to the next company — one bad
     company must never stop the batch.

Writes progress to stdout (parseable by Monitor) and updates
staging/gap_discovery/staged_import.json's import_ledger after every company
so the run is safely resumable if interrupted.
"""
from __future__ import annotations

import json
import re
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any

import requests

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env  # noqa: E402

load_research_env()

from api_client import ResearchApiClient  # noqa: E402
from import_staging import import_staging  # noqa: E402

STAGED_FILE = _HERE / "staging" / "gap_discovery" / "staged_import.json"
ROBOTS_DIR = _HERE / "staging" / "gap_discovery" / "robots"

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

_JUNK_RE = re.compile(
    r"view all|read more|learn more|lecture|webinar|whitepaper|à propos|"
    r"newsletter|^\+|^about |^über |^\W*$|^more$|^more\+$|quick view|new products?|"
    r"^close$|^link$|^option$|^overview$|\.{3}$|…$|"
    # CMS navigation artifacts (Barrett Technology: "Folder: Drive Systems")
    r"^folder:|^category:|^tag:|^untitled|^draft\b|^copy of |[-–—]\s*duplicate$|"
    # "read more" in other languages seen across this dataset (XMobots pt-BR
    # "Leia mais", Innok Robotics de-DE "Weiterlesen »" slipped through the
    # English-only pattern during the batch import 2026-07-30) — trailing
    # arrow/guillemet glyphs (»,→,›) allowed since CMS themes append them.
    r"^leia mais\s*[»›→]?$|^lire la suite\b|^leer m[aá]s\s*[»›→]?$|"
    r"^mehr erfahren\s*[»›→]?$|^weiterlesen\s*[»›→]?$|"
    r"^en savoir plus\s*[»›→]?$|^saiba mais\s*[»›→]?$|^plus d.infos?\s*[»›→]?$",
    re.I,
)
_LANG_RE = re.compile(
    r"^(fran[cç]ais|espa[nñ]ol|portugu[eê]s|t[uü]rk[cç]e|italiano|deutsch|"
    r"nederlands|polski|latvie[sš]u|o[ʻ']zbekcha|ti[eế]ng viet|vietnamese|"
    r"english|русский|日本語|한국어|简体中文|繁體中文)$",
    re.I,
)
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
# Funding/press-release headlines (Donecle's "€10M to Scale Drone-Based
# Inspection") — a currency amount is a signal no real product name carries.
_FUNDING_RE = re.compile(
    r"[$€£¥]\s*\d|(?<![\w.])\d+\s*(m|million|k|thousand|b|billion)\b.{0,20}"
    r"\b(fund|raise|round|invest)|series\s+[a-e]\b.{0,15}(extension|round|fund)",
    re.I,
)
# Vertical/solution-page nav links, not product names (found across Flyability,
# Wingtra, Symbotic, Saab etc. during manual QA — the discovery-time link
# miner's PRODUCT_LINK_KEYWORDS matched "solution"/"platform" too broadly).
_GENERIC_VERTICAL_RE = re.compile(
    r"^(oil\s*&?\s*gas|mining(\s*(and|&)\s*metals)?|agricultur\w*|construction|"
    r"defense|defence|healthcare|automotive|aerospace|security|logistics|"
    r"autonomy|solutions?|applications?|industr(y|ies)|technolog\w*|services?|"
    r"about( us)?|contact( us)?|careers?|news|blog|resources?|partners?|"
    r"investors?|events?|overview|products?|company|home|land|naval|air(\s*forces?)?|"
    # non-English nav/vertical terms observed in this dataset (ES/DE/FR/PT —
    # each new company's site keeps surfacing another language's equivalent
    # of "Services"/"Industries"; treating this as open-ended is unrealistic,
    # so only the terms actually seen are added rather than guessing ahead)
    r"industrias?|servicios|farmac[eé]utica( y salud)?|salud|noticias|empresa|"
    r"unternehmen|dienstleistungen|industrien|entreprise|services?|"
    r"industries?|soci[eé]t[eé]|"
    r"consumer( product)?s?|preschool( &|\s+and)?\s*plush|dashboard( &|\s+and)?\s*analytics|"
    r"support( &|\s+and)?\s*service|cities|commercial|"
    # industry-vertical nav links (Flyability, Saab, Symbotic-style sites: a
    # row of "who we serve" links, not products)
    r"maritime|marine|power(\s*gen(eration)?)?|chemicals?|sewers?|cement|"
    r"nuclear|infrastructure|water|energy|utilit(y|ies)|pharma(ceutical)?|"
    r"food(\s*(and|&)\s*beverage)?|beverage|manufacturing|insurance|finance|"
    r"banking|retail|telecom\w*|education|government|hospitality|facilit(y|ies)|"
    r"warehousing|e-?commerce|offshore|onshore|refining|inspection|plant|"
    r"upstream|downstream|midstream|distribution|geospatial|surveying|"
    r"mapping)$",
    re.I,
)
# Consumer home-appliance parts/accessory category names (SharkNinja's parts
# site: "Fans", "Wet Dry Vacuums", "Steam Mops" — none of these are robots,
# they're corded/manual appliance categories on a spare-parts catalog).
# "robot vacuum"/"robotic mop" etc. are explicitly exempted since those ARE
# legitimate catalog products.
_APPLIANCE_CATEGORY_RE = re.compile(
    r"^(corded |cordless |handheld |upright |canister |stick |wet ?dry )*"
    r"(vacuums?|mops?|sweepers?|fans?|purifiers?|blenders?|steamers?|"
    r"humidifiers?|dehumidifiers?|heaters?|coolers?|cleaners?)"
    r"(\s*&(amp;)?\s*(spot cleaners?|cooling|accessories))?$",
    re.I,
)


def _clean_name(name: str) -> str:
    return _unescape(name).strip()
# Marketing/press/inventory phrases anywhere in the name — found via manual
# QA of the first 8 companies bulk-imported 2026-07-30 (Symbotic's "Solutions
# Overview"/"AI & Software"/"Warehouse-as-a-Service", Robomow's "Best in
# Tests" press-award page, Orqa's "Internationalization of ORQA solutions"
# news article, HIWIN's "Modular Tables and Stages"/"Mechanical Components"/
# "IN-STOCK INVENTORY" component-catalog pages). Substring, not full-match —
# these appear inside longer titles the exact-match vertical regex misses.
_MARKETING_PHRASE_RE = re.compile(
    r"solutions?\b|overview\b|as[\s-]a[\s-]service|distribution\b|"
    r"\bbest in\b|internationali[sz]ation|\bannounces?\b|\bpartnership\b|"
    r"\bin[\s-]stock\b|\binventory\b|\bcomponents?\b|\bmodular\b|"
    r"\btables?\s+and\s+stages\b|\bwelcomes?\b|\bnewest\b|\bawards?\b|"
    # content-marketing / EdTech-SaaS page genre (LuxAI: "Usecases and
    # Success Stories", "Evidence based practices") and blog "we visited X"
    # posts (Kinisi Robotics: "Kinisi Visits Bear Robotics – Korea")
    r"\buse ?cases?\b|\bsuccess stories\b|\bcase stud(y|ies)\b|\bcurriculum\b|"
    r"\bevidence[\s-]based\b|\bimplementation support\b|\btraining\b|"
    r"\bvisits?\b.{0,25}[–\-]|\bride[\s-]?hail(ing)?\b",
    re.I,
)
_COMPONENT_ONLY_RE = re.compile(
    r"^(usb adapter|battery( set)?|transmitter|receiver|transmitter/receiver"
    r"( set)?|power meter|servo motor|gears?|strain wave gears?|cable|"
    r"charger|remote control|controller|adapter|connector|sensor module)"
    r"(\s+(v|version)?\s*[\d.]+)?$",
    re.I,
)
# B2B wholesale-marketplace listing template — e.g. Gongboshi Robot
# Technology's site repeated "Buy low priced {category} from {category}
# factory, We provide good quality..." verbatim across 8 different generic
# category names (Welding Robot Arm, Polishing Robot, ...). Real descriptions
# never use this exact template phrasing.
_MARKETPLACE_TEMPLATE_RE = re.compile(
    r"buy low priced|we provide good quality|wholesale price|"
    r"factory\s*,?\s*we (provide|offer)|OEM\s*/?\s*ODM\s+service|"
    # EVS TECH: "EVST supplies {category} ... that are {adjectives}!"
    # repeated across 19 generic robot-TYPE category pages (Welding Robot,
    # Painting Robot, ...) — a different wholesale-listing template than the
    # "buy low priced" one already caught, same underlying genre. Window is
    # wide (120 chars) since the category noun phrase between the verb and
    # "that are" can be long ("4-axis SCARA robot arms and 4-axis dispensing
    # robots that are ideal for...").
    r"\bsupplies?\b.{0,120}\bthat (are|have|offer|deliver)\b|for sale that (are|have|offer)\b",
    re.I,
)
# Encoding-corruption tell (Ã/Â mojibake from a mis-decoded page) surviving
# in a NAME specifically — Foxtech's "FOXTECH â\x80\x93 UAV TECHNOLOGY
# EXPERTS" tagline. fetch() already re-decodes via apparent_encoding but
# some sites' declared charset lies; catching the residue in names is cheap
# insurance (descriptions get truncated/garbled too but names are the
# user-facing field most worth protecting).
_MOJIBAKE_RE = re.compile(r"[ÃÂ][\x80-\xbf]|â\x80|\sâ\s|\sÂ\s")
# Marketing-imperative / capability-page voice. Recurring pattern across many
# B2B industrial sites (Badger Technologies, Basler, Big Joe Forklifts,
# Aurotek — QA 2026-07-30): real, non-duplicated, substantive prose that
# describes a CAPABILITY or FEATURE of one underlying product/platform
# ("Let the Badger robot...", "Explore our range of...", "Achieve efficient
# management...", "Transform your operations...") rather than naming a
# specific, purchasable product. Genuine product descriptions are almost
# always third-person declarative about a named thing ("SwarmStrike is a
# cruise-class...", "AGILOX ONE combines..."); marketing copy opens with a
# second-person imperative CTA verb.
_MARKETING_VOICE_RE = re.compile(
    r"^(explore|discover|transform|achieve|enhance|conquer|manage|"
    r"let (the|your)|better manage|revolutioniz|scan and|with an hourly|"
    r"efficiently manage|get high-speed|an overview of)\b",
    re.I,
)
# "X offers/provides/distributes a wide range of Y" — a category-catalog
# sentence, not a description of one specific product (Aurotek: "Sensors",
# "Universal Joints", "Service Robots" all open this way).
_CATEGORY_DESC_RE = re.compile(r"\ba (wide )?range of\b|\bcovering (applications|a variety)\b", re.I)
# Business-vertical / "who we serve" nav pages where two+ vertical nouns are
# joined by and/& (Delair's "SECURITY AND DEFENSE", "LINEAR & INFRASTRUCTURES")
# — the single-word exact-match _GENERIC_VERTICAL_RE above doesn't catch
# compound phrases. Token-based: every significant word must itself be a
# vertical/business term.
_VERTICAL_TOKEN_SET = frozenset({
    "security", "defense", "defence", "linear", "infrastructures", "infrastructure",
    "geospatial", "solutions", "solution", "business", "industrial", "industry",
    "healthcare", "logistics", "energy", "utilities", "mining", "agriculture",
    "construction", "automotive", "aerospace", "maritime", "government", "public",
    "commercial", "residential", "oil", "gas", "chemicals", "pharma", "food",
    "retail", "manufacturing",
})
_STOPWORDS_FOR_VERTICAL = frozenset({"and", "&", "of", "the", "for"})
# Research institutes/university centers publish org-chart "research cluster"
# pages (DFKI's "Multi-Robot Systems", "Field Robotics"), not commercial
# products — the whole company should be skipped, not filtered lead-by-lead.
_RESEARCH_INSTITUTE_COMPANY_RE = re.compile(
    r"\b(research (center|centre|institute|(and|&)\s*development\s*organi[sz]ation)|"
    r"forschungszentrum|fraunhofer|"
    r"max[\s-]planck|dfki|national laboratory|\bcnrs\b|\bdrdo\b)\b",
    re.I,
)


def _is_compound_vertical_name(name: str) -> bool:
    tokens = re.split(r"[^a-zA-Z]+", name.lower())
    tokens = [t for t in tokens if t]
    if len(tokens) < 2:
        return False
    meaningful = [t for t in tokens if t not in _STOPWORDS_FOR_VERTICAL]
    if not meaningful:
        return False
    return all(t in _VERTICAL_TOKEN_SET for t in meaningful)


def _fetch_company_pages(robots: list[dict[str, Any]], sess: requests.Session) -> dict[str, tuple[str, str, str]]:
    """Fetch every robot's URL once, return {url: (desc, img, title)}."""
    cache: dict[str, tuple[str, str, str]] = {}
    for r in robots:
        url = r.get("url") or ""
        if not url or url in cache:
            continue
        html = fetch(url, sess)
        desc = (og(html, "description") or meta_description(html)) if html else ""
        img = og(html, "image") if html else ""
        title = (og(html, "title") or page_title(html)) if html else ""
        cache[url] = (desc, img, title)
        time.sleep(0.15)
    return cache


def is_probable_product_name(name: str, company_name: str = "") -> bool:
    """Defence-in-depth filter for the batch run: reject blog/solution/nav-page
    anchors that survived discovery-time mining. Permissive by design — many
    real product names are short (ONE, eligo) so this only rejects strong
    negative signals, not anything merely unfamiliar.

    A name prefixed by the company's own brand (Movu ifollow, AGILOX ONE,
    Navimow X420, AmbiSort A-Series) is a strong positive signal — but NOT an
    unconditional bypass: "Badger in the Store" (Badger Technologies) also
    starts with the brand name and is pure marketing copy, so brand-prefix is
    just one more input to the same strong-signal gate, checked after (not
    instead of) the negative filters below.
    """
    n = name.strip()
    if not n:
        return False
    if _MOJIBAKE_RE.search(n):
        return False
    if _YEAR_RE.search(n):
        return False  # "Guide: Automated machine tending in 2026" etc.
    if _FUNDING_RE.search(n):
        return False  # "€10M to Scale Drone-Based Inspection" — press release
    if len(n.split()) >= 6:
        return False  # sentence/article-title shaped
    if _GENERIC_VERTICAL_RE.match(n):
        return False
    if _MARKETING_PHRASE_RE.search(n):
        return False
    if _COMPONENT_ONLY_RE.match(n):
        return False
    if _is_compound_vertical_name(n):
        return False
    if _APPLIANCE_CATEGORY_RE.match(n):
        return False
    return _has_strong_product_signal(n, company_name)


_MIXED_CASE_TOKEN_RE = re.compile(r"[a-z][A-Z]|[A-Z]{2,}[a-z]")  # SwarmOS, QTrobot, iFollow
_SUFFIX_FILLER_WORDS = frozenset({
    "series", "line", "set", "kit", "edition", "version", "type", "model",
    "pro", "plus", "mini", "max", "lite", "system",
})
# Singular domain vocabulary is itself a positive signal ("Gecko (Case
# Robot)", "Dash Robot") — deliberately singular-only: the PLURAL form is
# the exact category-page pattern being excluded elsewhere ("AI Robots",
# "Service Robots", "Logistics Robots" — Aurotek's nav categories, not
# products).
_SINGULAR_ROBOT_WORD_RE = re.compile(
    r"\b(robot|cobot|drone|amr|agv|uav|ugv|uas|rov|auv|exoskeleton)\b(?!s\b)",
    re.I,
)


def _has_strong_product_signal(n: str, company_name: str = "") -> bool:
    """Positive-evidence gate — replaces genre-by-genre negative filtering.

    QA of ~50 bulk-imported companies (2026-07-30) showed the negative-filter
    approach (excluding known-bad phrase patterns) never converges: every
    round found a new nav/vertical/language-selector/marketing genre the
    existing patterns missed (Aurotek's "Smart Logistics", Shanghai Huiju's
    literal list of language names, Carnegie's "AUTONOMOUS VEHICLES", French
    "Découvrir"). The one pattern that HELD across every confirmed-good
    record (K10, QuicKART M3, HARPY, SwarmOS, AGILOX ONE, DT46 LiDAR) and
    never appeared in confirmed-bad records: real product names carry a
    digit, a coined/brand-cased token, or a trademark mark. Plain dictionary
    words and phrases — in any language — don't. This trades recall (some
    genuinely plain-named real products get skipped) for precision, which is
    the right tradeoff after this many rounds of cleaning up prod junk.
    """
    co_tokens = re.sub(r"[^a-z0-9]+", " ", company_name.lower()).split()
    first_co_token = co_tokens[0] if co_tokens else ""
    if first_co_token and len(first_co_token) >= 3 and n.lower().startswith(first_co_token):
        return True
    if any(ch.isdigit() for ch in n):
        return True
    if any(sym in n for sym in ("™", "®", "℠")):
        return True
    if _MIXED_CASE_TOKEN_RE.search(n):
        return True
    if _SINGULAR_ROBOT_WORD_RE.search(n):
        return True
    # ALL-CAPS is only a strong signal for a SINGLE coined token (HARPY,
    # HAROP, KRS) — an all-caps PHRASE ("AUTONOMOUS VEHICLES", "SECURITY AND
    # DEFENSE") is a heading/vertical style choice, not a brand name. A
    # second word is tolerated only when it's a generic product-suffix noun
    # (Series/Mini/Set/Kit/...) that carries no meaning of its own — "KRS
    # Series", "B3M Series" are real Kondo Kagaku family names this way.
    words = re.findall(r"[A-Za-z]+", n)
    signal_words = [w for w in words if w.lower() not in _SUFFIX_FILLER_WORDS]
    if len(signal_words) == 1 and len(signal_words[0]) >= 2 and signal_words[0].isupper():
        return True
    return False


_DUP_LEAD_WORD_RE = re.compile(r"^(\S+)\s+\1\b", re.I)


def dedupe_leading_word(name: str) -> str:
    """Fix the "LuckiBot LuckiBot AI Delivery Robot" anchor-text extraction
    artifact (source page repeats the brand name as a visual heading before
    the link text) — safe mechanical cleanup, not content fabrication."""
    m = _DUP_LEAD_WORD_RE.match(name)
    return name[len(m.group(1)) + 1:].strip() if m else name


def norm_key(v: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (v or "").lower())


def og(html: str, prop: str) -> str:
    m = re.search(
        rf'<meta[^>]+(?:property|name)=["\']og:{prop}["\'][^>]+content=["\']([^"\']+)',
        html,
    ) or re.search(
        rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']og:{prop}',
        html,
    )
    return m.group(1).strip() if m else ""


def meta_description(html: str) -> str:
    m = re.search(
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)', html,
    ) or re.search(
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']description', html,
    )
    return m.group(1).strip() if m else ""


def page_title(html: str) -> str:
    m = re.search(r"<title[^>]*>([^<]+)</title>", html, re.I)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


import html as _html_mod  # noqa: E402


def _unescape(text: str) -> str:
    return _html_mod.unescape(text or "")


def fetch(url: str, sess: requests.Session, timeout: int = 12) -> str:
    try:
        r = sess.get(url, headers=UA, timeout=timeout, allow_redirects=True)
        if r.status_code == 200:
            r.encoding = r.apparent_encoding or r.encoding
            return r.text
    except requests.RequestException:
        pass
    return ""


def validate_image(url: str, sess: requests.Session) -> bool:
    if not url or not url.startswith("http"):
        return False
    try:
        r = sess.head(url, headers=UA, timeout=8, allow_redirects=True)
        if r.status_code >= 400 or r.status_code == 405:
            r = sess.get(url, headers=UA, timeout=8, allow_redirects=True, stream=True)
            r.close()
        return r.status_code < 400
    except requests.RequestException:
        return False


def enrich_company_robots(
    raw_robots: list[dict[str, Any]], company: dict[str, Any], sess: requests.Session,
) -> list[dict[str, Any]]:
    """Enrich every surviving robot lead for one company, sharing a page-fetch
    cache and detecting sitewide-boilerplate descriptions across the set.

    Bug found during manual QA 2026-07-30: several sites (Orqa, and others
    presumably) return the SAME og:description for every product URL — a
    JS-rendered SPA whose static HTML is just the homepage shell. Treating
    that repeated text as a per-product description silently mislabeled 9 of
    Orqa's 11 leads with an identical, non-specific company blurb. Any
    description shared by >=2 leads in the same company is therefore treated
    as invalid and discarded (falls back to the honest purpose sentence, or
    drops the lead if that's also empty).
    """
    cleaned_input: list[dict[str, Any]] = []
    for r in raw_robots:
        r = dict(r)
        if r.get("name"):
            r["name"] = dedupe_leading_word(_clean_name(r["name"]))
        cleaned_input.append(r)

    survivors = [
        r for r in cleaned_input
        if (r.get("name") or "").strip()
        and not _JUNK_RE.search(r["name"])
        and not _LANG_RE.match(r["name"])
        and is_probable_product_name(r["name"], company.get("name", ""))
    ]
    if not survivors:
        return []

    page_cache = _fetch_company_pages(survivors, sess)
    desc_counts: dict[str, int] = {}
    title_counts: dict[str, int] = {}
    for desc, _img, title in page_cache.values():
        if desc:
            desc_counts[desc] = desc_counts.get(desc, 0) + 1
        if title:
            title_counts[title] = title_counts.get(title, 0) + 1
    boilerplate_descs = {d for d, n in desc_counts.items() if n >= 2}
    # Same bug, different field: a <title> repeated across leads is the site's
    # homepage/shell title (e.g. Kondo Kagaku's Japanese-script company name
    # duplicated on 5 leads), not a per-product title — worthless as a
    # "meaningful title" signal.
    boilerplate_titles = {t for t, n in title_counts.items() if n >= 2}

    out: list[dict[str, Any]] = []
    for r in survivors:
        enriched = _enrich_one(dict(r), company, page_cache, boilerplate_descs, boilerplate_titles, sess)
        if enriched:
            out.append(enriched)
    return out


def enrich_company_robots_llm_approved(
    raw_robots: list[dict[str, Any]], company: dict[str, Any], sess: requests.Session,
) -> list[dict[str, Any]]:
    """Same pipeline as enrich_company_robots, but for the backlog-recovery
    pass: names were already judged real-vs-junk by batch LLM classification
    (2026-07-31, 16 agents covering all 452 backlog companies), so this skips
    ONLY `is_probable_product_name`'s structural-signal requirement. Every
    other safety net still applies — nav/language junk regex, description-
    required, duplicate-boilerplate/title detection, marketplace-template,
    marketing-voice, category-description, mojibake, CMS-artifact patterns —
    an LLM-approved name with no real page content or templated prose still
    gets dropped.
    """
    cleaned_input: list[dict[str, Any]] = []
    for r in raw_robots:
        r = dict(r)
        if r.get("name"):
            r["name"] = dedupe_leading_word(_clean_name(r["name"]))
        cleaned_input.append(r)

    survivors = [
        r for r in cleaned_input
        if (r.get("name") or "").strip()
        and not _JUNK_RE.search(r["name"])
        and not _LANG_RE.match(r["name"])
        and not _MOJIBAKE_RE.search(r["name"])
    ]
    if not survivors:
        return []

    page_cache = _fetch_company_pages(survivors, sess)
    desc_counts: dict[str, int] = {}
    title_counts: dict[str, int] = {}
    for desc, _img, title in page_cache.values():
        if desc:
            desc_counts[desc] = desc_counts.get(desc, 0) + 1
        if title:
            title_counts[title] = title_counts.get(title, 0) + 1
    boilerplate_descs = {d for d, n in desc_counts.items() if n >= 2}
    boilerplate_titles = {t for t, n in title_counts.items() if n >= 2}

    out: list[dict[str, Any]] = []
    for r in survivors:
        enriched = _enrich_one(dict(r), company, page_cache, boilerplate_descs, boilerplate_titles, sess)
        if enriched:
            out.append(enriched)
    return out


def _enrich_one(
    r: dict[str, Any],
    company: dict[str, Any],
    page_cache: dict[str, tuple[str, str, str]],
    boilerplate_descs: set[str],
    boilerplate_titles: set[str],
    sess: requests.Session,
) -> dict[str, Any] | None:
    url = r.get("url") or ""
    domain = re.match(r"https?://([^/]+)", url)
    host = domain.group(1).replace("www.", "") if domain else ""

    desc, img, title = page_cache.get(url, ("", "", ""))
    if desc in boilerplate_descs:
        desc = ""
    if title in boilerplate_titles:
        title = ""

    # Require a REAL, non-boilerplate description to auto-import. QA of the
    # first 14 bulk-imported companies (2026-07-30) showed every genuinely
    # bad record — Wingcopter's 13 press-release/investment-news leads,
    # Wonder Workshop's "Hour of Robotics" event page, a mangled-encoding
    # ZALA Aero entry — was a "title-only" fallback (no real page
    # description). Every record backed by a real scraped description was
    # good. The title-derived purpose sentence was too weak a signal on
    # arbitrary, unpredictable page titles (blog posts, press articles, CMS
    # category listings all produce *some* title) to keep using it.
    if not desc or len(desc) < 20:
        return None
    if _MARKETPLACE_TEMPLATE_RE.search(desc):
        return None
    if _MARKETING_VOICE_RE.match(desc.strip()):
        return None
    if _CATEGORY_DESC_RE.search(desc):
        return None
    r["description"] = _unescape(desc)[:600]

    if img and validate_image(img, sess):
        r["images"] = [{
            "url": img,
            "source_page_url": url,
            "source_tier": "manufacturer",
            "source_publisher": company.get("name", ""),
            "source_domain": host,
            "media_class": "official_render",
            "image_scope": "exact_variant",
            "confidence_score": 72,
            "match_reason": "og:image on official product page",
            "rights_status": "official_source",
        }]
    r["manufacturer_country_code"] = r.get("manufacturer_country_code") or company.get("country_code") or ""
    r["sources"] = [{"url": url, "type": "website", "title": f"{company.get('name', '')} official product page"}]
    r["research_notes"] = (
        (r.get("research_notes") or "")
        + " Light-enriched at bulk-import time from the official product page (og metadata); full enrichment pending."
    ).strip()
    if r.get("product_url_scope") not in (
        "exact_variant", "family", "category", "document", "third_party", "unknown",
    ):
        r["product_url_scope"] = "exact_variant"
    return r


def already_in_prod(name: str, client: ResearchApiClient, prod_name_cache: set[str]) -> bool:
    key = norm_key(name)
    if key in prod_name_cache:
        return True
    for hit in client.search_companies(name, page_size=5):
        if norm_key(hit.get("name", "")) == key:
            prod_name_cache.add(key)
            return True
    return False


def main() -> None:
    d = json.loads(STAGED_FILE.read_text(encoding="utf-8"))
    companies = {c["slug"]: c for c in d["companies"]}
    robots_by_slug: dict[str, list[dict[str, Any]]] = {}
    for r in d["robots"]:
        robots_by_slug.setdefault(r["company_slug"], []).append(r)

    ledger = d.setdefault("import_ledger", {"note": "", "imported": []})
    ledger.setdefault("imported", [])
    ledger.setdefault("skipped", [])
    done_slugs = {e["slug"] for e in ledger["imported"]}
    skipped_slugs = {e["slug"] for e in ledger.get("skipped", [])}

    todo = [s for s in robots_by_slug if s not in done_slugs and s not in skipped_slugs]
    print(f"=== Bulk import: {len(todo)} companies queued ===", flush=True)

    client = ResearchApiClient()
    sess = requests.Session()
    prod_name_cache: set[str] = set()

    n_created_co = 0
    n_created_robots = 0
    n_skipped = 0
    n_errors = 0

    for i, slug in enumerate(todo, 1):
        company = companies.get(slug)
        if not company:
            continue
        try:
            if _RESEARCH_INSTITUTE_COMPANY_RE.search(company["name"]):
                ledger["skipped"].append({"slug": slug, "reason": "research_institute_not_manufacturer"})
                n_skipped += 1
                print(f"[{i}/{len(todo)}] {company['name']}: SKIP (research institute)", flush=True)
                continue
            if already_in_prod(company["name"], client, prod_name_cache):
                ledger["skipped"].append({"slug": slug, "reason": "name_now_in_prod"})
                n_skipped += 1
                print(f"[{i}/{len(todo)}] {company['name']}: SKIP (now in prod)", flush=True)
                continue

            raw_robots = robots_by_slug[slug]
            enriched = enrich_company_robots(raw_robots, company, sess)

            if not enriched:
                ledger["skipped"].append({"slug": slug, "reason": "no_valid_robots_after_filter"})
                n_skipped += 1
                print(f"[{i}/{len(todo)}] {company['name']}: SKIP (0 valid robots)", flush=True)
                continue

            co_dir = ROBOTS_DIR / slug
            co_dir.mkdir(parents=True, exist_ok=True)
            for old in co_dir.glob("*.json"):
                old.unlink()
            used_names: set[str] = set()
            for r in enriched:
                base = re.sub(r"[^a-z0-9]+", "-", r["name"].lower()).strip("-")[:60] or "robot"
                fn = base
                n = 2
                while fn in used_names:
                    fn = f"{base}-{n}"
                    n += 1
                used_names.add(fn)
                (co_dir / f"{fn}.json").write_text(
                    json.dumps(r, indent=2, ensure_ascii=False), encoding="utf-8"
                )

            dry = import_staging(co_dir, dry_run=True)
            if not dry.get("ok"):
                ledger["skipped"].append({
                    "slug": slug, "reason": "dry_run_failed",
                    "errors": dry.get("errors", [])[:5],
                })
                n_skipped += 1
                print(f"[{i}/{len(todo)}] {company['name']}: SKIP (dry-run failed: "
                      f"{dry.get('errors', ['?'])[0][:100]})", flush=True)
                continue

            result = import_staging(co_dir, dry_run=False)
            created_ids = [r["id"] for r in result.get("results", []) if r.get("action") == "created"]
            errored = [r for r in result.get("results", []) if r.get("action") == "error"]

            if created_ids:
                n_created_co += 1
                n_created_robots += len(created_ids)
                ledger["imported"].append({
                    "slug": slug,
                    "prod_company_name": company["name"],
                    "robots": len(created_ids),
                    "robot_ids": created_ids,
                    "date": "2026-07-30",
                    "mode": "bulk_autonomous",
                })
                print(f"[{i}/{len(todo)}] {company['name']}: created {len(created_ids)} robots "
                      f"({', '.join(str(x) for x in created_ids)})"
                      + (f"; {len(errored)} errored" if errored else ""), flush=True)
            else:
                n_errors += 1
                ledger["skipped"].append({
                    "slug": slug, "reason": "apply_created_nothing",
                    "errors": [e.get("error", "") for e in errored][:5],
                })
                print(f"[{i}/{len(todo)}] {company['name']}: ERROR — created 0 "
                      f"({errored[0].get('error', '?')[:120] if errored else 'unknown'})", flush=True)

        except Exception as exc:  # noqa: BLE001 — one bad company must not kill the batch
            n_errors += 1
            ledger["skipped"].append({"slug": slug, "reason": "exception", "error": str(exc)[:200]})
            print(f"[{i}/{len(todo)}] {slug}: EXCEPTION {str(exc)[:150]}", flush=True)

        if i % 10 == 0 or i == len(todo):
            STAGED_FILE.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"--- checkpoint {i}/{len(todo)}: {n_created_co} companies / "
                  f"{n_created_robots} robots created, {n_skipped} skipped, "
                  f"{n_errors} errors ---", flush=True)

    STAGED_FILE.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"=== DONE: {n_created_co} companies / {n_created_robots} robots created, "
          f"{n_skipped} skipped, {n_errors} errors ===", flush=True)


if __name__ == "__main__":
    main()
