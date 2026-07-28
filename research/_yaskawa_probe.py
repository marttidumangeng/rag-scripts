from load_env import load_research_env
load_research_env()
from api_client import ResearchApiClient
import json
from collections import Counter
from pathlib import Path

c = ResearchApiClient()
co = c._get("companies/772/")
print("COMPANY", co.get("id"), co.get("name"), co.get("slug"), co.get("website"))
print("country", co.get("country") or co.get("hq_country"))
robots = list(c.list_robots_for_company(772))
print("robots", len(robots), "status", Counter(r.get("status") for r in robots))

def vids(r):
    v = r.get("videos") or r.get("linked_videos") or []
    return len(v) if isinstance(v, list) else (1 if v else 0)

aspx = []
motoman = []
no_vid = []
for r in robots:
    img = (r.get("s3_image") or r.get("image") or "")
    name = r.get("name") or ""
    if ".aspx" in img.lower() or ".aspx" in (r.get("image") or "").lower() or ".aspx" in (r.get("url") or "").lower():
        aspx.append(r)
    if name.lower().startswith("motoman") or "motoman" in name.lower():
        motoman.append(r)
    if vids(r) == 0:
        no_vid.append(r)

print("no_videos", len(no_vid))
print("aspx_related", len(aspx))
print("motoman_named", len(motoman))
print("--- sample ---")
for r in robots[:15]:
    print(r["id"], r["name"], "vid", vids(r), "img", (r.get("s3_image") or r.get("image") or "")[:90], "url", (r.get("url") or "")[:70])
print("--- aspx ---")
for r in aspx[:20]:
    print(r["id"], r["name"], "image", (r.get("image") or "")[:100], "s3", bool(r.get("s3_image")), "url", (r.get("url") or "")[:80])
print("--- motoman ---")
for r in motoman:
    print(r["id"], r["name"], "img", (r.get("s3_image") or r.get("image") or "")[:90], "url", (r.get("url") or "")[:80])

Path("staging/reports").mkdir(parents=True, exist_ok=True)
Path("staging/reports/yaskawa_772_probe.json").write_text(
    json.dumps({
        "company": {k: co.get(k) for k in ("id", "name", "slug", "website")},
        "robots": [{
            "id": r["id"], "name": r["name"], "status": r.get("status"),
            "url": r.get("url"), "image": r.get("image"), "s3_image": r.get("s3_image"),
            "videos": vids(r), "features_len": len(r.get("features") or ""),
            "tags": r.get("tags"),
        } for r in robots],
    }, indent=2, ensure_ascii=False),
    encoding="utf-8",
)
print("wrote staging/reports/yaskawa_772_probe.json")
