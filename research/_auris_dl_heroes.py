"""Download named Monarch Quest hero candidates for visual QA."""
from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote

import requests

HEADERS = {"User-Agent": "Mozilla/5.0"}
MEDIA = Path("staging/media/auris")
MEDIA.mkdir(parents=True, exist_ok=True)

URLS = {
    "quest_hero": (
        "https://images.contentstack.io/v3/assets/blt6442fb89e58ceab5/"
        "blt56332663aa4dd6f5/693c6a4931ed5e7752af6178/"
        "US_SRG_RADS_389015.1_Introducing_MONARCH%E2%84%A2_QUEST_Hero.jpg"
        "?width=1920&quality=80&format=webp"
    ),
    "quest_alt1": (
        "https://images.contentstack.io/v3/assets/blt6442fb89e58ceab5/"
        "bltb8423cc70c8de6f9/693c6a3b1c8295672c529ddd/"
        "US_SRG_RADS_389015.1_Introducing_MONARCH%E2%84%A2_QUEST_Alt_card_1.jpg"
        "?width=1920&quality=80&format=webp"
    ),
    "quest_alt2": (
        "https://images.contentstack.io/v3/assets/blt6442fb89e58ceab5/"
        "bltbd19149013b173fe/693c73e97e86296d74fd6bb9/"
        "US_SRG_RADS_389015.1_Introducing_MONARCH_QUEST_Alt_card_2.jpg"
        "?width=1920&quality=80&format=webp"
    ),
    "platform": (
        "https://images.contentstack.io/v3/assets/blt6442fb89e58ceab5/"
        "bltbdad7a148fa2c1fb/69ab4bc10761d20008823fc3/Monarch_Platform_Image.png"
        "?width=1920&quality=80&format=webp"
    ),
    "reach": (
        "https://images.contentstack.io/v3/assets/blt6442fb89e58ceab5/"
        "blt97df7b80bf0f7144/693c688af27a239d11fc0178/"
        "US_SRG_RADS_389015.1_Reach_further_into_the_lungs.jpg"
        "?width=1920&quality=90&format=webp"
    ),
    "main_hero": (
        "https://images.contentstack.io/v3/assets/blt6442fb89e58ceab5/"
        "blt0391701dfbc69dce/693c6a101c829546b6529dd9/US_SRG_RADS_389015.1.jpg"
        "?width=1920&quality=80&format=webp"
    ),
}

session = requests.Session()
session.headers.update(HEADERS)
for name, url in URLS.items():
    r = session.get(url, timeout=60)
    ctype = r.headers.get("content-type", "")
    ok = r.status_code == 200 and "image" in ctype.lower() and len(r.content) > 15000
    ext = ".webp" if "webp" in ctype.lower() or "webp" in url else ".jpg"
    path = MEDIA / f"{name}{ext}"
    if ok:
        path.write_bytes(r.content)
    print(f"{name}: {r.status_code} bytes={len(r.content)} ctype={ctype} ok={ok}", flush=True)
