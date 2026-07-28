"""Deep audit Bear Robotics (198) pending robots + OEM probe."""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from api_client import ResearchApiClient
from load_env import load_research_env
from web_extract import WebFetcher, extract_image_urls

load_research_env()
c = ResearchApiClient()
co = c.get_company(198)
print("company", co.get("name"), co.get("website"), co.get("country"))
robots = c.list_robots_for_company(198) or []
print("status", dict(Counter(r.get("status") for r in robots)))

for r in robots:
    if r.get("status") != "pending_review":
        continue
    d = c._get(f"robots/robots/{r['id']}/")
    print(f"\n=== {r['id']} {d.get('name')}")
    print(" url", d.get("url"))
    print(" img", (d.get("image") or d.get("s3_image") or "")[:110])
    print(" avail", d.get("availability_status"))
    print(" countries", bool(d.get("manufacturer_countries")))
    print(" cats", d.get("categories"))
    print(" uses", [u.get("key") for u in (d.get("uses") or [])])
    print(" inds", [i.get("key") for i in (d.get("industries") or [])])
    print(" family", d.get("family_key"))
    print(" purpose", (d.get("purpose") or "")[:100])
    print(" desc", (d.get("description") or "")[:140])
    print(" feats len", len(d.get("features") or ""), (d.get("features") or "")[:200])
    print(
        " specs",
        {
            k: d.get(k)
            for k in ("payload_kg", "weight_kg", "speed", "length_mm", "width_mm", "height_mm", "runtime_minutes")
        },
    )

f = WebFetcher()
pages = [
    "https://www.bearrobotics.ai/",
    "https://www.bearrobotics.ai/servi",
    "https://www.bearrobotics.ai/servi-plus",
    "https://www.bearrobotics.ai/servi-q",
    "https://www.bearrobotics.ai/servi-clean",
    "https://www.bearrobotics.ai/carti100",
    "https://www.bearrobotics.ai/carti-low-profile",
]
for url in pages:
    html = f.get(url) or ""
    print(f"\n### {url} len={len(html)}")
    if len(html) < 1000:
        continue
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    print(text[:1200])
    for u in extract_image_urls(html, base_url=url)[:10]:
        low = u.lower()
        if any(x in low for x in ("logo", "icon", "favicon", "emoji", "avatar")):
            continue
        print(" IMG", u[:130])
