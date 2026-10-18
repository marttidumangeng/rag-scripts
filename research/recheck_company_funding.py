"""Re-check the funding history of published companies from public sources.

Eugene (2026-10-16): "can your AI agent also comb our existing companies and
check again the numbers and funding they have received? That should be public
information." This is that agent.

For each published company it
  1. web-searches for funding rounds (serper.dev, 2 queries by default),
  2. reads the top result pages through the shared fetch ladder,
  3. asks Gemini (metered through spend_guard) to extract every round the
     evidence explicitly states — date, amount, currency, round, investors,
     the source that states it, and whether that source is the company
     itself, a filing or press — never inferring an amount,
  4. compares with the company's profile milestones, and
  5. files each new round, and each round whose amount disagrees with the
     milestone on record, as a DRAFT ChangeEvent (POST /api/v1/changes/) for
     a reviewer to publish from the admin. Nothing goes public on its own.

Dry run by default: prints what it would file and writes a JSON snapshot.
--apply files the drafts. --write-milestones additionally appends NEW rounds
to the company's milestones (read-all, append, write-back: the endpoint
replaces the list), which is public, so it is a separate switch.

Cost guards (every paid call is capped and counted):
  --max-companies (400)   companies per run
  --searches (2)          serper searches per company
  --pages (3)             result pages fetched per company (free tiers first;
                          scrape.serper.dev scrapes are capped per fetcher)
  Gemini: one call per company with evidence, via spend_guard (daily USD and
  call budgets; SpendBudgetExceeded stops the run). The end-of-run summary
  prints searches, pages, Gemini calls and spend_guard.status().

Run from scripts/research (cwd matters for the imports):
  export PYTHONIOENCODING=utf-8
  python recheck_company_funding.py --limit 5                    # dry run
  python recheck_company_funding.py --limit 5 --apply            # file drafts
  python recheck_company_funding.py --company-id 14 --apply --write-milestones
Env: IMPORT_SYNC_API_BASE_URL, IMPORT_SYNC_API_KEY (admin key), SERPER_API_KEY,
GEMINI_API_KEY. Missing ones are read from ../../robotaigeek-server/.env.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import urlparse

import requests

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

# ---------------------------------------------------------------------------
# Env
# ---------------------------------------------------------------------------

_ENV_FILE = _HERE.parent.parent / "robotaigeek-server" / ".env"
_ENV_KEYS = ("IMPORT_SYNC_API_BASE_URL", "IMPORT_SYNC_API_KEY", "SERPER_API_KEY", "GEMINI_API_KEY")


def load_env_file(path: Path = _ENV_FILE, keys: Iterable[str] = _ENV_KEYS) -> list[str]:
    """Fill missing env vars from the server .env (never overrides a set one)."""
    filled: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return filled
    wanted = set(keys)
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key in wanted and not os.environ.get(key):
            value = value.strip().strip('"').strip("'")
            if value:
                os.environ[key] = value
                filled.append(key)
    return filled


# ---------------------------------------------------------------------------
# Sources we do not read
# ---------------------------------------------------------------------------

# Paid databases whose terms forbid scraping, plus social sites: the round is
# always announced somewhere we may read (the company, a filing, the press).
SKIP_DOMAINS = (
    "crunchbase.com", "pitchbook.com", "tracxn.com", "cbinsights.com", "dealroom.co",
    "zoominfo.com", "owler.com", "craft.co", "linkedin.com", "facebook.com", "twitter.com",
    "x.com", "instagram.com", "youtube.com", "tiktok.com", "reddit.com", "glassdoor.com",
    "indeed.com", "apollo.io", "rocketreach.co", "signalhire.com", "multiples.vc", "growjo.com",
    "startuptalky.com", "cypherlabs.com", "failory.com", "seedtable.com", "wellfound.com",
    # Crunchbase/PitchBook restaters: same data, no primary source behind it.
    "bouncewatch.com", "crustdata.com", "cbinsights.com", "golden.com", "privco.com", "datanyze.com",
    "leadiq.com", "clay.com", "parsers.vc", "dealroom.net", "startupmap.iamsterdam.com",
    "startupintros.com",
    # Pre-IPO secondary-market sites restating rounds from the same databases.
    "forgeglobal.com", "caplight.com", "equityzen.com", "hiive.com", "notice.co",
    "whitefordresearch.com", "exa.ai",
)
COMPANY_SIGNAL_PATHS = ("news", "press", "blog", "media", "announcement", "newsroom")
FILING_DOMAINS = ("sec.gov", "companieshouse.gov.uk", "edinet-fsa.go.jp", "dart.fss.or.kr", "hkexnews.hk")

ROUND_PATTERNS = [
    (re.compile(r"\bpre[- ]?seed\b", re.I), "Pre-seed"),
    (re.compile(r"\bseed\b", re.I), "Seed"),
    (re.compile(r"\bangel\b", re.I), "Angel"),
    (re.compile(r"\bpre[- ]?series[\s-]*a\b|\bpre[- ]?a\b", re.I), "Pre-A"),
    (re.compile(r"\bseries[\s-]*a\+|\bseries[\s-]*a\s*plus\b|\ba\+\s*round\b", re.I), "Series A+"),
    (re.compile(r"\bseries[\s-]*a\b(?!\+)", re.I), "Series A"),
    (re.compile(r"\bseries[\s-]*b\+", re.I), "Series B+"),
    (re.compile(r"\bseries[\s-]*b\b(?!\+)", re.I), "Series B"),
    (re.compile(r"\bseries[\s-]*c\b", re.I), "Series C"),
    (re.compile(r"\bseries[\s-]*d\b", re.I), "Series D"),
    (re.compile(r"\bseries[\s-]*e\b", re.I), "Series E"),
    (re.compile(r"\bseries[\s-]*f\b", re.I), "Series F"),
    (re.compile(r"\bipo\b|\binitial public offering\b|\blisted on\b", re.I), "IPO"),
    (re.compile(r"\bacqui(?:red|sition)\b|\bbought by\b|\btakeover\b", re.I), "Acquisition"),
    (re.compile(r"\bstrategic\b", re.I), "Strategic"),
    (re.compile(r"\bgrowth\b", re.I), "Growth"),
    (re.compile(r"\bgrant\b", re.I), "Grant"),
    (re.compile(r"\bdebt\b|\bcredit facility\b|\bloan\b", re.I), "Debt"),
]

CURRENCY_SYMBOL = {"USD": "US$", "CNY": "CNY ", "EUR": "EUR ", "GBP": "GBP ", "JPY": "JPY ", "KRW": "KRW ",
                   "CHF": "CHF ", "CAD": "CA$", "AUD": "A$", "SGD": "S$", "HKD": "HK$", "INR": "INR ", "SEK": "SEK ",
                   "DKK": "DKK ", "NOK": "NOK ", "ILS": "ILS ", "TWD": "TWD "}


def domain_of(url: str) -> str:
    try:
        host = (urlparse(url).netloc or "").lower()
    except Exception:
        return ""
    return host[4:] if host.startswith("www.") else host


def is_skipped_domain(url: str) -> bool:
    host = domain_of(url)
    return any(host == d or host.endswith("." + d) for d in SKIP_DOMAINS)


def normalise_round(text: str) -> str:
    """'Series-A extension' -> 'Series A'; unknown -> 'Funding round'."""
    s = (text or "").strip()
    for pattern, label in ROUND_PATTERNS:
        if pattern.search(s):
            return label
    if s.lower() in ("", "round", "funding", "funding round", "investment", "financing", "other", "unknown",
                     "undisclosed", "venture", "venture round", "equity"):
        return "Funding round"
    return s[:40]


def _round_phrase(label: str) -> str:
    """'Series A' stays; 'Strategic' -> 'strategic round'; 'Debt' -> 'debt financing'."""
    if label == "Debt":
        return "debt financing"
    if label == "Funding round":
        return "funding round"
    if label in ("Strategic", "Growth", "Bridge", "Extension", "Convertible"):
        return f"{label.lower()} round"
    return label


def _article(following: str) -> str:
    """'a' or 'an' for the word that follows 'Raised': 'an Angel', 'a US$5M', 'a Series A'."""
    word = (following or "").split(" ")[0]
    if not word:
        return "a"
    if word[:2].isupper() or word[:1] in "$£€¥₩":  # currency codes and symbols read as consonants (US, EUR, CNY)
        return "a"
    return "an" if word[:1].lower() in "aeiou" else "a"


def parse_round_date(value: str) -> tuple[date, str] | None:
    """'2026-02-11' -> (date, 'day'); '2026-02' -> (…-02-01, 'month'); '2026' -> (…-01-01, 'year')."""
    s = (value or "").strip()
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        try:
            return date(int(m[1]), int(m[2]), int(m[3])), "day"
        except ValueError:
            return None
    m = re.fullmatch(r"(\d{4})-(\d{2})", s)
    if m and 1 <= int(m[2]) <= 12:
        return date(int(m[1]), int(m[2]), 1), "month"
    m = re.fullmatch(r"(\d{4})", s)
    if m and 1900 <= int(m[1]) <= 2100:
        return date(int(m[1]), 1, 1), "year"
    return None


def format_amount(amount: float | int | None, currency: str | None, amount_text: str = "") -> str:
    if amount is None:
        return (amount_text or "").strip() or "amount undisclosed"
    cur = (currency or "USD").upper()
    prefix = CURRENCY_SYMBOL.get(cur, cur + " ")
    a = float(amount)
    if a >= 1e9:
        num = f"{a / 1e9:.2f}".rstrip("0").rstrip(".") + "B"
    elif a >= 1e6:
        num = f"{a / 1e6:.2f}".rstrip("0").rstrip(".") + "M"
    elif a >= 1e3:
        num = f"{a / 1e3:.1f}".rstrip("0").rstrip(".") + "K"
    else:
        num = f"{a:g}"
    return f"{prefix}{num}"


def amount_key(amount: float | int | None, currency: str | None) -> str | None:
    """Rounded amount for matching against milestone text ('520M USD')."""
    if amount is None:
        return None
    return f"{format_amount(amount, currency)}"


@dataclass
class Round:
    date: str                      # YYYY-MM-DD / YYYY-MM / YYYY as the model gave it
    round: str                     # normalised label
    amount: float | None
    currency: str | None
    amount_text: str = ""
    lead_investors: list[str] = field(default_factory=list)
    participating_investors: list[str] = field(default_factory=list)
    source_url: str = ""
    source_kind: str = "press"     # company | filing | press | other
    confidence: str = "medium"     # high | medium | low
    quote: str = ""                # the sentence that states it

    @property
    def occurred(self) -> tuple[date, str] | None:
        return parse_round_date(self.date)

    @property
    def year(self) -> int | None:
        parsed = self.occurred
        return parsed[0].year if parsed else None


_UNDISCLOSED = ("", "undisclosed", "not disclosed", "amount undisclosed", "n/a", "unknown")


def summary_for_round(r: Round) -> str:
    if (r.amount_text or "").strip().lower() in _UNDISCLOSED:
        r.amount_text = ""
    amount = format_amount(r.amount, r.currency, r.amount_text)
    label = r.round
    investors = ", ".join(i for i in (r.lead_investors or [])[:3] if i)
    led = f" led by {investors}" if investors else ""
    others = ", ".join(i for i in (r.participating_investors or [])[:4] if i and i not in (r.lead_investors or []))
    if others:
        led += f" with {others}" if led else f" from {others}"
    if label == "Acquisition":
        who = f" by {investors}" if investors else ""
        amt = "" if r.amount is None and not r.amount_text else f" for {amount}"
        return f"Acquired{who}{amt}".strip()
    if label == "IPO":
        amt = "" if r.amount is None else f", raising {amount}"
        return f"Listed publicly{amt}"
    if label == "Grant":
        return f"Received {_article(amount)} {amount} grant{led}"
    phrase = _round_phrase(label)
    if r.amount is None and not r.amount_text:
        return f"Raised {_article(phrase)} {phrase} (amount undisclosed){led}"
    if r.amount is None:
        return f"Raised {_article(phrase)} {phrase} ({r.amount_text.strip()}){led}"
    return f"Raised {_article(amount)} {amount} {phrase}{led}"


# ---------------------------------------------------------------------------
# Comparison with what the profile already holds
# ---------------------------------------------------------------------------

_AMOUNT_IN_TEXT = re.compile(
    r"(?:US\$|USD|\$|CNY|RMB|¥|EUR|€|GBP|£|JPY|KRW|₩|HK\$|S\$|A\$|CA\$|INR|₹)\s*([0-9][0-9.,]*)\s*(B|M|K|billion|million|thousand|亿|万)?",
    re.I)


def amounts_in_text(text: str) -> set[int]:
    """Approximate amounts named in a milestone, in whole currency units, so that
    'US$520 million' and 'US$520M' and 520000000 compare equal."""
    out: set[int] = set()
    for m in _AMOUNT_IN_TEXT.finditer(text or ""):
        try:
            n = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        unit = (m.group(2) or "").lower()
        mult = {"b": 1e9, "billion": 1e9, "m": 1e6, "million": 1e6, "k": 1e3, "thousand": 1e3,
                "亿": 1e8, "万": 1e4}.get(unit, 1)
        out.add(int(round(n * mult)))
    return out


def match_existing(r: Round, milestones: list[dict[str, Any]]) -> tuple[str, dict[str, Any] | None]:
    """How a found round relates to the milestones on record.

    Returns ('known', m) when a milestone of the same year names the same round
    (or, for a round label we could not classify, the same amount);
    ('mismatch', m) when the same year + round is on record with a different
    amount; ('new', None) otherwise.
    """
    year = r.year
    if year is None:
        return "new", None
    label = r.round.lower()
    found_amount = int(round(float(r.amount))) if r.amount is not None else None
    same_year = [m for m in milestones if _milestone_year(m) == year]
    for m in same_year:
        text = str(m.get("description") or "")
        text_round = normalise_round(text).lower()
        text_amounts = amounts_in_text(text)
        same_round = label == text_round and label != "funding round"
        same_amount = found_amount is not None and any(abs(a - found_amount) <= max(1, found_amount * 0.02)
                                                       for a in text_amounts)
        if same_round and (same_amount or found_amount is None or not text_amounts):
            return "known", m
        if same_round and text_amounts and not same_amount:
            return "mismatch", m
        if not same_round and same_amount:
            return "known", m
    return "new", None


_SOURCE_RANK = {"company": 3, "filing": 3, "press": 1, "other": 0}
_CONFIDENCE_RANK = {"high": 2, "medium": 1, "low": 0}


def collapse_rounds(rounds: list[Round]) -> list[Round]:
    """One row per event: the same (year, round, amount) reported by several
    sources keeps the company's or a filing's own statement, with the lead
    investors merged. Keeps the first-seen order."""
    kept: list[Round] = []
    index: dict[tuple[Any, ...], int] = {}
    for r in rounds:
        amt = int(round(float(r.amount) / 1e5)) if r.amount is not None else (r.amount_text or "").strip().lower()
        key = (r.year, r.round.lower(), amt, (r.currency or "").upper() if r.amount is not None else "")
        if key not in index:
            index[key] = len(kept)
            kept.append(r)
            continue
        current = kept[index[key]]
        better = (_SOURCE_RANK.get(r.source_kind, 0), _CONFIDENCE_RANK.get(r.confidence, 1), r.occurred[1] == "day") > (
            _SOURCE_RANK.get(current.source_kind, 0), _CONFIDENCE_RANK.get(current.confidence, 1), current.occurred[1] == "day")
        winner, loser = (r, current) if better else (current, r)
        merged = list(winner.lead_investors) + [i for i in loser.lead_investors if i not in winner.lead_investors]
        winner.lead_investors = merged[:5]
        others = list(winner.participating_investors) + [i for i in loser.participating_investors
                                                         if i not in winner.participating_investors]
        winner.participating_investors = [i for i in others if i not in winner.lead_investors][:10]
        kept[index[key]] = winner
    return kept


# company_maturity values on the profile, in order; a round label maps to the
# stage it proves. Acquisition proves nothing about the stage.
STAGE_ORDER = ["seed", "series_a", "series_b", "series_c", "series_d_plus", "public_company"]
_STAGE_OF_ROUND = {
    "Pre-seed": "seed", "Seed": "seed", "Angel": "seed", "Pre-A": "seed",
    "Series A": "series_a", "Series A+": "series_a",
    "Series B": "series_b", "Series B+": "series_b",
    "Series C": "series_c",
    "Series D": "series_d_plus", "Series E": "series_d_plus", "Series F": "series_d_plus",
    "IPO": "public_company",
}


def stage_of_round(label: str) -> str | None:
    return _STAGE_OF_ROUND.get(label)


def stage_from_rounds(rounds: list[Round]) -> str | None:
    """The furthest stage the evidence proves (where the company is now)."""
    best = None
    for r in rounds:
        stage = stage_of_round(r.round)
        if stage and (best is None or STAGE_ORDER.index(stage) > STAGE_ORDER.index(best)):
            best = stage
    return best


def stage_is_later(suggested: str | None, on_record: str | None) -> bool:
    if not suggested or suggested not in STAGE_ORDER:
        return False
    if not on_record or on_record not in STAGE_ORDER:
        return True
    return STAGE_ORDER.index(suggested) > STAGE_ORDER.index(on_record)


def _milestone_year(m: dict[str, Any]) -> int | None:
    try:
        return int(m.get("year"))
    except (TypeError, ValueError):
        return None


def latest_funding_year(milestones: list[dict[str, Any]]) -> int | None:
    years = [_milestone_year(m) for m in milestones
             if normalise_round(str(m.get("description") or "")) not in ("Funding round",)
             or re.search(r"raised|funding|investment|financ", str(m.get("description") or ""), re.I)]
    years = [y for y in years if y]
    return max(years) if years else None


# ---------------------------------------------------------------------------
# Search, fetch, extract (each replaceable in tests)
# ---------------------------------------------------------------------------

_SERPER_DOWN = False


def serper_search(query: str, *, num: int = 8) -> list[dict[str, Any]]:
    """Google organic results via serper.dev: [{title, link, snippet, date}]."""
    global _SERPER_DOWN
    api_key = os.environ.get("SERPER_API_KEY", "")
    if not api_key or _SERPER_DOWN:
        return []
    try:
        resp = requests.post("https://google.serper.dev/search",
                             headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
                             json={"q": query, "num": num}, timeout=20)
        if resp.status_code in (400, 401, 402, 403, 429):
            print(f"  [serper] search refused ({resp.status_code}); no more searches this run", flush=True)
            _SERPER_DOWN = True
            return []
        resp.raise_for_status()
        return resp.json().get("organic") or []
    except (requests.RequestException, ValueError) as exc:
        print(f"  [serper] search failed: {exc}", flush=True)
        return []


def funding_queries(name: str, website: str = "") -> list[str]:
    host = domain_of(website)
    # q1 finds the latest round; q2 the history (seed, series A/B/C, investors).
    q1 = f'"{name}" funding round raised million led by investors'
    q2 = f'"{name}" "pre-seed" OR seed OR "series a" OR "series b" OR "series c" funding history investors'
    if host:
        q2 += f' OR site:{host} funding'
    return [q1, q2]


def select_links(results: list[dict[str, Any]], website: str, limit: int) -> list[dict[str, Any]]:
    """Top result links worth reading: company newsroom and filings first, then
    press; paid databases and social sites never."""
    host = domain_of(website)
    seen: set[str] = set()
    picked: list[tuple[int, dict[str, Any]]] = []
    for item in results:
        url = (item.get("link") or "").strip()
        if not url or url in seen or is_skipped_domain(url):
            continue
        seen.add(url)
        d = domain_of(url)
        score = 0
        if host and (d == host or d.endswith("." + host)):
            score += 3
            if any(p in url.lower() for p in COMPANY_SIGNAL_PATHS):
                score += 1
        if any(d == f or d.endswith("." + f) for f in FILING_DOMAINS):
            score += 3
        blob = f"{item.get('title', '')} {item.get('snippet', '')}".lower()
        if re.search(r"rais|fund|series|seed|invest|acqui|valuation|round", blob):
            score += 2
        picked.append((score, item))
    picked.sort(key=lambda x: -x[0])
    return [item for _, item in picked[:limit]]


def fetch_page_text(url: str, fetcher: Any = None) -> str:
    """Main text of a page through the shared fetch ladder (web_extract)."""
    try:
        import web_extract
        f = fetcher or web_extract.WebFetcher(serper_budget=6)
        page = web_extract.parse_page(f, url)
        if page is None:
            return ""
        return (page.main_text or page.text or "")[:12000]
    except Exception as exc:  # noqa: BLE001 — a dead page is not a reason to stop the run
        print(f"  [fetch] {url}: {exc}", flush=True)
        return ""


_GEMINI_SYSTEM = """You extract FUNDING EVENTS for ONE company from evidence snippets and pages.
Return JSON only: {"rounds": [ {...}, ... ]} with one object per distinct event:
  date: "YYYY-MM-DD", or "YYYY-MM" when only the month is known, or "YYYY" when only the year is
  round: e.g. "Seed", "Series A", "Series A+", "Series B", "Growth", "Strategic", "Acquisition", "IPO", "Grant"
  amount: number in whole currency units (e.g. 520000000), or null when not stated exactly
  currency: ISO code ("USD", "CNY", "EUR", "GBP", "JPY", "KRW") or null
  amount_text: the stated wording when there is no exact number ("hundreds of millions of yuan", "undisclosed")
  lead_investors: [names] of the investor(s) that led the round, or the acquirer; [] if not stated
  participating_investors: [names] of every other investor named in the round (new and existing); [] if none
  source_index: the number of the evidence block [S<n>] that states this event
  source_kind: "company" (the company's own announcement or site), "filing" (regulator), "press", or "other"
  confidence: "high" | "medium" | "low"
  quote: the one sentence from that block stating the event
Rules:
- Only money THIS company RECEIVED: a round it raised, a grant it received, its own listing, or
  THIS company being acquired. Never a deal it made: an acquisition it bought, a business or unit
  it sold, a fund it launched or an investment it made in another company (if Company X "acquired
  Y for US$3B", that is not an event for X). Never crowdfunding pre-orders (Kickstarter, Indiegogo).
- Only events the evidence explicitly states for THIS company (check the name; a different company
  with a similar name is not this company). A government or sovereign fund's total size is not a
  round: only the amount invested in THIS company counts. Never infer, estimate or convert an amount. A
  conversion in the text ("~US$220M") may be reported as amount_text, not as the amount.
- An extension of a round is its own event with the extension amount. A cumulative total
  ("has raised US$935M to date") is NOT an event.
- Capture the WHOLE history the evidence states — pre-seed, angel, seed, every series, strategic
  rounds, grants, acquisition, IPO — not only the latest round.
- Investor names exactly as written; "led by X" or "X led" makes X a lead, everyone else named as
  investing or participating goes in participating_investors.
- One event once: if several blocks state the same round, pick the company/filing block.
- No event at all -> {"rounds": []}."""


def gemini_extract(company: dict[str, Any], evidence: list[dict[str, str]], *, model: str = "models/gemini-2.5-flash") -> list[Round]:
    """One metered Gemini call over the collected evidence."""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key or not evidence:
        return []
    from google.genai import types

    import spend_guard
    client = spend_guard.client(api_key=api_key, http_options={"api_version": "v1beta"})
    blocks = []
    for i, ev in enumerate(evidence, 1):
        blocks.append(f"[S{i}] {ev.get('url', '')}\n{ev.get('text', '')[:9000]}")
    prompt = (f"{_GEMINI_SYSTEM}\n\nCompany: {company.get('name')}\nWebsite: {company.get('website') or 'unknown'}\n"
              f"Country: {company.get('country') or 'unknown'}\n\n--- Evidence ---\n" + "\n\n".join(blocks))
    resp = client.models.generate_content(
        model=model,
        contents=prompt[:60000],
        config=types.GenerateContentConfig(
            temperature=0.0, response_mime_type="application/json", max_output_tokens=2048,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", (resp.text or "").strip())
    try:
        data = json.loads(text)
    except ValueError:
        print("  [gemini] unparsable JSON; treated as no rounds", flush=True)
        return []
    return rounds_from_json(data, evidence)


_DEAL_MADE_RE = re.compile(
    r"\b(?:acquire[sd]?|acquiring|to acquire|bought|buys|purchas(?:e|ed|es|ing)|sold|sells|selling|divest(?:s|ed|iture)?|"
    r"invest(?:s|ed)? in|led the|launch(?:es|ed)? a (?:fund|venture)|kickstarter|indiegogo)\b", re.I)


_RAISE_RE = re.compile(r"\b(?:rais(?:e|es|ed|ing)|secur(?:e|es|ed|ing)|clos(?:e|es|ed|ing) (?:a|its|an)|"
                       r"land(?:s|ed)|bag(?:s|ged)|nets?|netted|receiv(?:e|es|ed)|gets?|got)\b", re.I)


_OBJECT_OF_DEAL_RE = re.compile(
    r"\b(?:acquired|acquires|acquire|acquisition of|purchase of|bought|buys|takeover of|merger with|invest(?:ed|s|ment)? in|"
    r"(?:share|stake|interest|holding)s? in)\s+(?:\w+\s+){0,5}$", re.I)


def is_deal_made_by(company_name: str, r: Round) -> bool:
    """True when the quote names this company as the one doing the deal
    ("Thermo Fisher to acquire PPD for US$17.4B"), which is not money it raised."""
    quote = r.quote or ""
    if not quote:
        return False
    if re.search(r"kickstarter|indiegogo", quote, re.I):
        return True
    if r.round in ("IPO", "Grant"):
        return False
    # "Ottobock (SuitX)", "QinetiQ (Foster-Miller)": the profile is the company in
    # brackets; its parent buying it is that company being acquired, not a deal it made.
    bracket = re.search(r"\(([^)]+)\)", company_name or "")
    if bracket:
        outer = (company_name or "")[:bracket.start()].strip()

        def _named(name: str) -> bool:
            toks = [t for t in re.split(r"[^\w]+", name.lower()) if len(t) >= 3][:2]
            return bool(toks) and any(re.search(r"\b" + re.escape(t) + r"\b", quote.lower()) for t in toks)

        if outer and _named(outer) and _named(bracket.group(1)):
            return False
        child = bracket.group(1).strip()
        child_tokens = [t for t in re.split(r"[^\w]+", child.lower()) if len(t) >= 3][:2]
        if child_tokens and any(t in quote.lower() for t in child_tokens):
            company_name = child
    tokens = [t for t in re.split(r"[^\w]+", (company_name or "").lower()) if len(t) >= 3][:2]
    if not tokens:
        return False
    low = quote.lower()
    # Whole words only: "PWR Pack" must not match inside "packaging".
    hits = [m.start() for t in tokens for m in [re.search(r"\b" + re.escape(t) + r"\b", low)] if m]
    pos = min(hits, default=-1)
    if pos < 0:
        return False
    # "Acquired Hydroid in 2020", "its acquisition of InTouch Technologies": a deal verb or
    # noun just BEFORE the name makes the company the object, i.e. the one being bought.
    if _OBJECT_OF_DEAL_RE.search(low[max(0, pos - 70):pos]):
        return False
    m = _DEAL_MADE_RE.search(quote, pos)
    # "<Company> acquires/acquired/sold/invested in ..." within the clause after the name
    if not m or m.start() - pos > 60:
        return False
    # "<Company> raises EUR 2.2M, sells package machines in ..." is a round: a raise verb
    # between the name and the deal verb means the company RECEIVED money.
    if _RAISE_RE.search(quote[pos:m.start()]):
        return False
    # "Franka Robotics (..., acquired by Agile Robots ...)": the deal verb followed by
    # "by" is passive, so the company is the one being acquired or invested in.
    if quote[m.end():m.end() + 4].lower().startswith(" by"):
        return False
    # "<Company> was acquired by ..." / "<Company> is acquired by ..." is the company being bought: keep it.
    between = low[pos:m.end()]
    return not re.search(r"\b(?:was|is|be|been|being|has been|will be)\s+(?:\w+\s+)?(?:acquired|bought|purchased|sold)\b", between)


def rounds_from_json(data: Any, evidence: list[dict[str, str]]) -> list[Round]:
    rounds: list[Round] = []
    for item in (data or {}).get("rounds", []) if isinstance(data, dict) else []:
        if not isinstance(item, dict):
            continue
        parsed = parse_round_date(str(item.get("date") or ""))
        if not parsed:
            continue
        amount = item.get("amount")
        try:
            amount = float(amount) if amount not in (None, "", "null") else None
        except (TypeError, ValueError):
            amount = None
        if amount is not None and amount <= 0:
            amount = None
        try:
            idx = int(item.get("source_index") or 0)
        except (TypeError, ValueError):
            idx = 0
        source_url = evidence[idx - 1]["url"] if 1 <= idx <= len(evidence) else ""
        rounds.append(Round(
            date=str(item.get("date")).strip(), round=normalise_round(str(item.get("round") or "")),
            amount=amount, currency=(str(item.get("currency") or "").upper()[:3] or None),
            amount_text=str(item.get("amount_text") or "").strip()[:120],
            lead_investors=[str(x).strip()[:80] for x in (item.get("lead_investors") or []) if str(x).strip()][:5],
            participating_investors=[str(x).strip()[:80] for x in (item.get("participating_investors") or [])
                                     if str(x).strip()][:10],
            source_url=source_url, source_kind=str(item.get("source_kind") or "press").lower(),
            confidence=str(item.get("confidence") or "medium").lower(),
            quote=str(item.get("quote") or "").strip()[:300],
        ))
    return rounds


# ---------------------------------------------------------------------------
# Filing
# ---------------------------------------------------------------------------

def change_payload(company_id: int, r: Round, relation: str, milestone: dict[str, Any] | None, run_id: str) -> dict[str, Any]:
    occurred, precision = r.occurred  # type: ignore[misc]
    summary = summary_for_round(r)
    note = f"funding_recheck {run_id}: {relation}"
    if relation == "mismatch" and milestone:
        note += f" — milestone on record ({milestone.get('year')}): {str(milestone.get('description'))[:200]}"
    if r.quote:
        note += f" | quote: {r.quote[:200]}"
    confidence = "verified" if r.source_kind in ("company", "filing") else "reported"
    return {
        "company": company_id,
        "event_type": "funding",
        "summary": summary,
        "occurred_on": occurred.isoformat(),
        "date_precision": precision,
        "confidence": confidence,
        "severity": "major",
        "source_url": r.source_url[:500],
        "source_label": r.source_kind,
        "status": "draft",
        "kind": "change",
        "new_value": {"round": r.round, "amount": r.amount, "currency": r.currency,
                      "amount_text": r.amount_text or None, "lead_investors": r.lead_investors,
                      "participating_investors": r.participating_investors},
        "review_note": note[:1000],
    }


def milestone_row(r: Round) -> dict[str, Any]:
    return {"year": r.year, "description": summary_for_round(r), "source_url": r.source_url[:500]}


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

@dataclass
class Stats:
    companies: int = 0
    searches: int = 0
    pages: int = 0
    gemini_calls: int = 0
    rounds_found: int = 0
    known: int = 0
    low_confidence: int = 0
    new: int = 0
    mismatch: int = 0
    filed: int = 0
    duplicates: int = 0
    milestones_written: int = 0
    stage_suggestions: int = 0
    deals_dropped: int = 0
    errors: int = 0


class FundingRecheck:
    def __init__(self, api: Any, *, search: Callable[..., list[dict[str, Any]]] = serper_search,
                 fetch: Callable[[str], str] = fetch_page_text, extract: Callable[..., list[Round]] = gemini_extract,
                 searches_per_company: int = 2, pages_per_company: int = 3, apply: bool = False,
                 write_milestones: bool = False, min_confidence: str = "medium", run_id: str = "",
                 makers_only: bool = True):
        self.api = api
        self.search = search
        self.fetch = fetch
        self.extract = extract
        self.searches_per_company = max(0, searches_per_company)
        self.pages_per_company = max(0, pages_per_company)
        self.apply = apply
        self.write_milestones = write_milestones and apply
        self.min_confidence = min_confidence
        self.run_id = run_id or datetime.now().strftime("%Y%m%d-%H%M")
        self.makers_only = makers_only
        self.stats = Stats()
        self.records: list[dict[str, Any]] = []

    # -- selection ----------------------------------------------------------

    def iter_companies(self, *, limit: int, company_ids: list[int] | None = None, start_page: int = 1,
                       exclude: set[int] | None = None) -> Iterable[dict[str, Any]]:
        if company_ids:
            for cid in company_ids[:limit]:
                yield {"id": cid}
            return
        page, yielded = start_page, 0
        while yielded < limit:
            data = self.api._get("companies/", params={"lite": 1, "page": page, "page_size": 100,
                                                       "ordering": "-public_robot_count,name"})
            rows = data.get("results") if isinstance(data, dict) else data
            if not rows:
                return
            for row in rows:
                if (row.get("publication_status") or "published") != "published":
                    continue
                if exclude and row.get("id") in exclude:
                    continue
                roles = row.get("roles") or []
                if self.makers_only and roles and "maker" not in roles:
                    continue
                yield row
                yielded += 1
                if yielded >= limit:
                    return
            if isinstance(data, dict) and not data.get("next"):
                return
            page += 1

    # -- one company --------------------------------------------------------

    def evidence_for(self, company: dict[str, Any]) -> list[dict[str, str]]:
        name, website = company.get("name") or "", company.get("website") or ""
        results: list[dict[str, Any]] = []
        for q in funding_queries(name, website)[: self.searches_per_company]:
            self.stats.searches += 1
            results += self.search(q)
        links = select_links(results, website, self.pages_per_company)
        evidence: list[dict[str, str]] = []
        for item in links:
            self.stats.pages += 1
            text = self.fetch(item["link"])
            if not text.strip():
                text = f"{item.get('title', '')}\n{item.get('snippet', '')}"
            if item.get("date"):
                text = f"Result date: {item['date']}\n{text}"
            evidence.append({"url": item["link"], "text": text})
        # Snippets of the results we did not open still carry dates and amounts.
        # One block each, so a round taken from a snippet still cites that page.
        opened = {i["link"] for i in links}
        seen: set[str] = set()
        for i in results:
            link = (i.get("link") or "").strip()
            if not link or link in opened or link in seen or is_skipped_domain(link):
                continue
            seen.add(link)
            if len(seen) > 8:
                break
            evidence.append({"url": link, "text": f"Search result ({i.get('date', '')}): {i.get('title', '')}\n{i.get('snippet', '')}"})
        return evidence

    def process(self, brief: dict[str, Any], *, since_year: int | None = None) -> dict[str, Any]:
        cid = int(brief["id"])
        company = self.api.get_company(cid)
        milestones = list(company.get("milestones") or company.get("timeline") or [])
        record: dict[str, Any] = {"company_id": cid, "name": company.get("name"), "rounds": [], "skipped": ""}
        if (company.get("publication_status") or "published") != "published":
            record["skipped"] = "not published"
            return record
        if since_year and (latest_funding_year(milestones) or 0) < since_year:
            record["skipped"] = f"no funding milestone since {since_year}"
            return record
        self.stats.companies += 1
        evidence = self.evidence_for(company)
        if not evidence:
            record["skipped"] = "no evidence found"
            return record
        self.stats.gemini_calls += 1
        extracted = self.extract(company, evidence)
        deals_made = [r for r in extracted if is_deal_made_by(company.get("name") or "", r)]
        if deals_made:
            self.stats.deals_dropped += len(deals_made)
            record["deals_dropped"] = [summary_for_round(r) + " | " + (r.quote or "")[:120] for r in deals_made]
        rounds = collapse_rounds([r for r in extracted if r not in deals_made])
        self.stats.rounds_found += len(rounds)
        order = {"low": 0, "medium": 1, "high": 2}
        confident = [r for r in rounds if order.get(r.confidence, 1) >= order.get(self.min_confidence, 1)]
        # Where the company is now: the furthest stage the evidence proves,
        # against the funding stage on the profile. Reported, never written.
        suggested = stage_from_rounds(confident)
        on_record = company.get("company_maturity") or ""
        # A listed company is public whatever early rounds the evidence
        # recalls; suggesting "series_b" for Yaskawa would be noise.
        if (company.get("company_status") or "").lower() == "public":
            suggested = "public_company" if on_record != "public_company" else None
        if stage_is_later(suggested, on_record):
            record["stage"] = {"on_record": on_record or None, "suggested": suggested}
            self.stats.stage_suggestions += 1
        new_milestones: list[dict[str, Any]] = []
        for r in rounds:
            entry: dict[str, Any] = {**asdict(r), "summary": summary_for_round(r)}
            if order.get(r.confidence, 1) < order.get(self.min_confidence, 1):
                entry["relation"] = "low_confidence"
                self.stats.low_confidence += 1
                record["rounds"].append(entry)
                continue
            relation, m = match_existing(r, milestones)
            entry["relation"] = relation
            if relation == "known":
                self.stats.known += 1
            else:
                self.stats.new += relation == "new"
                self.stats.mismatch += relation == "mismatch"
                payload = change_payload(cid, r, relation, m, self.run_id)
                if record.get("stage") and stage_of_round(r.round) == record["stage"]["suggested"]:
                    payload["review_note"] = (payload["review_note"] + f" | stage on record: {on_record or 'none'}; "
                                              f"evidence suggests {suggested}")[:1000]
                entry["payload"] = payload
                if self.apply:
                    entry["result"] = self.file_event(payload)
                    if relation == "new" and self.write_milestones and entry["result"] == "filed":
                        new_milestones.append(milestone_row(r))
            record["rounds"].append(entry)
        if new_milestones:
            self.append_milestones(cid, milestones, new_milestones)
            record["milestones_added"] = new_milestones
        return record

    def file_event(self, payload: dict[str, Any]) -> str:
        try:
            try:
                self.api._post("changes/", payload)
            except requests.HTTPError as exc:
                # A 502/503/504 is the gateway, not the request: retry once.
                if getattr(exc.response, "status_code", None) not in (502, 503, 504):
                    raise
                time.sleep(10)
                self.api._post("changes/", payload)
        except requests.HTTPError as exc:
            status = getattr(exc.response, "status_code", None)
            if status == 409:
                self.stats.duplicates += 1
                return "duplicate"
            self.stats.errors += 1
            body = getattr(exc.response, "text", "")[:200]
            print(f"  [changes] POST failed {status}: {body}", flush=True)
            return f"error {status}"
        self.stats.filed += 1
        return "filed"

    def append_milestones(self, cid: int, existing: list[dict[str, Any]], new_rows: list[dict[str, Any]]) -> None:
        rows = [{"year": m.get("year"), "description": m.get("description"), "source_url": m.get("source_url") or "",
                 "sort_order": i} for i, m in enumerate(existing)]
        rows += [{**r, "sort_order": len(rows) + i} for i, r in enumerate(new_rows)]
        try:
            self.api.patch_company(cid, {"milestones": rows})
            self.stats.milestones_written += len(new_rows)
        except requests.HTTPError as exc:
            self.stats.errors += 1
            print(f"  [milestones] PATCH failed {getattr(exc.response, 'status_code', None)}", flush=True)

    # -- loop ---------------------------------------------------------------

    def run(self, *, limit: int, company_ids: list[int] | None, since_year: int | None, start_page: int, pause: float,
            exclude: set[int] | None = None) -> None:
        for brief in self.iter_companies(limit=limit, company_ids=company_ids, start_page=start_page, exclude=exclude):
            try:
                try:
                    record = self.process(brief, since_year=since_year)
                except requests.ConnectionError:
                    # The prod API resets a connection now and then under load;
                    # one retry after a pause clears nearly all of them.
                    time.sleep(10)
                    record = self.process(brief, since_year=since_year)
            except Exception as exc:  # noqa: BLE001
                if type(exc).__name__ == "SpendBudgetExceeded":
                    print(f"STOP: {exc}", flush=True)
                    break
                self.stats.errors += 1
                record = {"company_id": brief.get("id"), "name": brief.get("name"), "error": f"{type(exc).__name__}: {exc}"[:300]}
                print(f"  [error] company {brief.get('id')}: {record['error']}", flush=True)
            self.records.append(record)
            self.print_record(record)
            if pause:
                time.sleep(pause)

    @staticmethod
    def print_record(record: dict[str, Any]) -> None:
        head = f"[{record.get('company_id')}] {record.get('name')}"
        if record.get("error"):
            print(f"{head}: ERROR {record['error']}", flush=True)
            return
        if record.get("skipped"):
            print(f"{head}: skipped ({record['skipped']})", flush=True)
            return
        if not record.get("rounds"):
            print(f"{head}: no rounds in evidence", flush=True)
            return
        print(head, flush=True)
        for r in sorted(record["rounds"], key=lambda x: x.get("date", "")):
            tag = r.get("relation")
            res = f" -> {r['result']}" if r.get("result") else ""
            print(f"    {tag:<14} {r['date']:<10} {r['summary']}  [{r.get('source_kind')}, {r.get('confidence')}] {r.get('source_url', '')}{res}", flush=True)
        if record.get("stage"):
            print(f"    stage: on record {record['stage']['on_record'] or 'none'}, evidence suggests {record['stage']['suggested']}", flush=True)

    def summary(self) -> str:
        s = self.stats
        spend = ""
        try:
            import spend_guard
            spend = f"\nGEMINI SPEND: {json.dumps(spend_guard.status(), default=str)}"
        except Exception:
            pass
        mode = "APPLY" if self.apply else "DRY RUN"
        return (f"\n{mode} run {self.run_id}: companies={s.companies} searches={s.searches} pages={s.pages} "
                f"gemini_calls={s.gemini_calls} rounds={s.rounds_found} known={s.known} new={s.new} "
                f"mismatch={s.mismatch} low_confidence={s.low_confidence} filed={s.filed} duplicates={s.duplicates} "
                f"milestones_written={s.milestones_written} stage_suggestions={s.stage_suggestions} deals_dropped={s.deals_dropped} "
                f"errors={s.errors}{spend}")


def done_company_ids(patterns: list[str]) -> set[int]:
    """Company ids processed in earlier runs (records without an error)."""
    import glob

    done: set[int] = set()
    for pattern in patterns or []:
        for path in glob.glob(pattern):
            try:
                data = json.loads(Path(path).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            for rec in data.get("records", []):
                if rec.get("company_id") and not rec.get("error"):
                    done.add(int(rec["company_id"]))
    return done


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--limit", type=int, default=50, help="companies to process this run (default 50)")
    ap.add_argument("--max-companies", type=int, default=400, help="hard cap on --limit (default 400)")
    ap.add_argument("--company-id", type=int, action="append", help="only this company (repeatable)")
    ap.add_argument("--start-page", type=int, default=1, help="list page to start from (100 per page, most robots first)")
    ap.add_argument("--since-days", type=int, default=0,
                    help="only companies with a funding milestone in the last N days (year granularity)")
    ap.add_argument("--searches", type=int, default=2, help="serper searches per company (default 2)")
    ap.add_argument("--pages", type=int, default=3, help="result pages fetched per company (default 3)")
    ap.add_argument("--min-confidence", choices=("low", "medium", "high"), default="medium")
    ap.add_argument("--pause", type=float, default=0.5, help="seconds between companies")
    ap.add_argument("--apply", action="store_true", help="file draft change events (default: dry run)")
    ap.add_argument("--write-milestones", action="store_true",
                    help="with --apply: also append NEW rounds to the public profile milestones")
    ap.add_argument("--out", default="", help="snapshot JSON path (default output/funding_recheck_<run>.json)")
    ap.add_argument("--include-operators", action="store_true",
                    help="also check companies whose roles do not include maker (operators, sellers)")
    ap.add_argument("--exclude-snapshots", action="append", default=[],
                    help="glob of earlier snapshot JSONs; companies in them are skipped (repeatable)")
    args = ap.parse_args(argv)

    filled = load_env_file()
    if filled:
        print(f"env from {_ENV_FILE.name}: {', '.join(filled)}", flush=True)
    for key in ("IMPORT_SYNC_API_BASE_URL", "IMPORT_SYNC_API_KEY"):
        if not os.environ.get(key):
            print(f"missing env {key}", file=sys.stderr)
            return 2
    if not os.environ.get("SERPER_API_KEY"):
        print("missing env SERPER_API_KEY (no searches possible)", file=sys.stderr)
        return 2
    if not os.environ.get("GEMINI_API_KEY"):
        print("missing env GEMINI_API_KEY (no extraction possible)", file=sys.stderr)
        return 2

    from api_client import ResearchApiClient
    limit = min(args.limit, args.max_companies)
    since_year = date.today().year - max(0, args.since_days) // 365 if args.since_days else None
    job = FundingRecheck(ResearchApiClient(), searches_per_company=args.searches, pages_per_company=args.pages,
                         apply=args.apply, write_milestones=args.write_milestones, min_confidence=args.min_confidence,
                         makers_only=not args.include_operators)
    print(f"{'APPLY' if args.apply else 'DRY RUN'} funding re-check {job.run_id}: up to {limit} companies, "
          f"{args.searches} searches + {args.pages} pages + 1 Gemini call each"
          f"{' (+ milestones)' if job.write_milestones else ''}", flush=True)
    exclude = done_company_ids(args.exclude_snapshots)
    if args.exclude_snapshots:
        print(f"skipping {len(exclude)} companies already in earlier snapshots", flush=True)
    job.run(limit=limit, company_ids=args.company_id, since_year=since_year, start_page=args.start_page, pause=args.pause,
            exclude=exclude)

    out = Path(args.out) if args.out else _HERE / "output" / f"funding_recheck_{job.run_id}.json"
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"run_id": job.run_id, "apply": args.apply, "stats": asdict(job.stats),
                                   "records": job.records}, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
        print(f"snapshot: {out}", flush=True)
    except OSError as exc:
        print(f"snapshot not written: {exc}", flush=True)
    print(job.summary(), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
