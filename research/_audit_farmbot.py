"""Deep audit FarmBot (34) pending robots + OEM page probe."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from api_client import ResearchApiClient
from load_env import load_research_env
from web_extract import WebFetcher, extract_image_urls

load_research_env()
c = ResearchApiClient()
co = c.get_company(34)
print("company", co.get("name"), co.get("website"), co.get("country"))

pending_ids = []
for r in c.list_robots_for_company(34) or []:
    d = c._get(f"robots/robots/{r['id']}/")
    print("\n===", r["id"], d.get("name"), d.get("status"))
    print(" url", d.get("url"))
    print(" img", (d.get("image") or d.get("s3_image") or "")[:100])
    print(" avail", d.get("availability_status"))
    print(" countries", d.get("manufacturer_countries"))
    print(" cats", d.get("categories"))
    print(" uses", [u.get("key") for u in (d.get("uses") or [])])
    print(" inds", [i.get("key") for i in (d.get("industries") or [])])
    print(" family", d.get("family_key"), d.get("family_name"))
    print(" purpose", (d.get("purpose") or "")[:120])
    print(" desc", (d.get("description") or "")[:160])
    print(" feats", (d.get("features") or "")[:300])
    print(
        " specs",
        {
            k: d.get(k)
            for k in (
                "payload_kg",
                "weight_kg",
                "length_mm",
                "width_mm",
                "height_mm",
                "speed",
                "runtime_minutes",
                "release_year",
            )
        },
    )
    if d.get("status") == "pending_review":
        pending_ids.append(r["id"])

f = WebFetcher()
urls = [
    "https://farm.bot/",
    "https://farm.bot/products/farmbot-genesis-v1-8",
    "https://farm.bot/products/farmbot-genesis-xl-v1-8",
    "https://express.farm.bot/",
]
for url in urls:
    html = f.get(url) or ""
    print("\n### PAGE", url, "len", len(html))
    if len(html) < 800:
        continue
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    print(text[:1500])
    for u in extract_image_urls(html, base_url=url)[:12]:
        low = u.lower()
        if any(x in low for x in ("logo", "icon", "favicon", "emoji")):
            continue
        print(" IMG", u[:120])

Path("staging/reports/farmbot-audit-ids.json").write_text(
    json.dumps(pending_ids), encoding="utf-8"
)
