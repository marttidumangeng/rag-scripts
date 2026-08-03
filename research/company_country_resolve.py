"""Resolve a company's HQ country to an ISO alpha-2 code.

WHY THIS EXISTS
---------------
`missing_manufacturer_country` is an **error**-severity flag ("No country"), yet
it was listed in `remedies.registry.UNFIXABLE_FLAGS` — no remedy could ever
clear it. Measured on prod 2026-07-31: 351 of 1596 pending robots had no
country, and the cause is upstream, not per-robot:

    232 of 806 companies have no country at all
    633 pending robots belong to such a company
     54 pending robots have no country even though their company DOES
        (pure propagation gap — enrichment reads company.country and copies it,
        so a company filled in later never back-propagates)

A robot's `manufacturer_country` is the manufacturer's HQ country, so fixing the
COMPANY fixes every one of its robots at once. That is what this module is for;
`resolve_pending_company_countries.py` is the batch driver.

Resolution tiers — first confident hit wins, and every tier is checked against
the ISO table so a hallucinated code can never be written:

  1. ccTLD of the company's own website  (.jp/.de/.cn/... — deterministic, free)
  2. Address / imprint text on the website itself
  3. serper.dev snippets for "<name> headquarters"
  4. Gemini extraction over the text tiers 2-3 collected

Fail-closed by design: an unresolved country returns "" and the caller leaves
the field blank. A WRONG country is worse than a missing one — it silently
mislabels the manufacturer on every robot page and in every country facet.
"""

from __future__ import annotations

import os
import re
import unicodedata
from typing import Any

import requests

from company_website_resolve import _HEADERS, _serper_search
from load_env import load_research_env

load_research_env()

# ---------------------------------------------------------------------------
# Tier 1: country-code TLDs
# ---------------------------------------------------------------------------
# Only unambiguous ccTLDs that a manufacturer plausibly uses as its primary
# domain. Deliberately excluded: vanity/repurposed TLDs (.ai Anguilla, .io BIOT,
# .co Colombia, .me Montenegro, .tv Tuvalu, .to Tonga, .sh, .ly, .cc, .is, .am)
# — a robotics startup on a .ai domain is not headquartered in Anguilla.
_CCTLD_TO_COUNTRY: dict[str, str] = {
    "au": "AU", "at": "AT", "be": "BE", "br": "BR", "ca": "CA", "ch": "CH",
    "cn": "CN", "cz": "CZ", "de": "DE", "dk": "DK", "es": "ES", "fi": "FI",
    "fr": "FR", "gr": "GR", "hk": "HK", "hu": "HU", "id": "ID", "ie": "IE",
    "il": "IL", "in": "IN", "it": "IT", "jp": "JP", "kr": "KR", "lu": "LU",
    "mx": "MX", "my": "MY", "nl": "NL", "no": "NO", "nz": "NZ", "ph": "PH",
    "pl": "PL", "pt": "PT", "ro": "RO", "ru": "RU", "se": "SE", "sg": "SG",
    "sk": "SK", "th": "TH", "tr": "TR", "tw": "TW", "ua": "UA", "uk": "GB",
    "vn": "VN", "za": "ZA",
    # second-level forms
    "co.uk": "GB", "co.jp": "JP", "co.kr": "KR", "com.cn": "CN", "com.au": "AU",
    "com.br": "BR", "com.tw": "TW", "co.nz": "NZ", "com.sg": "SG",
    "com.tr": "TR", "co.il": "IL", "co.in": "IN", "com.mx": "MX",
}

# ---------------------------------------------------------------------------
# Tier 2/3: country names seen in address / snippet text
# ---------------------------------------------------------------------------
_COUNTRY_NAME_TO_CODE: dict[str, str] = {
    "united states": "US", "usa": "US", "u.s.a.": "US", "u.s.": "US",
    "america": "US",
    "united kingdom": "GB", "great britain": "GB", "england": "GB",
    "scotland": "GB", "wales": "GB",
    "china": "CN", "prc": "CN", "hong kong": "HK", "taiwan": "TW",
    "japan": "JP", "south korea": "KR", "korea": "KR",
    "germany": "DE", "deutschland": "DE",
    "france": "FR", "italy": "IT", "italia": "IT", "spain": "ES",
    "espana": "ES", "netherlands": "NL", "holland": "NL",
    "belgium": "BE", "switzerland": "CH", "schweiz": "CH",
    "austria": "AT", "osterreich": "AT",
    "sweden": "SE", "norway": "NO", "denmark": "DK", "finland": "FI",
    "poland": "PL", "czech republic": "CZ", "czechia": "CZ",
    "portugal": "PT", "greece": "GR", "ireland": "IE", "iceland": "IS",
    "canada": "CA", "mexico": "MX", "brazil": "BR", "brasil": "BR",
    "argentina": "AR", "chile": "CL",
    "australia": "AU", "new zealand": "NZ",
    "india": "IN", "singapore": "SG", "malaysia": "MY", "thailand": "TH",
    "vietnam": "VN", "viet nam": "VN", "indonesia": "ID", "philippines": "PH",
    "israel": "IL", "turkey": "TR", "turkiye": "TR",
    "united arab emirates": "AE", "uae": "AE", "saudi arabia": "SA",
    "south africa": "ZA", "egypt": "EG",
    "russia": "RU", "ukraine": "UA", "belarus": "BY",
    "hungary": "HU", "romania": "RO", "slovakia": "SK", "slovenia": "SI",
    "croatia": "HR", "bulgaria": "BG", "serbia": "RS", "estonia": "EE",
    "latvia": "LV", "lithuania": "LT", "luxembourg": "LU",
}

# Words that turn a country name into a DIFFERENT place. "New Mexico" appears in
# every US state dropdown, and Dane Technologies (company 1637, Minnesota)
# resolved to MX off its contact page for exactly that reason.
_FALSE_PREFIX: dict[str, tuple[str, ...]] = {
    "mexico": ("new",),
    "india": ("west",),
    "guinea": ("new", "papua"),
}

# Regional tokens that imply a country when no country is named. Split by
# strength: POSTAL patterns are address-shaped by construction and are trusted
# even on a weak page; SOFT hints are city/keyword mentions, which a marketing
# page throws around freely ("our Tokyo partner"), so they are gated.
_REGION_POSTAL: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b[A-Z]{2}\s+\d{5}(-\d{4})?\b"), "US"),          # MN 55428
    (re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b"), "GB"),   # SW1A 1AA
]
_REGION_SOFT: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(california|texas|massachusetts|michigan|pennsylvania|"
                r"minnesota|new york|silicon valley|boston|pittsburgh|"
                r"san francisco)\b", re.I), "US"),
    (re.compile(r"\b(shenzhen|shanghai|beijing|hangzhou|suzhou|guangdong|"
                r"guangzhou|shandong|zhejiang|jiangsu)\b", re.I), "CN"),
    (re.compile(r"\b(tokyo|osaka|nagoya|kyoto|yokohama|aichi|kanagawa)\b", re.I), "JP"),
    (re.compile(r"\b(seoul|gyeonggi|daejeon|busan|incheon)\b", re.I), "KR"),
    # A company rarely writes its OWN country into its own address — the only
    # country spelled out on a contact page is usually the FOREIGN satellite.
    # Bluepath Robotics (company 1677) lists "Head Office ... Istanbul",
    # "Factory ... Kocaeli" and "US office ... Detroit, MI 48216, United States",
    # and resolved to US because Detroit's was the only line naming a country.
    # City hints are what let a domestic address speak for itself.
    (re.compile(r"\b(istanbul|ankara|izmir|kocaeli|pendik|bursa|gebze|antalya)\b", re.I), "TR"),
    (re.compile(r"\b(bengaluru|bangalore|mumbai|chennai|pune|hyderabad|noida|gurugram)\b", re.I), "IN"),
    (re.compile(r"\b(tel aviv|haifa|jerusalem|herzliya|rehovot)\b", re.I), "IL"),
    (re.compile(r"\b(munich|m[uü]nchen|berlin|hamburg|stuttgart|frankfurt|"
                r"d[uü]sseldorf|impressum)\b", re.I), "DE"),
    (re.compile(r"\b(paris|lyon|toulouse|grenoble|nantes|la rochelle|bordeaux)\b", re.I), "FR"),
    (re.compile(r"\b(milan|milano|turin|torino|bologna|rome|roma)\b", re.I), "IT"),
    (re.compile(r"\b(z[uü]rich|geneva|gen[eè]ve|lausanne|basel)\b", re.I), "CH"),
    (re.compile(r"\b(eindhoven|amsterdam|delft|rotterdam|utrecht)\b", re.I), "NL"),
    (re.compile(r"\b(barcelona|madrid|valencia|bilbao|zaragoza)\b", re.I), "ES"),
    (re.compile(r"\b(odense|copenhagen|k[oø]benhavn|aarhus)\b", re.I), "DK"),
    (re.compile(r"\b(stockholm|gothenburg|g[oö]teborg|lund|v[aä]ster[aå]s)\b", re.I), "SE"),
    (re.compile(r"\b(taipei|hsinchu|taichung|kaohsiung|new taipei)\b", re.I), "TW"),
    (re.compile(r"\b(singapore city|jurong|tuas)\b", re.I), "SG"),
    (re.compile(r"\b(toronto|vancouver|montreal|montr[eé]al|waterloo|kitchener)\b", re.I), "CA"),
    (re.compile(r"\b(sydney|melbourne|brisbane|perth|canberra)\b", re.I), "AU"),
    (re.compile(r"\b(warsaw|warszawa|krak[oó]w|wroc[lł]aw|pozna[nń])\b", re.I), "PL"),
    (re.compile(r"\b(london|cambridge|oxford|bristol|manchester|edinburgh)\b", re.I), "GB"),
]

# Labels that mark an address as a SATELLITE, not the headquarters. A country
# anchored to one of these must never win.
_SATELLITE_MARKER = re.compile(
    r"\b((us|u\.s\.|uk|eu|asia|apac|emea|regional|sales|branch|local|"
    r"subsidiary|representative)\s+(office|entity|branch|subsidiary)|"
    r"(office|branch|subsidiary)\s+in)\b",
    re.I,
)

# Pages that carry the legal address, BEST FIRST — and the homepage LAST.
#
# The homepage used to be tried first and it is the worst source on the site: it
# is marketing, so it names deployment countries, partners and press. Shark
# Robotics (company 1806, a French firm in La Rochelle) resolved to UKRAINE
# purely because its homepage carries a delivery story and never spells
# "France"; its /mentions-legales page states the address outright.
_CONTACT_PATHS: tuple[str, ...] = (
    # legal-notice pages: the address is a statutory requirement on these
    "/mentions-legales", "/imprint", "/impressum", "/legal-notice", "/legal",
    "/aviso-legal", "/note-legali",
    # contact pages
    "/contact", "/contact-us", "/nous-contacter", "/kontakt", "/contacto",
    "/en/contact", "/contact/",
    # about pages
    "/about", "/about-us", "/company", "/a-propos", "/ueber-uns",
    # homepage last, and only trusted with an address-shaped match (see
    # `_from_website`)
    "",
)

_MAX_PAGE_BYTES = 400_000


def country_from_domain(website: str) -> str:
    """ISO alpha-2 implied by the website's ccTLD, or ''. Offline and free."""
    return _tld_country(website)


def _tld_country(website: str) -> str:
    host = re.sub(r"^https?://", "", (website or "").strip().lower()).split("/")[0]
    host = host.split(":")[0].strip(".")
    if not host:
        return ""
    parts = host.split(".")
    for depth in (2, 1):
        if len(parts) > depth:
            suffix = ".".join(parts[-depth:])
            if suffix in _CCTLD_TO_COUNTRY:
                return _CCTLD_TO_COUNTRY[suffix]
    return ""


_HQ_MARKER = re.compile(
    r"\b(headquarter(s|ed)?|head office|hq|registered office|main office|"
    r"principal place of business|founded in|based in|address|located (at|in)|"
    # French/German/Spanish legal-notice wording — the pages most likely to
    # carry the statutory address are usually not in English.
    r"si[eè]ge social|si[eè]ge|adresse|sitz der gesellschaft|domicilio social)\b"
)
_HQ_WINDOW = 200
"""How far after an HQ marker a country name still counts as describing it."""

# Tokens that make a country mention look like part of a postal address rather
# than prose. Used to gate the homepage, which is the weakest page on any site.
_ADDRESS_CONTEXT = re.compile(
    # The digit run is a POSTAL CODE, so years are excluded — "delivered to
    # Ukraine in 2022" otherwise reads as an address and re-opens the exact
    # false positive this gate exists to stop.
    r"\b((?!(?:19|20)\d{2}\b)\d{4,6}|street|str\.|st\.|road|rue|avenue|ave\.|boulevard|blvd|"
    r"strasse|stra[sß]e|via|calle|zone|parc|park|building|bldg|suite|floor|"
    r"district|p\.?o\.? box|cedex)\b",
    re.I,
)
_ADDRESS_WINDOW = 120
"""How close an address token must sit to the country name to vouch for it."""


def _country_from_text(text: str, *, require_address_context: bool = False) -> str:
    """Country implied by an address block, or ''.

    Country NAMES beat regional hints: an explicit "Germany" in a footer beats a
    US-looking postcode elsewhere on the page. Where several countries appear,
    one that FOLLOWS an HQ marker wins over one that merely appears earlier —
    otherwise "our USA office opened; HQ in Germany" relocates the company.

    `require_address_context` demands that the winning mention sit near a postal
    code, a street word or an HQ marker. Pass it for weak sources (a homepage),
    where "delivered to Ukraine" is a news item, not a headquarters.
    """
    if not text:
        return ""
    lowered = _fold(re.sub(r"\s+", " ", _strip_code_blobs(text)))

    names: list[tuple[int, str]] = []
    for phrase, code in _COUNTRY_NAME_TO_CODE.items():
        pos = lowered.find(phrase)
        # Word-boundary check keeps "china" out of "chinatown" and, more
        # importantly, "usa" out of "usability"/"causal".
        while pos != -1:
            before = lowered[pos - 1] if pos else " "
            after_idx = pos + len(phrase)
            after = lowered[after_idx] if after_idx < len(lowered) else " "
            if (not before.isalnum() and not after.isalnum()
                    and not _has_false_prefix(lowered, pos, phrase)):
                names.append((pos, code))
                break
            pos = lowered.find(phrase, pos + 1)

    postal = [(m.start(), code) for pat, code in _REGION_POSTAL
              for m in [pat.search(text)] if m]
    soft = [(m.start(), code) for pat, code in _REGION_SOFT
            for m in [pat.search(lowered)] if m]

    # --- HQ anchoring, across ALL signal kinds --------------------------------
    # This has to include city hints, not just country names: a company writes
    # "Head Office ... Istanbul" and never writes "Turkey", so anchoring only
    # country names leaves the domestic HQ invisible and hands the answer to
    # whichever foreign office bothered to name its country.
    markers = [m.end() for m in _HQ_MARKER.finditer(lowered)]
    satellites = [m.end() for m in _SATELLITE_MARKER.finditer(lowered)]
    if markers:
        anchored = [
            (pos - m, code)
            for pos, code in names + postal + soft
            for m in markers
            if 0 <= pos - m <= _HQ_WINDOW
            # ...unless a satellite label sits between the marker and the hit,
            # which is what "Headquarters <addr> US office <addr>" looks like.
            and not any(m < s <= pos for s in satellites)
        ]
        if anchored:
            return min(anchored)[1]

    if names:
        # Several countries and nothing saying which one is the headquarters:
        # that is a page listing offices, distributors or deployments. Earliest
        # mention is not evidence, so hand the question to the next tier rather
        # than guess — a wrong country is worse than a blank one.
        if len({code for _pos, code in names}) > 1:
            return ""
        if require_address_context:
            addr = [m.start() for m in _ADDRESS_CONTEXT.finditer(lowered)]
            if not any(abs(pos - a) <= _ADDRESS_WINDOW for pos, _c in names for a in addr):
                return ""
        return min(names)[1]

    if postal:
        return min(postal)[1]
    if require_address_context:
        return ""
    if soft:
        return min(soft)[1]
    return ""


def _fold(text: str) -> str:
    """Lowercase and strip combining marks.

    Turkish addresses render Istanbul with a dotted capital I, which lowercases
    to "i" plus a combining dot — so a plain `.lower()` haystack never matches
    the literal "istanbul" in the hint table.
    """
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _has_false_prefix(lowered: str, pos: int, phrase: str) -> bool:
    """True when the preceding word makes this a different place ("new mexico")."""
    for bad in _FALSE_PREFIX.get(phrase, ()):
        if lowered[max(0, pos - len(bad) - 1):pos].strip() == bad:
            return True
    return False


# Long runs of JSON/JS object literals — i18n dictionaries, config blobs, inline
# data islands. They survive the <script> strip when the markup nests or escapes
# a closing tag, and they are pure noise for address detection (Shark Robotics
# ships a MediaElement.js language table listing every language on earth).
_CODE_BLOB = re.compile(r'(?:"[\w.\- ]+"\s*:\s*"[^"]*"\s*,\s*){4,}')


def _strip_code_blobs(text: str) -> str:
    return _CODE_BLOB.sub(" ", text)


def _fetch_text(url: str, session: requests.Session | None = None) -> str:
    sess = session or requests
    try:
        resp = sess.get(url, headers=_HEADERS, timeout=15, allow_redirects=True)
        if resp.status_code >= 400:
            return ""
        html = resp.text[:_MAX_PAGE_BYTES]
    except requests.RequestException:
        return ""
    html = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html)
    return re.sub(r"<[^>]+>", " ", html)


def _from_website(website: str, session: requests.Session | None = None) -> tuple[str, str]:
    """Scrape the company's own site for an address. Returns (code, how)."""
    base = (website or "").strip().rstrip("/")
    if not base:
        return "", "no-website"
    if "://" not in base:
        base = "https://" + base
    for path in _CONTACT_PATHS:
        text = _fetch_text(base + path, session)
        if not text:
            continue
        # The homepage is the weakest page on the site — it names deployment
        # countries, partners and press — so a bare country mention there is not
        # evidence. Require an address-shaped context (postal code, street word,
        # or an HQ marker) before believing it. Dedicated legal/contact pages
        # earn the benefit of the doubt.
        code = _country_from_text(text, require_address_context=(path == ""))
        if code:
            return code, f"website{path or '/'}"
    return "", "website-no-address"


def _from_search(name: str, website: str = "") -> tuple[str, str]:
    """serper.dev snippets for the HQ. Returns (code, how)."""
    if not name:
        return "", "no-name"
    votes: dict[str, int] = {}
    for query in (
        f'"{name}" robotics headquarters located',
        f'"{name}" company headquarters address',
    ):
        for item in _serper_search(query, max_results=8):
            blob = f"{item.get('title', '')} {item.get('snippet', '')}"
            code = _country_from_text(blob)
            if code:
                votes[code] = votes.get(code, 0) + 1
        if votes:
            break
    if not votes:
        return "", "search-no-hit"
    top = max(votes.items(), key=lambda kv: kv[1])
    # A single ambiguous snippet is not evidence. Require either two agreeing
    # snippets or an outright majority — "Company X opens US office" would
    # otherwise relocate a Japanese manufacturer to the United States.
    if top[1] < 2 and len(votes) > 1:
        return "", f"search-ambiguous:{sorted(votes)}"
    return top[0], f"search(votes={top[1]})"


_GEMINI_SYSTEM = """\
You identify where a robotics company is HEADQUARTERED.

Return ONLY a JSON object: {"country_code": "<ISO 3166-1 alpha-2>", "confidence": "high|medium|low"}

Rules:
- country_code must be the HEADQUARTERS country, not a sales office, not a
  factory, not the country of a distributor or investor.
- If the evidence names several countries and does not say which is the
  headquarters, return {"country_code": "", "confidence": "low"}.
- Never guess from the company name or from what the products look like.
- Return "" rather than a plausible-sounding answer you cannot support.
"""


def _from_gemini(name: str, evidence: str) -> tuple[str, str]:
    """Constrained extraction over already-collected text. Returns (code, how)."""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key or not evidence.strip():
        return "", "gemini-unavailable"
    try:
        from google import genai
        from google.genai import types

        import spend_guard
        client = spend_guard.client(api_key=api_key, http_options={"api_version": "v1beta"})
        resp = client.models.generate_content(
            model="models/gemini-2.5-flash",
            contents=f"{_GEMINI_SYSTEM}\n\nCompany: {name}\n\n--- Evidence ---\n{evidence[:8000]}",
            config=types.GenerateContentConfig(
                temperature=0.0,
                response_mime_type="application/json",
                max_output_tokens=256,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        import json

        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", (resp.text or "").strip())
        data: dict[str, Any] = json.loads(text)
    except Exception:  # noqa: BLE001 — fail-open: heuristics already ran
        return "", "gemini-error"
    code = str(data.get("country_code") or "").strip().upper()[:2]
    confidence = str(data.get("confidence") or "low").lower()
    if not re.fullmatch(r"[A-Z]{2}", code) or confidence == "low":
        return "", f"gemini-unconfident({confidence})"
    return code, f"gemini({confidence})"


def country_from_company_name(name: str) -> str:
    """Region named inside the company's own registered name, or ''.

    The strongest signal there is and the cheapest: a company does not put a
    foreign region in its own legal name. "Benson Intelligent Equipment
    (Shandong) Co., Ltd." is in Shandong — but its site never writes "China",
    and a case-study caption reading "equipment russia ... delivery site" was
    enough to resolve it to RUSSIA, which then propagated to 27 robots.
    """
    folded = _fold(name or "")
    for pattern, code in _REGION_SOFT:
        if pattern.search(folded):
            return code
    for phrase, code in _COUNTRY_NAME_TO_CODE.items():
        if re.search(rf"\b{re.escape(phrase)}\b", folded):
            return code
    return ""


def resolve_company_country(
    name: str,
    website: str = "",
    *,
    session: requests.Session | None = None,
    use_search: bool = True,
    use_gemini: bool = True,
) -> tuple[str, str]:
    """Best-effort ISO alpha-2 HQ country for a company.

    Returns ``(country_code, how)``. ``country_code`` is "" when no tier
    produced a supportable answer — callers must leave the field blank rather
    than fall back to a guess.
    """
    code = _tld_country(website)
    if code:
        return code, "cctld"

    code = country_from_company_name(name)
    if code:
        return code, "company-name"

    evidence_parts: list[str] = []

    site_code, site_how = _from_website(website, session)
    if site_code:
        return site_code, site_how
    if website:
        evidence_parts.append(_fetch_text(
            website if "://" in website else "https://" + website, session)[:4000])

    if use_search:
        search_code, search_how = _from_search(name, website)
        if search_code:
            return search_code, search_how
        for item in _serper_search(f'"{name}" robotics company headquarters', max_results=6):
            evidence_parts.append(f"{item.get('title', '')}: {item.get('snippet', '')}")

    if use_gemini:
        return _from_gemini(name, "\n".join(p for p in evidence_parts if p))
    return "", site_how
