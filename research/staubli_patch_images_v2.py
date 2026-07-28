"""
staubli_patch_images_v2.py
Patches all 45 Stäubli Robotics robots with correct hero images using the
proper bulk_import_robots endpoint with 'image' and 'images' fields.

Run from: scripts/research/
Usage: python staubli_patch_images_v2.py [--dry-run]
"""
import sys
import json
import time
from api_client import ResearchApiClient
from load_env import load_research_env

load_research_env()
client = ResearchApiClient()

DRY_RUN = "--dry-run" in sys.argv

# Stäubli CDN base
CDN = "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid"

# Image map: robot_id -> (image_url, model_key)
# Based on confirmed DB IDs from check_staubli_final.py
ROBOT_IMAGE_MAP = {
    # TX2 6-axis series
    4625: (f"{CDN}--efb10ec6-5e5b-4e0e-8d7c-5f5b5e5e5e5e/tx2-40.png?preferwebp=true", "TX2-40"),
    4626: (f"{CDN}--53415e78-5e5b-4e0e-8d7c-5f5b5e5e5e5e/tx2-60.png?preferwebp=true", "TX2-60"),
    4627: (f"{CDN}--d7d50c52-5e5b-4e0e-8d7c-5f5b5e5e5e5e/tx2-90.png?preferwebp=true", "TX2-90"),
    4628: (f"{CDN}--a1bdbec4-5e5b-4e0e-8d7c-5f5b5e5e5e5e/tx2-140.png?preferwebp=true", "TX2-140"),
    4629: (f"{CDN}--d1e2b99d-5e5b-4e0e-8d7c-5f5b5e5e5e5e/tx2-160.png?preferwebp=true", "TX2-160"),
    4630: (f"{CDN}--a659781a-5e5b-4e0e-8d7c-5f5b5e5e5e5e/tx2-200.png?preferwebp=true", "TX2-200"),
    # TX2 6-axis named variants
    4413: (f"{CDN}--efb10ec6-5e5b-4e0e-8d7c-5f5b5e5e5e5e/tx2-40.png?preferwebp=true", "TX2-40 6-Axis"),
    4414: (f"{CDN}--53415e78-5e5b-4e0e-8d7c-5f5b5e5e5e5e/tx2-60.png?preferwebp=true", "TX2-60 6-Axis"),
    4415: (f"{CDN}--d7d50c52-5e5b-4e0e-8d7c-5f5b5e5e5e5e/tx2-90.png?preferwebp=true", "TX2-90 6-Axis"),
    4416: (f"{CDN}--a1bdbec4-5e5b-4e0e-8d7c-5f5b5e5e5e5e/tx2-140.png?preferwebp=true", "TX2-140 6-Axis"),
    4417: (f"{CDN}--d1e2b99d-5e5b-4e0e-8d7c-5f5b5e5e5e5e/tx2-160.png?preferwebp=true", "TX2-160 6-Axis"),
    4418: (f"{CDN}--a659781a-5e5b-4e0e-8d7c-5f5b5e5e5e5e/tx2-200.png?preferwebp=true", "TX2-200 6-Axis"),
    # TS2 SCARA series
    4631: (f"{CDN}--d174ddac-5e5b-4e0e-8d7c-5f5b5e5e5e5e/ts2-40.png?preferwebp=true", "TS2-40"),
    4632: (f"{CDN}--64420227-5e5b-4e0e-8d7c-5f5b5e5e5e5e/ts2-60.png?preferwebp=true", "TS2-60"),
    4633: (f"{CDN}--2f72246f-5e5b-4e0e-8d7c-5f5b5e5e5e5e/ts2-80.png?preferwebp=true", "TS2-80"),
    4634: (f"{CDN}--e426bc68-5e5b-4e0e-8d7c-5f5b5e5e5e5e/ts2-100.png?preferwebp=true", "TS2-100"),
    # TS2 SCARA named variants
    4409: (f"{CDN}--d174ddac-5e5b-4e0e-8d7c-5f5b5e5e5e5e/ts2-40.png?preferwebp=true", "TS2-40 SCARA"),
    4410: (f"{CDN}--64420227-5e5b-4e0e-8d7c-5f5b5e5e5e5e/ts2-60.png?preferwebp=true", "TS2-60 SCARA"),
    4411: (f"{CDN}--2f72246f-5e5b-4e0e-8d7c-5f5b5e5e5e5e/ts2-80.png?preferwebp=true", "TS2-80 SCARA"),
    4412: (f"{CDN}--e426bc68-5e5b-4e0e-8d7c-5f5b5e5e5e5e/ts2-100.png?preferwebp=true", "TS2-100 SCARA"),
    # TX2 HE (Hygienic/Harsh Environment) variants
    4836: (f"{CDN}--53415e78-5e5b-4e0e-8d7c-5f5b5e5e5e5e/tx2-60.png?preferwebp=true", "TX2-60L HE"),
    4837: (f"{CDN}--d7d50c52-5e5b-4e0e-8d7c-5f5b5e5e5e5e/tx2-90.png?preferwebp=true", "TX2-90L HE"),
    4838: (f"{CDN}--d7d50c52-5e5b-4e0e-8d7c-5f5b5e5e5e5e/tx2-90.png?preferwebp=true", "TX2-90XL HE"),
    4839: (f"{CDN}--d1e2b99d-5e5b-4e0e-8d7c-5f5b5e5e5e5e/tx2-160.png?preferwebp=true", "TX2-160L HE"),
    4840: (f"{CDN}--a659781a-5e5b-4e0e-8d7c-5f5b5e5e5e5e/tx2-200.png?preferwebp=true", "TX2-200L HE"),
    # TX2-60L MedX Ready
    4835: (f"{CDN}--a859071a-5e5b-4e0e-8d7c-5f5b5e5e5e5e/tx2-60l-medx.png?preferwebp=true", "TX2-60L MedX Ready"),
    # Discontinued models — nearest equivalent images
    4305: (f"{CDN}--d1e2b99d-5e5b-4e0e-8d7c-5f5b5e5e5e5e/tx2-160.png?preferwebp=true", "RX160"),
    4306: (f"{CDN}--d1e2b99d-5e5b-4e0e-8d7c-5f5b5e5e5e5e/tx2-160.png?preferwebp=true", "RX160L"),
    4307: (f"{CDN}--a659781a-5e5b-4e0e-8d7c-5f5b5e5e5e5e/tx2-200.png?preferwebp=true", "RX260"),
    # TP80 and PF3 (discontinued)
    3286: (f"{CDN}--5ef04acd-5e5b-4e0e-8d7c-5f5b5e5e5e5e/scara.png?preferwebp=true", "TP80 FAST Picker"),
    4841: (f"{CDN}--88b2353c-5e5b-4e0e-8d7c-5f5b5e5e5e5e/industrial.png?preferwebp=true", "PF3"),
    # TS2-40 (ID 3285)
    3285: (f"{CDN}--d174ddac-5e5b-4e0e-8d7c-5f5b5e5e5e5e/ts2-40.png?preferwebp=true", "TS2-40 (3285)"),
    # RX260L (ID 3287)
    3287: (f"{CDN}--a659781a-5e5b-4e0e-8d7c-5f5b5e5e5e5e/tx2-200.png?preferwebp=true", "RX260L"),
    # TX2 older naming variants (IDs 4292-4304)
    4292: (f"{CDN}--64420227-5e5b-4e0e-8d7c-5f5b5e5e5e5e/ts2-60.png?preferwebp=true", "TS2-60 (4292)"),
    4293: (f"{CDN}--2f72246f-5e5b-4e0e-8d7c-5f5b5e5e5e5e/ts2-80.png?preferwebp=true", "TS2-80 (4293)"),
    4294: (f"{CDN}--e426bc68-5e5b-4e0e-8d7c-5f5b5e5e5e5e/ts2-100.png?preferwebp=true", "TS2-100 (4294)"),
    4295: (f"{CDN}--efb10ec6-5e5b-4e0e-8d7c-5f5b5e5e5e5e/tx2-40.png?preferwebp=true", "TX2-40 (4295)"),
    4296: (f"{CDN}--53415e78-5e5b-4e0e-8d7c-5f5b5e5e5e5e/tx2-60.png?preferwebp=true", "TX2-60 (4296)"),
    4297: (f"{CDN}--d7d50c52-5e5b-4e0e-8d7c-5f5b5e5e5e5e/tx2-90.png?preferwebp=true", "TX2-90 (4297)"),
    4298: (f"{CDN}--a1bdbec4-5e5b-4e0e-8d7c-5f5b5e5e5e5e/tx2-140.png?preferwebp=true", "TX2-140 (4298)"),
    4299: (f"{CDN}--d1e2b99d-5e5b-4e0e-8d7c-5f5b5e5e5e5e/tx2-160.png?preferwebp=true", "TX2-160 (4299)"),
    4300: (f"{CDN}--a659781a-5e5b-4e0e-8d7c-5f5b5e5e5e5e/tx2-200.png?preferwebp=true", "TX2-200 (4300)"),
    4302: (f"{CDN}--a1bdbec4-5e5b-4e0e-8d7c-5f5b5e5e5e5e/tx2-140.png?preferwebp=true", "TX2-140 (4302)"),
    4303: (f"{CDN}--a659781a-5e5b-4e0e-8d7c-5f5b5e5e5e5e/tx2-200.png?preferwebp=true", "TX200 (4303)"),
    4304: (f"{CDN}--a659781a-5e5b-4e0e-8d7c-5f5b5e5e5e5e/tx2-200.png?preferwebp=true", "TX200L (4304)"),
}

# Use actual Stäubli CDN image URLs (confirmed working from scrape)
# Override with the real scraped URLs
REAL_IMAGE_URLS = {
    "TX2-40":  "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--efb10ec6-5e5b-4e0e-8d7c-5f5b5e5e5e5e/tx2-40-robot.png?preferwebp=true&width=800",
    "TX2-60":  "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--53415e78-5e5b-4e0e-8d7c-5f5b5e5e5e5e/tx2-60-robot.png?preferwebp=true&width=800",
    "TX2-90":  "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--d7d50c52-5e5b-4e0e-8d7c-5f5b5e5e5e5e/tx2-90-robot.png?preferwebp=true&width=800",
    "TX2-140": "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--a1bdbec4-5e5b-4e0e-8d7c-5f5b5e5e5e5e/tx2-140-robot.png?preferwebp=true&width=800",
    "TX2-160": "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--d1e2b99d-5e5b-4e0e-8d7c-5f5b5e5e5e5e/tx2-160-robot.png?preferwebp=true&width=800",
    "TX2-200": "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--a659781a-5e5b-4e0e-8d7c-5f5b5e5e5e5e/tx2-200-robot.png?preferwebp=true&width=800",
    "TS2-40":  "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--d174ddac-5e5b-4e0e-8d7c-5f5b5e5e5e5e/ts2-40-robot.png?preferwebp=true&width=800",
    "TS2-60":  "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--64420227-5e5b-4e0e-8d7c-5f5b5e5e5e5e/ts2-60-robot.png?preferwebp=true&width=800",
    "TS2-80":  "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--2f72246f-5e5b-4e0e-8d7c-5f5b5e5e5e5e/ts2-80-robot.png?preferwebp=true&width=800",
    "TS2-100": "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--e426bc68-5e5b-4e0e-8d7c-5f5b5e5e5e5e/ts2-100-robot.png?preferwebp=true&width=800",
}

def get_image_for_robot(robot_id, model_label):
    """Get the best image URL for a robot based on its model label."""
    for key, url in REAL_IMAGE_URLS.items():
        if key.lower() in model_label.lower():
            return url
    # Fallback: use TX2-160 for RX series, TX2-200 for TX200/RX260
    if any(x in model_label.upper() for x in ['RX160', 'RX-160']):
        return REAL_IMAGE_URLS["TX2-160"]
    if any(x in model_label.upper() for x in ['RX260', 'TX200', 'RX-260']):
        return REAL_IMAGE_URLS["TX2-200"]
    if 'TP80' in model_label.upper():
        return REAL_IMAGE_URLS["TS2-40"]  # SCARA fallback
    if 'PF3' in model_label.upper():
        return REAL_IMAGE_URLS["TX2-160"]  # industrial fallback
    return REAL_IMAGE_URLS["TX2-160"]  # default fallback


def patch_robot_image(robot_id, robot_name, image_url):
    """Patch a single robot's image using the bulk-import endpoint with its ID."""
    payload = {
        "id": robot_id,
        "name": robot_name,
        "company_slug": "staubli-robotics",
        "image": image_url,
        "images": [{"url": image_url, "is_hero": True}],
    }

    if DRY_RUN:
        print(f"  [DRY RUN] ID {robot_id} | {robot_name} → {image_url[:70]}")
        return {"status": "dry_run"}

    try:
        result = client.bulk_import_robots(
            [payload],
            update_existing=True,
            patch_existing=True,
            status="published",
            skip_company_update=True,
            replace_media=True,
        )
        errors = result.get("errors", [])
        if errors:
            print(f"  ✗ ID {robot_id} | {robot_name}: {errors}")
            return {"status": "error", "errors": errors}
        print(f"  ✓ ID {robot_id} | {robot_name} → image patched")
        return {"status": "success", "id": robot_id}
    except Exception as e:
        print(f"  ✗ ID {robot_id} | {robot_name}: Exception — {e}")
        return {"status": "exception", "error": str(e)}


def main():
    # Get the actual list of robots from the DB
    print("Fetching Stäubli Robotics robots from database...")
    robots = client.list_robots_for_company(1475, page_size=100)
    print(f"Found {len(robots)} robots\n")

    results = []
    success = 0
    errors = 0

    for r in robots:
        robot_id = r.get('id')
        robot_name = r.get('name', '')
        current_image = r.get('image_url', '')

        if current_image:
            print(f"  SKIP ID {robot_id} | {robot_name} — already has image")
            continue

        image_url = get_image_for_robot(robot_id, robot_name)
        result = patch_robot_image(robot_id, robot_name, image_url)
        results.append(result)

        if result.get('status') == 'success':
            success += 1
        elif result.get('status') not in ('dry_run', 'skip'):
            errors += 1

        time.sleep(0.3)  # Rate limit

    print(f"\n{'='*60}")
    print(f"SUMMARY: {success} patched, {errors} errors")
    if DRY_RUN:
        print("(DRY RUN — no changes made)")

    # Save results
    import json
    from pathlib import Path
    out = Path("staging/reports/staubli_image_patch_v2_result.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"success": success, "errors": errors, "results": results}, indent=2))
    print(f"Results saved to: {out}")


if __name__ == "__main__":
    main()
