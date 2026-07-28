"""Fix double-encoded tags from prior soft-PATCH."""
from __future__ import annotations

import sys
from pathlib import Path

_RESEARCH = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env()

from api_client import ResearchApiClient

TAGSETS = {
    1648: [
        "Auris",
        "J&J MedTech",
        "MONARCH",
        "Bronchoscopy",
        "RAB",
        "Lung biopsy",
        "Healthcare",
        "USA",
    ],
    1649: [
        "Auris",
        "J&J MedTech",
        "MONARCH",
        "QUEST",
        "Bronchoscopy",
        "AI navigation",
        "Healthcare",
        "USA",
    ],
    4959: [
        "Globus Medical",
        "ExcelsiusFlex",
        "Excelsius",
        "TKA",
        "Orthopedics",
        "Surgical Robot",
        "Healthcare",
        "USA",
    ],
    4027: [
        "Shift Robotics",
        "Moonwalkers",
        "Robotic shoes",
        "Wearable",
        "Gait AI",
        "Micro-mobility",
        "USA",
    ],
    577: [
        "Shift Robotics",
        "Moonwalkers Aero",
        "Robotic shoes",
        "Wearable",
        "Gait AI",
        "Micro-mobility",
        "USA",
    ],
}


def main() -> int:
    client = ResearchApiClient()
    for rid, tags in TAGSETS.items():
        # Clear first — merging onto mangled string-list tags double-encodes.
        client._patch(f"robots/robots/{rid}/", {"tags": []})
        client._patch(f"robots/robots/{rid}/", {"tags": tags})
        r = client._get(f"robots/robots/{rid}/")
        print("tags", rid, r.get("tags"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
