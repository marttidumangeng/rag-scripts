"""Audit Ekso Bionics (147) pending for next US enrich."""
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
# from earlier candidate audit
IDS = [2481, 1968, 1967, 1966, 437, 436, 179]


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
    if img:
        try:
            h = requests.get(img, headers=UA, timeout=20)
            print(" img", h.status_code, len(h.content), img[-70:])
        except Exception as e:
            print(" img_err", e)
    else:
        print(" img NONE")
    print(" avail", r.get("availability_status"))
    print(" country_ref", r.get("manufacturer_country_ref"))
    print(" countries", bool(r.get("manufacturer_countries")))
    print(" cats", _names(r.get("categories"))[:6])
    print(" uses", _names(r.get("uses"))[:6])
    print(" inds", _names(r.get("industries"))[:6])
    print(" family", r.get("family_key"), r.get("family_name"))
    print(" purpose", (r.get("purpose") or "")[:180].replace("\n", " | "))
    print(" desc", (r.get("description") or "")[:200])
    feats = r.get("features") or ""
    print(" feats", len(feats), (feats or "")[:220])
    print(
        " specs",
        {
            k: r.get(k)
            for k in ("weight_kg", "payload_kg", "dof", "price_min", "price_max", "height_mm")
        },
    )
    print(" photos", len(r.get("photos") or []))
    print(" sources", [(s.get("url") if isinstance(s, dict) else s) for s in (r.get("information_sources") or [])][:3])
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
        print(plain[:1100])
    except Exception as e:
        print("OEM err", url, e)


def main() -> int:
    client = ResearchApiClient()
    for q in ("Ekso", "Indego", "EksoNR", "EksoGT", "EksoVest", "EVO"):
        data = client._get("robots/robots/", params={"search": q, "page_size": 15})
        print(f"search {q}:")
        for row in data.get("results") or []:
            name = row.get("name") or ""
            if "ekso" in name.lower() or "indego" in name.lower() or q.lower() in name.lower():
                print(" ", row.get("id"), row.get("status"), name)

    for rid in IDS:
        try:
            audit(client, rid)
        except Exception as e:
            print("ERR", rid, e)

    oem("https://eksobionics.com/")
    oem("https://eksobionics.com/eksonr/")
    oem("https://eksobionics.com/ekso-indego-personal/")
    oem("https://eksobionics.com/ekso-evo")
    oem("https://eksobionics.com/past-products/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
