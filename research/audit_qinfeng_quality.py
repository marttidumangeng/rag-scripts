from __future__ import annotations
import json, re, sys
from pathlib import Path
RESEARCH_DIR = Path(r"C:\Github_Personal\robot-ai-geek\scripts\research")
sys.path.insert(0, str(RESEARCH_DIR))
from api_client import ResearchApiClient  # type: ignore
client = ResearchApiClient()
company_id = 1914
robots = client.list_robots_for_company(company_id)
BAD = re.compile(r"502\\s+Bad\\s+Gateway|Bad\\s+Gateway|Browser\\s+Working|Host\\s+Error|发生什么事了|网站服务无法请求|WTS\\s+Working|Error\\s*\\d{3}", re.I)
fields = ["name","description","purpose","features","strengths","weaknesses","notes","tags","dof","payload_kg","reach_mm","repeatability_mm","speed","voltage","videos","image","image_url","s3_image"]
report = {"company_id": company_id, "robots": len(robots), "records": [], "summary": {"bad_text":0,"missing_primary":0,"no_gallery":0,"same_robot_duplicate_urls":0,"low_score":0,"quality_flags":0}}
for robot in robots:
    rid = int(robot.get("id") or 0)
    photos = robot.get("photos") or []
    if isinstance(photos, dict): photos = photos.get("results") or photos.get("items") or []
    urls = [str(p.get("url") or p.get("image") or p.get("image_url") or "").strip() for p in photos if isinstance(p, dict)]
    urls = [u for u in urls if u]
    duplicate_urls = sorted({u for u in urls if urls.count(u) > 1})
    bad_fields = [f for f in fields if BAD.search(str(robot.get(f) or ""))]
    conf = robot.get("verification_confidence")
    scores = {f: robot.get(f) for f in ("overall_score","technology_score","product_maturity_score")}
    low_score = False
    try: low_score = conf is None or float(conf) < 70 or any(v in (None, "") or float(v) <= 0 for v in scores.values())
    except (TypeError, ValueError): low_score = True
    flags = robot.get("quality_flags") or []
    rec = {"robot_id":rid,"name":robot.get("name"),"image":robot.get("image") or robot.get("image_url") or robot.get("s3_image"),"photo_count":len(urls),"duplicate_urls":duplicate_urls,"bad_fields":bad_fields,"scores":scores,"verification_confidence":conf,"quality_flags":flags,"missing_fields":[f for f in fields if not str(robot.get(f) or "").strip()]}
    report["records"].append(rec)
    report["summary"]["bad_text"] += bool(bad_fields)
    report["summary"]["missing_primary"] += not bool(rec["image"])
    report["summary"]["no_gallery"] += not bool(urls)
    report["summary"]["same_robot_duplicate_urls"] += len(duplicate_urls)
    report["summary"]["low_score"] += low_score
    report["summary"]["quality_flags"] += bool(flags)
out = RESEARCH_DIR / "staging" / "reports" / "qinfeng_quality_audit.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"company_id":company_id,"robots":len(robots),**report["summary"],"report":str(out)}, ensure_ascii=False, indent=2))
