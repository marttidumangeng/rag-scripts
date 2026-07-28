"""
staubli_fix_images_final.py
============================
Patches all Stäubli Robotics robots (company_id=1475) with VERIFIED, real
image URLs scraped directly from staubli.com product pages.

All URLs below were confirmed HTTP 200 / image/jpeg via requests.head().

Run:
    python staubli_fix_images_final.py [--dry-run]
"""
import sys
import time
import os

sys.path.insert(0, os.path.dirname(__file__))
from api_client import ResearchApiClient

DRY_RUN = "--dry-run" in sys.argv

# ---------------------------------------------------------------------------
# Verified real image URLs — scraped from staubli.com product pages
# All confirmed HTTP 200 image/jpeg
# ---------------------------------------------------------------------------
VERIFIED_IMAGES = {
    # 6-axis TX2 series
    "TX2-40":  "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--efb10ec6-1419-486b-985c-41234bf365fc/tx2-40-industrial-robot.jpg",
    "TX2-60":  "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--53415e78-1ac3-4d64-a081-2e0886bbfef5/tx2-60-industrial-robot-range.jpg",
    "TX2-90":  "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--d7d50c52-bef9-49e2-bcd2-3dc728ccaa59/tx2-90-industrial-robot-range.jpg",
    "TX2-140": "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--a7172079-d064-4b8d-979a-6136b8eab1b4/tx2-140-industrial-robot.jpg",
    "TX2-160": "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--d1e2b99d-7932-4a93-98b4-818efd9d7921/tx2-160-industrial-robot-range.jpg",
    "TX2-200": "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--993def67-c53a-4775-9950-5061fa0aa747/tx2-200-industrial-robot-range.jpg",
    # SCARA TS2 series
    "TS2-40":  "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--d174ddac-9ee0-4b70-9f53-86beabe023d0/ts2-40-scara-robot.jpg",
    "TS2-60":  "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--33516d84-7047-4016-afc9-1b439ac59080/industrial-robots.jpg",
    "TS2-80":  "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--2f72246f-cf84-405d-a6eb-cc8c932fcec0/ts2-80-scara-robot.jpg",
    "TS2-100": "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--e426bc68-a7b7-4ee3-854f-e876b09433f8/ts2-100-scara-robot.jpg",
}

# Fallback mapping: model name substring → image key from VERIFIED_IMAGES
# Used for HE variants, L variants, discontinued models, etc.
FALLBACK_MAP = [
    # HE / L / XL variants → use base model image
    ("TX2-200L",  "TX2-200"),
    ("TX2-160L",  "TX2-160"),
    ("TX2-90XL",  "TX2-90"),
    ("TX2-90L",   "TX2-90"),
    ("TX2-60L",   "TX2-60"),
    # MedX Ready → TX2-60
    ("MedX",      "TX2-60"),
    # Discontinued RX series → closest TX2 payload class
    ("RX260",     "TX2-200"),
    ("RX160",     "TX2-160"),
    # Discontinued TX200 → TX2-200
    ("TX200",     "TX2-200"),
    # TP80 picker → TS2-40 (SCARA/picker class)
    ("TP80",      "TS2-40"),
    # PF3 → TX2-60 (similar size class)
    ("PF3",       "TX2-60"),
]


def resolve_image(robot_name: str, model_name: str) -> str | None:
    """Return the best verified image URL for a robot by name/model matching."""
    # Work on name and model separately to avoid partial-match corruption
    name_up = robot_name.upper()
    model_up = (model_name or "").upper()

    # 1. Try fallback map first (more specific — longest patterns listed first)
    for substr, target_key in FALLBACK_MAP:
        s = substr.upper()
        if s in name_up or s in model_up:
            return VERIFIED_IMAGES[target_key]

    # 2. Direct match on base model key (e.g. TX2-40, TS2-100)
    for key, url in VERIFIED_IMAGES.items():
        k = key.upper()
        if k in name_up or k in model_up:
            return url

    return None


def main():
    client = ResearchApiClient()

    print("Fetching all Stäubli robots (company_id=1475)...")
    robots = client.list_robots_for_company(1475)
    print(f"Found {len(robots)} robots\n")

    matched = []
    unmatched = []

    for r in robots:
        rid = r.get("id")
        name = r.get("name", "")
        model = r.get("model_name", "") or ""
        company_slug = r.get("company_slug", "") or r.get("company", {}).get("slug", "") if isinstance(r.get("company"), dict) else ""
        current_image = r.get("image") or r.get("image_url") or ""

        image_url = resolve_image(name, model)

        if image_url:
            matched.append({
                "id": rid,
                "name": name,
                "model": model,
                "company_slug": company_slug or "staubli-robotics",
                "image_url": image_url,
                "had_image": bool(current_image),
            })
        else:
            unmatched.append({"id": rid, "name": name, "model": model})

    print(f"Matched:   {len(matched)}")
    print(f"Unmatched: {len(unmatched)}")

    if unmatched:
        print("\nUnmatched robots (will be skipped):")
        for r in unmatched:
            print(f"  id={r['id']} name={r['name']!r} model={r['model']!r}")

    if DRY_RUN:
        print("\n[DRY RUN] Would patch the following:")
        for r in matched:
            print(f"  id={r['id']} {r['name']!r} → {r['image_url']}")
        return

    print(f"\nPatching {len(matched)} robots with verified images...")
    ok = 0
    errors = 0

    for r in matched:
        payload = [{
            "id": r["id"],
            "name": r["name"],
            "company_slug": r["company_slug"],
            "image": r["image_url"],
        }]
        try:
            result = client.bulk_import_robots(
                payload,
                patch_existing=True,
                replace_media=True,
                status="published",
                skip_company_update=True,
            )
            ok += 1
            print(f"  ✓ id={r['id']} {r['name']!r}")
        except Exception as e:
            errors += 1
            print(f"  ✗ id={r['id']} {r['name']!r}: {e}")
        time.sleep(0.3)

    print(f"\nDone: {ok} patched, {errors} errors out of {len(matched)} robots")


if __name__ == "__main__":
    main()
