from __future__ import annotations
import json, re, sys
from pathlib import Path
RESEARCH_DIR = Path(r"C:\Github_Personal\robot-ai-geek\scripts\research")
sys.path.insert(0, str(RESEARCH_DIR))
from api_client import ResearchApiClient  # type: ignore
client=ResearchApiClient(); company_id=1706; robots=client.list_robots_for_company(company_id)
BAD=re.compile(r"502\\s+Bad\\s+Gateway|Bad\\s+Gateway|Browser\\s+Working|Host\\s+Error|WTS\\s+Working|Error\\s*\\d{3}|captcha|cloudflare",re.I)
rows=[]
for r in robots:
    d=client._get(f"robots/robots/{int(r['id'])}/")
    photos=d.get('photos') or []
    if isinstance(photos,dict): photos=photos.get('results') or photos.get('items') or []
    urls=[str(p.get('url') or p.get('image') or p.get('image_url') or '').strip() for p in photos if isinstance(p,dict)]
    urls=[u for u in urls if u]
    bad=[f for f in ('name','description','purpose','features','notes','strengths','weaknesses') if BAD.search(str(d.get(f) or ''))]
    dup=sorted({u for u in urls if urls.count(u)>1})
    rows.append({'id':d.get('id'),'name':d.get('name'),'model_name':d.get('model_name'),'url':d.get('url'),'image':d.get('image') or d.get('image_url') or d.get('s3_image'),'photo_count':len(urls),'duplicate_urls':dup,'bad_text_fields':bad,'quality_flags':d.get('quality_flags') or [],'verification_confidence':d.get('verification_confidence'),'missing_fields':[f for f in ('features','tags','videos','description','purpose') if not str(d.get(f) or '').strip()]})
out=RESEARCH_DIR/'staging'/'reports'/'hci_quality_audit.json'; out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps({'company_id':company_id,'records':rows},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'company_id':company_id,'robots':len(rows),'bad_text':sum(bool(r['bad_text_fields']) for r in rows),'missing_primary':sum(not bool(r['image']) for r in rows),'duplicates':sum(len(r['duplicate_urls']) for r in rows),'quality_flags':sum(bool(r['quality_flags']) for r in rows),'report':str(out)},ensure_ascii=False,indent=2))
for r in rows: print(json.dumps(r,ensure_ascii=False))
