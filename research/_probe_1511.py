from load_env import load_research_env
load_research_env()
from api_client import ResearchApiClient

c = ResearchApiClient()
co = c._get("companies/1511/")
print("NAME:", co.get("name"))
print("SLUG:", co.get("slug"))
print("WEBSITE:", co.get("website"))
print("COUNTRY:", co.get("country") or co.get("country_code"))
print("---")
robots = list(c.list_robots_for_company(1511))
print("ROBOT_COUNT:", len(robots))
for r in robots:
    img = r.get("s3_image") or r.get("image") or ""
    feats = r.get("features") or ""
    tags = r.get("tags") or r.get("tag_names") or []
    vids = r.get("videos") or []
    print(
        f"id={r['id']} name={r['name']!r} status={r.get('status')} "
        f"img={bool(img)} feat_len={len(feats)} "
        f"url={r.get('url') or ''} "
        f"tags={len(tags) if isinstance(tags, list) else tags} "
        f"vids={len(vids) if isinstance(vids, list) else vids} "
        f"wt={r.get('weight_kg') or r.get('weight')} dof={r.get('dof')}"
    )
    if img:
        print(f"  image={img[:140]}")
    if feats:
        print(f"  features={(feats[:180]).encode('ascii','replace').decode()}")
    desc = r.get("description") or ""
    if desc:
        print(f"  desc={(desc[:160]).encode('ascii','replace').decode()}")
