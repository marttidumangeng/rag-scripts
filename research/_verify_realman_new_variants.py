"""Detail-check new Realman variants + repair RX71 typed specs if wiped."""
from __future__ import annotations

import json
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient

c = ResearchApiClient()
for rid in (5511, 5512, 5230):
    r = c._get(f"robots/robots/{rid}/")
    imgs = r.get("images") or []
    print(
        json.dumps(
            {
                "id": rid,
                "name": r.get("name"),
                "status": r.get("status"),
                "images_n": len(imgs) if isinstance(imgs, list) else 0,
                "image": (r.get("image") or "")[-50:],
                "s3": bool(r.get("s3_image")),
                "feat_len": len(r.get("features") or ""),
                "country": (r.get("manufacturer_country_ref") or {}).get("code")
                if isinstance(r.get("manufacturer_country_ref"), dict)
                else r.get("manufacturer_country_ref"),
                "categories": r.get("categories"),
                "uses_n": len(r.get("uses") or []),
                "dof": r.get("dof"),
                "payload_kg": r.get("payload_kg"),
                "reach_mm": r.get("reach_mm"),
                "weight_kg": r.get("weight_kg"),
            },
            ensure_ascii=False,
        )
    )

# Repair RX71 typed specs if missing (rename patch should not have cleared them)
r = c._get("robots/robots/5230/")
if r.get("payload_kg") is None or r.get("reach_mm") is None:
    c._patch(
        "robots/robots/5230/",
        {
            "dof": 7,
            "payload_kg": 1.0,
            "reach_mm": 474.0,
            "weight_kg": 3.8,
            "manufacturer_countries": [3],
            "manufacturer_country_ref": 3,
        },
    )
    print("repaired 5230 typed specs")
    r2 = c._get("robots/robots/5230/")
    print("after", r2.get("payload_kg"), r2.get("reach_mm"), r2.get("dof"))
