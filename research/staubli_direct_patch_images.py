"""
staubli_direct_patch_images.py
================================
Force-updates the image field on all 45 Stäubli robots using direct PATCH
to the individual robot endpoint: PATCH /api/v1/robots/robots/{id}/

This bypasses the bulk_import_robots logic that skips existing images.

Run:
    python staubli_direct_patch_images.py [--dry-run]
"""
import sys
import time
import os

sys.path.insert(0, os.path.dirname(__file__))
from api_client import ResearchApiClient

DRY_RUN = "--dry-run" in sys.argv

# ---------------------------------------------------------------------------
# Verified real image URLs — all confirmed HTTP 200 / image/jpeg
# ---------------------------------------------------------------------------
VERIFIED_IMAGES = {
    "TX2-40":  "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--efb10ec6-1419-486b-985c-41234bf365fc/tx2-40-industrial-robot.jpg",
    "TX2-60":  "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--53415e78-1ac3-4d64-a081-2e0886bbfef5/tx2-60-industrial-robot-range.jpg",
    "TX2-90":  "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--d7d50c52-bef9-49e2-bcd2-3dc728ccaa59/tx2-90-industrial-robot-range.jpg",
    "TX2-140": "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--a7172079-d064-4b8d-979a-6136b8eab1b4/tx2-140-industrial-robot.jpg",
    "TX2-160": "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--d1e2b99d-7932-4a93-98b4-818efd9d7921/tx2-160-industrial-robot-range.jpg",
    "TX2-200": "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--993def67-c53a-4775-9950-5061fa0aa747/tx2-200-industrial-robot-range.jpg",
    "TS2-40":  "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--d174ddac-9ee0-4b70-9f53-86beabe023d0/ts2-40-scara-robot.jpg",
    "TS2-60":  "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--33516d84-7047-4016-afc9-1b439ac59080/industrial-robots.jpg",
    "TS2-80":  "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--2f72246f-cf84-405d-a6eb-cc8c932fcec0/ts2-80-scara-robot.jpg",
    "TS2-100": "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--e426bc68-a7b7-4ee3-854f-e876b09433f8/ts2-100-scara-robot.jpg",
}

FALLBACK_MAP = [
    ("TX2-200L",  "TX2-200"),
    ("TX2-160L",  "TX2-160"),
    ("TX2-90XL",  "TX2-90"),
    ("TX2-90L",   "TX2-90"),
    ("TX2-60L",   "TX2-60"),
    ("MEDX",      "TX2-60"),
    ("RX260",     "TX2-200"),
    ("RX160",     "TX2-160"),
    ("TX200",     "TX2-200"),
    ("TP80",      "TS2-40"),
    ("PF3",       "TX2-60"),
]


def resolve_image(robot_name: str, model_name: str) -> str | None:
    name_up = robot_name.upper()
    model_up = (model_name or "").upper()
    for substr, target_key in FALLBACK_MAP:
        if substr in name_up or substr in model_up:
            return VERIFIED_IMAGES[target_key]
    for key, url in VERIFIED_IMAGES.items():
        if key in name_up or key in model_up:
            return url
    return None


def main():
    client = ResearchApiClient()

    print("Fetching all Stäubli robots (company_id=1475)...")
    robots = client.list_robots_for_company(1475)
    print(f"Found {len(robots)} robots\n")

    ok = 0
    errors = 0
    skipped = 0

    for r in robots:
        rid = r.get("id")
        name = r.get("name", "")
        model = r.get("model_name", "") or ""

        image_url = resolve_image(name, model)

        if not image_url:
            print(f"  ? id={rid} {name!r} — no image match, skipping")
            skipped += 1
            continue

        if DRY_RUN:
            print(f"  [DRY] id={rid} {name!r} -> {image_url}")
            continue

        try:
            result = client._patch(f"robots/robots/{rid}/", {"image": image_url})
            ok += 1
            # Show the image field from the response to confirm it was updated
            returned_image = result.get("image") or result.get("image_url") or "?"
            # Only show first 80 chars to avoid line wrap
            print(f"  ✓ id={rid} {name!r}")
            print(f"    -> set: {image_url[:80]}")
            print(f"    <- got: {str(returned_image)[:80]}")
        except Exception as e:
            errors += 1
            print(f"  ✗ id={rid} {name!r}: {e}")
        time.sleep(0.2)

    if DRY_RUN:
        print(f"\n[DRY RUN complete] {len(robots) - skipped} would be patched, {skipped} skipped")
    else:
        print(f"\nDone: {ok} patched, {errors} errors, {skipped} skipped")


if __name__ == "__main__":
    main()
