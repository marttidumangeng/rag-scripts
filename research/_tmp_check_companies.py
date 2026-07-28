"""Quick check: which of these Robolist companies are already in the RAG DB?"""
from load_env import load_research_env
load_research_env()
from api_client import ResearchApiClient

client = ResearchApiClient()

test_names = [
    'iRobot', 'Yaskawa', 'BORUNTE', 'RealMan Robotics',
    'Beijing Geekplus Technology', 'Star Automation', 'RoboTronic Industries',
    'XQL LASER CHINA', 'Kondo Kagaku', 'Kawada Industries',
]

print("Checking company names against RAG DB:")
print("=" * 60)
for name in test_names:
    results = client.search_companies(name)
    if results:
        hits = [(r.get('id'), r.get('name')) for r in results[:2]]
        print(f"  FOUND   {name!r:40s} -> {hits}")
    else:
        print(f"  MISSING {name!r:40s}")
