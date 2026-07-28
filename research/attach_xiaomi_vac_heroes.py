"""Attach verified product heroes to the Xiaomi vacuum stubs (external mi.com -> copy-media).

Hero choice per robot picked visually from staging/_vach/_c.png — avoiding the mi.com
og:image logo trap (2527/4785/4791 og = orange MI logo) and text-banner shots.
CHOICE values: 'og' or an imgs[] index. 2528 (S20+) / 2530 (E10) had no scraped image
(mi.com blocked) — left imageless, reported.
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
VAC=json.loads((_RD/"staging"/"reports"/"xiaomi-vac.json").read_text(encoding="utf-8"))
CHOICE={2526:"og",2527:0,2529:0,3527:0,4785:0,4786:"og",4787:"og",4788:"og",4789:0,
        4790:0,4791:0,4792:0,4793:0,4794:0,4795:0,4796:0,4797:1,4798:0}
NO_IMAGE={2528:"S20+ (mi.com blocked scrape)",2530:"E10 (mi.com blocked scrape)"}

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

def hero_url(rid):
    info=VAC[str(rid)]; ch=CHOICE[rid]
    return info["og"] if ch=="og" else (info.get("imgs") or [])[ch]

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--apply",action="store_true"); a=ap.parse_args()
    c=ResearchApiClient(); S=requests.Session(); S.headers["User-Agent"]="Mozilla/5.0"
    plan=[]
    for rid in sorted(CHOICE):
        u=hero_url(rid)
        try:
            g=S.get(u,timeout=25); ok=g.ok and g.headers.get("Content-Type","").startswith("image") and len(g.content)>6000
        except Exception: ok=False
        if not ok: print(f"  {rid}: candidate not healthy {u[:70]}",file=sys.stderr); continue
        plan.append((rid,u)); print(f"  {rid} {VAC[str(rid)]['name'][:24]:<25} {u.split('/')[-1][:40]}")
    print(f"\nto attach: {len(plan)} | left imageless: {list(NO_IMAGE)}")
    if not a.apply: print("Dry-run."); return 0
    sec=_secret(); ok=fail=0
    for rid,u in plan:
        try: c._patch(f"robots/robots/{rid}/",{"images":[u]})
        except Exception as e: fail+=1; print("FAIL",rid,str(e)[:60],file=sys.stderr); continue
        cm=_copy(rid,sec); ok+=1; print(f"  ok {rid} copy_media={cm}"); time.sleep(0.2)
    print(json.dumps({"ok":fail==0,"attached":ok,"failed":fail})); return 0
if __name__=="__main__": raise SystemExit(main())
