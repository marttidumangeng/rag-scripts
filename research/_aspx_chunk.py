import re
import requests

HEADERS = {"User-Agent": "Mozilla/5.0"}
url = "https://www.noblelift.com/AGV/info.aspx?itemid=643&lcid=51"
html = requests.get(url, headers=HEADERS, timeout=45).text
idx = html.find("APT15")
print("idx", idx)
chunk = html[max(0, idx - 800) : idx + 2000]
print(chunk)
print("---ALL SRC---")
for m in re.findall(r'src=["\']([^"\']+)["\']', html, re.I):
    if "upload" in m.lower() or "agv" in m.lower() or ".jpg" in m.lower() or ".png" in m.lower():
        print(m)
