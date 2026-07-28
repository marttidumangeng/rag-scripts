"""Remap FANUC (189) dead source URLs to live fanucamerica.com pages.

Audit found 50 robots with a source URL that 404s: 26 on fanuc.eu with wrong slugs,
23 on fanucamerica.com pointing at series slugs that no longer resolve (e.g. DR-6iB ->
/series/dr, M-1iA -> /series/m-1, R-2000iD -> /series/r-2000e), 1 crx subdomain.

For each dead-url robot we build a prioritised list of CANDIDATE urls (correct series
slug from the probe below, then /products/robot/<model>, then a couple of variants) and
keep the FIRST that returns HTTP 200. Robots with no live page are left as-is and
reported (some heavy/education/DR models have no fanucamerica page at all).

URL is set via DRF PATCH (writable field). No media touched.

Usage:
  python fix_fanuc_urls.py            # dry-run (probes, shows the remap)
  python fix_fanuc_urls.py --apply
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except Exception:
    pass

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

import requests

from api_client import ResearchApiClient

COMPANY_ID = 189
FA = "https://www.fanucamerica.com"

# series-token -> verified live series slug (from the 2026-07-16 probe). Keys are the
# tokens series_key() produces (M-<num> before the 'i', so 'm-1' not 'm-1ia').
SERIES = {
    "lr mate": "lr-mate",
    "m-1": "m-1ia", "m-2": "m-2ia", "m-3": "m-3ia",
    "m-10": "m-10", "m-20": "m-20", "m-410": "m-410", "m-710": "m-710",
    "m-900": "m-900", "m-2000": "m-2000",
    "r-1000": "r-1000ia", "r-2000": "r-2000ic",
    "arc mate": "arc-mate",
    "crx": "crx", "scara": "scara",
    "p-40": "paint", "p-50": "paint", "p-250": "paint",
    "sr-": "scara",
}


def model_slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.replace("FANUC", "").strip().lower()).strip("-")


def series_key(name: str) -> str | None:
    """The SERIES-dict key for a model, matched on TOKEN boundaries (not raw prefix).

    'M-10iD/12'   -> 'm-10'     'M-1000iA/1000' -> 'm-1000'  (NOT 'm-10'!)
    'R-2000iD/..' -> 'r-2000'   'LR Mate 200iD' -> 'lr mate'
    'CRX-30iA/L'  -> 'crx'      'SR-3iA' -> 'sr-'  'P-40iB' -> 'p-40'
    """
    n = name.replace("FANUC", "").strip().lower()
    if n.startswith("lr mate"):
        return "lr mate"
    if n.startswith("arc mate"):
        return "arc mate"
    if n.startswith("crx"):
        return "crx"
    if n.startswith("sr-"):
        return "sr-"
    m = re.match(r"([mrp]-\d+)i", n)  # M-/R-/P- number before the 'i' generation marker
    if m:
        key = m.group(1)
        if key in SERIES:
            return key
        # P-40/P-250 painting → paint
        if key.startswith("p-"):
            return key if key in SERIES else "p-40"
    return None


def candidates(name: str):
    ms = model_slug(name)
    seen = []
    sk = series_key(name)
    if sk and sk in SERIES:
        seen.append(f"{FA}/products/robots/series/{SERIES[sk]}")
    # individual product page + a couple of slug variants (for DR/ER/M-800/M-810/M-1000 etc.)
    for u in (f"{FA}/products/robot/{ms}",
              f"{FA}/products/robots/series/{ms}",
              f"{FA}/products/robot/{ms.rsplit('-', 1)[0]}" if "-" in ms else ""):
        if u and u not in seen:
            seen.append(u)
    return seen


def main() -> int:
    ap = argparse.ArgumentParser(description="Remap dead FANUC source URLs")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    client = ResearchApiClient()
    robots = None
    for a in range(12):
        try:
            robots = client.list_robots_for_company(COMPANY_ID); break
        except Exception as e:
            print(f"list retry {a}: {str(e)[:60]}", file=sys.stderr); time.sleep(5)
    if robots is None:
        print("ERROR: fetch failed", file=sys.stderr); return 1

    S = requests.Session()
    S.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    cache: dict[str, int] = {}

    def code(u: str) -> int:
        if u in cache:
            return cache[u]
        try:
            r = S.get(u, timeout=25, allow_redirects=True)
            c = r.status_code
        except Exception:
            c = 0
        cache[u] = c
        time.sleep(0.1)
        return c

    pend = [r for r in robots if str(r.get("status") or "").lower() == "pending_review"]
    fixes, nofix = [], []
    for r in sorted(pend, key=lambda x: x["id"]):
        cur = (r.get("url") or "").strip()
        if cur and code(cur) == 200:
            continue  # already good
        picked = None
        for cand in candidates(r["name"]):
            if code(cand) == 200:
                picked = cand
                break
        if picked and picked != cur:
            fixes.append({"id": int(r["id"]), "name": r["name"], "old": cur, "new": picked})
            print(f"  {r['id']:<6}{r['name'][:24]:<25} {cur[-34:] or '(none)'} -> {picked.split('fanucamerica.com')[-1]}")
        else:
            nofix.append({"id": int(r["id"]), "name": r["name"], "old": cur})

    print(f"\nremap: {len(fixes)} | no live page found: {len(nofix)}")
    for x in nofix[:20]:
        print(f"   NOFIX {x['id']} {x['name'][:26]}: {x['old'][-40:]}")
    (_RESEARCH_DIR / "staging" / "reports" / "fanuc-urls-preview.json").write_text(
        json.dumps({"fixes": fixes, "nofix": nofix}, indent=2, ensure_ascii=False), encoding="utf-8")
    if not fixes:
        print("Nothing to remap."); return 0
    if not args.apply:
        print("Dry-run. Re-run with --apply"); return 0

    ok = fail = 0
    for x in fixes:
        try:
            client._patch(f"robots/robots/{x['id']}/", {"url": x["new"]})
            ok += 1
            print(f"  ok {x['id']} -> {x['new'].split('/series/')[-1]}")
        except Exception as e:
            fail += 1
            print(f"  FAIL {x['id']}: {str(e)[:60]}", file=sys.stderr)
        time.sleep(0.15)
    out = {"ok": fail == 0, "remapped": ok, "failed": fail, "nofix": len(nofix)}
    print(json.dumps(out, indent=2))
    (_RESEARCH_DIR / "staging" / "reports" / "fanuc-urls-result.json").write_text(
        json.dumps(out, indent=2) + "\n", encoding="utf-8")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
