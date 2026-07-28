"""How widespread is purpose==description across the DB? Sample companies."""
import re, difflib, sys
from collections import Counter
from load_env import load_research_env
load_research_env()
from api_client import ResearchApiClient
c=ResearchApiClient()
def norm(s): return re.sub(r"\s+"," ",(s or "").strip().lower()).rstrip(". ")
def first_sentence(s):
    s=(s or "").strip(); m=re.split(r"(?<=[.!?])\s+", s); return m[0] if m else s
COMPANIES=[50,283,771,1028,189,220,1396,109,245,32,1461,773]
tot=Counter(); rows=[]
for cid in COMPANIES:
    try: rs=c.list_robots_for_company(cid)
    except Exception as e:
        print("skip",cid,str(e)[:40]); continue
    n=len(rs); bad=0; kinds=Counter()
    for r in rs:
        d=(r.get("description") or "").strip(); p=(r.get("purpose") or "").strip()
        if not p: kinds["empty"]+=1; continue
        nd,np_=norm(d),norm(p); fs=norm(first_sentence(d))
        if np_==nd: kinds["exact"]+=1; bad+=1
        elif np_==fs: kinds["first_sentence"]+=1; bad+=1
        elif len(np_)>25 and np_ in nd: kinds["substring"]+=1; bad+=1
        elif difflib.SequenceMatcher(None,nd,np_).ratio()>0.85: kinds["near"]+=1; bad+=1
    company=(rs[0].get("company") or rs[0].get("company_name")) if rs else "?"
    rows.append((cid,str(company)[:28],n,bad,dict(kinds)))
    tot.update(kinds)
    print(f"{cid:<6}{str(company)[:28]:<29} {bad}/{n} dupes  {dict(kinds)}")
print("\nTOTAL kinds across sampled companies:", dict(tot))
