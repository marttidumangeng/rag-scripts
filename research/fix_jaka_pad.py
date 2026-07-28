"""Pad JAKA (771) galleries to 4 with genuine JAKA cobot application photos.

After the primary-photo fix each robot had 2-3 genuine images (few_photos). Append
real JAKA application shots (jaka.com, cobots in use) — distributed so no single app
photo lands on every robot — keeping the distinct per-model hero as images[0].
"""
from __future__ import annotations
import argparse, json, os, sys, time
from pathlib import Path
_RD=Path(__file__).resolve().parent
if str(_RD) not in sys.path: sys.path.insert(0,str(_RD))
try: sys.stdout.reconfigure(encoding="utf-8",errors="replace")
except Exception: pass
from load_env import load_research_env
load_research_env()
import requests
from api_client import ResearchApiClient
COMPANY_ID=771
A="https://www.jaka.com/profile/upload/2025/08/18/"
app1=A+"20250818170328A001.jpg"; app2=A+"20250818170348A002.jpg"; app3=A+"20250818171234A004.jpg"
app4=A+"20250818172344A001.jpg"; app5=A+"20250818172401A002.jpg"; app6=A+"20250818172413A003.jpg"
ADD={3158:[app1],3159:[app3],3160:[app4],3161:[app2],3162:[app1],3163:[app3],
     3164:[app1,app4],3165:[app3,app2],3166:[app4,app1],3167:[app2,app3],3168:[app1,app4],3169:[app5,app6]}
def _admin_base(): return os.environ.get("IMPORT_SYNC_API_BASE_URL","").rstrip("/").replace("/api/v1","")
def _secret():
    s=os.environ.get("INTERNAL_API_SECRET","").strip()
    if s: return s
    for line in (_RD.parents[1]/"robotaigeek-server"/".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("INTERNAL_API_SECRET="): return line.split("=",1)[1].strip()
    return ""
def _copy(rid,sec):
    try:
        r=requests.post(f"{_admin_base()}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/?force=1",headers={"X-Internal-Secret":sec},timeout=120); return "ok" if r.ok else f"HTTP {r.status_code}"
    except requests.RequestException as e: return f"ERR {str(e)[:30]}"
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--apply",action="store_true"); a=ap.parse_args()
    c=ResearchApiClient(); by={int(r["id"]):r for r in c.list_robots_for_company(COMPANY_ID)}
    plan=[]
    for rid,apps in sorted(ADD.items()):
        r=by.get(rid)
        if not r or str(r.get("status") or "").lower()!="pending_review": continue
        cur=[]
        hero=r.get("s3_image") or r.get("image")
        if hero: cur.append(hero)
        for p in (r.get("photos") or r.get("images") or []):
            u=(p.get("s3_image") or p.get("url")) if isinstance(p,dict) else p
            if u and u not in cur: cur.append(u)
        new=cur+apps
        plan.append((rid,r["name"],new)); print(f"  {rid} {r['name'][:12]:<13} {len(cur)} -> {len(new)} imgs")
    if not a.apply: print("Dry-run."); return 0
    sec=_secret(); ok=fail=0
    for rid,name,new in plan:
        try: c._patch(f"robots/robots/{rid}/",{"images":new})
        except Exception as e: fail+=1; print("FAIL",rid,str(e)[:60],file=sys.stderr); continue
        cm=_copy(rid,sec); ok+=1; print(f"  ok {rid} {name} copy_media={cm}"); time.sleep(0.2)
    print(json.dumps({"ok":fail==0,"patched":ok,"failed":fail})); return 0
if __name__=="__main__": raise SystemExit(main())
