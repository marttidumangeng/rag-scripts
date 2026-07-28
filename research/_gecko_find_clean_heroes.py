"""Find and download Gecko TOKA 4 / Flex robot-only hero candidates."""
from __future__ import annotations

import re
from pathlib import Path

import requests

UA = {"User-Agent": "Mozilla/5.0 (compatible; RobotAIGeekResearch/1.0)"}
OUT = Path("staging/tmp/gecko-qa2")
OUT.mkdir(parents=True, exist_ok=True)

PAGES = [
    "https://www.geckorobotics.com/solutions/industries/oil-gas/piping",
    "https://www.geckorobotics.com/case-study/spray-dry-absorber",
    "https://www.geckorobotics.com/solutions/robots",
    "https://www.geckorobotics.com/technology/robots",
    "https://blog.geckorobotics.com/tag/toka-flex",
    "https://resources.geckorobotics.com/toka-flex",
]

KNOWN = {
    "toka3-oem": "https://cdn.prod.website-files.com/63349fc0ae8d7c3feaab48a9/633d40453a4c38ce02aec560_Toka%203_1000.JPG",
    "toka-sda": "https://cdn.prod.website-files.com/63349fc1ae8d7c8af7ab48b3/6501b77912ae44da654ec2e2_TOKA%20on%20SDA.jpg",
    "scrubber": "https://cdn.prod.website-files.com/63349fc0ae8d7c3feaab48a9/633d3ad9accedcc9eef32358_scrubber.jpg",
}

for url in PAGES:
    print("===", url)
    try:
        html = requests.get(url, headers=UA, timeout=45).text
    except Exception as e:  # noqa: BLE001
        print("fail", e)
        continue
    print("chars", len(html))
    imgs = re.findall(
        r"(https://cdn\.prod\.website-files\.com/[^\"'\s>]+\.(?:jpg|jpeg|png|webp|JPG))",
        html,
    )
    seen: set[str] = set()
    for u in imgs:
        if u in seen:
            continue
        seen.add(u)
        low = u.lower()
        if any(x in low for x in ("logo", "icon", "svg", "avatar", "webclip")):
            continue
        print(" ", u[:150])

for name, url in KNOWN.items():
    r = requests.get(url, headers=UA, timeout=60)
    print(name, r.status_code, len(r.content))
    if r.ok and len(r.content) > 3000:
        ext = ".jpg"
        (OUT / f"{name}{ext}").write_bytes(r.content)
