"""Re-scrape FULL spec tables and fill any dims/speed/weight/payload/rep the first
(keyword-fragment, 1500-char-capped) pass silently dropped. Only fills blanks."""
from __future__ import annotations
import json, os, re, time
from html import unescape
from load_env import load_research_env
load_research_env()
from api_client import ResearchApiClient  # noqa: E402
try:
    from curl_cffi import requests as http
    def get(u): return http.get(u, impersonate="chrome124", timeout=25)
except Exception:
    import requests as http
    def get(u): return http.get(u, headers={"User-Agent": "Mozilla/5.0"}, timeout=25)

cache = {r["id"]: r for r in json.load(open(os.path.join(os.environ["TEMP"], "co1423.json"), encoding="utf-8"))}
client = ResearchApiClient()


def fulltext(html):
    t = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html)
    t = re.sub(r"(?s)<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", unescape(t))


def parse(s):
    out = {}
    m = re.search(r"Maximum payload[^0-9]*?([\d.]+)\s*kg", s, re.I)
    if m: out["payload_kg"] = float(m.group(1))
    m = re.search(r"Weight[^0-9]{0,40}?([\d.]+)\s*KG", s, re.I)
    if m: out["weight_kg"] = float(m.group(1))
    m = re.search(r"[Dd]imension[s]?[^0-9]{0,40}?(\d+)\s*\*\s*(\d+)\s*\*\s*(\d+)\s*mm", s)
    if m: out["length_mm"], out["width_mm"], out["height_mm"] = float(m[1]), float(m[2]), float(m[3])
    m = re.search(r"[Oo]peration speed[^0-9]*?([\d.]+)\s*m/s", s)
    if m: out["speed"] = round(float(m.group(1)) * 3.6, 2)
    m = re.search(r"Navigation position accuracy\s*(?:\[\d\])?\s*[±<]?\s*([\d.]+)\s*mm", s, re.I)
    if m: out["repeatability_mm"] = float(m.group(1))
    return out


def _bo(fn):
    for a in range(7):
        try:
            return fn()
        except Exception as e:
            if any(c in str(e) for c in ("429", "502", "503")):
                time.sleep(4 * (a + 1)); continue
            raise
    raise SystemExit("gave up")


import argparse
ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); args = ap.parse_args()

SPEC_COLS = ("payload_kg", "weight_kg", "length_mm", "width_mm", "height_mm", "speed", "repeatability_mm")
filled = 0
for rid, r in cache.items():
    cur = _bo(lambda: client._get(f"robots/robots/{rid}/"))
    missing = [k for k in SPEC_COLS if not cur.get(k)]
    if not missing:
        continue
    try:
        html = get(r["url"]).text
    except Exception as e:
        print(rid, "fetch ERR", e); continue
    parsed = parse(fulltext(html))
    add = {k: v for k, v in parsed.items() if k in missing and v}
    if not add:
        continue
    filled += len(add)
    print(f"{rid} {r['name'].replace('Wellwit Robotics','').strip():14} recovered {add}")
    if args.apply:
        _bo(lambda: client._patch(f"robots/robots/{rid}/", add))
    time.sleep(0.3)
print(f"\n{'applied' if args.apply else 'dry-run'}: recovered {filled} previously-dropped spec values")
