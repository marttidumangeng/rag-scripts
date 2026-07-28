"""Audit Dephy (814) + next small US pending candidates."""
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
# Dephy Sidekick; also peek Accuray if time
TARGETS = {
    814: [5088],
}


def _names(val):
    out = []
    for x in val or []:
        if isinstance(x, dict):
            out.append(x.get("key") or x.get("slug") or x.get("name") or str(x.get("id")))
        else:
            out.append(str(x))
    return out


def audit(client: ResearchApiClient, rid: int) -> None:
    r = client._get(f"robots/robots/{rid}/")
    img = r.get("image") or r.get("s3_image") or ""
    print(f"\n=== {rid} {r.get('name')}")
    print(" status", r.get("status"), "|", r.get("company"))
    print(" url", r.get("url"))
    print(" img", img)
    if img:
        try:
            h = requests.get(img, headers=UA, timeout=20)
            print(" img_http", h.status_code, len(h.content))
        except Exception as e:
            print(" img_err", e)
    print(" avail", r.get("availability_status"))
    print(" country_ref", r.get("manufacturer_country_ref"))
    print(" countries", r.get("manufacturer_countries"))
    print(" cats", _names(r.get("categories"))[:6])
    print(" uses", _names(r.get("uses"))[:6])
    print(" inds", _names(r.get("industries"))[:6])
    print(" family", r.get("family_key"), r.get("family_name"))
    print(" purpose", (r.get("purpose") or "")[:200].replace("\n", " | "))
    print(" desc", (r.get("description") or "")[:220])
    feats = r.get("features") or ""
    print(" feats", len(feats), (feats or "")[:280])
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
            "dof",
            "price_usd",
        )
    }
    print(" specs", specs)
    print(" photos", len(r.get("photos") or []))
    print(" tags", (r.get("tags") or [])[:10])
    for o in r.get("company_owners") or []:
        if isinstance(o, dict):
            print(" slug", o.get("slug"), o.get("id"))
            print(" co website", (o.get("website") if False else ""))
    # published siblings
    data = client._get("robots/robots/", params={"search": "dephy", "page_size": 20})
    for row in data.get("results") or []:
        print(
            " sibling",
            row.get("id"),
            row.get("status"),
            row.get("name"),
        )


def oem(url: str) -> None:
    try:
        resp = requests.get(url, headers=UA, timeout=40, allow_redirects=True)
        print(f"\nOEM {resp.url} -> {resp.status_code} len={len(resp.text)}")
        plain = re.sub(r"<script[\s\S]*?</script>", " ", resp.text, flags=re.I)
        plain = re.sub(r"<style[\s\S]*?</style>", " ", plain, flags=re.I)
        plain = re.sub(r"<[^>]+>", " ", plain)
        plain = re.sub(r"\s+", " ", plain)
        print(plain[:1100])
        imgs = sorted(
            set(
                re.findall(
                    r"https?://[^\"'\s>]+\.(?:webp|jpg|jpeg|png)",
                    resp.text,
                    flags=re.I,
                )
            )
        )
        for u in imgs[:15]:
            if any(x in u.lower() for x in ("sidekick", "product", "cdn", "shopify")):
                print(" IMG", u[:140])
    except Exception as e:
        print("OEM err", url, e)


def main() -> int:
    client = ResearchApiClient()
    for cid, ids in TARGETS.items():
        print(f"\n######## company {cid}")
        for rid in ids:
            audit(client, rid)
    oem("https://www.dephy.com")
    oem("https://shop.dephy.com/products/sidekick-starter-pack")
    oem("https://www.dephy.com/sidekick")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
