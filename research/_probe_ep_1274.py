"""Probe EP Equipment company 1274 + map product catalog."""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

URLS = [
    "https://ep-equipment.com/product/qdd30t-30ts/",
    "https://ep-equipment.com/product/ept20-30tw/",
    "https://ep-equipment.com/product/jxo/",
    "https://ep-equipment.com/product/es12-25wa/",
    "https://ep-equipment.com/product/es20-wa/",
    "https://ep-equipment.com/product/es12-12es-es12-25mm/",
    "https://ep-equipment.com/product/es10-10es-es10-22mm/",
    "https://ep-equipment.com/product/es18-40wa/",
    "https://ep-equipment.com/product/es14-30wa/",
    "https://ep-equipment.com/product/rpl251-301/",
    "https://ep-equipment.com/product/wpl201/",
    "https://ep-equipment.com/product/hpl152/",
    "https://ep-equipment.com/product/ept20-rap/",
    "https://ep-equipment.com/product/es15-15es/",
    "https://ep-equipment.com/product/esl122/",
    "https://ep-equipment.com/product/ept25-wa/",
    "https://ep-equipment.com/product/ept20-20wa/",
    "https://ep-equipment.com/product/kpl201/",
    "https://ep-equipment.com/product/epl185/",
    "https://ep-equipment.com/product/epl154/",
]


def main() -> None:
    c = ResearchApiClient()
    co = c._get("companies/1274/")
    print("=== COMPANY ===")
    print("name:", co.get("name"))
    print("slug:", co.get("slug"))
    print("web:", co.get("website"))
    print("country:", co.get("country"), co.get("country_code"))

    robots = c.list_robots_for_company(1274)
    print("robot_count:", len(robots))
    out = []
    for r in sorted(robots, key=lambda x: -x["id"]):
        img = r.get("s3_image") or r.get("image") or ""
        feat = r.get("features") or ""
        row = {
            "id": r["id"],
            "name": r["name"],
            "status": r.get("status"),
            "img": bool(img),
            "img_url": img[:120] if img else "",
            "feat_len": len(feat),
            "feat_preview": feat[:200].replace("\n", " | "),
            "payload_kg": r.get("payload_kg"),
            "weight_kg": r.get("weight_kg"),
            "url": r.get("url") or "",
            "family_key": r.get("family_key") or "",
            "purpose": (r.get("purpose") or "")[:120],
            "avail": r.get("availability_status"),
            "tags": r.get("tags") or [],
            "description": (r.get("description") or "")[:160],
        }
        out.append(row)
        print(
            f"{r['id']}|{r['name']}|{r.get('status')}|img={bool(img)}|"
            f"feat={len(feat)}|pay={r.get('payload_kg')}|fk={r.get('family_key') or '-'}|"
            f"avail={r.get('availability_status')}"
        )

    Path("staging/reports/_ep1274_probe.json").write_text(
        json.dumps(out, indent=2), encoding="utf-8"
    )

    print("\n=== PRODUCT PAGES ===")
    catalog = []
    for url in URLS:
        try:
            resp = requests.get(url, timeout=45, headers=HEADERS, allow_redirects=True)
            status = resp.status_code
            final = resp.url
            html = resp.text if status == 200 else ""
            title = ""
            m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
            if m:
                title = re.sub(r"\s+", " ", m.group(1)).strip()[:120]
            # Find product hero candidates
            imgs = re.findall(
                r'(?:src|data-src|data-lazy-src)=["\']([^"\']+\.(?:jpg|jpeg|png|webp)[^"\']*)',
                html,
                re.I,
            )
            # Also wp-content uploads
            imgs2 = re.findall(
                r'https?://[^"\'\s]+wp-content/uploads/[^"\'\s]+\.(?:jpg|jpeg|png|webp)',
                html,
                re.I,
            )
            all_imgs = []
            seen = set()
            for u in imgs + imgs2:
                full = urljoin(final, u.split("?")[0])
                if full in seen:
                    continue
                seen.add(full)
                low = full.lower()
                if any(
                    x in low
                    for x in (
                        "logo",
                        "favicon",
                        "icon",
                        "sprite",
                        "avatar",
                        "flag",
                        "banner",
                        "placeholder",
                    )
                ):
                    continue
                all_imgs.append(full)

            # Spec table sniff
            load_caps = re.findall(
                r"(?:Load\s*capacity|Rated\s*capacity|Capacity)[^<\d]{0,40}?(\d[\d,\.]*)\s*(?:kg|KG)",
                html,
                re.I,
            )
            # Features length estimate
            feat_blocks = re.findall(
                r"(?:feature|advantage|highlight)[^>]*>", html[:5000], re.I
            )
            catalog.append(
                {
                    "url": url,
                    "status": status,
                    "final": final,
                    "title": title,
                    "chars": len(html),
                    "img_count": len(all_imgs),
                    "imgs_top": all_imgs[:8],
                    "load_caps": load_caps[:6],
                }
            )
            print(f"{status} {url}")
            print(f"  title={title}")
            print(f"  imgs={len(all_imgs)} caps={load_caps[:4]}")
            if all_imgs:
                print(f"  hero0={all_imgs[0][:100]}")
        except Exception as e:
            print(f"ERR {url}: {e}")
            catalog.append({"url": url, "error": str(e)})

    Path("staging/reports/_ep1274_catalog.json").write_text(
        json.dumps(catalog, indent=2), encoding="utf-8"
    )
    print("\nWrote staging/reports/_ep1274_probe.json + _ep1274_catalog.json")


if __name__ == "__main__":
    main()
