import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from api_client import ResearchApiClient

c = ResearchApiClient()
for rid in [3394, 3393, 3392, 3384, 3383, 3382]:
    r = c._get(f"robots/robots/{rid}/")
    photos = r.get("photos") or []
    print(f"[{rid}] {r.get('name')} | url={r.get('url','')[:80]} | photos={len(photos)}")
