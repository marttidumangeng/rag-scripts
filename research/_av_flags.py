import json
from load_env import load_research_env
load_research_env()
from api_client import ResearchApiClient
c = ResearchApiClient()
rs = c.list_robots_for_company(283)
by = {int(r["id"]): r for r in rs}
LEGACY=("weight","width","length","height","runtime","battery_capacity","charging_time","voltage",
        "joint_torque","torque_density","connectivity","sensors","materials","charging_type","computation","actuation_mechanism")
TYPED=("weight_kg","width_mm","length_mm","height_mm","speed","walking_speed","runtime_minutes","battery_wh",
       "charging_time_minutes","joint_torque_nm","torque_density_nm_per_kg","dof","payload_kg","reach_mm","repeatability_mm")
for rid in (519,1506,1509,1510):
    r=by[rid]
    desc=(r.get("description") or "").strip()
    purp=(r.get("purpose") or "").strip()
    feat=(r.get("features") or "").strip()
    specs_set=[f for f in TYPED+LEGACY if r.get(f) not in (None,"",[],{})]
    print("\n=== %s (%s) locale=%s ==="%(r["name"],rid,r.get("source_locale")))
    print(" desc(%d):"%len(desc), desc[:130])
    print(" purpose(%d):"%len(purp), purp[:100])
    print(" features(%d):"%len(feat), feat[:100])
    print(" specs_set:", specs_set)
    print(" release_year:", r.get("release_year"), "avail_id:", r.get("availability_status_id") or (r.get("availability_status") or {}).get("id") if isinstance(r.get("availability_status"),dict) else r.get("availability_status"))
    print(" categories:", r.get("categories"), " n_uses:", len(r.get("uses") or []))
