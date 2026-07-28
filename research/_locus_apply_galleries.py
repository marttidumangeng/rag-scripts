"""Apply fixed CDN galleries for Locus Vector + Array via full staging import."""
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
from discover_locus_robots import copy_media
from import_staging import import_staging, resolve_created_by_id

VECTOR_URLS = [
    "https://cdn.robotaigeek.com/research-staging/locus/vector-fix-0-20260720.jpg",
    "https://cdn.robotaigeek.com/research-staging/locus/vector-fix-1-20260720.jpg",
    "https://cdn.robotaigeek.com/research-staging/locus/vector-fix-2-20260720.jpg",
]
ARRAY_URLS = [
    "https://cdn.robotaigeek.com/research-staging/locus/array-fix-0-20260720.jpg",
    "https://cdn.robotaigeek.com/research-staging/locus/array-fix-1-20260720.jpg",
    "https://cdn.robotaigeek.com/research-staging/locus/array-fix-2-20260720.jpg",
    "https://cdn.robotaigeek.com/research-staging/locus/array-fix-3-20260720.jpg",
]

ROWS = [
    {
        "id": 4885,
        "name": "Locus Vector",
        "model_name": "Vector",
        "company_slug": "locus-robotics",
        "company_name": "Locus Robotics",
        "purpose": "Heavy omnidirectional AMR for case picking and point-to-point transport",
        "description": (
            "Locus Vector is a material-handling AMR with Mecanum omnidirectional drive "
            "for case picking, shelf moves, and point-to-point transport."
        ),
        "features": (
            "OEM Locus Vector: up to 272 kg / 600 lb payload; Mecanum drive; dual "
            "safety-rated LiDAR; 8–10 h runtime."
        ),
        "image": VECTOR_URLS[0],
        "images": VECTOR_URLS,
        "url": "https://locusrobotics.com/locusone/fleet/locus-vector-material-handling-robot",
        "manufacturer_country_code": "US",
        "availability_status": 11,
        "family_key": "locus:vector",
        "family_name": "Vector",
        "family_url": "https://locusrobotics.com/locusone/fleet/locus-vector-material-handling-robot",
        "sources": [
            {
                "url": "https://locusrobotics.com/locusone/fleet/locus-vector-material-handling-robot",
                "type": "website",
                "title": "Locus Vector",
            }
        ],
        "information_source_urls": [
            "https://locusrobotics.com/locusone/fleet/locus-vector-material-handling-robot"
        ],
        "category_slugs": "industrial-robots",
        "use_keys": "transport|warehouse|logistics",
        "movement_type_keys": "wheeled",
    },
    {
        "id": 2536,
        "name": "Locus Array",
        "model_name": "Array",
        "company_slug": "locus-robotics",
        "company_name": "Locus Robotics",
        "purpose": "Fully autonomous aisle picking and robots-to-goods fulfillment",
        "description": (
            "Locus Array is a Physical AI mobile manipulator for robots-to-goods "
            "fulfillment with six active totes and NeuraGrasp end-effector."
        ),
        "features": (
            "OEM Locus Array: autonomous aisle pick/putaway; 6 totes; NeuraGrasp "
            "soft-membrane gripper; LocusONE orchestrated."
        ),
        "image": ARRAY_URLS[0],
        "images": ARRAY_URLS,
        "url": "https://locusrobotics.com/locusone/fleet/locus-array",
        "manufacturer_country_code": "US",
        "availability_status": 11,
        "family_key": "locus:array",
        "family_name": "Array",
        "family_url": "https://locusrobotics.com/locusone/fleet/locus-array",
        "sources": [
            {
                "url": "https://locusrobotics.com/locusone/fleet/locus-array",
                "type": "website",
                "title": "Locus Array",
            }
        ],
        "information_source_urls": ["https://locusrobotics.com/locusone/fleet/locus-array"],
        "category_slugs": "industrial-robots",
        "use_keys": "pick-and-place|warehouse|logistics",
        "movement_type_keys": "wheeled",
    },
]


def main() -> int:
    client = ResearchApiClient()
    for row in ROWS:
        path = (
            _RESEARCH
            / "staging"
            / "robots"
            / "locus-robotics"
            / f"{row['model_name'].lower()}-gallery.json"
        )
        path.write_text(json.dumps(row, indent=2), encoding="utf-8")
        print(
            row["id"],
            import_staging(
                path,
                dry_run=False,
                patch=True,
                force_overwrite=True,
                replace_media=True,
                status="pending_review",
                created_by_id=resolve_created_by_id(1),
                skip_company_update=True,
            ),
        )
        client._patch(
            f"robots/robots/{row['id']}/",
            {
                "image": row["image"],
                "s3_image": None,
                "purpose": row["purpose"],
                "features": row["features"],
                "family_key": row["family_key"],
                "family_name": row["family_name"],
                "family_url": row["family_url"],
            },
        )
        print("copy", copy_media(row["id"]))
        after = client._get(f"robots/robots/{row['id']}/")
        print(
            " after image",
            after.get("image"),
            "photos",
            len(after.get("photos") or []),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
