"""Purge the two shared JUNK images from Noblelift (1028) galleries.

The bulk import padded galleries with a country FLAG (sha 1001e2fd5d, on 18 robots) and
the NOBLELIFT LOGO (sha 471a571ec5, on 12 robots) — neither is a product photo. They
survived the size filter (30KB / 7KB) so only a content-hash pass catches them (same
per-robot-CDN-key trick as the FANUC junk). Drop them; keep the hero + every genuine
product photo (product duplicates are kept — redundant, not garbage). No copy-media:
heroes are already correct product images.

Usage: python fix_noblelift_junk.py [--apply]
"""
from __future__ import annotations
import argparse, hashlib, json, sys, time
from pathlib import Path
_RD=Path(__file__).resolve().parent
if str(_RD) not in sys.path: sys.path.insert(0,str(_RD))
try: sys.stdout.reconfigure(encoding="utf-8",errors="replace")
except Exception: pass
from load_env import load_research_env
load_research_env()
import requests
from api_client import ResearchApiClient
COMPANY_ID=1028
JUNK={"1001e2fd5d":"Australian flag","471a571ec5":"NOBLELIFT logo"}
S=requests.Session(); S.headers["User-Agent"]="Mozilla/5.0"; _cache={}
def sha(u):
    if u in _cache: return _cache[u]
    try:
        g=S.get(u,timeout=20); h=hashlib.sha256(g.content).hexdigest()[:10] if g.ok else None
    except Exception: h=None
    _cache[u]=h; return h
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--apply",action="store_true"); a=ap.parse_args()
    c=ResearchApiClient(); robots=None
    for i in range(12):
        try: robots=c.list_robots_for_company(COMPANY_ID); break
        except Exception as e: print("retry",i,str(e)[:50],file=sys.stderr); time.sleep(5)
    plan=[]
    for r in sorted(robots,key=lambda x:int(x["id"])):
        if str(r.get("status") or "").lower()!="pending_review": continue
        rid=int(r["id"]); hero=r.get("s3_image") or r.get("image")
        urls=[(p.get("s3_image") or p.get("url")) if isinstance(p,dict) else p for p in (r.get("photos") or r.get("images") or [])]
        kept,dropped=[],0
        for u in urls:
            if sha(u) in JUNK: dropped+=1
            else: kept.append(u)
        if not dropped: continue
        # keep hero first, then kept gallery (dedupe by url)
        new=[hero]+[u for u in kept if u!=hero]
        seen=set(); new=[x for x in new if x and not (x in seen or seen.add(x))]
        plan.append((rid,r["name"],new,dropped))
        print(f"  {rid:<6}{r['name'][:26]:<27} drop {dropped} junk -> {len(new)} photos")
    print(f"\nrobots with junk photos: {len(plan)}")
    if not a.apply:
        print("Dry-run."); return 0
    ok=fail=0
    for rid,name,new,dr in plan:
        try: c._patch(f"robots/robots/{rid}/",{"images":new}); ok+=1; print(f"  ok {rid} {name}: -{dr} junk, {len(new)} left")
        except Exception as e: fail+=1; print("FAIL",rid,str(e)[:70],file=sys.stderr)
        time.sleep(0.15)
    print(json.dumps({"ok":fail==0,"patched":ok,"failed":fail},indent=2)); return 0
if __name__=="__main__": raise SystemExit(main())
