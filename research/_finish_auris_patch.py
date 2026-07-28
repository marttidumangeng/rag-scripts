"""Finish Auris soft-PATCH after import (keep ™ names — plain name 500s)."""
from __future__ import annotations

import sys
from pathlib import Path

_RESEARCH = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env()

from api_client import ResearchApiClient

BRONCH = (
    "https://www.jnjmedtech.com/en-US/products/robotics/monarch-platform/bronchoscopy/"
)
QUEST_PR = (
    "https://www.jnjmedtech.com/en-US/news/press-releases/"
    "johnson-johnson-medtech-announces-clearance-of-monarch-quest-for-enhanced-"
    "robotic-assisted-bronchoscopy/"
)

SPECS = [
    {
        "id": 1648,
        "name": "MONARCH™ Platform",
        "model_name": "MONARCH",
        "variant_code": "MONARCH-Platform",
        "variant_label": "Platform",
        "url": BRONCH,
        "purpose": (
            "Robotic-assisted peripheral lung nodule biopsy\n"
            "Bronchoscopic airway visualization and access"
        ),
        "description": (
            "The MONARCH™ Platform from Johnson & Johnson MedTech (Auris Health) is a "
            "flexible robotic-assisted bronchoscopy system. A telescoping scope-in-sheath "
            "design with continuous visualization helps clinicians navigate peripheral "
            "airways and biopsy suspicious lung nodules."
        ),
        "features": (
            "OEM J&J MedTech MONARCH™ Platform (bronchoscopy PDP): first flexible "
            "robotic-assisted bronchoscopy platform; AI-powered navigation/image "
            "processing; telescoping scope + sheath with independent articulation; "
            "access all 18 lung segments; continuous vision during procedure; "
            "ergonomic controller for sit/stand OR positioning; indicated for "
            "bronchoscopic visualization and airway access for diagnostic/therapeutic "
            "procedures (FDA 510(k) lineage K152819). Soft: typed system mass/dims/MSRP "
            "not published on OEM PDP."
        ),
        "sources": [
            BRONCH,
            "https://www.aurishealth.com/en-US/products/robotics/monarch-platform/bronchoscopy/",
        ],
        "tags": [
            "Auris",
            "J&J MedTech",
            "MONARCH",
            "Bronchoscopy",
            "RAB",
            "Lung biopsy",
            "Healthcare",
            "USA",
        ],
        "hero": (
            "https://images.contentstack.io/v3/assets/blt6442fb89e58ceab5/"
            "blt0391701dfbc69dce/693c6a101c829546b6529dd9/US_SRG_RADS_389015.1.jpg"
        ),
    },
    {
        "id": 1649,
        "name": "MONARCH™ QUEST",
        "model_name": "MONARCH QUEST",
        "variant_code": "MONARCH-QUEST",
        "variant_label": "QUEST",
        "url": f"{BRONCH}#monarch-quest",
        "purpose": (
            "AI-enhanced robotic bronchoscopy navigation\n"
            "Intraprocedural 3D imaging–guided nodule targeting"
        ),
        "description": (
            "MONARCH™ QUEST is Johnson & Johnson MedTech's FDA-cleared (March 2025) "
            "navigation advancement for the MONARCH™ Platform. It adds more powerful "
            "AI navigation algorithms and verified interfaces to GE HealthCare OEC 3D "
            "and Siemens Cios Spin imaging for tool-in-lesion confirmation workflows."
        ),
        "features": (
            "OEM J&J MedTech MONARCH™ QUEST (PDP + 2025-03-12 clearance PR): latest "
            "MONARCH navigation technology; AI-powered algorithms; verified OEC Open "
            "interface with GE HealthCare OEC 3D mobile CBCT; Siemens Cios Spin "
            "integration cited on PDP; fused navigation / tool-in-lesion confirmation "
            "workflow; airway mapping deeper into periphery. Soft: software/capability "
            "upgrade on MONARCH hardware — typed kinematics/MSRP not applicable on PDP."
        ),
        "sources": [f"{BRONCH}#monarch-quest", QUEST_PR, BRONCH],
        "tags": [
            "Auris",
            "J&J MedTech",
            "MONARCH",
            "QUEST",
            "Bronchoscopy",
            "AI navigation",
            "Healthcare",
            "USA",
        ],
        "hero": (
            "https://images.contentstack.io/v3/assets/blt6442fb89e58ceab5/"
            "blt56332663aa4dd6f5/693c6a4931ed5e7752af6178/"
            "US_SRG_RADS_389015.1_Introducing_MONARCH%E2%84%A2_QUEST_Hero.jpg"
        ),
    },
]


def main() -> int:
    client = ResearchApiClient()
    tax_uses = {u["key"]: u["id"] for u in client._get("robots/uses/")}
    tax_ind = {u["key"]: u["id"] for u in client._get("robots/industries/")}
    tax_mov = {u["key"]: u["id"] for u in client._get("robots/movement-types/")}

    for spec in SPECS:
        rid = spec["id"]
        notes = (
            "[AI Research] Auris/J&J enrich 2026-07-20: US; family auris:monarch; "
            "Available; OEM bronchoscopy + QUEST PR; soft typed mass/dims/MSRP absent on PDP."
        )
        body = {
            "manufacturer_countries": [20],
            "manufacturer_country_ref": 20,
            "availability_status": 11,
            "name": spec["name"],
            "model_name": spec["model_name"],
            "variant_code": spec["variant_code"],
            "variant_label": spec["variant_label"],
            "description": spec["description"],
            "features": spec["features"],
            "purpose": spec["purpose"],
            "url": spec["url"],
            "information_source_urls": spec["sources"],
            "family_key": "auris:monarch",
            "family_name": "MONARCH",
            "family_url": BRONCH,
            "product_url_scope": "exact_variant",
            "notes": notes,
            "tags": spec["tags"],
            "uses": [tax_uses["surgery"], tax_uses["medical-assistance"]],
            "industries": [tax_ind["healthcare"]],
            "movement_types": [tax_mov["stationary"]],
            "image": spec["hero"],
        }
        client._patch(f"robots/robots/{rid}/", body)
        print("patched", rid)
        sync = {
            "updates": [
                {
                    "id": rid,
                    "locale": loc,
                    "source_hash": f"auris-en-{rid}-20260720b-{loc}",
                    "translated_fields": {
                        "description": spec["description"],
                        "features": spec["features"],
                        "purpose": spec["purpose"],
                        "name": spec["name"],
                    },
                }
                for loc in ("zh-CN", "zh-TW")
            ]
        }
        resp = client._session.post(
            client._url("robots/robots/translation-sync/?force=1"),
            json=sync,
            timeout=60,
        )
        print("  sync", rid, resp.status_code)

    print("=== VERIFY ===")
    for rid in [1653, 1648, 1649, 4959, 4027, 577]:
        r = client._get(f"robots/robots/{rid}/")
        purpose = (r.get("purpose") or "").replace("\n", " / ")[:60]
        print(
            rid,
            r.get("status"),
            r.get("name"),
            "fam=" + str(r.get("family_key")),
            "feat=" + str(len(r.get("features") or "")),
            "purpose=" + purpose,
            "speed=" + str(r.get("speed")),
            "wt=" + str(r.get("weight_kg")),
            "pay=" + str(r.get("payload_kg")),
            "price=" + str(r.get("price_min")),
            "src=" + str(bool(r.get("information_source_urls"))),
            "avail=" + str((r.get("availability_status") or {}).get("key")),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
