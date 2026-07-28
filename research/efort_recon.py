"""Recon: fetch all EFORT (company 1479) PDPs, extract heading, hero candidates, visible spec text.
Writes staging/reports/efort_recon.json for hand-classification before building the fixer.
"""
import json, os, re, time
import requests
from load_env import load_research_env
load_research_env()
from api_client import ResearchApiClient

OUT = os.path.join(os.path.dirname(__file__), "staging", "reports", "efort_recon.json")
os.makedirs(os.path.dirname(OUT), exist_ok=True)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124 Safari/537.36")


def norm_url(u):
    # normalize .ht truncation and ensure https + .htm
    u = (u or "").strip()
    if not u:
        return u
    if u.endswith(".ht"):
        u = u + "m"
    if not u.startswith("http"):
        u = "https://efort.com.cn" + (u if u.startswith("/") else "/" + u)
    return u


def scrape(url):
    h = {"User-Agent": UA, "Referer": url}
    r = requests.get(url, headers=h, timeout=40)
    t = r.text
    # heading: try h1/h2 in detail area, and <title>
    heads = re.findall(r'<h[12][^>]*>(.*?)</h[12]>', t, re.S)
    heads = [re.sub(r'<[^>]+>', '', h).strip() for h in heads]
    heads = [h for h in heads if h][:6]
    # pic.cen ordered images
    pics = re.findall(r'<div class="pic">\s*<img src="([^"]+)"[^>]*class="cen"', t)
    # visible spec near this model (payload/reach/axes text if present)
    txt = re.sub(r'<script.*?</script>', ' ', t, flags=re.S)
    txt = re.sub(r'<[^>]+>', ' ', txt)
    import html as _html
    txt = _html.unescape(txt)
    txt = re.sub(r'[ \t\r\n]+', ' ', txt)
    specs = re.findall(
        r'Max\.?\s*payload on wrist\s*[:：]\s*([\d\.]+)\s*kg\s+Reach\s*[:：]\s*([\d\.]+)\s*mm\s+Controlled axes\s*[:：]\s*(\d+)',
        txt)
    return {"status": r.status_code, "heads": heads, "pics": pics, "spec_cards": specs}


def main():
    c = ResearchApiClient()
    rows = c.list_robots_for_company(1479)
    out = []
    for r in rows:
        url = norm_url(r.get("url"))
        cat = ""
        m = re.search(r'/product/product/(\d+)/(\d+)\.htm', url)
        if m:
            cat = m.group(1)
        rec = {"id": r["id"], "name": r["name"], "category": cat, "url": url,
               "has_img": bool(r.get("s3_image") or r.get("image"))}
        try:
            rec.update(scrape(url))
        except Exception as e:
            rec["error"] = str(e)
        out.append(rec)
        print(rec["id"], rec["name"], "cat=" + cat, "st=" + str(rec.get("status")),
              "pics=" + str(len(rec.get("pics") or [])),
              "cards=" + str(len(rec.get("spec_cards") or [])),
              "| head=" + (rec.get("heads") or [""])[0][:40])
        time.sleep(0.3)
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("WROTE", OUT, "n=", len(out))


if __name__ == "__main__":
    main()
