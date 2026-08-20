from __future__ import annotations
import json, sys
from pathlib import Path
RESEARCH_DIR = Path(r"C:\Github_Personal\robot-ai-geek\scripts\research")
sys.path.insert(0, str(RESEARCH_DIR))
from api_client import ResearchApiClient  # type: ignore
client = ResearchApiClient()
robots = client.list_robots_for_company(1914)
rows=[]
for r in robots:
    rows.append({k:r.get(k) for k in ("id","name","model_name","family_name","url","product_url_scope","description","source_locale")})
out=RESEARCH_DIR/"staging"/"reports"/"qinfeng_names_source_inventory.json"
out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding="utf-8")
for row in rows:
    print("|".join(str(row.get(k) or "") for k in ("id","name","model_name","url")))
print("report:",out)
