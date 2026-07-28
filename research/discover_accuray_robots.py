"""Accuray Inc. (1378): reject CyberKnife trademark dupes; enrich Radixact + TomoTherapy.

Reject:
  1477 CyberKnife® S7™ → dupe of published CyberKnife S7 (222)
  1478 CyberKnife® M6™ → dupe of published CyberKnife M6 (368)

Enrich pending:
  1479 Radixact® System (current TomoTherapy gen) Available
  1480/1481/1482 TomoTherapy Hi-Art / HD / HDA Discontinued lineage

Also soft-fill published CyberKnife 222/368 (EN + URL + sources + features ≥40).

OEM site Cloudflare-blocked this pass — cite Accuray IR + PubMed lineage reviews.

Usage:
  python discover_accuray_robots.py --apply
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import requests

_RESEARCH = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient
from import_staging import import_staging, resolve_created_by_id

COMPANY_SLUG = "accuray-inc"
COMPANY_NAME = "Accuray Incorporated"
US_ID = 20
AVAILABLE = 11
DISCONTINUED = 4

REJECTS = [
    (
        1477,
        "duplicate: keep published CyberKnife S7 (222); pending 1477 is trademark-spelling shell",
    ),
    (
        1478,
        "duplicate: keep published CyberKnife M6 (368); pending 1478 is trademark-spelling shell",
    ),
]

PRODUCTS: list[dict[str, Any]] = [
    {
        "id": 1479,
        "name": "Radixact System",
        "model_name": "Radixact",
        "variant_code": "Radixact",
        "variant_label": "Radixact",
        "url": "https://www.accuray.com/radixact/",
        "family_key": "accuray:radixact",
        "family_name": "Radixact",
        "family_url": "https://www.accuray.com/radixact/",
        "product_url_scope": "exact_variant",
        "availability_status": AVAILABLE,
        "purpose": (
            "Image-guided intensity-modulated radiation therapy\n"
            "Helical and discrete-angle radiotherapy delivery"
        ),
        "description": (
            "Radixact is Accuray's current image-guided radiation therapy platform — "
            "the fourth-generation evolution of TomoTherapy — combining helical/"
            "TomoDirect delivery with MVCT (and optional ClearRT kV imaging) for "
            "precise IMRT/SBRT-class treatments."
        ),
        "features": (
            "Accuray Radixact / TomoTherapy lineage (IR 510(k) 2016 + clinical reviews): "
            "ring-gantry IG-IMRT; helical + TomoDirect modalities; ultra-fast MLC; "
            "MVCT image guidance; optional ClearRT kV-CT; redesigned Precision TPS + "
            "iDMS; higher dose-rate class (~1000 cGy/min cited vs ~850 on prior gens). "
            "Soft: OEM PDP Cloudflare-blocked this pass; typed room dims/price not set."
        ),
        "use_keys": "surgery|medical-assistance",
        "industry_keys": "healthcare",
        "category_slugs": "medical-robots|service-robots",
        "movement_keys": "stationary",
        "tags": [
            "Accuray",
            "Radixact",
            "TomoTherapy",
            "IGRT",
            "IMRT",
            "Radiotherapy",
            "Healthcare",
            "USA",
        ],
        "sources": [
            {"url": "https://www.accuray.com/radixact/", "type": "website", "title": "OEM Radixact"},
            {
                "url": "https://investors.accuray.com/news-releases/news-release-details/accuray-receives-510k-fda-clearance-radixacttm-image-guided",
                "type": "website",
                "title": "FDA 510(k) Radixact clearance",
            },
            {
                "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC9712831/",
                "type": "website",
                "title": "Hi-ART / Tomo-HD / Radixact comparison",
            },
        ],
    },
    {
        "id": 1482,
        "name": "TomoTherapy HDA System",
        "model_name": "TomoTherapy HDA",
        "variant_code": "TomoTherapy-HDA",
        "variant_label": "HDA",
        "url": "https://www.accuray.com/tomotherapy/tomotherapy-history/#hda",
        "family_key": "accuray:tomotherapy",
        "family_name": "TomoTherapy",
        "family_url": "https://www.accuray.com/tomotherapy/",
        "product_url_scope": "exact_variant",
        "availability_status": DISCONTINUED,
        "purpose": (
            "Image-guided IMRT with dynamic jaws\n"
            "Legacy TomoTherapy H-series radiotherapy"
        ),
        "description": (
            "TomoTherapy HDA is Accuray's third-generation TomoTherapy platform "
            "(~2012), integrating helical/TomoDirect delivery and TomoEDGE dynamic "
            "jaws for faster, more precise IG-IMRT before Radixact."
        ),
        "features": (
            "TomoTherapy H-series / HDA lineage: helical IG-IMRT; TomoDirect fixed-angle "
            "IMRT; TomoEDGE dynamic jaws; MVCT guidance; ~850 cGy/min class cited in "
            "generation comparisons. Soft: Discontinued / superseded by Radixact; OEM "
            "history URL retained; shared stock hero soft across TomoTherapy pending."
        ),
        "use_keys": "surgery|medical-assistance",
        "industry_keys": "healthcare",
        "category_slugs": "medical-robots|service-robots",
        "movement_keys": "stationary",
        "tags": [
            "Accuray",
            "TomoTherapy",
            "HDA",
            "IGRT",
            "IMRT",
            "Discontinued",
            "Healthcare",
            "USA",
        ],
        "sources": [
            {
                "url": "https://www.accuray.com/tomotherapy/tomotherapy-history/#hda",
                "type": "website",
                "title": "TomoTherapy HDA history",
            },
            {
                "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC9712831/",
                "type": "website",
                "title": "Generation comparison",
            },
        ],
    },
    {
        "id": 1481,
        "name": "TomoTherapy HD System",
        "model_name": "TomoTherapy HD",
        "variant_code": "TomoTherapy-HD",
        "variant_label": "HD",
        "url": "https://www.accuray.com/tomotherapy/tomotherapy-history/#hd",
        "family_key": "accuray:tomotherapy",
        "family_name": "TomoTherapy",
        "family_url": "https://www.accuray.com/tomotherapy/",
        "product_url_scope": "exact_variant",
        "availability_status": DISCONTINUED,
        "purpose": (
            "Image-guided IMRT with TomoDirect delivery\n"
            "Second-generation TomoTherapy radiotherapy"
        ),
        "description": (
            "TomoTherapy HD is Accuray's second-generation TomoTherapy system "
            "(~2007), adding TomoDirect fixed-beam IMRT alongside helical delivery "
            "and improved imaging versus Hi-Art."
        ),
        "features": (
            "TomoTherapy HD lineage: helical IG-IMRT + TomoDirect; improved image "
            "quality vs Hi-Art; TomoEDGE dynamic jaws on later configs; MVCT guidance. "
            "Soft: Discontinued; superseded by HDA then Radixact; OEM history URL retained."
        ),
        "use_keys": "surgery|medical-assistance",
        "industry_keys": "healthcare",
        "category_slugs": "medical-robots|service-robots",
        "movement_keys": "stationary",
        "tags": [
            "Accuray",
            "TomoTherapy",
            "HD",
            "IGRT",
            "IMRT",
            "Discontinued",
            "Healthcare",
            "USA",
        ],
        "sources": [
            {
                "url": "https://www.accuray.com/tomotherapy/tomotherapy-history/#hd",
                "type": "website",
                "title": "TomoTherapy HD history",
            },
            {
                "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC9712831/",
                "type": "website",
                "title": "Generation comparison",
            },
        ],
    },
    {
        "id": 1480,
        "name": "TomoTherapy Hi-Art System",
        "model_name": "TomoTherapy Hi-Art",
        "variant_code": "TomoTherapy-Hi-Art",
        "variant_label": "Hi-Art",
        "url": "https://www.accuray.com/tomotherapy/tomotherapy-history/#hi-art",
        "family_key": "accuray:tomotherapy",
        "family_name": "TomoTherapy",
        "family_url": "https://www.accuray.com/tomotherapy/",
        "product_url_scope": "exact_variant",
        "availability_status": DISCONTINUED,
        "purpose": (
            "Helical image-guided IMRT\n"
            "First commercial TomoTherapy radiotherapy system"
        ),
        "description": (
            "TomoTherapy Hi-Art was Accuray's first commercial TomoTherapy system "
            "(clinical launch ~2002), combining a CT-class imager with a linear "
            "accelerator for daily MVCT-guided helical IMRT."
        ),
        "features": (
            "TomoTherapy Hi-Art: first commercial helical IG-IMRT platform; integrated "
            "MVCT + linac on ring gantry; binary MLC; daily imaging for precise dose "
            "delivery. Soft: Discontinued; lineage continues through HD/HDA to Radixact."
        ),
        "use_keys": "surgery|medical-assistance",
        "industry_keys": "healthcare",
        "category_slugs": "medical-robots|service-robots",
        "movement_keys": "stationary",
        "tags": [
            "Accuray",
            "TomoTherapy",
            "Hi-Art",
            "IGRT",
            "IMRT",
            "Discontinued",
            "Healthcare",
            "USA",
        ],
        "sources": [
            {
                "url": "https://www.accuray.com/tomotherapy/tomotherapy-history/#hi-art",
                "type": "website",
                "title": "TomoTherapy Hi-Art history",
            },
            {
                "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC9712831/",
                "type": "website",
                "title": "Generation comparison",
            },
        ],
    },
]

PUBLISHED_SOFT = [
    {
        "id": 222,
        "name": "CyberKnife S7",
        "url": "https://www.accuray.com/cyberknife/",
        "family_key": "accuray:cyberknife",
        "family_name": "CyberKnife",
        "family_url": "https://www.accuray.com/cyberknife/",
        "variant_code": "CyberKnife-S7",
        "variant_label": "S7",
        "purpose": (
            "Robotic stereotactic radiosurgery and SBRT\n"
            "Non-invasive tumor-targeted radiation delivery"
        ),
        "description": (
            "CyberKnife S7 is Accuray's robotic radiosurgery system for stereotactic "
            "radiosurgery (SRS) and stereotactic body radiation therapy (SBRT), "
            "delivering precise non-invasive treatments with real-time tracking."
        ),
        "features": (
            "OEM Accuray CyberKnife platform: robotic arm–mounted linac; real-time "
            "tumor tracking; SRS/SBRT across intracranial and extracranial indications; "
            "S7 generation current-class system. Soft: OEM PDP Cloudflare-blocked this "
            "pass; typed kinematics/price not set."
        ),
        "sources": [
            "https://www.accuray.com/cyberknife/",
            "https://www.accuray.com/",
        ],
    },
    {
        "id": 368,
        "name": "CyberKnife M6",
        "url": "https://www.accuray.com/cyberknife/#m6-1",
        "family_key": "accuray:cyberknife",
        "family_name": "CyberKnife",
        "family_url": "https://www.accuray.com/cyberknife/",
        "variant_code": "CyberKnife-M6",
        "variant_label": "M6",
        "purpose": (
            "Robotic stereotactic radiosurgery and SBRT\n"
            "Prior-generation CyberKnife radiosurgery platform"
        ),
        "description": (
            "CyberKnife M6 is Accuray's prior-generation robotic radiosurgery system "
            "for SRS/SBRT with real-time tracking, preceding the S7 generation."
        ),
        "features": (
            "OEM Accuray CyberKnife M6: robotic radiosurgery; SRS/SBRT; real-time "
            "tracking; InCise MLC-class beam shaping on M6 configs. Soft: superseded "
            "in lineup by S7; OEM URL retained; typed kinematics/price not set."
        ),
        "sources": [
            "https://www.accuray.com/cyberknife/#m6-1",
            "https://www.accuray.com/cyberknife/",
            "https://www.accuray.com/",
        ],
    },
]


def taxonomy_ids(client: ResearchApiClient) -> dict[str, dict[str, int]]:
    def idx(path: str) -> dict[str, int]:
        rows = client._get(path)
        return {
            (r.get("key") or "").lower(): int(r["id"])
            for r in rows
            if r.get("key") and r.get("id")
        }

    return {
        "uses": idx("robots/uses/"),
        "industries": idx("robots/industries/"),
        "movement": idx("robots/movement-types/"),
    }


def map_keys(tax: dict[str, dict[str, int]], group: str, keys: str) -> list[int]:
    out = []
    for k in keys.split("|"):
        kid = tax[group].get(k.strip().lower())
        if kid:
            out.append(kid)
        else:
            print(f"  warn missing {group}={k}")
    return out


def force_en(client: ResearchApiClient, rid: int, row: dict[str, Any]) -> None:
    sync = {
        "updates": [
            {
                "id": rid,
                "locale": loc,
                "source_hash": f"accuray-en-{rid}-20260720-{loc}",
                "translated_fields": {
                    "description": row.get("description") or "",
                    "features": row.get("features") or "",
                    "purpose": row.get("purpose") or "",
                    "name": row.get("name") or "",
                },
            }
            for loc in ("zh-CN", "zh-TW")
        ]
    }
    try:
        resp = client._session.post(
            client._url("robots/robots/translation-sync/?force=1"),
            json=sync,
            timeout=60,
        )
        print(f"  translation-sync {rid}: {resp.status_code}")
    except requests.RequestException as e:
        print(f"  translation-sync warn {rid}: {e}")


def reject_dupes(client: ResearchApiClient) -> None:
    for rid, reason in REJECTS:
        try:
            client._patch(
                f"robots/robots/{rid}/",
                {
                    "status": "rejected",
                    "rejection_reason": reason[:500],
                    "notes": f"[AI Research] Rejected 2026-07-20: {reason}",
                },
            )
            print("rejected", rid, reason[:60])
        except Exception as e:
            print("reject FAIL", rid, e)


def soft_fill_published(client: ResearchApiClient, tax: dict) -> None:
    for spec in PUBLISHED_SOFT:
        rid = spec["id"]
        body: dict[str, Any] = {
            "name": spec["name"],
            "url": spec["url"],
            "information_source_urls": spec["sources"],
            "family_key": spec["family_key"],
            "family_name": spec["family_name"],
            "family_url": spec["family_url"],
            "model_name": "CyberKnife",
            "variant_code": spec["variant_code"],
            "variant_label": spec["variant_label"],
            "product_url_scope": "exact_variant",
            "manufacturer_countries": [US_ID],
            "manufacturer_country_ref": US_ID,
            "availability_status": AVAILABLE,
            "description": spec["description"],
            "purpose": spec["purpose"],
            "features": spec["features"],
            "tags": [
                "Accuray",
                "CyberKnife",
                spec["variant_label"],
                "Radiosurgery",
                "SRS",
                "SBRT",
                "Healthcare",
                "USA",
            ],
            "uses": map_keys(tax, "uses", "surgery|medical-assistance"),
            "industries": map_keys(tax, "industries", "healthcare"),
            "movement_types": map_keys(tax, "movement", "stationary"),
            "notes": (
                "[AI Research] Soft-fill published CyberKnife 2026-07-20: EN + URL + "
                "sources + family (soft warns filled when data known)."
            ),
        }
        try:
            client._patch(f"robots/robots/{rid}/", body)
            force_en(client, rid, body)
            print("soft-filled published", rid, spec["name"])
        except Exception as e:
            print("soft-fill FAIL", rid, e)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    client = ResearchApiClient()
    tax = taxonomy_ids(client)
    staging = _RESEARCH / "staging" / "robots" / COMPANY_SLUG
    staging.mkdir(parents=True, exist_ok=True)

    if args.apply:
        reject_dupes(client)
        soft_fill_published(client, tax)

    for spec in PRODUCTS:
        existing = client._get(f"robots/robots/{spec['id']}/")
        img = existing.get("image") or existing.get("s3_image") or ""
        # Prefer draft Radixact hero if pending still on shared Tomo stock
        if spec["id"] == 1479:
            try:
                draft = client._get("robots/robots/369/")
                dimg = draft.get("image") or ""
                if dimg and dimg != img:
                    img = dimg
                    print("using draft Radixact hero for 1479")
            except Exception:
                pass
        notes = (
            f"[AI Research] Accuray enrich 2026-07-20: US; family {spec['family_key']}; "
            f"avail={spec['availability_status']}; soft specs from IR/PubMed lineage."
        )
        info_urls = [s["url"] for s in spec["sources"]]
        row: dict[str, Any] = {
            "id": spec["id"],
            "name": spec["name"],
            "model_name": spec["model_name"],
            "variant_code": spec["variant_code"],
            "variant_label": spec["variant_label"],
            "company_slug": COMPANY_SLUG,
            "company_name": COMPANY_NAME,
            "manufacturer_country_code": "US",
            "manufacturer_country_codes": "US",
            "description": spec["description"],
            "purpose": spec["purpose"],
            "features": spec["features"],
            "url": spec["url"],
            "image": img,
            "images": [img] if img else [],
            "source_locale": "en",
            "availability_status": spec["availability_status"],
            "family_key": spec["family_key"],
            "family_name": spec["family_name"],
            "family_url": spec["family_url"],
            "product_url_scope": spec["product_url_scope"],
            "movement_type_keys": spec["movement_keys"],
            "category_slugs": spec["category_slugs"],
            "use_keys": spec["use_keys"],
            "industry_keys": spec["industry_keys"],
            "tags": spec["tags"],
            "notes": notes,
            "research_notes": notes,
            "sources": spec["sources"],
            "information_source_urls": info_urls,
        }
        path = staging / f"{spec['variant_code'].lower()}.json"
        path.write_text(json.dumps(row, indent=2, ensure_ascii=False), encoding="utf-8")
        print("staged", path.name)

        if not args.apply:
            continue

        print(
            "import",
            spec["id"],
            import_staging(
                path,
                dry_run=False,
                patch=True,
                force_overwrite=True,
                replace_media=bool(spec["id"] == 1479 and img),
                status="pending_review",
                created_by_id=resolve_created_by_id(1),
                skip_company_update=True,
            ),
        )
        body: dict[str, Any] = {
            "manufacturer_countries": [US_ID],
            "manufacturer_country_ref": US_ID,
            "availability_status": spec["availability_status"],
            "description": spec["description"],
            "features": spec["features"],
            "purpose": spec["purpose"],
            "name": spec["name"],
            "url": spec["url"],
            "information_source_urls": info_urls,
            "family_key": spec["family_key"],
            "family_name": spec["family_name"],
            "family_url": spec["family_url"],
            "notes": notes,
            "tags": spec["tags"],
            "uses": map_keys(tax, "uses", spec["use_keys"]),
            "industries": map_keys(tax, "industries", spec["industry_keys"]),
            "movement_types": map_keys(tax, "movement", spec["movement_keys"]),
        }
        if img:
            body["image"] = img
        client._patch(f"robots/robots/{spec['id']}/", body)
        force_en(client, spec["id"], row)

    print("done apply=", args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
