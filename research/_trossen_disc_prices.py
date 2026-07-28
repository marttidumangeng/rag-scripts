"""Check discontinued banners + OEM dollar prices."""
from __future__ import annotations

import re
import sys

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
UA = {"User-Agent": "Mozilla/5.0"}
URLS = {
    5266: "https://www.trossenrobotics.com/aloha-solo",
    5267: "https://www.trossenrobotics.com/aloha-stationary",
    5268: "https://www.trossenrobotics.com/mobile-ai",
    5269: "https://www.trossenrobotics.com/pincherx100",
    5270: "https://www.trossenrobotics.com/viperx-300",
    5271: "https://www.trossenrobotics.com/viperx-aloha",
    5272: "https://www.trossenrobotics.com/widowx-250",
    5273: "https://www.trossenrobotics.com/widowx-ai",
    5274: "https://www.trossenrobotics.com/widowx-aloha-set",
}

for rid, url in URLS.items():
    html = requests.get(url, headers=UA, timeout=60).text
    disc = "THIS PRODUCT HAS BEEN DISCONTINUED" in html
    prices = []
    for m in re.findall(r"\$([0-9]{1,3}(?:,[0-9]{3})*\.[0-9]{2})", html):
        v = float(m.replace(",", ""))
        if 100 < v < 100000 and m not in prices:
            prices.append(m)
    print(rid, "DISC" if disc else "live ", prices[:8], url.split("/")[-1])
