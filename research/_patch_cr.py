"""Give each MULE variant a photograph from its OWN page. DRY RUN unless APPLY=1.

The crawler stripped every image from all five rows: construction-robotics.com is
a Framer site whose assets are opaque hashes (0HCpM1WPO6sbfEPQgjUvg7nNfGI.jpeg)
shared across pages, so the site-wide-asset guard demoted the lot.

Filename matching cannot work here - there are no names. Page provenance can:
an image that appears ONLY on /solutions/solar-panel is a Solar MULE picture,
and one that appears only on /solutions/masonry-mule is a Masonry MULE picture.
Checked by eye first: the solar pages show a MULE with vacuum grippers lifting
panels, the masonry pages one placing a concrete block.

Anything appearing on more than one page is site furniture and is skipped, so a
variant with no unique image is left without rather than given a generic one.
"""
import glob
import json
import os
import re
from collections import defaultdict
from urllib.parse import urljoin

import requests
import urllib3

urllib3.disable_warnings()

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "Chrome/135.0.0.0 Safari/537.36",
      "Referer": "https://www.construction-robotics.com/"}
STAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "staging", "robots", "construction-robotics")
APPLY = os.environ.get("APPLY") == "1"
B = "https://www.construction-robotics.com/solutions/"

PAGE_FOR = {
    "Masonry MULE": "masonry-mule",
    "Solar MULE": "solar-panel",
    "SRW MULE": "srw-civil",
    "MULE-R": "muler-refractory",
    "Block Plant MULE": "manufacturing-plants",
}


def page_assets(slug):
    """asset-id -> best (largest) url on this page."""
    r = requests.get(B + slug, timeout=60, headers=UA, verify=False)
    r.encoding = "utf-8"
    best = {}
    for m in re.findall(r'(?:src|data-src|srcset)="([^"]+)"', r.text):
        for part in m.split(","):
            p = part.strip().split(" ")[0].replace("&amp;", "&")
            k = re.search(r"framerusercontent\.com/images/([A-Za-z0-9]+)\.(png|jpe?g)", p, re.I)
            if not k:
                continue
            w = int(re.search(r"[?&]width=(\d+)", p).group(1)) if "width=" in p else 0
            if w < 800:            # thumbnails and icons
                continue
            aid = k.group(1)
            if aid not in best or w > best[aid][0]:
                best[aid] = (w, urljoin(B, p))
    return best


assets = {slug: page_assets(slug) for slug in set(PAGE_FOR.values())}
seen_on = defaultdict(set)
for slug, d in assets.items():
    for aid in d:
        seen_on[aid].add(slug)

print("page                    assets>=800px   unique to it")
for slug, d in assets.items():
    uniq = [a for a in d if len(seen_on[a]) == 1]
    print(f"  {slug:<22} {len(d):>3}            {len(uniq)}")

print("\nassignment:")
for f in sorted(glob.glob(os.path.join(STAGE, "*.json"))):
    d = json.load(open(f, encoding="utf-8"))
    name = (d.get("name") or "").strip()
    slug = PAGE_FOR.get(name)
    if not slug or (d.get("images") or []):
        continue
    uniq = sorted([(w, u) for a, (w, u) in assets[slug].items()
                   if len(seen_on[a]) == 1], reverse=True)
    if not uniq:
        print(f"  {name:<20} no image unique to its page - left without")
        continue
    pick = [{"url": u, "source_page_url": B + slug} for _, u in uniq[:3]]
    print(f"  {name:<20} {len(pick)} image(s) from /{slug}")
    if APPLY:
        d["images"] = pick
        d["image"] = pick[0]["url"]
        json.dump(d, open(f, "w", encoding="utf-8"), indent=1, ensure_ascii=False)

print("\n(DRY RUN)" if not APPLY else "\n  staging patched")
