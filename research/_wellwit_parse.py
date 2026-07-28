"""Parse Wellwit spec tables + assign families; print a review table (no writes)."""
from __future__ import annotations
import json, os, re

d = {x["id"]: x for x in json.load(open(os.path.join(os.environ["TEMP"], "wellwit_scrape.json"), encoding="utf-8"))}
robots = json.load(open(os.path.join(os.environ["TEMP"], "co1423.json"), encoding="utf-8"))


def num(pat, s, grp=1):
    m = re.search(pat, s, re.I)
    return m.group(grp) if m else None


def parse(s: str) -> dict:
    out = {}
    p = num(r"Maximum payload[^0-9]*?([\d.]+)\s*kg", s)
    if p: out["payload_kg"] = float(p)
    w = num(r"Weight[^0-9]{0,40}?([\d.]+)\s*KG", s)
    if w: out["weight_kg"] = float(w)
    dm = re.search(r"[Dd]imension[s]?[^0-9]{0,40}?(\d+)\s*\*\s*(\d+)\s*\*\s*(\d+)\s*mm", s)
    if dm:
        out["length_mm"], out["width_mm"], out["height_mm"] = float(dm[1]), float(dm[2]), float(dm[3])
    sp = num(r"[Oo]peration speed[^0-9]*?([\d.]+)\s*m/s", s)
    if sp: out["speed"] = round(float(sp) * 3.6, 2)  # m/s -> km/h
    na = num(r"[Nn]avigation position accuracy[^0-9]*?([\d.]+)\s*mm", s)
    if na: out["repeatability_mm"] = float(na)
    bat = re.search(r"Battery capacity[^0-9]*?(\d+)\s*V[^0-9]{0,6}(\d+)\s*Ah", s)
    if bat: out["battery_wh"] = int(bat[1]) * int(bat[2])
    lift = num(r"lifting height[^0-9]*?([\d.]+)\s*mm", s)
    if lift: out["_lift_mm"] = lift
    return out


def family(model: str) -> tuple[str, str]:
    if model.startswith("WMF-APR"): return "wellwit:wmf-apr", "WMF-APR Pallet AMR"
    if model.startswith("WMF1000"): return "wellwit:wmf1000", "WMF1000 Autonomous Forklift"
    if model.startswith("WMF"):     return "wellwit:wmf300", "WMF-300 Autonomous Forklift"
    m = re.match(r"(W\d)", model)
    if m: return f"wellwit:{m[1].lower()}", f"{m[1]} Series AMR"
    return "", ""


rows = []
for r in robots:
    model = r["name"].replace("Wellwit Robotics", "").strip()
    sp = d[r["id"]]
    specs = parse(sp["specs"])
    fk, fn = family(model)
    rows.append({"id": r["id"], "model": model, "fk": fk, "og": sp["og"], "specs": specs})

# print review table
hdr = f'{"id":>5} {"model":16} {"family":18} {"pay":>5} {"wt":>5} {"L":>5} {"W":>5} {"H":>5} {"km/h":>5} {"rep":>4} {"Wh":>5}'
print(hdr); print("-" * len(hdr))
miss_specs = miss_dims = 0
for x in rows:
    s = x["specs"]
    if "payload_kg" not in s: miss_specs += 1
    if "length_mm" not in s: miss_dims += 1
    print(f'{x["id"]:>5} {x["model"]:16} {x["fk"].replace("wellwit:",""):18} '
          f'{s.get("payload_kg","-")!s:>5} {s.get("weight_kg","-")!s:>5} '
          f'{s.get("length_mm","-")!s:>5} {s.get("width_mm","-")!s:>5} {s.get("height_mm","-")!s:>5} '
          f'{s.get("speed","-")!s:>5} {s.get("repeatability_mm","-")!s:>4} {s.get("battery_wh","-")!s:>5}')
print(f"\n{len(rows)} robots | missing payload: {miss_specs} | missing dims: {miss_dims}")
import collections
fams = collections.Counter(x["fk"] for x in rows)
print("families:", dict(fams))
json.dump(rows, open(os.path.join(os.environ["TEMP"], "wellwit_plan.json"), "w", encoding="utf-8"), ensure_ascii=False)
