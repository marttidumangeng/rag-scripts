"""Audit Piaggio Fast Forward (236) pending robots for soft enrich."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import requests

_RESEARCH = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient

UA = {"User-Agent": "Mozilla/5.0"}
IDS = [3767, 3765]


def _names(val):
    if not val:
        return []
    out = []
    for x in val:
        if isinstance(x, dict):
            out.append(x.get("key") or x.get("slug") or x.get("name") or str(x.get("id")))
        else:
            out.append(str(x))
    return out


def main() -> int:
    client = ResearchApiClient()
    for rid in IDS:
        r = client._get(f"robots/robots/{rid}/")
        img = r.get("image") or r.get("s3_image") or ""
        feats = r.get("features") or ""
        purpose = r.get("purpose") or ""
        desc = r.get("description") or ""
        print(f"\n=== {rid} {r.get('name')}")
        print(" status", r.get("status"))
        print(" url", r.get("url"))
        print(" img", img)
        if img:
            try:
                h = requests.get(img, headers=UA, timeout=20)
                print(" img_http", h.status_code, len(h.content))
            except Exception as e:
                print(" img_err", e)
        print(" avail", r.get("availability_status"))
        print(
            " country_ref",
            r.get("manufacturer_country_ref"),
            "countries",
            r.get("manufacturer_countries"),
        )
        print(" cats", _names(r.get("categories"))[:8])
        print(" uses", _names(r.get("uses"))[:8])
        print(" inds", _names(r.get("industries"))[:8])
        print(" movement", _names(r.get("movement_types"))[:6])
        print(" family", r.get("family_key"), r.get("family_name"), r.get("family_url"))
        print(" purpose", (purpose or "")[:200].replace("\n", " | "))
        print(" desc", (desc or "")[:220])
        print(" feats len", len(feats))
        print(" feats", (feats or "")[:300])
        specs = {
            k: r.get(k)
            for k in (
                "payload_kg",
                "weight_kg",
                "speed",
                "length_mm",
                "width_mm",
                "height_mm",
                "runtime_minutes",
            )
        }
        print(" specs", specs)
        print(" photos", len(r.get("photos") or []))
        tags = r.get("tags") or []
        print(" tags", tags[:10] if isinstance(tags, list) else tags)
        print(" notes", (r.get("notes") or "")[:200])

    for url in (
        "https://www.piaggiofastforward.com/",
        "https://piaggiofastforward.com/shop/gitamini",
        "https://piaggiofastforward.com/shop/gitaplus",
        "https://piaggiofastforward.com/gita",
        "https://www.piaggiofastforward.com/gita",
    ):
        try:
            resp = requests.get(url, headers=UA, timeout=40, allow_redirects=True)
            print(f"\nOEM {resp.url} -> {resp.status_code} len={len(resp.text)}")
            plain = re.sub(r"<script[\s\S]*?</script>", " ", resp.text, flags=re.I)
            plain = re.sub(r"<style[\s\S]*?</style>", " ", plain, flags=re.I)
            plain = re.sub(r"<[^>]+>", " ", plain)
            plain = re.sub(r"\s+", " ", plain)
            print(plain[:1000])
            imgs = sorted(
                set(
                    re.findall(
                        r"https?://[^\"'\s>]+\.(?:webp|jpg|jpeg|png)",
                        resp.text,
                        flags=re.I,
                    )
                )
            )
            for u in imgs[:12]:
                if any(x in u.lower() for x in ("gita", "product", "cdn", "shopify", "shop")):
                    print(" IMG", u[:130])
        except Exception as e:
            print("OEM err", url, e)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
