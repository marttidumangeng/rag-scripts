"""Enrich the 20 Xiaomi robot-vacuum stubs re-parented out of NASA into Xiaomi (115).

Non-media flag clearance (heroes handled separately — mi.com og:image is a logo trap):
  uses=cleaning, movement=wheeled, industries=homes+cleaning, tags, country=China (was
  wrongly USA from the NASA bucket), a task purpose (fixes purpose==description dupes),
  and battery_capacity from the scraped mAh (clears missing_specs). Suction (Pa) appended
  to features since there is no suction column.
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
from validate_staging import purpose_duplicates_description

VAC = json.loads((_RD/"staging"/"reports"/"xiaomi-vac.json").read_text(encoding="utf-8"))
# not vacuums — skip here (handled individually)
SKIP = {"2660","4362"}
USES=[2]; MOVE=[4]; IND=[9,5]  # cleaning / wheeled / homes+cleaning
TAGS=["Robot Vacuum","Cleaning","Mopping","LiDAR Navigation"]
PURPOSE="Autonomous vacuuming and mopping of home floors"


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--apply",action="store_true"); a=ap.parse_args()
    c=ResearchApiClient(); ok=fail=0
    for rid_s,info in sorted(VAC.items(), key=lambda kv:int(kv[0])):
        if rid_s in SKIP: continue
        rid=int(rid_s)
        r=c._get(f"robots/robots/{rid}/")
        desc=(r.get("description") or "").strip()
        body={"uses":USES,"movement_types":MOVE,"industries":IND,"tags":TAGS,
              "manufacturer_country":"China"}
        # purpose: task statement; only overwrite if blank OR duplicates description
        cur_p=(r.get("purpose") or "").strip()
        if not cur_p or purpose_duplicates_description(cur_p, desc):
            body["purpose"]=PURPOSE
        # battery spec -> clears missing_specs
        mah=info.get("mah") or []
        if mah:
            body["battery_capacity"]=f"{mah[0].replace(',','')} mAh"
        # suction into features (append, don't clobber)
        pa=info.get("pa") or []
        if pa:
            feat=(r.get("features") or "").strip()
            suction=f"{pa[0].replace(',','')} Pa suction"
            if "Pa" not in feat:
                body["features"]=(feat+"\n"+suction).strip() if feat else suction
        print(f"  {rid} {info['name'][:26]:<27} keys={[k for k in body]}")
        if a.apply:
            try: c._patch(f"robots/robots/{rid}/",body); ok+=1
            except Exception as e: fail+=1; print("   FAIL",str(e)[:70],file=sys.stderr)
            time.sleep(0.15)
    if a.apply: print(json.dumps({"ok":fail==0,"patched":ok,"failed":fail}))
    else: print("Dry-run.")
if __name__=="__main__": raise SystemExit(main())
