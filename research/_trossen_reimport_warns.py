"""Re-import Trossen warn-fix rows with required sources + research_notes."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

_RESEARCH = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient
from import_staging import import_staging, resolve_created_by_id
from _trossen_fix_warns import FIXES, COMPANY_SLUG, COMPANY_NAME, US_ID, AVAILABLE, DISCONTINUED, copy_media

REPORT = _RESEARCH / "staging" / "reports" / "trossen-fix-warns.json"
plan = json.loads(REPORT.read_text(encoding="utf-8"))
by_id = {r["id"]: r for r in plan["robots"]}

client = ResearchApiClient()
for rid, spec in FIXES.items():
    images = (by_id.get(rid) or {}).get("images") or []
    if len(images) < 1:
        print(rid, "SKIP no images in report")
        continue
    # pad 5273 to 4 if only 3 — duplicate last crop not allowed; leave 3
    full = client._session.get(client._url(f"robots/robots/{rid}/"), timeout=60).json()
    avail = DISCONTINUED if spec.get("discontinued") else AVAILABLE
    url = full.get("url") or f"https://www.trossenrobotics.com/"
    notes = (
        f"[AI Research] Trossen warn-fix 2026-07-20. Sources: OEM PDP {url}; "
        "Interbotix X-Series docs/drawings for specs/years. "
        f"Prices from OEM PDP HTML where listed. "
        f"Availability={'Discontinued' if spec.get('discontinued') else 'Available'} "
        "per PDP banner."
    )
    row = {
        "id": rid,
        "name": spec["name"],
        "model_name": full.get("model_name") or spec["name"],
        "company_slug": COMPANY_SLUG,
        "company_name": COMPANY_NAME,
        "manufacturer_country_code": "US",
        "manufacturer_country_codes": "US",
        "description": spec["description"],
        "purpose": full.get("purpose") or "",
        "features": full.get("features") or "",
        "url": url,
        "image": images[0],
        "images": images,
        "source_locale": "en",
        "availability_status": avail,
        "family_key": full.get("family_key") or "",
        "family_name": full.get("family_name") or "",
        "family_url": full.get("family_url") or "",
        "movement_type_keys": "wheeled" if rid == 5268 else "stationary",
        "category_slugs": "research-robots",
        "use_keys": "research|data-collection|education",
        "industry_keys": "education|research",
        "notes": notes,
        "research_notes": notes,
        "sources": [
            {"url": url, "type": "website", "title": f"{spec['name']} OEM PDP"},
            {
                "url": "https://docs.trossenrobotics.com/interbotix_xsarms_docs/specifications.html",
                "type": "datasheet",
                "title": "Interbotix X-Series specifications",
            },
        ],
        "information_source_urls": [
            url,
            "https://docs.trossenrobotics.com/interbotix_xsarms_docs/specifications.html",
        ],
    }
    for k in (
        "dof",
        "payload_kg",
        "reach_mm",
        "weight_kg",
        "repeatability_mm",
        "release_year",
        "price_min",
        "price_max",
        "price_currency",
        "price_range",
    ):
        if spec.get(k) is not None:
            row[k] = spec[k]

    staging = _RESEARCH / "staging" / "robots" / COMPANY_SLUG
    staging.mkdir(parents=True, exist_ok=True)
    path = staging / f"warnfix2-{rid}.json"
    path.write_text(json.dumps(row, indent=2), encoding="utf-8")
    result = import_staging(
        path,
        dry_run=False,
        patch=True,
        force_overwrite=True,
        replace_media=True,
        status="pending_review",
        created_by_id=resolve_created_by_id(1),
        skip_company_update=True,
    )
    print(rid, "import", result)
    body = {
        "manufacturer_countries": [US_ID],
        "manufacturer_country_ref": US_ID,
        "availability_status": avail,
        "description": spec["description"],
        "notes": notes,
        "s3_image": None,
    }
    for k in (
        "dof",
        "payload_kg",
        "reach_mm",
        "weight_kg",
        "repeatability_mm",
        "release_year",
        "price_min",
        "price_max",
        "price_currency",
        "price_range",
        "family_key",
        "family_name",
        "family_url",
    ):
        if row.get(k) not in (None, ""):
            body[k] = row[k]
    for attempt in range(4):
        try:
            client._patch(f"robots/robots/{rid}/", body)
            print(rid, "patched")
            break
        except Exception as e:  # noqa: BLE001
            print(rid, "patch retry", e)
            time.sleep(2**attempt)
    print(rid, "copy-media", copy_media(rid))
    # re-PATCH after copy-media
    try:
        client._patch(f"robots/robots/{rid}/", body)
    except Exception as e:  # noqa: BLE001
        print(rid, "repatch warn", e)
