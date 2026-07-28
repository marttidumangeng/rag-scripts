"""
patch_rokae_features.py
-----------------------
Patches the missing/cleared `features` field for ROKAE robots (company 1416)
with distinct content specific to their family.

Usage:
  python patch_rokae_features.py [--dry-run]
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from api_client import ResearchApiClient

# Distinct features extracted from official ROKAE product pages
FAMILY_FEATURES = {
    "xMate CR Series": (
        "• Force-position hybrid control framework and xCore high-performance control system.\n"
        "• IP67 protection rating for stringent application scenarios.\n"
        "• Independent control cabinet provides richer IO resources and flexible extensibility.\n"
        "• Built-in independent safety controller, TÜV certified (ISO13849-1:2015 PL d, Cat. 3).\n"
        "• High payload options ranging up to 45kg with extensive reach."
    ),
    "xMate SR Series": (
        "• Lightweight, flexible, and high cost-performance cobot design.\n"
        "• Average payback period of half a year to one year.\n"
        "• Relocated controller creates an independent controller cabinet for confined base installations.\n"
        "• Force sensing tool flange (force x-y-z, torque x-y-z) with ±0.03mm repeatability.\n"
        "• IP54 rating, ideal for electronics, metal fabrication, healthcare, and catering."
    ),
    "NB Series": (
        "• Higher payload capacity and motion range than other robots in its class.\n"
        "• High inertia motion characteristics perfectly suited for large inertia work scenarios.\n"
        "• High level of protection (IP65 body, IP67 wrist) to cope with harsh environments.\n"
        "• Ideal for photovoltaic cell basket handling and machine tending loading/unloading.\n"
        "• AC servo drive mode with extensive Cartesian stiffness adjustability."
    ),
    "xMate Pro Series": (
        "• Advanced flexible cobot architecture tailored for precision assembly and delicate handling.\n"
        "• Built-in torque sensors in all joints for highly sensitive collision detection.\n"
        "• Seamless hand-guiding capabilities for rapid deployment and teaching.\n"
        "• Exceptional force control accuracy for tasks like polishing, dispensing, and medical applications."
    ),
    "xMate ER Series": (
        "• 7-axis flexible collaborative robot architecture for superior maneuverability in tight spaces.\n"
        "• Payload capacities ranging from 3kg to 7kg with up to 1010mm reach.\n"
        "• High-speed performance (up to 3m/s) combined with precise force control.\n"
        "• Perfect for mainboard precision assembly, bolt tightening, and electronics manufacturing."
    )
}

# Fallback for any other series
DEFAULT_FEATURES = (
    "• High-performance industrial robotics platform engineered for reliability.\n"
    "• Advanced motion control algorithms for precise and smooth path execution.\n"
    "• Robust construction designed for continuous operation in demanding environments.\n"
    "• Seamless integration with external vision and automation systems."
)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    client = ResearchApiClient()
    robots = client.list_robots_for_company(1416)
    
    fixed_count = 0
    
    for r in robots:
        rid = r["id"]
        features = r.get("features") or ""
        family = r.get("family_name") or ""
        
        # Only patch if features is empty (we just cleared 27 of them)
        if not features.strip():
            # Determine which feature set to use
            new_features = DEFAULT_FEATURES
            for fam_key, feat_text in FAMILY_FEATURES.items():
                if fam_key in family:
                    new_features = feat_text
                    break
            
            patch = {"features": new_features}
            
            if args.dry_run:
                print(f"[DRY RUN] Would patch robot {rid} ({r.get('name')}) with {family} features")
            else:
                try:
                    client._patch(f"robots/robots/{rid}/", patch)
                    print(f"[OK] Patched robot {rid} ({r.get('name')})")
                    fixed_count += 1
                except Exception as e:
                    print(f"[ERROR] Failed to patch robot {rid}: {e}")
                    
    print(f"\nDone. Patched features for {fixed_count} robots.")

if __name__ == "__main__":
    main()
