"""Probe Pangolin/CSJBOT sources and sample robot fields."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
import urllib3

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
from verify_cdn_images import probe_url

SESS = requests.Session()
SESS.headers["User-Agent"] = "Mozilla/5.0"
SESS.verify = False

SITES = [
    "https://www.csjbot.com/",
    "https://csjbot.com/",
    "https://www.alpha-robot.com.cn/",
    "https://alpha-robot.com.cn/",
    "http://www.csjbot.com/",
    "http://www.alpha-robot.com.cn/",
]


def main() -> None:
    client = ResearchApiClient()
    co = client._get("companies/1413/")
    print("company keys sample:", {k: co.get(k) for k in (
        "name", "website", "country", "hq_country", "hq_city", "description"
    ) if k in co or True})
    print("country field:", co.get("country"), co.get("hq_country"), co.get("manufacturer_country"))

    # sample robots with/without image
    robots = client.list_robots_for_company(1413)
    pending = [r for r in robots if str(r.get("status") or "").lower() == "pending_review"]
    with_img = []
    for r in pending:
        full = client._get(f"robots/robots/{int(r['id'])}/")
        img = (full.get("image") or full.get("s3_image") or "").strip()
        if img:
            with_img.append(full)
        if len(with_img) >= 3:
            break
    for full in with_img:
        img = (full.get("image") or full.get("s3_image") or "").strip()
        check = probe_url(img)
        print(
            f"SAMPLE {full['id']} {(full.get('name') or '')[:40]!r}\n"
            f"  country={full.get('manufacturer_country')!r} cats={full.get('categories')} "
            f"uses={full.get('uses')}\n"
            f"  url={full.get('url')}\n"
            f"  img_ok={check.get('ok')} status={check.get('status')} {img[:80]}"
        )

    print("\n=== site probes ===")
    for u in SITES:
        try:
            r = SESS.get(u, timeout=25, allow_redirects=True)
            title_m = re.search(r"<title[^>]*>([^<]+)", r.text, re.I)
            title = (title_m.group(1).strip() if title_m else "")[:60]
            print(f"OK {r.status_code} {u} -> {r.url} title={title!r} len={len(r.text)}")
            # product links
            hrefs = re.findall(r'href=["\']([^"\']+)["\']', r.text, re.I)
            interesting = []
            for h in hrefs:
                low = h.lower()
                if any(x in low for x in ("product", "chanpin", "robot", "amr", "goods", "item")):
                    interesting.append(urljoin(r.url, h))
            interesting = sorted(set(interesting))[:20]
            for h in interesting:
                print(f"  link {h}")
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL {u}: {exc}")


if __name__ == "__main__":
    main()
