"""Fix robot 6111 into the real product: the FlexQube Navigator AMR.

It was staged as "AMR System" pointing at the CATEGORY page /carts/amr-solutions/.
The actual product page is /flexqube-amr-robot-system/ and FlexQube brands the
robot itself "Navigator" (the name is printed on the chassis in their renders).

Two passes, deliberately separate:
  1. Plain DRF PATCH for text/specs/taxonomy/tags. `images` is NEVER sent here —
     RobotSerializer.save() treats `images` as a wipe-and-replace of ALL photos.
  2. bulk_import patch mode for the gallery (dedupes by URL, hero only-if-empty).
"""
import json
import sys
import time

from api_client import ResearchApiClient

RID = 6111
APPLY = "--apply" in sys.argv

PRODUCT_URL = "https://www.flexqube.com/flexqube-amr-robot-system/"

DESCRIPTION = (
    "Non-load-carrying AMR that docks under FlexQube's motorized load carriers through a "
    "standardized coupling, powering and steering whichever carrier the job needs - flatbed, "
    "towing or roller."
)

PURPOSE = (
    "Move pallets, racks, kits and cart trains around manufacturing and warehouse floors on a "
    "one-robot/multi-carrier model, so one AMR serves many load types."
)

FEATURES = "\n".join([
    "One robot, many carriers: the Navigator carries no load itself and docks to motorized "
    "load carriers through a standardized coupling that transfers both power and data to the "
    "carrier's motors.",
    "Carrier range: Flatbed (Q-100-6673), Towing (Q-100-8145) and Roller (Q-100-8194) load "
    "carriers; flatbed and roller carriers are built from 910 x 840 mm up to 2520 x 2520 mm.",
    "Towing capacity 2,500 kg (5,500 lbs) with the towing load carrier.",
    "BlueBotics ANT natural-feature navigation and fleet management - no floor tape, magnets "
    "or reflectors, and minimal infrastructure change.",
    "Wiferion inductive charging with no contact between pad and receiver, mounted on the rear "
    "and underside; roughly one minute of charge per fifteen minutes of operation.",
    "SICK safety laser scanner and a people-friendly profile for shared factory aisles.",
    "Roller carrier adds automatic roller height adjustment and motorized rollers, so pallets "
    "transfer to and from roller racks without the robot stopping to be loaded.",
])

# Navigator's own body is non-load-carrying; 2,500 kg is the towing capacity of the
# system (stated on the Towing Load Carrier page). Stored here because it is the
# headline capacity figure, and spelled out in features so it cannot be misread.
PATCH = {
    "name": "FlexQube Navigator AMR",
    "model_name": "Navigator AMR",
    "url": PRODUCT_URL,
    "family_name": "FlexQube AMR Robot System",
    "family_key": "flexqube:amr-system",
    "family_url": PRODUCT_URL,
    "product_url_scope": "family",
    "description": DESCRIPTION,
    "purpose": PURPOSE,
    "features": FEATURES,
    "payload_kg": 2500.0,
    "movement_engine": "Differential drive with castor support; motorized carrier wheels driven "
                       "through the coupling",
    "software": "BlueBotics ANT navigation and ANT fleet management",
    "charging_type": "Wiferion inductive (contactless), rear and underside receivers",
    "connectivity": "ANT fleet management over the site network; standardized coupling carries "
                    "power and data to the docked carrier",
    "environment": "Indoor manufacturing and warehouse floors, shared with pedestrian traffic",
    "sensors": ["SICK safety laser scanner", "Natural-feature navigation laser (BlueBotics ANT)"],
    "programming_interface": "ANT fleet management (route and mission configuration); on-board "
                             "touchscreen for manual and auto mode",
    "safety_fencing": "Fenceless - safety laser scanner with speed and stop zones, emergency stop "
                      "and status beacon; designed to operate among people without barriers",
    "mounting_options": "Docks beneath FlexQube motorized load carriers via the standardized "
                        "coupling interface; carriers are configured per application",
    "deployment_context": "Intralogistics in complex manufacturing environments - seat and door "
                          "delivery to assembly lines, pallet and rack moves, tugger-train replacement.",
    "ecosystem_compatibility": "Interchangeable with any FlexQube motorized load carrier "
                               "(flatbed, towing, roller) sharing the coupling interface.",
    # 'Care Robot', 'Drone' and 'Humanoid' were on this row and are simply wrong for an AMR.
    "tags": ["AMR", "Autonomous Mobile Robot", "Intralogistics", "Material Handling",
             "Logistics", "Industrial Automation", "Mobile Robot", "Autonomous Transport",
             "Modular", "Internal Transport"],
    "industries": [12, 11, 26],            # manufacturing, logistics, automotive
    "uses": [16, 32, 74, 55, 54, 30, 31],  # transport, material-handling, intralogistics,
                                           # heavy-load-transportation, pallet-transportation,
                                           # loading, unloading
    "categories": ["logistics-robots", "mobile-robots", "warehouse-robots"],
}

# Every one visually confirmed to show the Navigator AMR (FlexQube-branded, "navigator"
# printed on the chassis in the renders).
NEW_PHOTOS = [
    "https://flexqube.imgix.net/1/3a/navigator-rendering-setup45.png",
    "https://flexqube.imgix.net/e/d7/navigator-rendering-setup88.png",
    "https://flexqube.imgix.net/d/8a/navigator-rendering-setup104.png",
    "https://flexqube.imgix.net/2024/12/n50vUtE1-amrtuggeruncoupled.jpg",
    "https://flexqube.imgix.net/2025/02/PB0i0AOy-amrtowingwarehouseautonomousmobilerobotflexqube.jpg",
    "https://flexqube.imgix.net/2023/10/Osvc09nq-navigator-marketing-4.png",
]


def main() -> int:
    c = ResearchApiClient()
    before = c._get(f"robots/robots/{RID}/")
    print("BEFORE")
    print(f"  name   : {before.get('name')}")
    print(f"  url    : {before.get('url')}")
    print(f"  tags   : {before.get('tags')}")
    print(f"  photos : {len(before.get('photos') or [])}")
    print(f"  status : {before.get('status')}  conf={before.get('verification_confidence')}")

    if before.get("status") in ("approved", "published"):
        print("REFUSING: robot is live; tools touch draft/pending_review only.")
        return 1

    if not APPLY:
        print("\nDry run. Would PATCH these keys:")
        print(" ", sorted(PATCH))
        print(f"and add {len(NEW_PHOTOS)} photos via bulk_import patch mode.")
        return 0

    resp = c._patch(f"robots/robots/{RID}/", PATCH)
    print("\nPATCH ok:", resp.get("name"), "|", resp.get("url"))

    time.sleep(2)
    media_row = {
        "id": RID,
        "name": PATCH["name"],
        "company_slug": "flexqube",
        "images": NEW_PHOTOS,
    }
    out = c.bulk_import_robots(
        [media_row], update_existing=True, patch_existing=True, created_by_id=1,
    )
    print("media patch:", {k: out.get(k) for k in
                           ("created_count", "updated_count", "skipped_count", "error_count")})
    if out.get("warnings"):
        print("  warnings:", out["warnings"][:5])

    after = c._get(f"robots/robots/{RID}/")
    print("\nAFTER")
    print(f"  name   : {after.get('name')}")
    print(f"  model  : {after.get('model_name')}")
    print(f"  url    : {after.get('url')}")
    print(f"  tags   : {after.get('tags')}")
    print(f"  uses   : {[u['key'] for u in (after.get('uses') or [])]}")
    print(f"  inds   : {[i['key'] for i in (after.get('industries') or [])]}")
    print(f"  cats   : {after.get('categories')}")
    print(f"  photos : {len(after.get('photos') or [])}")
    print(f"  videos : {len(after.get('videos') or [])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
