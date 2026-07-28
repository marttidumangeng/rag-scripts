"""Scrape wellwit.com per-model pages for hero image + spec text (company 1423)."""
from __future__ import annotations
import json, os, re, time
from html import unescape
from urllib.parse import urljoin

robots = json.load(open(os.path.join(os.environ["TEMP"], "co1423.json"), encoding="utf-8"))

try:
    from curl_cffi import requests as http
    def get(u): return http.get(u, impersonate="chrome124", timeout=25)
except Exception:
    import requests as http
    def get(u): return http.get(u, headers={"User-Agent": "Mozilla/5.0"}, timeout=25)

SKIP = re.compile(r"(logo|icon|favicon|sprite|placeholder|loader|blank|spinner)", re.I)

def og_image(html, base):
    for pat in (r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']'):
        m = re.search(pat, html, re.I)
        if m: return urljoin(base, unescape(m.group(1)))
    return ""

def text(html):
    t = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html)
    t = re.sub(r"(?s)<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", unescape(t)).strip()

# spec keywords to surface for typed-column mapping
KW = re.compile(r"(load|payload|capacity|weight|speed|lifting|height|turning|radius|"
                r"battery|runtime|charging|dimension|width|length|precision|accuracy|"
                r"\d+\s*(kg|mm|m/s|km/h|kw|v|ah|wh|mm/s|ton|t\b))", re.I)

out = []
for r in robots:
    url = r.get("url") or ""
    rec = {"id": r["id"], "name": r["name"], "url": url, "og": "", "specs": "", "status": None}
    if url:
        try:
            resp = get(url)
            rec["status"] = resp.status_code
            if resp.status_code == 200:
                html = resp.text
                og = og_image(html, url)
                rec["og"] = "" if (og and SKIP.search(og)) else og
                body = text(html)
                # keep sentences/fragments that mention a spec keyword
                frags = re.split(r"(?<=[.;])\s+|\s{2,}|\|", body)
                rec["specs"] = " | ".join(f.strip() for f in frags if KW.search(f))[:1500]
        except Exception as e:
            rec["status"] = f"ERR {type(e).__name__}"
    out.append(rec)
    time.sleep(0.4)
    print(rec["id"], rec["status"], "og:", "Y" if rec["og"] else "-", "| specs chars:", len(rec["specs"]))

json.dump(out, open(os.path.join(os.environ["TEMP"], "wellwit_scrape.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("saved", len(out))
