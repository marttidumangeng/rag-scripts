"""Probe company 1404 + verify Hitbot 976 post-approval status."""
from collections import Counter
import json
from pathlib import Path

from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient

c = ResearchApiClient()

print("=== Hitbot 976 ===")
robots976 = list(c.list_robots_for_company(976))
print("STATUS", Counter(r.get("status") for r in robots976))

print("\n=== Company 1404 ===")
co = c._get("companies/1404/")
print("NAME:", co.get("name"))
print("SLUG:", co.get("slug"))
print("WEB:", co.get("website"))
print("COUNTRY:", co.get("country"), co.get("country_id"))
print("DESC:", (co.get("description") or "")[:300])
robots = list(c.list_robots_for_company(1404))
print("TOTAL:", len(robots))
print("STATUS:", Counter(r.get("status") for r in robots))
slim = []
for r in sorted(robots, key=lambda x: x["id"]):
    detail = c._get(f"robots/robots/{r['id']}/")
    img = detail.get("s3_image") or detail.get("image") or ""
    tags = detail.get("tags") or []
    row = {
        "id": r["id"],
        "name": detail.get("name"),
        "status": detail.get("status"),
        "url": detail.get("url"),
        "image": detail.get("image"),
        "s3_image": detail.get("s3_image"),
        "features_len": len(detail.get("features") or ""),
        "description_len": len(detail.get("description") or ""),
        "purpose": (detail.get("purpose") or "")[:200],
        "family_key": detail.get("family_key"),
        "family_name": detail.get("family_name"),
        "payload_kg": detail.get("payload_kg"),
        "reach_mm": detail.get("reach_mm"),
        "weight_kg": detail.get("weight_kg"),
        "dof": detail.get("dof"),
        "repeatability_mm": detail.get("repeatability_mm"),
        "availability_status": detail.get("availability_status"),
        "tags": [t.get("name") if isinstance(t, dict) else t for t in tags][:10],
        "categories": detail.get("categories"),
        "uses": [
            u.get("id") if isinstance(u, dict) else u for u in (detail.get("uses") or [])
        ][:12],
        "manufacturer_countries": detail.get("manufacturer_countries"),
        "manufacturer_country_ref": detail.get("manufacturer_country_ref"),
        "notes": (detail.get("notes") or "")[:400],
    }
    slim.append(row)
    print(
        f"{r['id']}|{detail.get('status')}|img={bool(img)}|"
        f"fam={detail.get('family_key') or ''}|"
        f"{(detail.get('name') or '')[:50]}|"
        f"url={(detail.get('url') or '')[:65]}"
    )

out = Path("staging/reports/company-1404-raw.json")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(
    json.dumps({"company": co, "robots": slim}, indent=2, ensure_ascii=False),
    encoding="utf-8",
)
print("wrote", out)
