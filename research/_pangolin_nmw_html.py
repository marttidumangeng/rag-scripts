"""Dump Niumowang PDP HTML fragments around load/size labels."""
from __future__ import annotations

import re
import sys

import requests
import urllib3

urllib3.disable_warnings()
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

url = "https://www.alpha-robot.com.cn/productnmw/141/detail/15.html"
html = requests.get(url, verify=False, timeout=45).text
for pat in ["最大载重", "F300", "F150", "F600", "640", "885", "医疗"]:
    for m in re.finditer(re.escape(pat), html):
        start = max(0, m.start() - 120)
        end = min(len(html), m.end() + 220)
        frag = re.sub(r"\s+", " ", html[start:end])
        print(f"\n--- {pat} @ {m.start()} ---")
        print(frag[:320])
        break

# print all table-like text
from bs4 import BeautifulSoup

soup = BeautifulSoup(html, "html.parser")
print("\n=== TABLES ===")
for i, table in enumerate(soup.find_all("table")[:5]):
    print(f"TABLE {i}")
    for tr in table.find_all("tr")[:15]:
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        print(" | ".join(cells))
