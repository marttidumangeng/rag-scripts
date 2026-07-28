"""Noblelift (1028) To Review cleanup — media quality + fixable warnings.

Per stakeholder: fix warnings, remove garbage images/videos, ensure the primary image
matches the product. Concretely:

  VIDEOS  11 AGV robots carried 3 NON-Noblelift clips (Wuhan Donglisheng M&E / "campur
          gado" / LOGIBRIDGE) -> replaced with official "Noblelift Intelligent" AGV videos
          (APT15 gets its own model video). Every other group is already a Noblelift channel.
  HEROES  3187 hero was a 525-byte broken PNG; 3378 hero was a forklift AIR-CONDITIONING
          accessory banner (not a forklift); 3379 hero was a partial cab crop -> each
          repointed to a product-forward Noblelift banner (external -> force copy-media so
          the sticky owned-CDN s3_image actually refreshes).
  PHOTOS  25 robots had a 525-byte broken placeholder photo -> dropped (garbage). Galleries
          keep only healthy images (may fall to 3 -> few_photos, an accepted trade vs garbage).
  AVAIL   OPL10 (3373) + ES15 (3381) missing_availability -> released (ORM, done separately).
  SPECS   26 of the 29 missing_specs robots get payload_kg from the model's rated capacity
          (encoded in the name, confirmed on the OEM pages: PS20=2000kg, RT16=1600kg, ...).
          3 generic records (Counterbalanced Forklift/Reach Truck/Pallet Truck) have no
          capacity in the name and are left (reported).

release_year (all 55) + price (all 55) left: Noblelift publishes no per-model launch year
or public price. Reported, not invented.

Usage: python fix_noblelift.py [--ids ...] [--apply]
"""
from __future__ import annotations
import argparse, json, os, re, sys, time
from pathlib import Path

_RD = Path(__file__).resolve().parent
if str(_RD) not in sys.path:
    sys.path.insert(0, str(_RD))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
from load_env import load_research_env
load_research_env(local="--local" in sys.argv)
import requests
from api_client import ResearchApiClient

COMPANY_ID = 1028
PH = json.loads((_RD/"staging"/"reports"/"nl-photohealth.json").read_text(encoding="utf-8"))

AGV_IDS = {2210,2214,3186,3187,3331,3332,3333,3334,3335,3336,3368}
V_AGV = "https://www.youtube.com/watch?v=vm1b-_WbSCA"
V_APT15 = "https://www.youtube.com/watch?v=3alOSdsZFjA"
V_CASE1 = "https://www.youtube.com/watch?v=HzC5p28TRzg"
V_CASE2 = "https://www.youtube.com/watch?v=HyiIYBK85f8"
def agv_videos(rid):
    base=[{"url":V_AGV,"title":"Noblelift AGV"},
          {"url":V_CASE1,"title":"Noblelift AGV Customer Case - Tailored Automation for Renewable Growth"},
          {"url":V_CASE2,"title":"Noblelift AGV Customer Case - Automation for the Short Fiber Industry"}]
    if rid==3186:
        return [{"url":V_APT15,"title":"Noblelift AGV - APT15"}]+base[:2]
    return base

# external product-forward Noblelift banners (copy-media will fetch these)
HERO_EXT = {
 3187: "https://www.noblelift.com/uploadfiles/2024/07/20240713151013846.jpg",       # RT16P/20P Reach AGV
 3378: "https://www.noblelift.com/uploadfiles/2024/10/20241016165837241.png",       # FE4P electric forklift
 3379: "https://www.noblelift.com/uploadfiles/2025/03/20250304013932412.jpg",       # RT20G sit-on reach truck
}
DROP_EXTRA = {3378: {"https://cdn.robotaigeek.com/robots/photos/photo-3378-13869-v1783773524.jpg"}}  # AC-unit accessory

def payload_from_name(name):
    n=name.replace("Noblelift","").strip()
    # explicit kg
    kgs=[int(x) for x in re.findall(r"(\d{3,5})\s*kg", n, re.I)]
    if kgs: return float(max(kgs))
    low=n.lower()
    if low.startswith(("nr","nb","nd","ans")): return None   # scrubbers: number is width, not load
    m=re.match(r"[a-z0]{1,4}[-]?(\d{2})", low)  # model code: first 2-digit token x100 = kg
    if m:
        nums=[int(x) for x in re.findall(r"(?<![\d.])(\d{2})(?!\d)", n.split()[0])]
        if nums: return float(max(nums)*100)
    return None

def _admin_base():
    return os.environ.get("IMPORT_SYNC_API_BASE_URL","").rstrip("/").replace("/api/v1","")
def _secret():
    s=os.environ.get("INTERNAL_API_SECRET","").strip()
    if s: return s
    env=_RD.parents[1]/"robotaigeek-server"/".env"
    if env.is_file():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("INTERNAL_API_SECRET="): return line.split("=",1)[1].strip()
    return ""
def _copy_media(rid,sec):
    url=f"{_admin_base()}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/?force=1"
    try:
        r=requests.post(url,headers={"X-Internal-Secret":sec},timeout=120); return "ok" if r.ok else f"HTTP {r.status_code}"
    except requests.RequestException as e: return f"ERR {str(e)[:30]}"

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--apply",action="store_true"); ap.add_argument("--ids",type=int,nargs="*")
    args=ap.parse_args()
    c=ResearchApiClient(); robots=None
    for a in range(12):
        try: robots=c.list_robots_for_company(COMPANY_ID); break
        except Exception as e: print("retry",a,str(e)[:50],file=sys.stderr); time.sleep(5)
    by={int(r["id"]):r for r in robots}
    ids=set(args.ids) if args.ids else set(by)
    plan=[]
    for rid in sorted(ids):
        r=by.get(rid)
        if not r or str(r.get("status") or "").lower()!="pending_review": continue
        body={}; copymedia=False
        ph=PH.get(str(rid)) or {}
        healthy=[u for u,sz,bad in ph.get("photos",[]) if not bad]
        # images: rebuild only if hero must change OR there are bad photos
        if rid in HERO_EXT:
            keep=[u for u in healthy if u not in DROP_EXTRA.get(rid,set())]
            body["images"]=[HERO_EXT[rid]]+keep; copymedia=True
        elif ph.get("photos") and any(bad for _,_,bad in ph["photos"]):
            hero=r.get("s3_image") or r.get("image")
            imgs=[hero]+[u for u in healthy if u!=hero]
            # dedupe preserve order
            seen=set(); imgs=[x for x in imgs if not (x in seen or seen.add(x))]
            body["images"]=imgs
        # videos
        if rid in AGV_IDS:
            body["video_urls"]=agv_videos(rid)
        # payload spec
        if rid in {2210,2214,3186,3187,3331,3332,3333,3334,3335,3336,3350,3351,3352,3353,3354,3355,3356,3357,3358,3359,3368,3373,3374,3375,3376,3381}:
            pl=payload_from_name(r["name"])
            if pl: body["payload_kg"]=pl
        if not body: continue
        plan.append((rid,r["name"],body,copymedia))
        desc={k:(f"{len(v)} imgs" if k=="images" else (f"{len(v)} vids" if k=="video_urls" else v)) for k,v in body.items()}
        print(f"  {rid:<6}{r['name'][:24]:<25} {desc}{' +copymedia' if copymedia else ''}")
    print(f"\nrobots to patch: {len(plan)}")
    if not args.apply:
        print("Dry-run."); return 0
    sec=_secret(); ok=fail=0
    for rid,name,body,cm in plan:
        try: c._patch(f"robots/robots/{rid}/",body)
        except Exception as e: fail+=1; print("FAIL",rid,str(e)[:70],file=sys.stderr); continue
        s=""
        if cm: s=" copy_media="+_copy_media(rid,sec)
        ok+=1; print(f"  ok {rid} {name}{s}"); time.sleep(0.15)
    print(json.dumps({"ok":fail==0,"patched":ok,"failed":fail},indent=2))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
