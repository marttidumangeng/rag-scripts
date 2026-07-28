"""JAKA Robotics (771) — fix the shared primary photo + garbage media + specs.

All 12 pending cobot-arm records shared ONE gallery: a generic company lineup (the hero),
FOUR QR codes, and a wrong-brand (orange-arm) application photo — every image identical
across all 12. And all 12 shared 3 videos about OTHER JAKA products (Kargo AMR + a wheeled
humanoid), not cobot arms.

Fix, per model:
  HERO/GALLERY  distinct per-model JAKA render from jaka.com (Zu3..Zu20 six renders,
                S5/S12, Pro5/12/16, Mini 2) + the clean series render(s). The lineup,
                4 QR codes and orange-arm photo are dropped. External URLs -> force
                copy-media so the sticky owned-CDN s3_image actually refreshes.
  VIDEOS        replaced with genuine JAKA cobot-arm demos (official JAKA Robotics
                channel Zu12/Zu30 + Zu-series; Zu5 gets its own model video).
  SPECS         payload_kg from the model name (Zu3=3kg ... Pro16=16kg) — the defining
                cobot spec, previously null (weight_kg+dof were already set).

release_year + price left: JAKA publishes no per-model launch year / public price.

Usage: python fix_jaka.py [--ids ...] [--apply]
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
J="https://www.jaka.com/profile/upload/"
ZU_EXTRA=[J+"2023/12/01/zu_20231201182918A002.jpg", J+"2024/03/05/ZuB_20240305182009A031.jpg"]
S_SERIES=J+"2024/05/10/S-750x1160_20240510103707A067.jpg"
PRO_SERIES=J+"2024/01/02/pro_20240102184212A088.jpg"
IMAGES={
 3158:[J+"2025/02/07/20250207153651A066.png"]+ZU_EXTRA,  # Zu3
 3159:[J+"2025/02/07/20250207153303A053.png"]+ZU_EXTRA,  # Zu5
 3160:[J+"2025/02/07/20250207154102A085.png"]+ZU_EXTRA,  # Zu7
 3161:[J+"2025/02/07/20250207154404A097.png"]+ZU_EXTRA,  # Zu12
 3162:[J+"2025/02/07/20250207155524A125.png"]+ZU_EXTRA,  # Zu18
 3163:[J+"2025/02/07/20250207160057A157.png"]+ZU_EXTRA,  # Zu20
 3164:[J+"2024/05/10/S5-540x604_20240510110320A071.png", S_SERIES],   # S5
 3165:[J+"2024/05/10/S12-540x604_20240510113324A077.png", S_SERIES],  # S12
 3166:[J+"2023/12/12/p5_20231212173343A068.png", PRO_SERIES],   # Pro5
 3167:[J+"2023/12/12/p12_20231212173406A071.png", PRO_SERIES],  # Pro12
 3168:[J+"2023/12/12/p16_20231212173425A074.png", PRO_SERIES],  # Pro16
 3169:[J+"2024/01/02/mmm_20240102184452A094.jpg", J+"2023/12/01/JAKA%20MiniCobo_20231201183158A007.jpg"],  # Mini 2
}
V_ZU30={"url":"https://www.youtube.com/watch?v=wOwMiiKq8Xg","title":"JAKA Zu30 Collaborative Robot - Globally Launched"}
V_ZUSER={"url":"https://www.youtube.com/watch?v=zWdrMQnT57s","title":"JAKA Zu cobot series"}
V_ZU12={"url":"https://www.youtube.com/watch?v=Dllkxar7Vus","title":"JAKA Zu 12 Cobot"}
V_ZU5={"url":"https://www.youtube.com/watch?v=oq_MAz0b6E0","title":"JAKA Zu 5 cobot (collaborative robot)"}
def videos(rid):
    if rid==3159: return [V_ZU5,V_ZU30,V_ZUSER]          # Zu5
    if rid==3161: return [V_ZU12,V_ZU30,V_ZUSER]         # Zu12
    if 3158<=rid<=3163: return [V_ZU30,V_ZUSER,V_ZU12]   # other Zu
    return [V_ZU30,V_ZUSER]                              # S/Pro/Mini: generic JAKA cobot demos
PAYLOAD={3158:3,3159:5,3160:7,3161:12,3162:18,3163:20,3164:5,3165:12,3166:5,3167:12,3168:16}  # Mini 2 uncertain -> skip

def _admin_base(): return os.environ.get("IMPORT_SYNC_API_BASE_URL","").rstrip("/").replace("/api/v1","")
def _secret():
    s=os.environ.get("INTERNAL_API_SECRET","").strip()
    if s: return s
    env=_RD.parents[1]/"robotaigeek-server"/".env"
    if env.is_file():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("INTERNAL_API_SECRET="): return line.split("=",1)[1].strip()
    return ""
def _copy(rid,sec):
    u=f"{_admin_base()}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/?force=1"
    try:
        r=requests.post(u,headers={"X-Internal-Secret":sec},timeout=120); return "ok" if r.ok else f"HTTP {r.status_code}"
    except requests.RequestException as e: return f"ERR {str(e)[:30]}"

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--apply",action="store_true"); ap.add_argument("--ids",type=int,nargs="*"); a=ap.parse_args()
    c=ResearchApiClient(); robots=None
    for i in range(12):
        try: robots=c.list_robots_for_company(COMPANY_ID); break
        except Exception as e: print("retry",i,str(e)[:50],file=sys.stderr); time.sleep(5)
    by={int(r["id"]):r for r in robots}
    S=requests.Session(); S.headers["User-Agent"]="Mozilla/5.0"
    def ok(u):
        try:
            r=S.get(u,timeout=30); return bool(r.ok and r.headers.get("Content-Type","").startswith("image") and len(r.content)>4000)
        except Exception: return False
    ids=set(a.ids) if a.ids else set(IMAGES)
    plan=[]
    for rid in sorted(ids):
        r=by.get(rid)
        if not r or str(r.get("status") or "").lower()!="pending_review": continue
        imgs=IMAGES[rid]; bad=[u for u in imgs if not ok(u)]
        if bad: print(f"  {rid}: DEAD img {bad}",file=sys.stderr); return 1
        body={"images":imgs,"video_urls":videos(rid)}
        if rid in PAYLOAD: body["payload_kg"]=float(PAYLOAD[rid])
        plan.append((rid,r["name"],body))
        print(f"  {rid:<6}{r['name'][:14]:<15} {len(imgs)} imgs, {len(body['video_urls'])} vids, payload={body.get('payload_kg')}")
    print(f"\nto patch: {len(plan)}")
    if not a.apply: print("Dry-run."); return 0
    sec=_secret(); okc=fail=0
    for rid,name,body in plan:
        try: c._patch(f"robots/robots/{rid}/",body)
        except Exception as e: fail+=1; print("FAIL",rid,str(e)[:70],file=sys.stderr); continue
        cm=_copy(rid,sec); okc+=1; print(f"  ok {rid} {name} copy_media={cm}"); time.sleep(0.2)
    print(json.dumps({"ok":fail==0,"patched":okc,"failed":fail},indent=2)); return 0
if __name__=="__main__": raise SystemExit(main())
