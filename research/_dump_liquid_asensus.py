"""Dump Liquid Robotics (429) and Asensus (328) pending robots for overnight enrich."""
from __future__ import annotations

import json
import sys
from pathlib import Path

_RESEARCH = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient

TARGETS = {
    429: [3869],
    328: [4032, 1654, 1635],
}
FIELDS = [
    "id",
    "name",
    "slug",
    "status",
    "url",
    "website_url",
    "description",
    "purpose",
    "features",
    "availability_status",
    "family_key",
    "family_name",
    "family_url",
    "model_name",
    "variant_code",
    "variant_label",
    "product_url_scope",
    "manufacturer_country_ref",
    "manufacturer_countries",
    "payload_kg",
    "weight_kg",
    "speed",
    "length_mm",
    "width_mm",
    "height_mm",
    "runtime_minutes",
    "dof",
    "price_min",
    "price_max",
    "price_currency",
    "image",
    "s3_image",
    "tags",
    "notes",
    "information_source_urls",
    "rejection_reason",
]


def main() -> int:
    client = ResearchApiClient()
    out: dict = {}
    for company_id, robot_ids in TARGETS.items():
        company = client.get_company(company_id)
        out[str(company_id)] = {
            "company": {
                "id": company.get("id"),
                "name": company.get("name"),
                "slug": company.get("slug"),
                "website": company.get("website"),
                "country": company.get("country"),
            },
            "robots": [],
        }
        for rid in robot_ids:
            r = client._get(f"robots/robots/{rid}/")
            slim = {k: r.get(k) for k in FIELDS}
            # keep photo count
            photos = r.get("photos") or []
            slim["photo_count"] = len(photos)
            slim["primary_photo"] = None
            for p in photos:
                if p.get("is_primary") or not slim["primary_photo"]:
                    slim["primary_photo"] = {
                        "url": p.get("s3_image") or p.get("image") or p.get("url"),
                        "is_primary": p.get("is_primary"),
                    }
            out[str(company_id)]["robots"].append(slim)
            print(
                f"{company_id}/{rid}",
                slim.get("name"),
                slim.get("status"),
                "url=",
                (slim.get("url") or "")[:80],
                "family=",
                slim.get("family_key"),
                "avail=",
                slim.get("availability_status"),
            )
    path = _RESEARCH / "staging" / "reports" / "liquid-asensus-dump.json"
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print("wrote", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
