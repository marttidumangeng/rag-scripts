from load_env import load_research_env
load_research_env()
from api_client import ResearchApiClient

c = ResearchApiClient()
co = c._get("companies/1461/")
print("website:", co.get("website"))
for rid in [2911, 2916, 5185, 5190, 5191]:
    r = c._get(f"robots/robots/{rid}/")
    img = r.get("s3_image") or r.get("image") or ""
    tags = r.get("tags") or r.get("tag_names") or []
    vids = r.get("videos") or []
    print("=" * 50)
    print(r["name"], r.get("status"))
    print("  url:", r.get("url"))
    print("  s3:", (r.get("s3_image") or "")[:100])
    print("  image:", (r.get("image") or "")[:100])
    print("  feat:", len(r.get("features") or ""))
    print("  tags:", len(tags) if isinstance(tags, list) else tags)
    print("  vids:", len(vids) if isinstance(vids, list) else vids)
    print("  dims:", r.get("dimensions_mm"), "payload:", r.get("payload_kg"), "wt:", r.get("weight_kg"))
