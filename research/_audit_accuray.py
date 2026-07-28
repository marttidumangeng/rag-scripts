"""Audit Accuray (1378) pending CyberKnife / TomoTherapy fleet."""
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
# From earlier candidate audit
IDS = [1482, 1481, 1480, 1479, 1478, 1477]


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
    print(" status", r.get("status"))
    print(" url", r.get("url"))
    print(" img", (img or "")[:100], "bytes?", end=" ")
    if img:
        try:
            h = requests.get(img, headers=UA, timeout=20)
            print(h.status_code, len(h.content))
        except Exception as e:
            print("err", e)
    else:
        print("none")
    print(" avail", r.get("availability_status"))
    print(" country", r.get("manufacturer_country_ref"), r.get("manufacturer_countries"))
    print(" cats", _names(r.get("categories"))[:6])
    print(" uses", _names(r.get("uses"))[:6])
    print(" inds", _names(r.get("industries"))[:6])
    print(" family", r.get("family_key"), r.get("family_name"), r.get("family_url"))
    print(" purpose", (r.get("purpose") or "")[:180].replace("\n", " | "))
    print(" desc", (r.get("description") or "")[:200])
    feats = r.get("features") or ""
    print(" feats", len(feats), (feats or "")[:220])
    print(
        " specs",
        {
            k: r.get(k)
            for k in (
                "payload_kg",
                "weight_kg",
                "dof",
                "price_min",
                "price_max",
                "length_mm",
                "width_mm",
                "height_mm",
            )
        },
    )
    print(" photos", len(r.get("photos") or []))
    print(" sources", r.get("information_sources"))
    print(" tags", (r.get("tags") or [])[:8])
    for o in r.get("company_owners") or []:
        if isinstance(o, dict):
            print(" slug", o.get("slug"), o.get("id"))


def oem(url: str) -> None:
    try:
        resp = requests.get(url, headers=UA, timeout=40, allow_redirects=True)
        print(f"\nOEM {resp.url} -> {resp.status_code} len={len(resp.text)}")
        plain = re.sub(r"<script[\s\S]*?</script>", " ", resp.text, flags=re.I)
        plain = re.sub(r"<style[\s\S]*?</style>", " ", plain, flags=re.I)
        plain = re.sub(r"<[^>]+>", " ", plain)
        plain = re.sub(r"\s+", " ", plain)
        print(plain[:1000])
    except Exception as e:
        print("OEM err", url, e)


def main() -> int:
    client = ResearchApiClient()
    # also list any other pending via search
    data = client._get("robots/robots/", params={"search": "CyberKnife", "page_size": 20})
    print("CyberKnife search:")
    for row in data.get("results") or []:
        print(" ", row.get("id"), row.get("status"), row.get("name"))
    data2 = client._get("robots/robots/", params={"search": "TomoTherapy", "page_size": 20})
    print("TomoTherapy search:")
    for row in data2.get("results") or []:
        print(" ", row.get("id"), row.get("status"), row.get("name"))
    data3 = client._get("robots/robots/", params={"search": "Radixact", "page_size": 20})
    print("Radixact search:")
    for row in data3.get("results") or []:
        print(" ", row.get("id"), row.get("status"), row.get("name"))

    for rid in IDS:
        try:
            audit(client, rid)
        except Exception as e:
            print("ERR", rid, e)

    oem("https://www.accuray.com/")
    oem("https://www.accuray.com/cyberknife/")
    oem("https://www.accuray.com/radixact/")
    oem("https://www.accuray.com/tomotherapy/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
