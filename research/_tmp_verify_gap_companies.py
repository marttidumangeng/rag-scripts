"""Verify which of the top gap companies are actually in the RAG DB."""
from load_env import load_research_env
load_research_env()
from api_client import ResearchApiClient

client = ResearchApiClient()

# The companies we want to verify — mix of "already in RAG" and "gap" claims
CHECK = [
    # High-value gap candidates (claimed missing)
    "Kondo Kagaku",
    "Enchanted Tools",
    "NAVER LABS",
    "Niryo",
    "Stäubli",
    "TechMagic",
    "Ti5 Robot",
    "Beatbot",
    "Lefant",
    "Smorobot",
    "Ilife",
    "Noble Machines",
    "UniX AI",
    "Spirit AI",
    "Willow Garage",
    "RobotLAB Group",
    "Novarc Technologies",
    "Tokyo Robotics",
    "Hengbot",
    "Sevnce Robotics",
    # Claimed already in RAG (should be found)
    "iRobot",
    "Yaskawa",
    "BORUNTE",
    "RealMan Robotics",
    "Beijing Geekplus Technology",
]

print("=" * 70)
print(f"{'Company':<40} {'Status':<12} {'DB Name / ID'}")
print("=" * 70)

for name in CHECK:
    results = client.search_companies(name)
    if results:
        top = results[0]
        db_name = top.get("name", "?")
        db_id = top.get("id", "?")
        # Check if it's a real match or just a partial hit
        import re
        name_norm = re.sub(r"[^a-z0-9]", "", name.lower())
        db_norm = re.sub(r"[^a-z0-9]", "", db_name.lower())
        is_match = name_norm in db_norm or db_norm in name_norm or name_norm[:6] in db_norm
        status = "IN DB" if is_match else "PARTIAL?"
        print(f"  {name:<40} {status:<12} id={db_id} name={db_name!r}")
    else:
        print(f"  {name:<40} {'MISSING':<12}")

print("=" * 70)
