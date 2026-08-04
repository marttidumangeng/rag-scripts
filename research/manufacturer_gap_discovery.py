"""Manufacturer & Robot Gap Discovery workflow.

A broad, multi-source discovery workflow (complementary to
competitor_gap_discover.py) whose goal is to find as many robot
MANUFACTURERS and their ROBOTS as possible that are NOT yet present in the
RobotAIGeek prod database, and stage them in review-ready JSON files that
match the StagedCompany / StagedRobot schemas used by the bulk-import
pipeline.

Pipeline stages:

  Stage A — Baseline
    Load staging/reports/prod_baseline.json (produced by
    dump_prod_baseline.py). Contains normalized name indexes for every
    company and robot currently in prod.

  Stage B — Multi-source manufacturer harvesting
    Scrape public robot directories and encyclopedic indexes:
      1. Robolist.ai        (sitemap + categories)   [reused conventions]
      2. Aparobot.com       (humanoid directory)
      3. Wikipedia          (robotics company category + list pages)
      4. IFR / trade lists  (optional seeds file)
      5. Manual seeds       (seeds/gap_discovery_seeds.txt, one name per line,
                             optional "Name | website | country | category")

  Stage C — Dedupe vs prod
    Fuzzy-match harvested names against the baseline company index using
    the same alias rules as competitor_gap_discover (suffix stripping).
    Only companies NOT in prod survive.

  Stage D — Robot catalog discovery (per new company)
    For each new manufacturer with a resolvable website, fetch the site and
    extract product/robot candidate pages (name + URL) using keyword link
    mining. Robots are deduped against the prod robot index too (covers the
    case where the robot exists under a different company record).

  Stage E — Staging output
    Writes a single review-ready staging file:
      staging/gap_discovery/staged_import.json
        { "companies": [StagedCompany...], "robots": [StagedRobot...] }
    plus per-company robot JSON under staging/gap_discovery/robots/{slug}/
    and a human-readable summary report.

Nothing is imported automatically. Review the staged JSON, then import via:
  python cli.py import --dir staging/gap_discovery/robots/{slug}/ --dry-run

Usage:
  python manufacturer_gap_discovery.py                        # full run
  python manufacturer_gap_discovery.py --harvest-only         # stages A-C
  python manufacturer_gap_discovery.py --max-companies 40     # cap stage D
  python manufacturer_gap_discovery.py --source wikipedia     # single source
  python manufacturer_gap_discovery.py --resume               # skip harvested
  python manufacturer_gap_discovery.py --local
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree as ET

import requests
from bs4 import BeautifulSoup

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env  # noqa: E402

load_research_env(local="--local" in sys.argv)

from company_country_resolve import resolve_company_country  # noqa: E402
from company_website_resolve import (  # noqa: E402
    domain_matches_company,
    is_skippable_domain,
    resolve_company_website,
    validate_website,
)
from robot_categories import categories_from_discovery_hints, derive_category_slugs  # noqa: E402
from schema import (  # noqa: E402
    SourceRef,
    StagedCompany,
    StagedRobot,
    normalize_image_candidates,
)

# ── Paths ────────────────────────────────────────────────────────────────────

BASELINE = _HERE / "staging" / "reports" / "prod_baseline.json"
OUT_DIR = _HERE / "staging" / "gap_discovery"
HARVEST_FILE = OUT_DIR / "harvested_manufacturers.json"
STAGED_FILE = OUT_DIR / "staged_import.json"
ROBOTS_DIR = OUT_DIR / "robots"
SUMMARY_FILE = OUT_DIR / "gap_discovery_summary.md"
LOCAL_SOURCES_HARVEST = OUT_DIR / "local_sources_harvest.json"
SEEDS_FILE = _HERE / "seeds" / "gap_discovery_seeds.txt"


def set_round(round_no: int) -> None:
    """Switch module-level output paths for a numbered discovery round.

    Round 2+ writes staged_import_{n}.json / robots_{n}/ / etc. and treats
    ALL earlier rounds' staged files as part of the dedupe baseline.
    """
    global HARVEST_FILE, STAGED_FILE, ROBOTS_DIR, SUMMARY_FILE, LOCAL_SOURCES_HARVEST
    if round_no <= 1:
        return
    HARVEST_FILE = OUT_DIR / f"harvested_manufacturers_{round_no}.json"
    STAGED_FILE = OUT_DIR / f"staged_import_{round_no}.json"
    ROBOTS_DIR = OUT_DIR / f"robots_{round_no}"
    SUMMARY_FILE = OUT_DIR / f"gap_discovery_summary_{round_no}.md"
    LOCAL_SOURCES_HARVEST = OUT_DIR / f"local_sources_{round_no}_harvest.json"


def prior_round_staged_files(round_no: int) -> list[Path]:
    """Staged files from all earlier rounds (round 1 has no suffix)."""
    files = []
    for n in range(1, round_no):
        p = OUT_DIR / ("staged_import.json" if n == 1 else f"staged_import_{n}.json")
        if p.exists():
            files.append(p)
    return files

ROBOLIST_BASE = "https://robolist.ai"
APAROBOT_BASE = "https://aparobot.com"

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

ROBOLIST_CATEGORIES = [
    "agricultural", "agv", "amr-warehouse", "autonomous-vehicle", "cleaning",
    "cobot", "delivery", "education", "exoskeleton", "hospitality-service",
    "humanoid", "industrial-arm", "mobile-manipulator", "quadruped",
    "research", "surgical-medical",
]

WIKI_API = "https://en.wikipedia.org/w/api.php"
WIKI_CATEGORIES = [
    "Category:Robotics companies",
    "Category:Robotics companies by country",
    "Category:Industrial robots",
    "Category:Service robots",
    "Category:Humanoid robots",
    "Category:Unmanned aerial vehicle manufacturers",
    "Category:Medical robotics",
]

# Wikipedia page titles that are lists, not companies
_WIKI_SKIP_RE = re.compile(
    r"^(list of|category:|template:|portal:|draft:|robotics industry|"
    r"timeline of|outline of|history of)", re.I,
)

# Harvested names that are clearly not manufacturers (countries, universities,
# research institutes, generic words) — hard-skip during merge. The university
# stems cover non-English spellings too (Universität, Université, Universidad,
# Universidade, Universiteit, Università — QA found several staged as makers).
_NON_MANUFACTURER_RE = re.compile(
    r"^(india|japan|china|germany|france|italy|russia|korea|south korea|"
    r"united states|usa|uk|united kingdom|canada|australia|brazil|spain|"
    r"vietnam|europe|asia|africa|robot|robots|robotics|unknown|various manufacturers?|"
    r"other|misc|miscellaneous|company|companies|manufacturer|manufacturers)$"
    r"|^(universit|universidad|institute|instituto|laborator|academy|college|"
    r"school|hochschule|polytechni|politecnico)\w*\b"
    r"|\b(universit\w+|universidad\w*|institute of technology)\b", re.I,
)

# Wikipedia harvests robot MODEL pages out of the robotics categories; some
# aren't in the prod robot index yet, so they slip past the robot-name dedupe
# and get staged as "manufacturers" (QA: FEDOR, MABEL, Murata Boy and Murata
# Girl, ZEUS robotic surgical system, Honda P series). Title-shape heuristics,
# applied to wikipedia-sourced names only.
_WIKI_ROBOT_TITLE_RE = re.compile(
    r"\b(robotic surgical system|surgical robot|humanoid robot|robot dog|"
    r"robotic arm)\b"
    r"|\bseries\s*$"          # 'Honda P series', 'Aibo ERS series'
    r"|\b(boy|girl)\b", re.I, # 'Murata Boy and Murata Girl'
)


def _looks_like_wiki_robot_title(name: str) -> bool:
    nm = (name or "").strip()
    if _WIKI_ROBOT_TITLE_RE.search(nm):
        return True
    # Short all-caps single words (FEDOR, MABEL, ZEUS) are robot names, not
    # companies. Real all-caps makers of this shape (KUKA, ABB, AUBO) are
    # already in prod and would be deduped anyway.
    if re.fullmatch(r"[A-Z]{2,6}", nm):
        return True
    return False


def is_junk_company_name(name: str, source: str = "") -> bool:
    """Hard-skip filter for harvested company names.

    Catches ISO country codes staged as companies (At/Au/Be/Ca/Cn/Fr/Jp...),
    other <=3-char fragments (cog, fbr, vex), non-manufacturer entities, and
    Wikipedia robot-page titles. Manual seeds are curated and exempt from the
    length rule.
    """
    nm = (name or "").strip()
    if not nm:
        return True
    if len(nm) <= 3 and source != "manual_seed":
        return True
    if _NON_MANUFACTURER_RE.search(nm):
        return True
    if source == "wikipedia" and _looks_like_wiki_robot_title(nm):
        return True
    return False

PRODUCT_LINK_KEYWORDS = (
    "product", "robot", "cobot", "arm", "amr", "agv", "humanoid", "quadruped",
    "drone", "uav", "uuv", "auv", "exoskeleton", "vehicle", "platform",
    "surgical", "gripper", "manipulator", "mobile", "delivery", "cleaning",
    "solution", "series", "model",
)

NAV_JUNK_RE = re.compile(
    r"^(home|about|about us|contact|contact us|news|blog|careers|support|"
    r"login|sign ?in|sign ?up|privacy|terms|faq|search|menu|products?|"
    r"solutions?|services?|company|resources?|downloads?|partners?|"
    r"investors?|events?|videos?|learn more|read more|view all|see all|"
    r"overview|applications?|industries)$", re.I,
)

# Exact-match nav lexicon (casefolded) — anchors QA kept finding staged as
# robots: "More"/"MORE+", "Quick view", "Option", "Close", "New Products"...
_NAV_LEXICON: frozenset[str] = frozenset(map(str.casefold, (
    "more", "more+", "...more", "view more", "see more", "show more",
    "discover more", "find out more", "quick view", "quickview", "option",
    "options", "close", "open", "new products", "new product", "documentation",
    "link", "links", "details", "detail", "view details", "download",
    "downloads", "download center", "back", "next", "previous", "prev",
    "newsletter", "compare", "cookie", "cookies", "get a quote",
    "request a demo", "request a quote", "watch video", "watch case study",
    "shop", "shop all", "shop now", "buy now", "add to cart",
)))

# Language-switcher anchors (endonyms + English language names) — nav noise
# from i18n pickers, never product names (QA: français, Türkçe, Latviešu,
# Oʻzbekcha, Deutsch, español, Portuguese, Vietnamese...).
_LANGUAGE_ANCHORS: frozenset[str] = frozenset(map(str.casefold, (
    "english", "deutsch", "français", "francais", "español", "espanol",
    "português", "portugues", "italiano", "türkçe", "turkce", "nederlands",
    "polski", "čeština", "cestina", "slovenčina", "slovenščina", "svenska",
    "norsk", "suomi", "dansk", "íslenska", "magyar", "română", "romana",
    "ελληνικά", "русский", "українська", "беларуская", "български", "srpski",
    "hrvatski", "bosanski", "shqip", "македонски", "latviešu", "lietuvių",
    "eesti", "oʻzbekcha", "o'zbekcha", "ozbekcha", "қазақша", "кыргызча",
    "azərbaycanca", "türkmençe", "тоҷикӣ", "hayeren", "ქართული",
    "bahasa indonesia", "bahasa melayu", "tiếng việt", "filipino", "tagalog",
    "ไทย", "中文", "简体中文", "繁體中文", "日本語", "한국어", "العربية", "فارسی",
    "עברית", "हिन्दी", "বাংলা", "اردو", "kiswahili",
    # English names of languages (some switchers use them)
    "german", "french", "spanish", "portuguese", "italian", "turkish",
    "russian", "ukrainian", "polish", "czech", "dutch", "swedish", "norwegian",
    "finnish", "danish", "greek", "hungarian", "romanian", "bulgarian",
    "vietnamese", "thai", "indonesian", "malay", "japanese", "korean",
    "chinese", "arabic", "hebrew", "hindi", "latvian", "lithuanian",
    "estonian", "uzbek", "kazakh",
)))

# Anchors that are just numbers / measurement ranges (pagination "2", payload
# filters "1-7kg", ">1000kg") — never robot names.
_NUMERIC_ANCHOR_RE = re.compile(
    r"^[\s\d\-–—+.,<>~]*(kg|t|mm|cm|m|lbs?)?\s*$", re.I,
)


# ── Mojibake repair ──────────────────────────────────────────────────────────
# UTF-8 (or GBK) pages served without a charset header get decoded as
# latin-1/cp1252, yielding "franÃ§ais" / "TCHÎèÌ¨µ¹¹Ò..." junk. Detect the
# signature and re-decode instead of dropping the lead.

# Ã/Â followed by a Latin-1-supplement or cp1252-punctuation char, or a long
# run of high-latin chars (CJK bytes misdecoded as latin-1).
_CP1252_TAILS = (
    "€‚ƒ„…†‡ˆ‰Š‹"
    "ŒŽ‘’“”•–—˜™"
    "š›œžŸ"
)
_MOJIBAKE_HINT_RE = re.compile(
    r"[ÂÃ][-ÿ%s]|[-ÿ]{4,}" % re.escape(_CP1252_TAILS)
)


def _mojibake_score(text: str) -> int:
    """Density of Latin-1-supplement chars — mojibake text is full of them."""
    return sum(1 for ch in text if 0x80 <= ord(ch) <= 0xFF)


def fix_mojibake(text: str) -> str:
    """Repair charset mojibake by round-tripping through the original bytes.

    'franÃ§ais' -> 'français'; GBK-as-latin-1 gibberish -> CJK. Returns the
    input unchanged when no repair improves it (accented text like 'Kärcher'
    is left alone).
    """
    if not text or not _MOJIBAKE_HINT_RE.search(text):
        return text
    original_score = _mojibake_score(text)
    # UTF-8 always wins when it round-trips ('français'); GBK is only a
    # fallback for CJK bytes (which are never valid UTF-8 sequences).
    for dec in ("utf-8", "gbk"):
        for enc in ("cp1252", "latin-1"):
            try:
                fixed = text.encode(enc).decode(dec)
            except (UnicodeEncodeError, UnicodeDecodeError, LookupError):
                continue
            if _mojibake_score(fixed) < original_score:
                return fixed
    return text


# ── Utilities ────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def norm_name(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.casefold()
    text = text.replace("&", " and ")
    text = re.sub(r"[®™©]", "", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def norm_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


_ALIAS_SUFFIXES = (
    " robotics", " robot", " robots", " automation", " intelligent",
    " intelligence", " technology", " technologies", " tech", " systems",
    " system", " corporation", " corp", " company", " co ltd", " co",
    " ltd", " limited", " inc", " llc", " gmbh", " ag", " ab", " as",
    " bv", " srl", " spa", " sa", " se", " plc", " kk", " oy", " group",
    " holdings", " holding", " international", " industries", " industrial",
    " heavy industries", " motor", " motors", " division", " and", " ai",
    " labs", " lab", " electric", " electronics",
)


def company_aliases(name: str) -> set[str]:
    """Progressively strip corporate/domain suffixes, keeping every stage.

    'yamaha motor co ltd robotics division' -> {'yamaha motor co ltd robotics
    division', ..., 'yamaha'}
    """
    n = norm_name(name)
    aliases = {n}
    current = n
    for _ in range(8):  # iterate until stable (bounded)
        stripped = None
        for suffix in _ALIAS_SUFFIXES:
            if current.endswith(suffix) and len(current) > len(suffix) + 2:
                stripped = current[: -len(suffix)].strip()
                break
        if not stripped or stripped == current:
            break
        current = stripped
        aliases.add(current)
    return {a for a in aliases if len(a) >= 3}


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return s[:60] or "company"


def _decode_response(r: Any) -> str:
    """Response text, re-decoded with the apparent encoding when the header
    charset produced mojibake (UTF-8/GBK pages served without a charset get
    latin-1-decoded by requests, yielding 'franÃ§ais'-style junk)."""
    text = r.text
    if not _MOJIBAKE_HINT_RE.search(text):
        return text
    enc = getattr(r, "apparent_encoding", None)
    if enc:
        try:
            fixed = r.content.decode(enc, errors="replace")
        except (LookupError, UnicodeDecodeError):
            return text
        if _mojibake_score(fixed[:20_000]) < _mojibake_score(text[:20_000]):
            return fixed
    return text


# Visible-text floor below which a 200 is almost certainly an unrendered app
# shell rather than a real page. Mirrors web_extract._JS_SHELL_TEXT_CHARS.
_JS_SHELL_TEXT_CHARS = 5000
_ESCALATION_FETCHER = None

# Link-mining caps. Previously hard-coded 60 mined / 60 audited / 40 kept, which
# truncates a real manufacturer catalogue before it is ever looked at — the same
# class of defect as the nightly's max_per_page=4 discarding catalogue pages
# outright. A genuine catalogue runs 10-60 models (HD Hyundai's industrial line
# alone is 46), so the old ceiling cut mid-catalogue. Env-tunable for a cheap
# smoke run without a code change.
_MINE_LIMIT = int(os.environ.get("GAP_DISCOVERY_MINE_LIMIT", "150") or 150)
_AUDIT_LIMIT = int(os.environ.get("GAP_DISCOVERY_AUDIT_LIMIT", "150") or 150)
_KEEP_LIMIT = int(os.environ.get("GAP_DISCOVERY_KEEP_LIMIT", "100") or 100)


def _visible_text_len(html: str) -> int:
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html or "", flags=re.S | re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    return len(re.sub(r"\s+", " ", t).strip())


def _escalating_fetcher():
    """Lazy shared WebFetcher: curl-impersonation then Playwright render.

    Reused rather than reimplemented — WebFetcher already owns the stealth and
    render tiers, and serialises render calls on _PLAYWRIGHT_LOCK.
    """
    global _ESCALATION_FETCHER
    if _ESCALATION_FETCHER is None:
        from web_extract import WebFetcher
        _ESCALATION_FETCHER = WebFetcher(stealth=True)
    return _ESCALATION_FETCHER


def fetch_html(url: str, sess: requests.Session, retries: int = 2) -> str:
    """Fetch a page, escalating past WAF blocks and JS shells.

    This workflow previously used plain `requests` only, with no render tier at
    all. That is the same blindness that made link mining return 23 mostly-junk
    records for HD Hyundai (two controllers, three copies of a page heading)
    where the site's own catalogue held 69 real robots: the listing is
    axios-rendered and the CDN 403s non-browser agents, so a plain client sees
    a placeholder and moves on. Sampling four unconfigured OEM sites, two
    returned 403 and two returned ~6-7k-character shells — i.e. roughly half of
    real manufacturer sites are unreadable without escalation.

    Escalation is opt-out via GAP_DISCOVERY_ESCALATE=0 (it costs a browser
    launch per rescued page, so a smoke run may want it off).
    """
    escalate = os.environ.get("GAP_DISCOVERY_ESCALATE", "1").lower() not in ("0", "false", "no")
    for attempt in range(retries + 1):
        try:
            r = sess.get(url, headers=UA, timeout=30, allow_redirects=True)
            if r.status_code == 200:
                html = _decode_response(r)
                # A 200 carrying no visible text is not a success for mining.
                if not escalate or _visible_text_len(html) >= _JS_SHELL_TEXT_CHARS:
                    return html
                break
            if r.status_code in (403, 429, 503):
                if attempt < retries:
                    time.sleep(3 * (attempt + 1))
                    continue
                break          # blocked after retries -> escalate below
            return ""
        except requests.RequestException:
            if attempt < retries:
                time.sleep(2)

    if not escalate:
        return ""
    try:
        return _escalating_fetcher().get(url) or ""
    except Exception:
        return ""


# ── Stage A: baseline ────────────────────────────────────────────────────────

def _baseline_name_variants(name: str) -> set[str]:
    """All useful variants of a prod company name for matching.

    Handles prod naming patterns like:
      'SIASUN Robot & Automation Co., Ltd.'
      'Epson (Seiko Epson Corporation)'
      'Yamaha Motor Co., Ltd. (Robotics Division)'
      'iRobot (part of Amazon Robotics)'
    """
    variants: set[str] = set()
    raw = (name or "").strip()
    if not raw:
        return variants
    candidates = {raw}
    # Text outside parentheses
    no_paren = re.sub(r"\s*\([^)]*\)\s*", " ", raw).strip()
    if no_paren:
        candidates.add(no_paren)
    # Text inside parentheses (e.g. 'Seiko Epson Corporation')
    for inner in re.findall(r"\(([^)]+)\)", raw):
        inner = re.sub(r"^(part of|formerly|now|a division of)\s+", "", inner, flags=re.I).strip()
        if len(inner) > 2:
            candidates.add(inner)
    for cand in candidates:
        for alias in company_aliases(cand):
            variants.add(norm_key(alias))
        variants.add(norm_key(cand))
    return {v for v in variants if v}


def load_baseline() -> dict[str, Any]:
    if not BASELINE.exists():
        raise SystemExit(
            f"Baseline missing: {BASELINE}\nRun: python dump_prod_baseline.py first."
        )
    data = json.loads(BASELINE.read_text(encoding="utf-8"))
    company_index: set[str] = set()
    for raw in data.get("company_name_index", []):
        company_index.add(raw)
    # Also index name variants (paren-stripped, division-stripped, aliases)
    for c in data.get("companies", []):
        company_index.update(_baseline_name_variants(c.get("name") or ""))
        if c.get("slug"):
            company_index.add(norm_key(c["slug"]))

    robot_index: set[str] = set(data.get("robot_name_index", []))
    robot_global: set[str] = {k.split("::", 1)[-1] for k in robot_index}
    website_index: set[str] = set()
    for c in data.get("companies", []):
        w = (c.get("website") or "").strip().lower()
        if w:
            host = urlparse(w if "://" in w else f"https://{w}").netloc
            host = host.replace("www.", "")
            if host:
                website_index.add(host)
    return {
        "raw": data,
        "company_index": company_index,
        "robot_index": robot_index,
        "robot_global": robot_global,
        "website_index": website_index,
    }


# Harvested names whose robotics arm already exists in prod under a different
# brand (harvested name -> prod brand), including known robot BRAND names that
# are not the maker's corporate name (Motoman is Yaskawa's robot brand).
# Extend as reviewers find more.
_KNOWN_PROD_EQUIVALENTS = {
    "kawasaki heavy industries": "kawasaki robotics",
    "omron adept": "omron robotics",
    "yamaha robotics": "yamaha motor",
    "epson robots": "epson",
    "mitsubishi": "mitsubishi electric",
    "motoman": "yaskawa electric",
    "motoman robotics": "yaskawa electric",
    "yaskawa motoman": "yaskawa electric",
    "yaskawa": "yaskawa electric",
}


def company_in_db(name: str, website: str, baseline: dict[str, Any]) -> bool:
    equiv = _KNOWN_PROD_EQUIVALENTS.get(norm_name(name))
    if equiv and any(
        norm_key(v) in baseline["company_index"]
        for v in ([equiv] + list(company_aliases(equiv)))
    ):
        return True
    for variant in _baseline_name_variants(name):
        if variant in baseline["company_index"]:
            return True
    if norm_key(name) in baseline["company_index"]:
        return True
    if website:
        host = urlparse(website if "://" in website else f"https://{website}").netloc
        host = host.replace("www.", "").lower()
        if host and host in baseline["website_index"]:
            return True
    return False


# ── Stage B: harvesting sources ──────────────────────────────────────────────

def harvest_robolist(sess: requests.Session) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    print("[robolist] sitemap ...", flush=True)
    xml_text = fetch_html(f"{ROBOLIST_BASE}/sitemap.xml", sess)
    if xml_text:
        xml_text = re.sub(r'\sxmlns="[^"]+"', "", xml_text, count=1)
        try:
            root = ET.fromstring(xml_text)
            for loc in root.findall(".//loc"):
                url = (loc.text or "").strip()
                if "/companies/" in url:
                    slug = urlparse(url).path.rstrip("/").split("/")[-1]
                    if slug and slug != "companies" and slug not in out:
                        out[slug] = {
                            "name": slug.replace("-", " ").title(),
                            "source": "robolist",
                            "source_url": url,
                            "categories": [],
                        }
        except ET.ParseError:
            pass
    print(f"[robolist] sitemap slugs: {len(out)}", flush=True)

    for cat in ROBOLIST_CATEGORIES:
        html = fetch_html(f"{ROBOLIST_BASE}/categories/{cat}", sess)
        if not html:
            continue
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.select('a[href^="/companies/"]'):
            href = (a.get("href") or "").split("?", 1)[0].rstrip("/")
            slug = href.rsplit("/", 1)[-1]
            if not slug or slug == "companies":
                continue
            raw_name = a.get_text(" ", strip=True)
            name = re.split(r"\s*[·•|]\s*", raw_name, maxsplit=1)[0].strip()
            entry = out.setdefault(slug, {
                "name": name or slug.replace("-", " ").title(),
                "source": "robolist",
                "source_url": f"{ROBOLIST_BASE}/companies/{slug}",
                "categories": [],
            })
            if name and (entry["name"] == entry["name"].title() or len(name) > len(entry["name"])):
                entry["name"] = name
            if cat not in entry["categories"]:
                entry["categories"].append(cat)
        time.sleep(0.6)
    print(f"[robolist] total: {len(out)}", flush=True)
    return out


def harvest_aparobot(sess: requests.Session) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for path in ("/companies", "/robots"):
        html = fetch_html(f"{APAROBOT_BASE}{path}", sess)
        if not html:
            continue
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.select('a[href*="/compan"], a[href*="/manufacturer"]'):
            name = a.get_text(" ", strip=True)
            if not name or len(name) > 80 or NAV_JUNK_RE.match(name):
                continue
            slug = slugify(name)
            out.setdefault(slug, {
                "name": name,
                "source": "aparobot",
                "source_url": urljoin(APAROBOT_BASE, a.get("href") or ""),
                "categories": ["humanoid"],
            })
        time.sleep(0.8)
    print(f"[aparobot] total: {len(out)}", flush=True)
    return out


_WIKI_UA = {
    "User-Agent": (
        "RobotAIGeek-GapDiscovery/1.0 (https://robotaigeek.com; "
        "research@robotaigeek.com) requests"
    ),
    "Accept": "application/json",
}


def _wiki_query(sess: requests.Session, params: dict[str, Any]) -> dict[str, Any]:
    params = {"format": "json", "action": "query", **params}
    for attempt in range(5):
        try:
            r = sess.get(WIKI_API, params=params, headers=_WIKI_UA, timeout=30)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After") or 0) or (2 ** attempt * 2)
                time.sleep(min(wait, 30))
                continue
            return {}
        except (requests.RequestException, ValueError):
            time.sleep(2 ** attempt)
    return {}


def harvest_wikipedia(sess: requests.Session) -> dict[str, dict[str, Any]]:
    """Harvest robotics company names from Wikipedia categories (recursive one level)."""
    out: dict[str, dict[str, Any]] = {}
    seen_cats: set[str] = set()
    queue = list(WIKI_CATEGORIES)
    depth = {c: 0 for c in queue}
    max_depth = 2

    while queue:
        cat = queue.pop(0)
        if cat in seen_cats:
            continue
        seen_cats.add(cat)
        cont: dict[str, Any] = {}
        while True:
            data = _wiki_query(sess, {
                "list": "categorymembers",
                "cmtitle": cat,
                "cmlimit": "500",
                "cmtype": "page|subcat",
                **cont,
            })
            members = (data.get("query") or {}).get("categorymembers") or []
            for m in members:
                title = m.get("title") or ""
                if title.startswith("Category:"):
                    tl = title.lower()
                    if depth.get(cat, 0) < max_depth and any(
                        k in tl for k in (
                            "robotics compan", "robot manufactur",
                            "vehicle manufactur", "drone", "robots",
                        )
                    ) and "defunct" not in tl:
                        queue.append(title)
                        depth[title] = depth.get(cat, 0) + 1
                    continue
                if _WIKI_SKIP_RE.match(title):
                    continue
                slug = slugify(title)
                out.setdefault(slug, {
                    "name": re.sub(r"\s*\(.*?\)\s*$", "", title).strip(),
                    "source": "wikipedia",
                    "source_url": "https://en.wikipedia.org/wiki/" + title.replace(" ", "_"),
                    "categories": [],
                })
            cont = data.get("continue") or {}
            if not cont:
                break
            time.sleep(1.2)
        print(f"[wikipedia] {cat}: cumulative {len(out)}", flush=True)
        time.sleep(1.2)
    return out


def harvest_seeds() -> dict[str, dict[str, Any]]:
    """Manual seeds: 'Name | website | country_code | category' per line."""
    out: dict[str, dict[str, Any]] = {}
    if not SEEDS_FILE.exists():
        return out
    for line in SEEDS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        name = parts[0]
        if not name:
            continue
        entry: dict[str, Any] = {
            "name": name,
            "source": "manual_seed",
            "source_url": "",
            "categories": [],
        }
        if len(parts) > 1 and parts[1]:
            entry["website"] = parts[1]
        if len(parts) > 2 and parts[2]:
            entry["country_code"] = parts[2].upper()
        if len(parts) > 3 and parts[3]:
            entry["categories"] = [parts[3]]
        out[slugify(name)] = entry
    print(f"[seeds] total: {len(out)}", flush=True)
    return out


def harvest_local_sources() -> dict[str, dict[str, Any]]:
    """Companies pre-extracted from local source files by harvest_local_sources.py.

    Reads staging/gap_discovery/local_sources_harvest.json (produced by the
    Gemini-based extractor over seeds/gap_sources/*). Only entries classified
    as actual robot manufacturers are harvested; agencies/VCs/software-only
    companies are skipped.
    """
    out: dict[str, dict[str, Any]] = {}
    path = LOCAL_SOURCES_HARVEST
    if not path.exists():
        print(f"[local_sources] no {path.name} - run harvest_local_sources.py first", flush=True)
        return out
    skipped = 0
    for item in json.loads(path.read_text(encoding="utf-8")):
        if not item.get("is_manufacturer"):
            skipped += 1
            continue
        name = (item.get("name") or "").strip()
        if not name:
            continue
        entry: dict[str, Any] = {
            "name": name,
            "source": "local:" + item.get("source", "unknown"),
            "source_url": "",
            "categories": [c for c in [item.get("category", "")] if c and c != "other"],
        }
        if item.get("website"):
            entry["website"] = item["website"]
        if item.get("country"):
            entry["country_name"] = item["country"]
        if item.get("note"):
            entry["note"] = item["note"]
        out[slugify(name)] = entry
    print(f"[local_sources] total: {len(out)} manufacturers ({skipped} non-manufacturers skipped)", flush=True)
    return out


HARVESTERS = {
    "robolist": harvest_robolist,
    "aparobot": harvest_aparobot,
    "wikipedia": harvest_wikipedia,
    "local_sources": harvest_local_sources,
}


# ── Stage C: dedupe ──────────────────────────────────────────────────────────

def merge_and_dedupe(  # noqa: C901
    harvests: dict[str, dict[str, dict[str, Any]]],
    baseline: dict[str, Any],
) -> tuple[list[dict[str, Any]], int]:
    merged: dict[str, dict[str, Any]] = {}
    for source, companies in harvests.items():
        for slug, entry in companies.items():
            name = entry.get("name") or ""
            if is_junk_company_name(name, source):
                continue
            # Wikipedia harvests include robot MODEL pages (e.g. 'Ameca',
            # 'Amazon Astro'). If the name matches a robot already in prod,
            # it is a robot page, not a new manufacturer.
            if source == "wikipedia" and norm_key(name) in baseline["robot_global"]:
                continue
            key = norm_key(sorted(company_aliases(name))[0]) if company_aliases(name) else norm_key(name)
            if not key:
                continue
            if key in merged:
                tgt = merged[key]
                if source not in tgt["found_on_sources"]:
                    tgt["found_on_sources"].append(source)
                for cat in entry.get("categories", []):
                    if cat not in tgt["categories"]:
                        tgt["categories"].append(cat)
                if entry.get("website") and not tgt.get("website"):
                    tgt["website"] = entry["website"]
            else:
                merged[key] = {
                    "slug": slugify(name),
                    "name": name,
                    "website": entry.get("website", ""),
                    "country_code": entry.get("country_code", ""),
                    "categories": list(entry.get("categories", [])),
                    "found_on_sources": [source],
                    "source_url": entry.get("source_url", ""),
                }

    total = len(merged)
    gaps = [
        e for e in merged.values()
        if not company_in_db(e["name"], e.get("website", ""), baseline)
    ]
    # priority: multi-source > has website > has categories
    for e in gaps:
        score = len(e["found_on_sources"]) * 30
        if e.get("website"):
            score += 20
        score += min(len(e.get("categories", [])), 3) * 10
        e["priority_score"] = score
    gaps.sort(key=lambda e: (-e["priority_score"], e["name"].lower()))
    return gaps, total


# ── Stage D: website resolution + robot catalog discovery ────────────────────

def resolve_website(entry: dict[str, Any], sess: requests.Session) -> tuple[str, str]:
    """Resolve + validate the manufacturer's official website.

    Returns ``(website, method)``. Every candidate is aggregator-screened,
    domain-matched against the company name, and HEAD/GET-validated — a wrong
    OEM website is worse than none (enrichment would scrape the wrong site).
    """
    if entry.get("website"):
        w = entry["website"]
        if "://" not in w:
            w = "https://" + w
        if validate_website(w, session=sess):
            return w, "seed"
        entry["website"] = ""

    # Tier 0: Wikipedia infobox external links (free, high precision when present)
    if entry.get("source_url", "").startswith("https://en.wikipedia.org/"):
        title = entry["source_url"].rsplit("/", 1)[-1]
        data = _wiki_query(sess, {
            "prop": "extlinks",
            "titles": title.replace("_", " "),
            "ellimit": "50",
        })
        pages = (data.get("query") or {}).get("pages") or {}
        for page in pages.values():
            for link in page.get("extlinks") or []:
                url = (link.get("*") or "").strip()
                if not url or is_skippable_domain(url):
                    continue
                root_match = re.match(r"(https?://[^/]+)", url)
                root = root_match.group(1) if root_match else url
                if not domain_matches_company(root, entry["name"]):
                    continue
                if validate_website(root, session=sess):
                    return root, "wikipedia"

    # Tiers 1-2: Robolist company page, then serper.dev search (both validated)
    robolist_slug = entry["slug"] if "robolist" in (entry.get("found_on_sources") or []) else ""
    site, method = resolve_company_website(
        entry["name"],
        robolist_slug,
        country=entry.get("country_code") or None,
        session=sess,
    )
    return site or "", method if site else "none"


def extract_robot_candidates(
    html: str, base_url: str, company_name: str
) -> list[dict[str, str]]:
    """Mine product-like links (robot name + URL) from a manufacturer page."""
    soup = BeautifulSoup(html, "html.parser")
    base_host = urlparse(base_url).netloc.lower().replace("www.", "")
    out: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    seen_names: set[str] = set()
    co_norm = norm_name(company_name)

    for a in soup.select("a[href]"):
        href = a.get("href") or ""
        full = urljoin(base_url, href)
        low = full.lower()
        if any(x in low for x in ("#", "javascript:", "mailto:", "tel:", ".pdf",
                                  ".jpg", ".png", ".zip", ".mp4")):
            continue
        host = urlparse(full).netloc.lower().replace("www.", "")
        if base_host and host and base_host not in host and host not in base_host:
            continue
        anchor = re.sub(r"\s+", " ", a.get_text(" ", strip=True))[:120]
        anchor = fix_mojibake(anchor)  # re-decode 'franÃ§ais'-style junk
        path = urlparse(full).path.lower()
        if not any(k in path or k in anchor.lower() for k in PRODUCT_LINK_KEYWORDS):
            continue
        if not anchor or NAV_JUNK_RE.match(anchor):
            continue
        anchor_cf = anchor.casefold()
        # Language-switcher + exact-match nav anchors are never product names
        if anchor_cf in _LANGUAGE_ANCHORS or anchor_cf in _NAV_LEXICON:
            continue
        # Pure numbers / measurement ranges (pagination '2', filters '1-7kg')
        if _NUMERIC_ANCHOR_RE.match(anchor):
            continue
        # Anchor should look like a product name: short-ish, not a sentence
        if len(anchor) > 70 or anchor.count(" ") > 8:
            continue
        name = anchor.strip()
        # Drop anchors that are just the company name
        if norm_name(name) == co_norm:
            continue
        nkey = norm_key(name)
        if full in seen_urls or nkey in seen_names or not nkey:
            continue
        seen_urls.add(full)
        seen_names.add(nkey)
        out.append({"name": name, "url": full})
        if len(out) >= _MINE_LIMIT:
            break
    return out


_GEMINI_FILTER_PROMPT = """You are auditing links mined from a robot manufacturer's website.
Manufacturer: "{company}"

For each candidate below decide whether it is a ROBOT PRODUCT or PRODUCT FAMILY
(industrial arm, cobot, AMR/AGV, humanoid, drone, exoskeleton, service robot, etc.)
made by this manufacturer. It is NOT a robot if it is: navigation/UI text
("View Products", "Learn More"), a component (servo, gearbox, ballscrew, sensor,
controller, gripper, linear stage, software), an accessory, an industry/application
page, news, or a third-party product.

Return a JSON array, one object per candidate, same order:
{{"idx": <int>, "is_robot": <bool>, "clean_name": "<canonical English product/family name, e.g. 'KHR-3HV', 'KXR Series'>", "kind": "<robot|family|component|nav|other>"}}

Candidates:
{candidates}
"""


_GENAI_CLIENT = None
_GENAI_FAILED = False


def _get_genai_client():
    """Lazy Gemini client; fail-open (returns None) like grounded_select."""
    global _GENAI_CLIENT, _GENAI_FAILED
    if _GENAI_CLIENT is not None or _GENAI_FAILED:
        return _GENAI_CLIENT
    try:
        from google import genai
        key = os.environ.get("GEMINI_API_KEY", "")
        if not key:
            raise RuntimeError("GEMINI_API_KEY not set")
        _GENAI_CLIENT = genai.Client(api_key=key, http_options={"api_version": "v1beta"})
    except Exception as exc:  # noqa: BLE001
        print(f"  WARN: Gemini unavailable ({exc}); falling back to heuristics", flush=True)
        _GENAI_FAILED = True
    return _GENAI_CLIENT


def llm_filter_candidates(
    company: str, candidates: list[dict[str, str]]
) -> list[dict[str, str]] | None:
    """Use Gemini to keep only real robots and clean/anglicise names.

    Returns filtered candidate list (possibly empty), or None if the LLM is
    unavailable/fails — caller keeps heuristic results with low confidence.
    """
    client = _get_genai_client()
    if client is None or not candidates:
        return None
    listing = "\n".join(
        f"{i}. name={c['name']!r} url={c['url']}" for i, c in enumerate(candidates)
    )
    try:
        response = client.models.generate_content(
            model="models/gemini-2.5-flash",
            contents=_GEMINI_FILTER_PROMPT.format(company=company, candidates=listing),
            config={
                "response_mime_type": "application/json",
                "temperature": 0.0,
                "max_output_tokens": 8192,
                "thinking_config": {"thinking_budget": 0},
            },
        )
        raw = (response.text or "").strip()
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
        start, end = raw.find("["), raw.rfind("]")
        if start == -1 or end <= start:
            return None
        rows = json.loads(raw[start:end + 1])
    except Exception as exc:  # noqa: BLE001
        print(f"  WARN gemini filter fail: {str(exc)[:100]}", flush=True)
        return None
    kept: list[dict[str, str]] = []
    for row in rows:
        try:
            idx = int(row.get("idx"))
        except (TypeError, ValueError):
            continue
        if not (0 <= idx < len(candidates)):
            continue
        if not row.get("is_robot"):
            continue
        cand = dict(candidates[idx])
        clean = (row.get("clean_name") or "").strip()
        if clean and len(clean) >= 2:
            cand["name"] = clean[:120]
        cand["kind"] = str(row.get("kind") or "robot")
        kept.append(cand)
    return kept


def _category_from_product_type(product_type: str) -> str:
    """Map an extractor's per-product type label onto a catalogue category.

    `derive_category_slugs` matches on model names and free text and does not
    recognise catalogue-section phrasing like "industrial articulated" or "FPD
    glass transfer", so those fall through to the company-level hint and get
    mis-stamped. This is the narrow bridge for that, and it stays deliberately
    small: only phrases a source actually emits, no guessing.
    """
    t = (product_type or "").lower()
    if not t:
        return ""
    if "collaborative" in t or "cobot" in t:
        return "cobot"
    if "articulated" in t or "industrial" in t:
        return "industrial-arm"
    if "glass" in t or "fpd" in t or "wafer" in t:
        return "industrial-arm"
    if "mobile" in t or "amr" in t:
        return "amr-warehouse"
    if "drone" in t or "uav" in t:
        return "drone"
    return ""


def _structured_robots(
    entry: dict[str, Any],
    website: str,
    html: str,
    baseline: dict[str, Any],
) -> list[StagedRobot]:
    """Run the extraction ladder and map any hits onto StagedRobot.

    Deliberately conservative about what it claims: only fields the source
    actually stated are written. Descriptions are composed from those fields
    rather than lifted from marketing copy, and nothing is inferred to fill a
    gap — an absent payload stays absent.
    """
    try:
        from extractors.ladder import ExtractionLadder
    except Exception:
        return []

    try:
        result, report = ExtractionLadder().run(website, html)
    except Exception as exc:
        print(f"      structured extraction failed: {str(exc)[:110]}", flush=True)
        return []
    if not result:
        return []

    # EVIDENCE GATE. A registered site config was mapped by a human, so its
    # output is trusted. Anything discovered generically — a page-declared
    # endpoint, a __NEXT_DATA__ island, loose JSON-LD — is a guess about what
    # a list of dicts means, and that guess is wrong in a specific, damaging
    # way: Zoox's nav menu extracted as four "products" ("How To Ride",
    # "Support", "Where to Ride"). Because a structured hit SHORT-CIRCUITS
    # link mining, junk here does not merely add noise, it REPLACES the result
    # the old path would have produced. So an unregistered extraction must
    # show real product evidence — a spec or an image — on at least half its
    # rows, or we discard it and fall through to link mining.
    try:
        from extractors.base import registry as _reg
        trusted = _reg.site_config(website) is not None
    except Exception:
        trusted = False
    if not trusted:
        def _has_evidence(p) -> bool:
            return bool(p.payload_kg or p.reach_mm or p.dof or p.image_urls)
        strong = sum(1 for p in result.products if _has_evidence(p))
        if strong * 2 < len(result.products):
            print(f"      structured extraction DISCARDED ({len(result.products)} rows, "
                  f"only {strong} carried a spec or image — treating as non-product "
                  f"data and falling back to link mining)", flush=True)
            return []

    co_slug = entry["slug"]
    co_norm = norm_key(entry["name"])
    company_categories = categories_from_discovery_hints(entry.get("categories"))
    out: list[StagedRobot] = []
    seen: set[str] = set()

    for p in result.products:
        name = (p.name or "").strip()
        rkey = norm_key(name)
        if not name or not rkey or rkey in seen:
            continue
        # Same dedupe the link-mining path applies, plus the legacy alias: a
        # renamed model must not be imported twice under both designations.
        if f"{co_norm}::{rkey}" in baseline["robot_index"] or rkey in baseline["robot_global"]:
            continue
        akey = p.alias_key()
        if akey and (f"{co_norm}::{akey}" in baseline["robot_index"]
                     or akey in baseline["robot_global"]):
            continue
        seen.add(rkey)

        bits = [f"{name} is a product listed by {entry['name']}."]
        if p.payload_kg:
            bits.append(f"Rated payload {p.payload_kg:g} kg.")
        if p.reach_mm:
            bits.append(f"Maximum reach {p.reach_mm:g} mm.")
        if p.dof:
            bits.append(f"{p.dof} axes.")
        if p.drive:
            bits.append(f"Drive type: {p.drive}.")
        if p.controllers:
            bits.append(f"Compatible controllers: {p.controllers}.")
        for k, v in (p.extra or {}).items():
            if k != "description" and isinstance(v, (str, int, float)) and str(v).strip():
                bits.append(f"{k.replace('_', ' ').capitalize()}: {v}.")
        if p.in_production is False:
            bits.append("Listed by the manufacturer as no longer in production.")

        fam_token = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:32]
        out.append(StagedRobot(
            name=name,
            company_slug=co_slug,
            company_name=entry["name"],
            model_name=name,
            variant_code=p.alias,
            family_key=f"{co_slug}:{fam_token}",
            family_name=name,
            url=p.source_url or website,
            product_url_scope="exact_variant",
            manufacturer_country_code=entry.get("country_code", ""),
            description=" ".join(bits),
            purpose=f"{entry['name']} product: {name}.",
            payload_kg=p.payload_kg,
            reach_mm=p.reach_mm,
            dof=p.dof,
            # Precedence: the model's own name, then the SOURCE'S per-product
            # type label, and only then the company-level directory hint.
            # That order matters — a company tagged both "industrial-arm" and
            # "cobot" would otherwise stamp `collaborative-robot` on its
            # industrial arms purely because the hint is company-wide. The
            # product_type comes from the manufacturer's own catalogue split,
            # so it is evidence about THIS model, not about the firm.
            category_slugs=(
                derive_category_slugs(name=name, fallback="")
                or _category_from_product_type(p.product_type)
                or company_categories
            ),
            availability_status_key=("discontinued" if p.in_production is False else "available"),
            source_locale="en",
            images=normalize_image_candidates([
                {"url": u, "source_page_url": p.source_url or website,
                 "source_tier": "manufacturer", "source_publisher": entry["name"],
                 "media_class": "official_render", "image_scope": "exact_variant",
                 "confidence_score": 85, "rights_status": "official_source",
                 "match_reason": f"image published alongside the product by the manufacturer ({p.via})"}
                for u in (p.image_urls or [])[:3]
            ]),
            sources=[SourceRef(url=p.source_url or website, type="website",
                               title=f"{entry['name']} product catalogue")],
            confidence={"name": "high", "specs": "high"},
            research_notes=(
                f"[AI Research] Extracted from the manufacturer's own structured data "
                f"via '{p.via}' on {_now()[:10]} ({report.summary()[:120]}). Specs are the "
                f"source's typed fields, not parsed prose."
                + (f" Legacy designation: {p.alias}." if p.alias else "")
            ),
        ))
    return out


def discover_robots(
    entry: dict[str, Any],
    baseline: dict[str, Any],
    sess: requests.Session,
) -> list[StagedRobot]:
    website = entry.get("website") or ""
    if not website:
        return []
    if "://" not in website:
        website = "https://" + website
    html = fetch_html(website, sess)
    if not html or len(html) < 400:
        return []

    # STRUCTURED FIRST. If the site publishes its catalogue as data — its own
    # product JSON API, schema.org Product markup, or a real spec table — read
    # that instead of scraping anchor text. Link mining reconstructs by guess
    # what the server already stated precisely: on HD Hyundai it produced 23
    # records (~9 real) against 69 complete models with payload/reach/DOF from
    # the same site's API. Falls through silently when nothing structured is
    # present, which is the common case, so this only ever adds.
    structured = _structured_robots(entry, website, html, baseline)
    if structured:
        print(f"      structured extraction: {len(structured)} products", flush=True)
        return structured

    candidates = extract_robot_candidates(html, website, entry["name"])

    # Follow one product-listing page deep if few candidates on homepage
    if len(candidates) < 3:
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.select("a[href]"):
            text = (a.get_text(" ", strip=True) or "").lower()
            if re.search(r"\b(products?|robots?|portfolio|solutions?)\b", text):
                sub = urljoin(website, a.get("href") or "")
                if urlparse(sub).netloc.replace("www.", "") == urlparse(website).netloc.replace("www.", ""):
                    sub_html = fetch_html(sub, sess)
                    if sub_html:
                        more = extract_robot_candidates(sub_html, sub, entry["name"])
                        known = {norm_key(c["name"]) for c in candidates}
                        candidates.extend(c for c in more if norm_key(c["name"]) not in known)
                    break

    # LLM audit: keep only real robots, clean + anglicise names. Fail-open.
    filtered = llm_filter_candidates(entry["name"], candidates[:_AUDIT_LIMIT])
    llm_ok = filtered is not None
    if llm_ok:
        candidates = filtered

    co_slug = entry["slug"]
    co_norm = norm_key(entry["name"])
    # Directory-source labels ("humanoid", "amr", ...) are a claim about the
    # COMPANY, so they only survive here as a floor: enrichment reads the actual
    # product page the same night and re-derives from the robot's own taxonomy.
    # A floor still beats nothing — it is the difference between a name-only row
    # landing in To Review categorised or flagged "No category".
    company_categories = categories_from_discovery_hints(entry.get("categories"))
    robots: list[StagedRobot] = []
    seen_clean: set[str] = set()
    for cand in candidates[:_KEEP_LIMIT]:
        rkey = norm_key(cand["name"])
        if not rkey or rkey in seen_clean:
            continue
        seen_clean.add(rkey)
        if f"{co_norm}::{rkey}" in baseline["robot_index"]:
            continue
        if rkey in baseline["robot_global"]:
            continue
        fam_token = re.sub(r"[^a-z0-9]+", "-", cand["name"].lower()).strip("-")[:32]
        robots.append(StagedRobot(
            name=cand["name"],
            company_slug=co_slug,
            company_name=entry["name"],
            model_name=cand["name"],
            family_key=f"{co_slug}:{fam_token}",
            family_name=cand["name"],
            family_url=cand["url"],
            product_url_scope="family",
            url=cand["url"],
            manufacturer_country_code=entry.get("country_code", ""),
            # Name keywords first (a link literally called "SCARA robot" is direct
            # evidence about THIS model), company focus as the floor.
            category_slugs=derive_category_slugs(
                name=cand["name"], fallback="",
            ) or company_categories,
            availability_status_key="available",
            company_website=entry.get("website", ""),
            # Carries the resolved HQ country onto the COMPANY at import
            # (views.py fills `company.country` from this when it is blank), so
            # the fix lands once for the manufacturer rather than per robot.
            company_hq_country_code=entry.get("country_code", ""),
            sources=[SourceRef(url=cand["url"], type="website", title=f"{entry['name']} product page")],
            confidence={"name": "medium" if llm_ok else "low",
                        "url": "medium" if llm_ok else "low"},
            research_notes=(
                "[AI Research] Gap-discovery candidate mined from manufacturer "
                f"website link crawl on {_now()[:10]}"
                + (" and screened by Gemini (robot-vs-junk, name cleanup)"
                   if llm_ok else " (heuristic only — LLM screen unavailable)")
                + ". Name/URL only — specs, images, and descriptions require "
                "enrichment before approval."
            ),
        ))
    return robots


# ── Stage E: staging output ──────────────────────────────────────────────────

def stage_company(entry: dict[str, Any]) -> StagedCompany:
    sources = []
    if entry.get("source_url"):
        sources.append(SourceRef(url=entry["source_url"], type="directory",
                                 title=f"Found via {', '.join(entry['found_on_sources'])}"))
    if entry.get("website"):
        w = entry["website"]
        sources.append(SourceRef(url=w if "://" in w else "https://" + w,
                                 type="website", title="Official website"))
    return StagedCompany(
        name=entry["name"],
        slug=entry["slug"],
        website=entry.get("website", ""),
        country_code=entry.get("country_code", ""),
        primary_focus=list(entry.get("categories", [])),
        sources=sources,
        research_notes=(
            "[AI Research] Discovered by manufacturer_gap_discovery.py on "
            f"{_now()[:10]}; sources: {', '.join(entry['found_on_sources'])}. "
            + (f"Website resolved via {entry['website_method']} (validated). "
               if entry.get("website_method") not in (None, "", "none") else
               "No validated official website found. ")
            + "Not present in prod DB at baseline "
            "(see staging/reports/prod_baseline.json)."
        ),
    )


def write_summary(
    gaps: list[dict[str, Any]],
    staged_companies: list[StagedCompany],
    staged_robots: list[StagedRobot],
    merged_total: int,
    baseline: dict[str, Any],
) -> None:
    raw = baseline["raw"]
    lines = [
        "# Manufacturer & Robot Gap Discovery — Summary",
        "",
        f"- Generated: {_now()}",
        f"- Prod baseline: {raw.get('company_count')} companies, {raw.get('robot_count')} robots"
        f" (as of {raw.get('generated_at', '?')[:19]})",
        f"- Harvested (all sources, merged): {merged_total} manufacturers",
        f"- **New manufacturers not in prod: {len(gaps)}**",
        f"- Staged companies: {len(staged_companies)}",
        f"- **Staged robots (new, deduped): {len(staged_robots)}**",
        "",
        "## Top staged manufacturers",
        "",
        "| Company | Website | Sources | Categories | Robots staged |",
        "|---|---|---|---|---|",
    ]
    per_co: dict[str, int] = {}
    for r in staged_robots:
        per_co[r.company_slug] = per_co.get(r.company_slug, 0) + 1
    for c in staged_companies[:150]:
        lines.append(
            f"| {c.name} | {c.website or '—'} | "
            f"{', '.join(s.title or s.type for s in c.sources) or '—'} | "
            f"{', '.join(c.primary_focus) or '—'} | {per_co.get(c.slug, 0)} |"
        )
    lines += [
        "",
        "## Next steps",
        "",
        "1. Review `staged_import.json` (companies + robots).",
        "2. Optionally enrich robots via `overnight_queue_enrich.py` after import.",
        "3. Import companies first, then robots:",
        "   `python cli.py import --dir staging/gap_discovery/robots/{slug}/ --dry-run`",
        "",
    ]
    SUMMARY_FILE.write_text("\n".join(lines), encoding="utf-8")


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", choices=list(HARVESTERS) + ["seeds", "all"], default="all")
    ap.add_argument("--harvest-only", action="store_true", help="stop after stage C")
    ap.add_argument("--max-companies", type=int, default=None,
                    help="cap number of new companies to run robot discovery for")
    ap.add_argument("--resume", action="store_true",
                    help="reuse harvested_manufacturers.json if present")
    ap.add_argument("--merge-source", default=None, choices=list(HARVESTERS),
                    help="harvest ONE source and merge into the existing harvest "
                         "file, then run stage D only for companies new to the "
                         "harvest (stage E merges into existing staged_import.json)")
    ap.add_argument("--min-score", type=int, default=0,
                    help="minimum priority score for stage D")
    ap.add_argument("--local", action="store_true")
    ap.add_argument("--round", type=int, default=1,
                    help="discovery round number (2+ dedupes against prior rounds)")
    args = ap.parse_args()

    if args.round >= 2:
        set_round(args.round)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ROBOTS_DIR.mkdir(parents=True, exist_ok=True)
    sess = requests.Session()

    print(f"=== Stage A: baseline (round {args.round}) ===", flush=True)
    baseline = load_baseline()
    # Extend baseline with prior rounds' staged companies/robots
    for prior_f in prior_round_staged_files(args.round):
        prior = json.loads(prior_f.read_text(encoding="utf-8"))
        for c in prior.get("companies", []):
            baseline["company_index"].update(
                _baseline_name_variants(c.get("name") or ""))
            if c.get("slug"):
                baseline["company_index"].add(norm_key(c["slug"]))
            w = (c.get("website") or "").strip().lower()
            if w:
                host = urlparse(w if "://" in w else f"https://{w}").netloc
                host = host.replace("www.", "")
                if host:
                    baseline["website_index"].add(host)
        for r in prior.get("robots", []):
            rk = norm_key(r.get("name") or "")
            if rk:
                baseline["robot_global"].add(rk)
        print(f"  + prior round: {prior_f.name} "
              f"({prior.get('company_count', '?')} cos / "
              f"{prior.get('robot_count', '?')} robs)", flush=True)
    print(f"baseline: {len(baseline['company_index'])} company variants / "
          f"{len(baseline['robot_global'])} robot names", flush=True)

    print("=== Stage B: harvest ===", flush=True)
    merge_new_slugs: set[str] | None = None
    if args.merge_source:
        harvests = (json.loads(HARVEST_FILE.read_text(encoding="utf-8"))
                    if HARVEST_FILE.exists() else {})
        before = {slug for src in harvests.values() for slug in src}
        harvests[args.merge_source] = HARVESTERS[args.merge_source](sess) \
            if args.merge_source != "local_sources" else harvest_local_sources()
        merge_new_slugs = {
            slug for slug in harvests[args.merge_source] if slug not in before
        }
        HARVEST_FILE.write_text(json.dumps(harvests, indent=2, ensure_ascii=False),
                                encoding="utf-8")
        print(f"merged source '{args.merge_source}': "
              f"{len(harvests[args.merge_source])} entries, "
              f"{len(merge_new_slugs)} new slugs", flush=True)
    elif args.resume and HARVEST_FILE.exists():
        harvests = json.loads(HARVEST_FILE.read_text(encoding="utf-8"))
        print(f"resumed harvest file: {sum(len(v) for v in harvests.values())} entries")
    else:
        harvests: dict[str, dict[str, dict[str, Any]]] = {}
        wanted = list(HARVESTERS) if args.source in ("all",) else (
            [args.source] if args.source in HARVESTERS else []
        )
        for src in wanted:
            try:
                harvests[src] = (harvest_local_sources() if src == "local_sources"
                                 else HARVESTERS[src](sess))
            except Exception as exc:
                print(f"[{src}] FAILED: {exc}")
                harvests[src] = {}
        if args.source in ("all", "seeds"):
            harvests["manual_seed"] = harvest_seeds()
        HARVEST_FILE.write_text(json.dumps(harvests, indent=2, ensure_ascii=False),
                                encoding="utf-8")

    print("=== Stage C: dedupe vs prod ===", flush=True)
    gaps, merged_total = merge_and_dedupe(harvests, baseline)
    print(f"merged {merged_total} manufacturers -> {len(gaps)} NOT in prod", flush=True)

    gaps_path = OUT_DIR / "gap_manufacturers.json"
    gaps_path.write_text(json.dumps({
        "generated_at": _now(),
        "merged_total": merged_total,
        "gaps_found": len(gaps),
        "gaps": gaps,
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    if args.harvest_only:
        print(f"harvest-only: wrote {gaps_path}")
        return

    print("=== Stage D: website + robot discovery ===", flush=True)
    todo = [g for g in gaps if g["priority_score"] >= args.min_score]
    if merge_new_slugs is not None:
        todo = [g for g in todo if g["slug"] in merge_new_slugs]
        print(f"merge mode: stage D restricted to {len(todo)} newly merged companies",
              flush=True)
    if args.max_companies:
        todo = todo[: args.max_companies]

    staged_companies: list[StagedCompany] = []
    staged_robots: list[StagedRobot] = []
    skipped_alias: list[dict[str, str]] = []
    for i, entry in enumerate(todo, 1):
        try:
            website, method = resolve_website(entry, sess)
            entry["website"] = website
            entry["website_method"] = method
            # Resolve the HQ country HERE, at discovery, for the same reason the
            # website is resolved here: a company staged without one is imported
            # without one, and enrichment then copies that blank onto every robot
            # it owns as the error-severity "No country" flag. Directory sources
            # supply a country for only a minority of entries.
            if not entry.get("country_code") and website:
                code, how = resolve_company_country(entry["name"], website, session=sess)
                if code:
                    entry["country_code"] = code
                    entry["country_method"] = how
            # Alias guard: the resolved OEM domain may already belong to a prod
            # company listed under a different name — skip, don't duplicate.
            if website:
                host = urlparse(website).netloc.replace("www.", "").lower()
                if host and host in baseline["website_index"]:
                    skipped_alias.append({"name": entry["name"], "website": website})
                    print(f"  [{i}/{len(todo)}] {entry['name']}: SKIP "
                          f"(domain {host} already in prod)", flush=True)
                    continue
            robots = discover_robots(entry, baseline, sess)
        except Exception as exc:
            print(f"  [{i}/{len(todo)}] {entry['name']}: ERROR {str(exc)[:120]}")
            robots = []
        staged_companies.append(stage_company(entry))
        if robots:
            co_dir = ROBOTS_DIR / entry["slug"]
            co_dir.mkdir(parents=True, exist_ok=True)
            for r in robots:
                (co_dir / f"{slugify(r.name)}.json").write_text(
                    json.dumps(r.to_dict(), indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
            staged_robots.extend(robots)
        print(f"  [{i}/{len(todo)}] {entry['name']}: web={'Y' if entry.get('website') else 'N'} "
              f"robots={len(robots)}", flush=True)
        time.sleep(0.4)

    print("=== Stage E: staging output ===", flush=True)
    out_companies = [c.to_dict() for c in staged_companies]
    out_robots = [r.to_dict() for r in staged_robots]
    if merge_new_slugs is not None and STAGED_FILE.exists():
        prev = json.loads(STAGED_FILE.read_text(encoding="utf-8"))
        have_c = {c["slug"] for c in out_companies}
        have_r = {(r.get("company_slug"), r.get("name")) for r in out_robots}
        out_companies = [c for c in prev.get("companies", [])
                         if c["slug"] not in have_c] + out_companies
        out_robots = [r for r in prev.get("robots", [])
                      if (r.get("company_slug"), r.get("name")) not in have_r] + out_robots
        skipped_alias = prev.get("skipped_alias_domains", []) + skipped_alias
        print(f"merge mode: combined into {len(out_companies)} companies / "
              f"{len(out_robots)} robots", flush=True)
    STAGED_FILE.write_text(json.dumps({
        "generated_at": _now(),
        "workflow": "manufacturer_gap_discovery",
        "baseline_generated_at": baseline["raw"].get("generated_at"),
        "company_count": len(out_companies),
        "robot_count": len(out_robots),
        "skipped_alias_domains": skipped_alias,
        "companies": out_companies,
        "robots": out_robots,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    write_summary(gaps, staged_companies, staged_robots, merged_total, baseline)
    print(f"Wrote {STAGED_FILE}")
    print(f"Wrote {SUMMARY_FILE}")


if __name__ == "__main__":
    main()
