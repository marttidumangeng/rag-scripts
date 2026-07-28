import json
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient

c = ResearchApiClient()
for rid in (3220, 3221, 5221, 5230):
    r = c._get(f"robots/robots/{rid}/")
    print(
        json.dumps(
            {
                "id": rid,
                "name": r.get("name"),
                "status": r.get("status"),
                "country": r.get("manufacturer_country_ref") or r.get("country"),
                "countries": r.get("manufacturer_countries"),
                "categories": r.get("categories"),
                "uses": r.get("uses"),
                "industries": r.get("industries"),
                "movement_types": r.get("movement_types"),
                "tags": r.get("tags"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
