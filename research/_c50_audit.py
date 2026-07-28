import re, difflib
from load_env import load_research_env
load_research_env()
from api_client import ResearchApiClient
c=ResearchApiClient()
rs=c.list_robots_for_company(50)
print("company 50 total:", len(rs))
if rs: print("company:", rs[0].get("company") or rs[0].get("company_name"))
from collections import Counter
print("statuses:", dict(Counter(str(r.get("status") or "").lower() for r in rs)))

def norm(s): return re.sub(r"\s+"," ",(s or "").strip().lower()).rstrip(". ")
def first_sentence(s):
    s=(s or "").strip()
    m=re.split(r"(?<=[.!?])\s+", s)
    return m[0] if m else s

dupe=[]
for r in sorted(rs, key=lambda x:int(x["id"])):
    st=str(r.get("status") or "").lower()
    d=(r.get("description") or "").strip(); p=(r.get("purpose") or "").strip()
    if not p: kind="EMPTY_PURPOSE"
    else:
        nd,np_=norm(d),norm(p)
        fs=norm(first_sentence(d))
        ratio=difflib.SequenceMatcher(None,nd,np_).ratio()
        if np_==nd: kind="EXACT_EQUAL"
        elif np_==fs: kind="EQUALS_FIRST_SENTENCE"
        elif nd.startswith(np_) and len(np_)>25: kind="PREFIX_OF_DESC"
        elif np_ in nd and len(np_)>25: kind="SUBSTRING_OF_DESC"
        elif ratio>0.8: kind="NEAR_DUP(%.2f)"%ratio
        else: kind=None
    if kind:
        dupe.append((int(r["id"]),r.get("name"),st,kind))
        print("\n--- %s (%s) [%s] %s"%(r.get("name"),r["id"],st,kind))
        print("  DESC:", d[:150])
        print("  PURP:", p[:150])
print("\n\n=== SUMMARY ===")
print("robots with purpose problem:", len(dupe), "/", len(rs))
print(dict(Counter(k for _,_,_,k in dupe)))
print("by status:", dict(Counter(s for _,_,s,_ in dupe)))
