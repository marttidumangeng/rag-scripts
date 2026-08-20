from __future__ import annotations
import json, sys
from pathlib import Path
RESEARCH_DIR=Path(r"C:\Github_Personal\robot-ai-geek\scripts\research")
sys.path.insert(0,str(RESEARCH_DIR))
from api_client import ResearchApiClient  # type: ignore
client=ResearchApiClient()
company_id=int(sys.argv[1]) if len(sys.argv)>1 else 1706
robots=client.list_robots_for_company(company_id)
for r in robots[:3]:
    print(json.dumps({'id':r.get('id'),'name':r.get('name'),'keys':sorted(r.keys()),'selected':{k:r.get(k) for k in sorted(r.keys()) if any(x in k.lower() for x in ('purpose','use','industry','categor','tag','feature','description','source_locale'))}},ensure_ascii=False,indent=2))
