"""Check a funding event against the page it cites.

A funding round is only worth showing if the source it cites actually says it.
The 2026-10-20 audit of the change history found the recheck agent's rows
failing in five ways, and each is a check here:

  * page not checkable    - blocked, empty, unreadable PDF      -> UNVERIFIABLE
  * data mill             - a Crunchbase/PitchBook restater      -> FAIL
  * company not on page   - the page is about someone else       -> FAIL
  * amount not on page    - the figure is not in the source      -> FAIL
  * wrong kind of money   - a valuation, a fund, a joint venture
                            or order pipeline, revenue           -> FAIL
  * company is the buyer  - a deal it made, not money it got     -> FAIL

`verify_event(event, page_text)` is pure (no network), so it is shared by the
one-off audit of rows already filed (this module's CLI) and by the recheck
agent's gate before it files anything (recheck_company_funding.py).

CLI (audit):  python verify_funding_source.py --events EXPORT.json --out VERDICTS.json
EXPORT.json is a list of change-event dicts (id, company, summary, source_url,
new_value, review_note, ...). Pages are fetched once per URL and cached in
--cache so a rerun does not refetch.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

PASS, FAIL, UNVERIFIABLE = "pass", "fail", "unverifiable"
MIN_PAGE_CHARS = 400

_MULT = {"billion": 1e9, "bn": 1e9, "b": 1e9, "million": 1e6, "mn": 1e6, "mln": 1e6, "m": 1e6,
         "thousand": 1e3, "k": 1e3, "亿": 1e8, "万": 1e4, "億": 1e8, "萬": 1e4, "crore": 1e7, "lakh": 1e5}
_NUM_RE = re.compile(
    r"(?<![\w.])(\d{1,3}(?:[,.]\d{3})+|\d+(?:\.\d+)?)\s*"
    r"(billion|bn|million|mn|mln|thousand|crore|lakh|亿|萬|万|億|[bmk](?![a-z]))?",
    re.I)

# Wording that makes a figure something other than money the company received.
_WRONG_MONEY = [
    ("valuation", re.compile(r"\bvaluation\b|\bvalued at\b|\bvaluing\b|\bmarket (?:cap|capitali[sz]ation|value)\b|\bworth\b|估值|市值", re.I)),
    ("fund", re.compile(r"\b(?:venture |investment |innovation )?fund (?:size|of)\b|\blaunch(?:es|ed)? (?:a |its )?\S*\s*fund\b|"
                        r"\bclos(?:es|ed) (?:its |a )?\S*\s*fund\b|\bfund(?:s)? (?:totall?ing|worth)\b|基金规模", re.I)),
    ("joint venture / pipeline", re.compile(r"\bjoint[- ]venture\b|\bpipeline\b|\border(?:s| book)?\b|\bbacklog\b|\bcontract(?:s)? worth\b|"
                                            r"\bframework agreement\b|合资|订单", re.I)),
    ("revenue", re.compile(r"\brevenue\b|\bsales of\b|\bturnover\b|营收|营业收入", re.I)),
]
_WINDOW = 60  # characters before a figure that decide what the figure is

# A quote about money the company SPENT (acquisitions it made) or a unit it SOLD.
_SPEND_RE = re.compile(r"\bacquisitions?\b|\bto acquire\b|\bacquir(?:ed|es|ing)\b|\bpaying\b|\bconsideration for\b|"
                       r"\bpurchase (?:of|price)\b|\bto buy\b|\bequity interests of\b|"
                       r"\binvest(?:ed|s|ing)? (?:\S+ ){0,3}in(?:to)?\b|\binvestment in\b", re.I)
_UNIT_SALE_RE = re.compile(r"\bbuys?\s+(?:out\s+)?\S+(?:'s|’s)\s+(?:\w+\s+){0,2}(?:business|unit|division|arm)\b|"
                           r"\bsold (?:off )?(?:its|their|the) (?:\w+ ){0,2}(?:business|unit|division|arm)\b|"
                           r"\bdivest\w*\b|\bspin(?:s|ning)? off\b|\bcarve-?out\b", re.I)
_JV_QUOTE_RE = re.compile(r"\bjoint[- ]ventures?\b|\bforged a pact\b|\bcreate a new (?:\w+ )?company\b", re.I)
_RAISE_WORDS_RE = re.compile(r"\braise[sd]?\b|\braising\b|\bfunding\b|\bseries [a-h]\d?\b|\brights (?:issue|offering)\b|"
                             r"\bipo\b|\bplacement\b|\bbonds?\b|\bfinancing\b|\bsecures?\b|\bclos(?:es|ed) (?:a|its)\b|"
                             r"\binvestment from\b|\battract(?:s|ed)\b|\breceiv(?:es|ed)\b|\bthe round\b|\bparticipation from\b", re.I)
_BACKER_MARK_RE = re.compile(r"\bfrom\b|\bled by\b|\bby\b|\bincluding\b|\binvestors?\b|\bparticipat", re.I)


def _words(name: str, strip_brackets: bool = True) -> str:
    text = re.sub(r"\([^)]*\)", "", name or "") if strip_brackets else (name or "")
    return " ".join(t for t in re.split(r"[^\w]+", text.lower()) if t)


def _is_self(company: str, name: str) -> bool:
    """The investor / acquirer named is the company itself (or its own arm, e.g.
    'Waseda University Ventures' for Waseda University). A parent buying the
    company ('Amazon' for Amazon Robotics) is not."""
    # A bracketed record ('Chowbotics (DoorDash)', 'QinetiQ (Foster-Miller)') names a parent and a
    # unit: the parent buying the unit is real, so only the WHOLE name counts as self.
    own, other = _words(company, strip_brackets=False), _words(name, strip_brackets=False)
    return bool(own) and "founder" not in other and re.search(r"(?:^| )" + re.escape(own) + r"(?: |$)", other) is not None


def _company_is_recipient(company: str, quote: str) -> bool:
    """The quote names the company as the one raising: its name comes before any
    'from / led by / investors' wording and the quote says money came in."""
    from recheck_company_funding import _GENERIC_NAME_WORDS

    low = (quote or "").lower()
    mark = _BACKER_MARK_RE.search(low)
    head = low[:mark.start()] if mark else low
    toks = [t for t in _words(company).split() if len(t) >= 3 and t not in _GENERIC_NAME_WORDS]
    return bool(toks) and all(re.search(r"\b" + re.escape(t), head) for t in toks) and bool(_RAISE_WORDS_RE.search(low))


def _company_is_target(company: str, quote: str) -> bool:
    """'EQT has acquired a stake in BBS Automation' - the company is what was bought into."""
    from recheck_company_funding import _name_tokens

    low = (quote or "").lower()
    for m in _SPEND_RE.finditer(low):
        tail = low[m.end():m.end() + 60]
        if re.match(r"\s*(?:the company|it)\b", tail):
            return True
        if any(re.search(r"\b" + re.escape(t), tail) for t in _name_tokens(company, limit=1)):
            return True
    return False


def page_numbers(text: str) -> list[tuple[float, int]]:
    """Every figure on the page in whole units with its position:
    '520 million' -> 520e6, 'US$1.5B' -> 1.5e9, '1.5亿' -> 1.5e8."""
    out: list[tuple[float, int]] = []
    for m in _NUM_RE.finditer(text or ""):
        raw, unit = m.group(1), (m.group(2) or "").lower()
        if re.fullmatch(r"\d{1,3}(?:\.\d{3}){2,}", raw):  # 1.234.567 (European thousands)
            raw = raw.replace(".", "")
        raw = raw.replace(",", "")                        # 1,234,567
        try:
            n = float(raw)
        except ValueError:
            continue
        out.append((n * _MULT.get(unit, 1), m.start()))
    return out


def _close(a: float, b: float, tol: float = 0.03) -> bool:
    return b > 0 and abs(a - b) <= max(1.0, b * tol)


def _quote_overlap(quote: str, text: str) -> float:
    words = [w for w in re.findall(r"[\w$€£¥]+", (quote or "").lower()) if len(w) >= 4]
    if not words:
        return 1.0
    low = (text or "").lower()
    return sum(1 for w in words if w in low) / len(words)


def event_quote(event: dict[str, Any]) -> str:
    note = event.get("review_note") or ""
    m = re.search(r"quote:\s*(.+?)(?:\s*\|\s*stage on record|$)", note)
    return (m.group(1).strip() if m else "") or (event.get("quote") or "")


def event_amount(event: dict[str, Any]) -> float | None:
    nv = event.get("new_value") or {}
    if isinstance(nv, dict) and nv.get("amount") not in (None, ""):
        try:
            v = float(nv["amount"])
            return v if v > 0 else None
        except (TypeError, ValueError):
            return None
    # backfill rows carry the amount in the summary only
    nums = [n for n, _ in page_numbers(event.get("summary") or "") if n >= 1e4]
    return max(nums) if nums else None


def company_on_page(company: str, text: str) -> bool:
    from recheck_company_funding import _name_tokens

    low = (text or "").lower()
    names = [company or ""]
    bracket = re.search(r"\(([^)]+)\)", company or "")
    if bracket:
        names = [company[:bracket.start()], bracket.group(1)]
    for name in names:
        cjk = "".join(re.findall(r"[一-鿿぀-ヿ]+", name))
        if len(cjk) >= 2 and cjk[:4] in (text or ""):
            return True
        for tok in _name_tokens(name, limit=3):
            if re.search(r"\b" + re.escape(tok) + r"\b", low):
                return True
    return False


def verify_event(event: dict[str, Any], page_text: str | None, *, page_url: str = "") -> tuple[str, list[str]]:
    """(verdict, reasons). Pure: the caller supplies the page text."""
    from recheck_company_funding import Round, is_deal_made_by, is_skipped_domain

    url = page_url or event.get("source_url") or ""
    if not url:
        return FAIL, ["no source"]
    if is_skipped_domain(url):
        return FAIL, ["data mill"]
    text = page_text or ""
    if len(text.strip()) < MIN_PAGE_CHARS:
        return UNVERIFIABLE, ["page not readable"]

    company = event.get("company") or ""
    quote = event_quote(event)
    reasons: list[str] = []

    if not company_on_page(company, text):
        return FAIL, ["company not on page"]

    amount = event_amount(event)
    hits = [pos for n, pos in page_numbers(text) if _close(n, amount)] if amount else []
    if amount and not hits:
        reasons.append("amount not on page")

    overlap = _quote_overlap(quote, text)
    if quote and overlap < 0.5 and not hits:
        reasons.append("quote not on page")

    # What the figure is: read the words just before each place it appears.
    if hits:
        kinds: set[str] = set()
        clean = False
        for pos in hits:
            before = text[max(0, pos - _WINDOW):pos]
            found = [label for label, rx in _WRONG_MONEY if rx.search(before)]
            if found:
                kinds.update(found)
            else:
                clean = True
        if kinds and not clean:
            reasons.append(" / ".join(sorted(kinds)))
    for label, rx in _WRONG_MONEY:
        if quote and label in ("valuation", "fund", "joint venture / pipeline") and rx.search(quote) \
                and not re.search(r"\braised?\b|\bfunding\b|\bround\b|\binvest", quote, re.I):
            reasons.append(f"quote describes a {label}")
            break

    rnd = Round(event.get("occurred_on") or "", (event.get("new_value") or {}).get("round") or "Funding round"
                if isinstance(event.get("new_value"), dict) else "Funding round",
                amount, None, quote=quote)
    nv = event.get("new_value") if isinstance(event.get("new_value"), dict) else {}
    backers = [] if _company_is_recipient(company, quote) else \
        list(nv.get("lead_investors") or []) + list(nv.get("participating_investors") or [])
    acquired_by = re.match(r"acquired by (.+?)(?: for |$)", event.get("summary") or "", re.I)
    if acquired_by:
        backers.append(acquired_by.group(1))
    if any(_is_self(company, b) for b in backers):
        reasons.append("company is the investor or buyer")
    elif is_deal_made_by(company, rnd):
        reasons.append("company is the buyer")
    elif quote and not (event.get("summary") or "").lower().startswith("acquired by "):
        # An acquisition OF the company names its buyer; anything else whose quote is about
        # spending, selling a unit or forming a JV is not money the company raised.
        raised = _RAISE_WORDS_RE.search(quote)
        if _SPEND_RE.search(quote) and not raised and not _company_is_target(company, quote):
            reasons.append("quote is about money the company spent")
        elif _UNIT_SALE_RE.search(quote) and not raised:
            reasons.append("quote is about a business the company sold")
        elif _JV_QUOTE_RE.search(quote) and not re.search(r"\braise[sd]?\b|\bseries [a-h]\b|\brights issue\b", quote, re.I):
            reasons.append("quote describes a joint venture")

    return (FAIL, reasons) if reasons else (PASS, [])


# ---------------------------------------------------------------------------
# Fetching (CLI audit only)
# ---------------------------------------------------------------------------

def fetch_text(url: str, fetcher: Any) -> str:
    """Readable text of a page or PDF; '' when it cannot be read."""
    import requests

    try:
        if url.lower().split("?")[0].endswith(".pdf"):
            resp = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0 (RobotAIGeek verifier)"})
            if not resp.ok:
                return ""
            from io import BytesIO

            from pypdf import PdfReader
            reader = PdfReader(BytesIO(resp.content))
            return "\n".join((p.extract_text() or "") for p in reader.pages[:40])
        import web_extract
        page = web_extract.parse_page(fetcher, url)
        if page is None:
            return ""
        return page.text or page.main_text or ""
    except Exception:  # noqa: BLE001 - an unreadable page is a verdict, not a crash
        return ""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Audit filed funding events against their cited pages.")
    ap.add_argument("--events", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cache", default="", help="URL -> page text cache (JSON), reused across runs")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--serper-budget", type=int, default=300, help="cap on paid scrape.serper.dev calls")
    args = ap.parse_args(argv)

    from recheck_company_funding import load_env_file
    load_env_file()
    import web_extract

    events = [e for e in json.loads(Path(args.events).read_text(encoding="utf-8"))
              if e.get("event_type") == "funding"]
    cache_path = Path(args.cache) if args.cache else None
    cache: dict[str, str] = {}
    if cache_path and cache_path.exists():
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
    urls = sorted({e["source_url"] for e in events if e.get("source_url")} - set(cache))
    print(f"{len(events)} funding events, {len(urls)} pages to fetch ({len(cache)} cached)", flush=True)

    fetcher = web_extract.WebFetcher(serper_budget=args.serper_budget)
    lock = threading.Lock()
    done = 0

    def work(u: str) -> tuple[str, str]:
        return u, fetch_text(u, fetcher)

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = [pool.submit(work, u) for u in urls]
        for fut in as_completed(futures):
            u, text = fut.result()
            with lock:
                cache[u] = text[:200000]
                done += 1
                if done % 50 == 0:
                    print(f"  fetched {done}/{len(urls)}", flush=True)
                    if cache_path:
                        cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    if cache_path:
        cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")

    verdicts = []
    for e in events:
        verdict, reasons = verify_event(e, cache.get(e.get("source_url") or ""))
        verdicts.append({"id": e["id"], "status": e.get("status"), "origin": e.get("origin"), "company": e.get("company"),
                         "summary": e.get("summary"), "source_url": e.get("source_url"),
                         "verdict": verdict, "reasons": reasons})
    Path(args.out).write_text(json.dumps(verdicts, ensure_ascii=False, indent=1), encoding="utf-8")
    from collections import Counter
    print("verdicts:", dict(Counter(v["verdict"] for v in verdicts)))
    print("by status:", dict(Counter((v["status"], v["verdict"]) for v in verdicts)))
    print("fail reasons:", Counter(r for v in verdicts for r in v["reasons"]).most_common(12))
    return 0


if __name__ == "__main__":
    sys.exit(main())
