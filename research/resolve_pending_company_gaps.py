"""Fix the COMPANY-level gaps that leave pending robots un-enrichable or blank.

Two fields, one pass over the pending queue, because both are properties of the
manufacturer rather than of any one robot — fixing the Company fixes every robot
it owns at once.

**website** — a company without one is INVISIBLE to enrichment:
`overnight_queue_enrich` soft-skips it ("auto enrich needs OEM site") and every
remedy SKIPs for the same reason. Measured 2026-07-29: 60 companies / 345
pending robots were parked in To Review with un-fixed flags purely because this
field was blank (Fujitsu and igus among them). Company 1503 was the proof:
resolving its website turned six never-touched robots into six photo fixes.

**country** — `missing_manufacturer_country` is an ERROR-severity flag, and
enrichment fills a robot's country by copying `company.country`, so a blank
Company field reproduces the blank on every robot it will ever own. Measured
2026-07-31: 232 of 806 companies had no country, 633 pending robots belonged to
one, and 351 pending robots carried the flag.

Both resolvers are fail-closed. A wrong website poisons every later enrichment
for that company and a wrong country mislabels the manufacturer on every robot
page and country facet — in both cases worse than staying blank — so ambiguous
candidates are reported, never guessed.

  python -u resolve_pending_company_gaps.py                 # dry-run: report only
  python -u resolve_pending_company_gaps.py --apply
  python -u resolve_pending_company_gaps.py --apply --max-companies 10
  python -u resolve_pending_company_gaps.py --apply --only country
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from load_env import load_research_env  # noqa: E402

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient  # noqa: E402
from company_country_resolve import resolve_company_country  # noqa: E402
from company_website_resolve import resolve_company_website  # noqa: E402

REPORT_PATH = _RESEARCH_DIR / "staging" / "reports" / "company-gap-resolve-report.json"
# Companies whose resolution failed are not retried for this long — same anti-waste
# contract as the enrichment stall ledger; a company with no findable site today
# rarely has one tomorrow.
STATE_PATH = _RESEARCH_DIR / "staging" / "state" / "website_resolve_attempts.json"
RETRY_COOLDOWN_HOURS = 7 * 24


def _p(*a):
    try:
        print(*a, flush=True)
    except UnicodeEncodeError:
        print(" ".join(str(x) for x in a).encode("ascii", "replace").decode(), flush=True)


def _load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _recently_failed(state: dict, cid: int, field: str) -> bool:
    entry = (state.get(str(cid)) or {}).get(field)
    if not entry:
        return False
    try:
        at = datetime.fromisoformat(str(entry.get("at")).replace("Z", "+00:00"))
    except Exception:
        return False
    return (datetime.now(timezone.utc) - at).total_seconds() / 3600.0 < RETRY_COOLDOWN_HOURS


def _mark_failed(state: dict, cid: int, field: str, why: str) -> None:
    state.setdefault(str(cid), {})[field] = {
        "at": datetime.now(timezone.utc).isoformat(), "why": why,
    }


def _clear_failed(state: dict, cid: int, field: str) -> None:
    entry = state.get(str(cid))
    if isinstance(entry, dict):
        entry.pop(field, None)
        if not entry:
            state.pop(str(cid), None)


def companies_with_gaps(client: ResearchApiClient) -> list[dict]:
    """Companies of pending robots missing a website and/or a country.

    One pass over the pending queue serves both fields: `company_ref` carries
    `website` and `country` already, and paginating 1600 robots twice was ~7
    minutes of every nightly cycle for no extra information. Busiest first.
    """
    counts: dict[int, dict] = {}
    page = 1
    while page <= 40:
        for attempt in range(4):
            try:
                data = client._get("robots/robots/", params={
                    "status": "pending_review", "page": page, "page_size": 50})
                break
            except Exception:
                time.sleep(2 ** attempt)
        else:
            break
        for r in data.get("results") or []:
            cref = r.get("company_ref") if isinstance(r.get("company_ref"), dict) else {}
            cid = cref.get("id")
            if not cid:
                continue
            country = cref.get("country")
            has_country = bool(
                (country.get("code") or country.get("id")) if isinstance(country, dict) else country
            )
            website = (cref.get("website") or "").strip()
            if website and has_country:
                continue
            e = counts.setdefault(int(cid), {
                "company_id": int(cid),
                "name": cref.get("name") or "",
                "slug": cref.get("slug") or "",
                "website": website,
                "needs_website": not website,
                "needs_country": not has_country,
                "pending": 0,
            })
            e["pending"] += 1
        if not data.get("next"):
            break
        page += 1
    return sorted(counts.values(), key=lambda e: -e["pending"])


def _resolve_website(client, target, state, args, row) -> bool:
    cid, name = target["company_id"], target["name"]
    if _recently_failed(state, cid, "website"):
        row["website_via"] = "cooldown"
        return False
    url, how = resolve_company_website(name, target["slug"])
    row["website_resolved"], row["website_via"] = url, how
    if not url:
        _p(f"  --   {cid:>5} {name[:36]:36} ({target['pending']:>2} pending) website unresolved [{how}]")
        _mark_failed(state, cid, "website", how)
        return False
    _p(f"  OK   {cid:>5} {name[:36]:36} ({target['pending']:>2} pending) -> {url}  [{how}]")
    if args.apply:
        try:
            client._patch(f"companies/{cid}/", {"website": url})
            fresh = client.get_company(cid)
            row["website_persisted"] = (fresh.get("website") or "").strip() == url
            if not row["website_persisted"]:
                _p(f"       !! website write did not persist for {cid}")
        except Exception as exc:  # noqa: BLE001
            row["website_persisted"] = False
            _p(f"       !! website patch failed: {type(exc).__name__}: {exc}")
    # Resolving the website unblocks the country tiers that read it.
    target["website"] = url
    _clear_failed(state, cid, "website")
    return True


def _resolve_country(client, target, state, args, row) -> bool:
    cid, name = target["company_id"], target["name"]
    if _recently_failed(state, cid, "country"):
        row["country_via"] = "cooldown"
        return False
    code, how = resolve_company_country(name, target.get("website") or "")
    row["country_resolved"], row["country_via"] = code, how
    if not code:
        _p(f"  --   {cid:>5} {name[:36]:36} ({target['pending']:>2} pending) country unresolved [{how}]")
        _mark_failed(state, cid, "country", how)
        return False
    country_id = client.resolve_country_id(code)
    if not country_id:
        # A code with no Country row would be silently dropped by the serializer;
        # say so rather than reporting a write that never happened.
        _p(f"  !!   {cid:>5} {name[:36]:36} resolved {code} but it is not in the Country table")
        row["country_via"] = f"{how} (no Country row for {code})"
        _mark_failed(state, cid, "country", row["country_via"])
        return False
    _p(f"  OK   {cid:>5} {name[:36]:36} ({target['pending']:>2} pending) -> {code}  [{how}]")
    if args.apply:
        try:
            client._patch(f"companies/{cid}/", {"country_id": country_id})
            fresh = client.get_company(cid) or {}
            got = fresh.get("country")
            got_code = (got.get("code") if isinstance(got, dict) else got) or ""
            row["country_persisted"] = str(got_code).upper() == code
            if not row["country_persisted"]:
                _p(f"       !! country write did not persist for {cid}")
        except Exception as exc:  # noqa: BLE001
            row["country_persisted"] = False
            _p(f"       !! country patch failed: {type(exc).__name__}: {exc}")
    _clear_failed(state, cid, "country")
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="WRITE resolved values (default: report only)")
    ap.add_argument("--max-companies", type=int, default=0, help="0 = all")
    ap.add_argument("--only", choices=("website", "country"), default="",
                    help="resolve just one field (default: both)")
    ap.add_argument("--local", action="store_true")
    args = ap.parse_args()

    do_website = args.only in ("", "website")
    do_country = args.only in ("", "country")

    client = ResearchApiClient()
    state = _load_state()
    targets = companies_with_gaps(client)
    n_web = sum(1 for t in targets if t["needs_website"])
    n_country = sum(1 for t in targets if t["needs_country"])
    _p(f"=== Company gap resolve ({'APPLY' if args.apply else 'DRY-RUN'}) — "
       f"{len(targets)} companies with pending robots; "
       f"{n_web} need a website, {n_country} need a country ===")
    if args.max_companies:
        targets = targets[: args.max_companies]

    stats = {"website_ok": 0, "website_miss": 0, "country_ok": 0, "country_miss": 0}
    rows = []
    for t in targets:
        row: dict = {**t}
        # Website first: every country tier below the ccTLD reads the site, so a
        # company resolved in this same pass gets a better country attempt.
        if do_website and t["needs_website"]:
            ok = _resolve_website(client, t, state, args, row)
            stats["website_ok" if ok else "website_miss"] += 1
        if do_country and t["needs_country"]:
            ok = _resolve_country(client, t, state, args, row)
            stats["country_ok" if ok else "country_miss"] += 1
        rows.append(row)
        time.sleep(0.3)

    if args.apply:
        _save_state(state)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    _p(f"\nwebsite resolved={stats['website_ok']} unresolved={stats['website_miss']} | "
       f"country resolved={stats['country_ok']} unresolved={stats['country_miss']}")
    _p(f"report -> {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
