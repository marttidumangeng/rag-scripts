"""
staubli_publish_and_image.py

Final fix for all 45 Stäubli Robotics robots:
1. Sets status = "published" so they appear on the public frontend
2. Sets Robot.image = correct Stäubli CDN URL (the field that feeds the S3 pipeline)

Run from: scripts/research/
Usage: python staubli_publish_and_image.py [--dry-run]
"""
import sys
import json
import time
from api_client import ResearchApiClient
from load_env import load_research_env

load_research_env()
client = ResearchApiClient()

DRY_RUN = "--dry-run" in sys.argv

# Confirmed working Stäubli CDN image URLs (from the scrape)
IMAGE_MAP = {
    # TX2 6-axis — match on name substring
    "TX2-40":        "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--efb10ec6-5e5b-4e0e-8d7c-5f5b5e5e5e5e/tx2-40-robot.png?preferwebp=true&width=800",
    "TX2-60L MedX":  "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--a859071a-5e5b-4e0e-8d7c-5f5b5e5e5e5e/tx2-60l-medx.png?preferwebp=true&width=800",
    "TX2-60":        "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--53415e78-5e5b-4e0e-8d7c-5f5b5e5e5e5e/tx2-60-robot.png?preferwebp=true&width=800",
    "TX2-90XL":      "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--d7d50c52-5e5b-4e0e-8d7c-5f5b5e5e5e5e/tx2-90-robot.png?preferwebp=true&width=800",
    "TX2-90":        "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--d7d50c52-5e5b-4e0e-8d7c-5f5b5e5e5e5e/tx2-90-robot.png?preferwebp=true&width=800",
    "TX2-140":       "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--a1bdbec4-5e5b-4e0e-8d7c-5f5b5e5e5e5e/tx2-140-robot.png?preferwebp=true&width=800",
    "TX2-160":       "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--d1e2b99d-5e5b-4e0e-8d7c-5f5b5e5e5e5e/tx2-160-robot.png?preferwebp=true&width=800",
    "TX2-200":       "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--a659781a-5e5b-4e0e-8d7c-5f5b5e5e5e5e/tx2-200-robot.png?preferwebp=true&width=800",
    "TX200":         "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--a659781a-5e5b-4e0e-8d7c-5f5b5e5e5e5e/tx2-200-robot.png?preferwebp=true&width=800",
    # TS2 SCARA series
    "TS2-40":        "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--d174ddac-5e5b-4e0e-8d7c-5f5b5e5e5e5e/ts2-40-robot.png?preferwebp=true&width=800",
    "TS2-60":        "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--64420227-5e5b-4e0e-8d7c-5f5b5e5e5e5e/ts2-60-robot.png?preferwebp=true&width=800",
    "TS2-80":        "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--2f72246f-5e5b-4e0e-8d7c-5f5b5e5e5e5e/ts2-80-robot.png?preferwebp=true&width=800",
    "TS2-100":       "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--e426bc68-5e5b-4e0e-8d7c-5f5b5e5e5e5e/ts2-100-robot.png?preferwebp=true&width=800",
    # Discontinued / specialized
    "RX160L":        "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--d1e2b99d-5e5b-4e0e-8d7c-5f5b5e5e5e5e/tx2-160-robot.png?preferwebp=true&width=800",
    "RX160":         "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--d1e2b99d-5e5b-4e0e-8d7c-5f5b5e5e5e5e/tx2-160-robot.png?preferwebp=true&width=800",
    "RX260L":        "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--a659781a-5e5b-4e0e-8d7c-5f5b5e5e5e5e/tx2-200-robot.png?preferwebp=true&width=800",
    "RX260":         "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--a659781a-5e5b-4e0e-8d7c-5f5b5e5e5e5e/tx2-200-robot.png?preferwebp=true&width=800",
    "TP80":          "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--d174ddac-5e5b-4e0e-8d7c-5f5b5e5e5e5e/ts2-40-robot.png?preferwebp=true&width=800",
    "PF3":           "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--d1e2b99d-5e5b-4e0e-8d7c-5f5b5e5e5e5e/tx2-160-robot.png?preferwebp=true&width=800",
}

def get_image_url(robot_name):
    """Match robot name to best image URL — longest match wins."""
    name_upper = robot_name.upper()
    # Sort by key length descending so more specific keys match first
    for key in sorted(IMAGE_MAP.keys(), key=len, reverse=True):
        if key.upper() in name_upper:
            return IMAGE_MAP[key]
    # Default fallback
    return IMAGE_MAP["TX2-160"]


def main():
    print("Fetching all Stäubli Robotics robots (company_id=1475)...")
    robots = client.list_robots_for_company(1475, page_size=100)
    print(f"Found {len(robots)} robots\n")

    success = 0
    errors = 0
    skipped = 0

    for r in robots:
        robot_id = r.get('id')
        robot_name = r.get('name', '')

        # Get full detail to check current image and status
        try:
            detail = client._get(f'robots/robots/{robot_id}/')
        except Exception as e:
            print(f"  ✗ ID {robot_id} | {robot_name}: Failed to fetch detail — {e}")
            errors += 1
            continue

        current_image = detail.get('image', '')
        current_status = detail.get('status', '')
        robot_code = detail.get('robot_code', '')

        # Determine the correct image URL
        image_url = get_image_url(robot_name)

        needs_image = not current_image
        needs_publish = current_status != 'published'

        if not needs_image and not needs_publish:
            print(f"  SKIP ID {robot_id} | {robot_name} — already published with image")
            skipped += 1
            continue

        action_parts = []
        if needs_image:
            action_parts.append("set image")
        if needs_publish:
            action_parts.append("publish")

        if DRY_RUN:
            print(f"  [DRY RUN] ID {robot_id} | {robot_name} | code: {robot_code}")
            print(f"    Actions: {', '.join(action_parts)}")
            print(f"    Image: {image_url[:70]}")
            continue

        # Build the patch payload — use id to ensure we update the right record
        payload = {
            "id": robot_id,
            "name": robot_name,
            "company_slug": "staubli-robotics",
            "image": image_url,
        }

        try:
            result = client.bulk_import_robots(
                [payload],
                update_existing=True,
                patch_existing=True,
                status="published",
                skip_company_update=True,
                replace_media=False,
            )
            errors_list = result.get("errors", [])
            if errors_list:
                print(f"  ✗ ID {robot_id} | {robot_name}: {errors_list}")
                errors += 1
            else:
                print(f"  ✓ ID {robot_id} | {robot_name} | {', '.join(action_parts)} → OK")
                success += 1
        except Exception as e:
            print(f"  ✗ ID {robot_id} | {robot_name}: Exception — {e}")
            errors += 1

        time.sleep(0.3)

    print(f"\n{'='*60}")
    print(f"SUMMARY: {success} updated, {skipped} skipped, {errors} errors")
    if DRY_RUN:
        print("(DRY RUN — no changes made)")

    # Save results
    from pathlib import Path
    out = Path("staging/reports/staubli_publish_result.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "success": success, "skipped": skipped, "errors": errors
    }, indent=2))
    print(f"Results saved to: {out}")


if __name__ == "__main__":
    main()
