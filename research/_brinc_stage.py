"""Stage BRINC's real drones (company 1783) after the 3 CTA rows were rejected.

Imported: Guardian, Responder, LEMUR 2.

NOT imported — BRINC Ball. Their own copy calls it "The Next Gen Throw Phone,
Two-way communication device": a throwable mic/speaker with no locomotion and no
actuation. It is sold alongside the drones but it is not a robot (same call as
[[project_component_vendors]]). Guardian Station / Responder Station are docking
infrastructure and LiveOps is software, so neither is a robot either.

Image note: /wp-content/uploads/ on this site holds only chrome — Rectangle-230
and footer.webp are on ALL four product pages. The real assets are under
/themes/bdrones/assets/images/<per-product folder>/, and even there the automatic
pick had to be corrected by eye: it offered a POLICE CAR (guardian/car-siren) and
an interior stairwell photo (lemur-2/day-controller) as product images.
"""
import json
import os
import sys

OUT_DIR = "staging/robots/brinc"
B = "https://brincdrones.com/wp-content/themes/bdrones/assets/images/"

ROBOTS = {
    "Guardian": {
        "slug": "guardian",
        "desc": (
            "BRINC's flagship Drone as First Responder aircraft, built to launch from a rooftop dock "
            "and be over a 911 call before officers arrive. It flies 62 minutes, carries dual HD "
            "thermal with optical zoom alongside 640x-zoom 4K visual cameras, and keeps working after "
            "dark with an integrated SkyBeam spotlight and a built-in laser rangefinder. Satellite "
            "connectivity removes the range limit, and robotic battery swapping at the dock is what "
            "makes genuine 24/7 unattended operation possible."
        ),
        "purpose": "Rooftop-launched Drone as First Responder aircraft for 911 call response.",
        "features": ["640x Zoom 4k Visual Cameras", "Dual HD Thermal With Optical Zoom",
                     "Integrated SkyBeam Spotlight", "Built-In Laser Rangefinder",
                     "62 Minutes of Flight Time", "IP55 Weather Resistance",
                     "Satellite Internet Connectivity", "130 dBA Siren & Speaker",
                     "True 24/7 DFR Operations", "Robotic Battery Swapping"],
        "runtime_minutes": 62,
        "images": [B + "product-guardian/beacon4.webp", B + "product-guardian/engine-drone3.webp",
                   B + "product-guardian/camera-small.webp", B + "product-guardian/controller3.webp"],
        "uses": "reconnaissance|monitoring|search-and-rescue|inspection|patrol",
    },
    "Responder": {
        "slug": "responder",
        "desc": (
            "A public-safety drone that works in an automated Drone as First Responder system, in a "
            "patrol-led DFR approach, or flown manually. It gives 42 minutes of flight time with 40x "
            "total zoom and a 640 px thermal camera, and carries two-way comms with a loudspeaker plus "
            "emergency lights and siren so an operator can talk to people on scene. Forward obstacle "
            "avoidance, mesh networking and 4G LTE teleoperations round out the airframe, and an "
            "attachment rail takes additional payloads."
        ),
        "purpose": "Public-safety response drone for automated, patrol-led or manual DFR deployment.",
        "features": ["Flight Time: 42 min", "Total Zoom: 40x", "Thermal Camera: 640 px",
                     "Teleoperations over 4G LTE", "IPX4 Water Resistant",
                     "2-Way Comms with Loudspeaker", "Emergency Lights and Siren",
                     "Forward Obstacle Avoidance", "Attachment Rail", "Mesh Networking"],
        "runtime_minutes": 42,
        "images": [B + "responder/camera/drone_render_final.webp",
                   B + "responder/airframe/airframe-frame-1.webp",
                   B + "responder/airframe/airframe-block-img-3.webp"],
        "uses": "reconnaissance|monitoring|search-and-rescue|inspection|patrol",
    },
    "LEMUR 2": {
        "slug": "lemur-2",
        "desc": (
            "An indoor tactical drone for police and SWAT work, weighing 3.3 lb (1.5 kg) and flying "
            "20 minutes on four autonomy sensors with 360-degree position flight hold. Its glass "
            "breaker defeats tempered, automotive and most residential glass to get inside a "
            "structure, and it can nudge interior doors open, drag or deliver a small object during a "
            "negotiation, and flip itself upright with turtle mode if it lands on its back. Two-way "
            "comms, livestreaming, mesh networking and real-time floor plans support the operator."
        ),
        "purpose": "Indoor tactical drone for police entry, negotiation and structure clearing.",
        "features": ["Weight: 3.3 lb (1.5 kg)", "Flight time: 20 min", "Autonomy Sensors: 4",
                     "Gimbal Rotation: 190°", "360° position flight hold",
                     "Glass breaker effective on tempered, automotive and most residential glass",
                     "Can push open most interior doors",
                     "Can deliver or drag a small object during a negotiation",
                     "Turtle mode flips it upright to redeploy after landing inverted",
                     "2-way comms, livestreaming, mesh networking and real-time floor plans"],
        "runtime_minutes": 20,
        "weight_kg": 1.5,
        "images": [B + "product-lemur-2/drone-2.webp", B + "product-lemur-2/drone-1-new.webp",
                   B + "product-lemur-2/drone-3.webp", B + "product-lemur-2/drone-5.webp"],
        "uses": "reconnaissance|monitoring|search-and-rescue|inspection",
    },
}


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    for name, r in ROBOTS.items():
        url = f"https://brincdrones.com/{r['slug']}/"
        row = {
            "name": f"BRINC {name}", "model_name": name,
            "company_slug": "brinc", "company_name": "Brinc",
            "url": url, "product_url_scope": "exact_variant",
            "manufacturer_country_code": "US", "source_locale": "en",
            "description": r["desc"], "purpose": r["purpose"],
            "features": "\n".join(r["features"]),
            "availability_status_key": "released",
            "movement_type_keys": "aerial",
            "industry_keys": "defence|government|security",
            "use_keys": r["uses"],
            "category_slugs": "aerial|security",
            "sub_category_slug": "security",
            "tags": "Drone|UAV|Aerial|Public Safety|Security|Autonomous|Surveillance",
            "image": r["images"][0], "images": [{"url": u} for u in r["images"]],
            "sources": [{"url": url, "type": "website", "title": f"{name} - BRINC"}],
            "information_source_urls": url,
            "research_notes": (
                "Harvested from the BRINC product page 2026-08-23. The page looks like a JS app "
                "('You need to enable JavaScript to run this app') but the product copy is served in "
                "the HTML under template-specific classes. Images taken from the per-product theme "
                "folder — /wp-content/uploads/ on this site is chrome only. Replaces the CTA/program "
                "rows 6456-6458, which were a sales-enquiry page, a livery configurator and a program "
                "category page rejected the same day."),
        }
        if "runtime_minutes" in r:
            row["runtime_minutes"] = r["runtime_minutes"]
        if "weight_kg" in r:
            row["weight_kg"] = r["weight_kg"]
        with open(f"{OUT_DIR}/{r['slug']}.json", "w", encoding="utf-8") as fh:
            json.dump(row, fh, ensure_ascii=False, indent=1)
        print(f"  staged {row['name']:18s} imgs={len(r['images'])} feats={len(r['features'])}")
    print(f"\n{len(ROBOTS)} staged in {OUT_DIR} (BRINC Ball excluded - throwable comms device, not a robot)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
