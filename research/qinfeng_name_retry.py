from __future__ import annotations
import json, sys, time
from pathlib import Path
RESEARCH_DIR = Path(r"C:\Github_Personal\robot-ai-geek\scripts\research")
sys.path.insert(0, str(RESEARCH_DIR))
from api_client import ResearchApiClient  # type: ignore

def canonical_name(r):
    model = str(r.get("model_name") or "").strip()
    if model.startswith("QF-CJ-"): return f"Riveting Pin Insertion Machine - {model}"
    if model.startswith("QF-GJ-"): return f"Joint Stamping Robot - {model}"
    if model.startswith(("QF-BB-", "LB-BB-")): return f"Swing Arm Stamping Manipulator - {model}"
    if model.startswith("QF-L-S-"): return f"Strip Feeder - {model}"
    if model.startswith("QF-LJ-"): return f"Material Rack - {model}"
    if model == "Automatic Material Rack": return "Automatic Material Rack"
    if model == "二三次元机械手": return "Two-/Three-Dimensional Manipulator"
    if model == "关节机械手": return None
    if model in {"Ⅰ代", "I"}: return "Intelligent Swing Arm Stamping Manipulator - Generation I"
    if model in {"Ⅱ代", "II"}: return "Intelligent Swing Arm Stamping Manipulator - Generation II"
    if model in {"Ⅲ代", "III"}: return "Intelligent Swing Arm Stamping Manipulator - Generation III"
    if model == "鼎峰Ⅰ代": return "Dingfeng Five-Axis Intelligent Stamping Robot - Generation I"
    if model == "3kg老宝小黄人": return "Old Treasure Little Yellow Man - 3 kg"
    if model == "3/5kg摆臂机械手": return "Swing Arm Stamping Manipulator - 3/5 kg"
    if model == "5kg摆臂机械手": return "Swing Arm Stamping Manipulator - 5 kg"
    if model == "10kg摆臂机械手": return "Swing Arm Stamping Manipulator - 10 kg"
    if model == "20kg摆臂机械手": return "Swing Arm Stamping Manipulator - 20 kg"
    if model == "QF智能摆臂机械手系列": return "QF Smart Swing Arm Stamping Manipulator Series"
    if model == "QF-MD系列": return "QF-MD Smart Articulated Robot Series"
    return None

client=ResearchApiClient(); robots=client.list_robots_for_company(1914)
changes=[]; errors=[]; skipped=[]
for r in robots:
    new=canonical_name(r); old=str(r.get("name") or "").strip(); rid=int(r["id"])
    if not new:
        skipped.append({"robot_id":rid,"name":old,"model_name":r.get("model_name")}); continue
    if new == old: continue
    try:
        client._patch(f"robots/robots/{rid}/", {"name":new})
        changes.append({"robot_id":rid,"old_name":old,"new_name":new,"model_name":r.get("model_name")})
    except Exception as exc:
        errors.append({"robot_id":rid,"old_name":old,"new_name":new,"model_name":r.get("model_name"),"error":str(exc)})
    time.sleep(0.2)
report={"company_id":1914,"changes":changes,"errors":errors,"skipped":skipped}
out=RESEARCH_DIR/"staging"/"reports"/"qinfeng_name_retry.json"; out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps({"changes":len(changes),"errors":len(errors),"skipped":len(skipped),"report":str(out)},ensure_ascii=False,indent=2))
for e in errors: print(json.dumps(e,ensure_ascii=False))
