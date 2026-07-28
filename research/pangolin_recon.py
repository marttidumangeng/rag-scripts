"""Scrape Pangolin / alpha-robot.com.cn product pages → heroes + copy."""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
import urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_RESEARCH_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH_DIR))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from load_env import load_research_env

load_research_env()

from api_client import ResearchApiClient

OUT = _RESEARCH_DIR / "staging" / "reports" / "pangolin-recon.json"
SESS = requests.Session()
SESS.headers["User-Agent"] = "Mozilla/5.0"
SESS.verify = False
BASE = "https://www.alpha-robot.com.cn"


def fetch(url: str) -> tuple[str, str]:
    r = SESS.get(url, timeout=45, allow_redirects=True)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    return str(r.url), r.text


def abs_url(base: str, u: str) -> str:
    if not u:
        return ""
    return urljoin(base, u.strip())


def scrape_pdp(url: str) -> dict:
    final, html = fetch(url)
    soup = BeautifulSoup(html, "html.parser")
    title = ""
    h1 = soup.find("h1")
    if h1:
        title = h1.get_text(" ", strip=True)
    if not title:
        t = soup.find("title")
        title = t.get_text(" ", strip=True) if t else ""

    # images
    imgs: list[str] = []
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or ""
        if not src:
            continue
        u = abs_url(final, src)
        low = u.lower()
        if any(x in low for x in ("logo", "icon", "qrcode", "wechat", "wx", ".svg", "banner-bg")):
            continue
        if any(x in low for x in (".jpg", ".jpeg", ".png", ".webp")):
            imgs.append(u.split("?")[0])
    # prefer product uploads
    ranked = []
    for u in dict.fromkeys(imgs):
        score = 0
        low = u.lower()
        if "/upload" in low or "/product" in low or "/goods" in low:
            score += 5
        if any(x in low for x in ("banner", "swiper", "slide")):
            score -= 2
        ranked.append((score, u))
    ranked.sort(key=lambda x: -x[0])
    heroes = [u for _, u in ranked[:8]]

    # text bits
    text = soup.get_text("\n", strip=True)
    # payload / size hints
    payload = None
    m = re.search(r"(?:负载|载重|最大负载)[^\d]{0,8}([\d.]+)\s*kg", text, re.I)
    if m:
        payload = float(m.group(1))

    # short description: first meaningful paragraph-like chunk
    paras = [p.get_text(" ", strip=True) for p in soup.find_all(["p", "li"]) if p.get_text(strip=True)]
    paras = [p for p in paras if 20 <= len(p) <= 300 and "版权" not in p and "备案" not in p]
    blurb = " ".join(paras[:3])[:500]

    return {
        "url": final,
        "title": title,
        "heroes": heroes,
        "payload_kg": payload,
        "blurb": blurb,
        "text_len": len(text),
    }


def main() -> None:
    client = ResearchApiClient()
    robots = [
        r
        for r in client.list_robots_for_company(1413)
        if str(r.get("status") or "").lower() == "pending_review"
    ]
    recon: dict[str, dict] = {}
    for r in sorted(robots, key=lambda x: int(x["id"])):
        rid = int(r["id"])
        full = client._get(f"robots/robots/{rid}/")
        url = (full.get("url") or full.get("website_url") or "").strip()
        name = full.get("name") or ""
        has_img = bool((full.get("image") or full.get("s3_image") or "").strip())
        entry = {
            "id": rid,
            "name": name,
            "url": url,
            "has_img": has_img,
            "country": full.get("manufacturer_country"),
            "categories": full.get("categories"),
            "uses": full.get("uses"),
        }
        if url and "alpha-robot.com.cn" in url:
            try:
                pdp = scrape_pdp(url)
                entry["pdp"] = pdp
                print(
                    f"{rid} ok title={pdp['title'][:40]!r} heroes={len(pdp['heroes'])} "
                    f"payload={pdp.get('payload_kg')} has_img={has_img}"
                )
                if pdp["heroes"]:
                    print(f"   hero0={pdp['heroes'][0][:90]}")
            except Exception as exc:  # noqa: BLE001
                entry["pdp_error"] = str(exc)
                print(f"{rid} PDP FAIL {url}: {exc}")
        else:
            print(f"{rid} no alpha URL name={name[:40]!r}")
        recon[str(rid)] = entry
        time.sleep(0.15)

    OUT.write_text(json.dumps(recon, indent=2, ensure_ascii=False), encoding="utf-8")
    with_heroes = sum(1 for v in recon.values() if (v.get("pdp") or {}).get("heroes"))
    print(f"wrote {OUT} robots={len(recon)} with_pdp_heroes={with_heroes}")


if __name__ == "__main__":
    main()
