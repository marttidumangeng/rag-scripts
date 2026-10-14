"""Enrich the one Shandong Kewei row (company 1604), robot 6737 KW1012B-2010.

It arrived from gap discovery with a truncated description and nothing else:
missing features, purpose, specs, category, taxonomy, tags and video, one photo,
never AI-verified. Everything below is read off the vendor's own spec-table image
(cdn.cnyandex.com/kw_en/uploads/vfwerfdew.png) on the product page.

Brand note: the robot in the product photo is marked KOWELL, which is
keweirobot.com's own logo — same company, not a cross-attributed image.

NOTE: `ip_rating` is NOT a RobotSerializer field (checked), so IP56/IP67 goes in
features text rather than being silently dropped.
"""
import sys
import time

from api_client import ResearchApiClient

RID = 6737
APPLY = "--apply" in sys.argv

PRODUCT_URL = "https://www.keweirobot.com/welding-robot-kw1012b-2010/"
PHOTOS = [
    "https://cdn.cnyandex.com/kw_en/uploads/KW1012B-2010.jpg",   # product render (hero)
    "https://cdn.cnyandex.com/kw_en/uploads/vfwerfdew.png",      # spec table
    "https://cdn.cnyandex.com/kw_en/uploads/fgewrf.png",         # work-envelope diagram
]

DESCRIPTION = (
    "A 12 kg, 2,010 mm six-axis arm sold specifically for welding, pairing the arm with Kewei's "
    "own intelligent welding control system and digital welding power source as one integrated "
    "package rather than a robot plus a bought-in welder. Repeatability is ±0.05 mm and the body "
    "weighs 313 kg. It mounts floor-standing, on a bracket or inverted from a gantry, and is rated "
    "to IP56/IP67, so it can sit inside a working weld cell. Kewei positions it for both arc and "
    "spot welding duty."
)

FEATURES = "\n".join([
    "Vertically articulated six-axis arm rated 12 kg payload with a 2,010 mm working radius.",
    "Position repetition accuracy of ±0.05 mm; body weight 313 kg.",
    "Supplied with an integrated intelligent welding control system and digital welding equipment.",
    "Protection rated equivalent to IP56/IP67.",
    "Mounts floor standing, bracket standing or inverted (hanging).",
    "Power capacity 4.5 kVA.",
    "Axis travel: J1 ±165°, J2 +80/-145°, J3 +145/-75°, J4 ±190°, J5 +50/-210°, J6 ±220°.",
    "Maximum axis speeds: J1 203°/s, J2 203°/s, J3 214°/s, J4 392°/s, J5 276°/s, J6 1356°/s.",
    "Rated for 0-45 °C and 20-80% RH, non-condensing.",
])

PATCH = {
    "model_name": "KW1012B-2010",
    "url": PRODUCT_URL,
    "description": DESCRIPTION,
    "purpose": "Robotic arc and spot welding in industrial weld cells.",
    "features": FEATURES,
    "payload_kg": 12.0,
    "reach_mm": 2010.0,
    "repeatability_mm": 0.05,
    "weight_kg": 313.0,
    "dof": 6,
    "environment": "Indoor industrial weld cells; 0-45 °C, 20-80% RH, non-condensing.",
    "mounting_options": "Floor standing, bracket standing, or inverted (hanging) mounting.",
    "manipulation": "Welding torch end effector; integrated digital welding power source.",
    "availability_status_key": "released",
    "family_name": "Kewei KW10 Series",
    "family_key": "kewei:kw10-series",
    "product_url_scope": "exact_variant",
    "variant_code": "KW1012B-2010",
    "source_locale": "en",
    "tags": ["Welding", "arc-welding", "spot-welding", "6-Axis", "Industrial Robot",
             "Robotic Arm", "Industrial Arm", "Automation", "Manufacturing"],
    "categories": ["industrial-robot", "robotic-arms"],
}

NOTE = (
    "2026-08-23: enriched from the vendor spec-table image on the product page "
    "(cdn.cnyandex.com/kw_en/uploads/vfwerfdew.png) — payload 12 kg, working radius 2010 mm, "
    "repeatability ±0.05 mm, body weight 313 kg, 6 axes, IP56/IP67, 4.5 kVA, 0-45 °C / 20-80% RH. "
    "IP rating kept in features because ip_rating is not a RobotSerializer field. The product photo "
    "is branded KOWELL, which is keweirobot.com's own logo — same company, not cross-attribution. "
    "release_year and price left blank: neither is published."
)


def main() -> int:
    c = ResearchApiClient()
    for attempt in range(8):
        try:
            cur = c._get(f"robots/robots/{RID}/")
            break
        except Exception:
            time.sleep(3 * (attempt + 1))
    else:
        print("unreadable")
        return 1

    if cur.get("status") in ("approved", "published"):
        print("LIVE, refusing")
        return 1

    print(f"{RID} {cur.get('name')} ({cur.get('status')})")
    print(f"  desc  {len(cur.get('description') or '')} -> {len(DESCRIPTION)}")
    print(f"  feat  {len(cur.get('features') or '')} -> {len(FEATURES)}")
    print(f"  photos {len(cur.get('photos') or [])} -> {len(PHOTOS)}")
    if not APPLY:
        print("\nDry run — pass --apply to write.")
        return 0

    body = dict(PATCH)
    body["notes"] = ((cur.get("notes") or "").strip() + "\n\n" + NOTE).strip()
    c._patch(f"robots/robots/{RID}/", body)   # no `images` — would wipe the gallery
    print("  patched")

    time.sleep(1)
    out = c.bulk_import_robots(
        [{"id": RID, "name": cur.get("name"), "company_slug": "shandong-kewei-robot",
          "image": PHOTOS[0], "images": [{"url": u} for u in PHOTOS],
          "movement_type_keys": "stationary",
          "industry_keys": "manufacturing|automotive",
          "use_keys": "welding|assembly|material-handling",
          "category_slugs": "industrial-robot|robotic-arms",
          "sub_category_slug": "manufacturing-industrial"}],
        update_existing=True, patch_existing=True, skip_company_update=True, created_by_id=1,
    )
    print("  media/taxonomy:", {k: out.get(k) for k in ("updated_count", "error_count")},
          out.get("warnings") or "")
    return 0


if __name__ == "__main__":
    sys.exit(main())
