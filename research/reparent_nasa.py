"""Re-parent the mis-filed robots out of NASA (174) to their correct companies.

NASA (174) was a mixed bucket: only Perseverance Rover (1235) is NASA. 24 robots are
Xiaomi (mi.com URLs) and 1 is Noetix (noetixrobotics.com) — all raising url_domain_mismatch
purely because of the wrong company. Xiaomi (#115) and Noetix (#135) already exist and were
empty, so this is a clean move (no dedupe). Uses the serializer's `company`-string path,
which get_or_create-matches the EXISTING company by exact name (verified: 4798 -> #115, no
duplicate company created).

Usage: python reparent_nasa.py [--apply]
"""
from __future__ import annotations
import argparse, json, sys, time
from pathlib import Path
_RD=Path(__file__).resolve().parent
if str(_RD) not in sys.path: sys.path.insert(0,str(_RD))
try: sys.stdout.reconfigure(encoding="utf-8",errors="replace")
except Exception: pass
from load_env import load_research_env
load_research_env()
from api_client import ResearchApiClient

XIAOMI = [19,112,2526,2527,2528,2529,2530,2660,3527,4362,
          4785,4786,4787,4788,4789,4790,4791,4792,4793,4794,4795,4796,4797,4798]
NOETIX = [166]
TARGET = {**{rid:("Xiaomi",115) for rid in XIAOMI}, **{rid:("NOETIX Robotics",135) for rid in NOETIX}}
KEEP_NASA = {1235}  # Perseverance — the only real NASA robot


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--apply",action="store_true"); a=ap.parse_args()
    c=ResearchApiClient()
    rs={int(r["id"]):r for r in c.list_robots_for_company(174)}
    # also pick up any already-moved ones? just report from NASA current set + targets
    plan=[]
    for rid,(cname,cid) in TARGET.items():
        r=rs.get(rid)
        cur=(r.get("company_ref") or {}).get("id") if r else "(not under NASA)"
        if r is None:
            # already moved (e.g. 4798 in the test) — verify it sits at the target
            det=c._get(f"robots/robots/{rid}/")
            cur=(det.get("company_ref") or {}).get("id")
            if cur==cid:
                print(f"  {rid}: already at {cname} (#{cid}) — skip"); continue
        plan.append((rid,r.get("name") if r else str(rid),cname,cid,cur))
        print(f"  {rid:<6}{str(r.get('name') if r else rid)[:26]:<27} {cur} -> {cname} (#{cid})")
    print(f"\nto re-parent: {len(plan)} | Perseverance {sorted(KEEP_NASA)} stays NASA")
    if not a.apply:
        print("Dry-run."); return 0
    ok=fail=0
    for rid,name,cname,cid,cur in plan:
        try:
            c._patch(f"robots/robots/{rid}/", {"company":cname})
            det=c._get(f"robots/robots/{rid}/"); got=(det.get('company_ref') or {}).get('id')
            if got!=cid:
                fail+=1; print(f"  WARN {rid}: landed at #{got}, expected #{cid}",file=sys.stderr); continue
            ok+=1; print(f"  ok {rid} {name} -> {cname} (#{got})")
        except Exception as e:
            fail+=1; print(f"  FAIL {rid}: {str(e)[:70]}",file=sys.stderr)
        time.sleep(0.15)
    print(json.dumps({"ok":fail==0,"reparented":ok,"failed":fail},indent=2)); return 0
if __name__=="__main__": raise SystemExit(main())
