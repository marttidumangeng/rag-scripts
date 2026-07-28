"""
staubli_patch_images.py
Patches all 19 Stäubli Robotics staged robot JSONs with correct hero image URLs
sourced directly from staubli.com CDN (dynamicmedia).

Run from: scripts/research/
Usage: python staubli_patch_images.py [--dry-run]
"""

import json
import os
import sys
import glob
from pathlib import Path

DRY_RUN = "--dry-run" in sys.argv

# Map: model name keywords → official Stäubli CDN image URL
# All images verified from staubli.com product pages July 2026
IMAGE_MAP = {
    # TX2 6-axis series
    "TX2-40": "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--efb10ec6-1419-486b-985c-41234bf365fc/tx2-40-industrial-robot.jpg?quality=82&preferwebp=true",
    "TX2-60L HE": "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--53415e78-1ac3-4d64-a081-2e0886bbfef5/tx2-60-industrial-robot-range.jpg?quality=82&preferwebp=true",
    "TX2-60L MedX": "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--a859071a-44e6-4ecd-b468-cd6297280803/medx-ready-medical-robot.jpg?quality=82&preferwebp=true",
    "TX2-60": "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--53415e78-1ac3-4d64-a081-2e0886bbfef5/tx2-60-industrial-robot-range.jpg?quality=82&preferwebp=true",
    "TX2-90L HE": "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--d7d50c52-bef9-49e2-bcd2-3dc728ccaa59/tx2-90-industrial-robot-range.jpg?quality=82&preferwebp=true",
    "TX2-90XL HE": "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--d7d50c52-bef9-49e2-bcd2-3dc728ccaa59/tx2-90-industrial-robot-range.jpg?quality=82&preferwebp=true",
    "TX2-90": "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--d7d50c52-bef9-49e2-bcd2-3dc728ccaa59/tx2-90-industrial-robot-range.jpg?quality=82&preferwebp=true",
    "TX2-140": "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--a1bdbec4-d127-450f-8131-4f2db8f7a20b/staubli-articulated-robots.jpg?quality=82&preferwebp=true",
    "TX2-160L HE": "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--d1e2b99d-7932-4a93-98b4-818efd9d7921/tx2-160-industrial-robot-range.jpg?quality=82&preferwebp=true",
    "TX2-160": "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--d1e2b99d-7932-4a93-98b4-818efd9d7921/tx2-160-industrial-robot-range.jpg?quality=82&preferwebp=true",
    "TX2-200L HE": "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--a659781a-2977-402a-8951-370396013220/tx2-200-robot-01.jpg?quality=82&preferwebp=true",
    "TX2-200": "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--a659781a-2977-402a-8951-370396013220/tx2-200-robot-01.jpg?quality=82&preferwebp=true",
    # TS2 SCARA series
    "TS2-40": "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--d174ddac-9ee0-4b70-9f53-86beabe023d0/ts2-40-scara-robot.jpg?quality=82&preferwebp=true",
    "TS2-60": "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--64420227-2101-4473-827c-011119777170/TS2-60_front_01.jpg?quality=82&preferwebp=true",
    "TS2-80": "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--2f72246f-cf84-405d-a6eb-cc8c932fcec0/ts2-80-scara-robot.jpg?quality=82&preferwebp=true",
    "TS2-100": "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--e426bc68-a7b7-4ee3-854f-e876b09433f8/ts2-100-scara-robot.jpg?quality=82&preferwebp=true",
    # Specialized robots
    "TP80": "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--5ef04acd-c53b-4c53-8968-2b2ecdabaa95/staubli-scara-robots.jpg?quality=82&preferwebp=true",
    "PF3": "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--88b2353c-67bd-4576-b879-a87a279f3135/robotics-industrial-robots-product-range.jpg?quality=82&preferwebp=true",
    # Legacy/discontinued models — use TX2-200 hero as closest visual match
    "TX200L": "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--a659781a-2977-402a-8951-370396013220/tx2-200-robot-01.jpg?quality=82&preferwebp=true",
    "TX200": "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--a659781a-2977-402a-8951-370396013220/tx2-200-robot-01.jpg?quality=82&preferwebp=true",
    "RX160L": "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--d1e2b99d-7932-4a93-98b4-818efd9d7921/tx2-160-industrial-robot-range.jpg?quality=82&preferwebp=true",
    "RX160": "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--d1e2b99d-7932-4a93-98b4-818efd9d7921/tx2-160-industrial-robot-range.jpg?quality=82&preferwebp=true",
    "RX260L": "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--a659781a-2977-402a-8951-370396013220/tx2-200-robot-01.jpg?quality=82&preferwebp=true",
    "RX260": "https://www.staubli.com/adobe/dynamicmedia/deliver/dm-aid--a659781a-2977-402a-8951-370396013220/tx2-200-robot-01.jpg?quality=82&preferwebp=true",
}

def get_image_url(robot_name: str, model_name: str) -> str | None:
    """Find the best matching image URL for a robot based on name/model."""
    search_str = f"{robot_name} {model_name}".upper()
    
    # Try longest match first (most specific)
    candidates = sorted(IMAGE_MAP.keys(), key=len, reverse=True)
    for key in candidates:
        if key.upper() in search_str:
            return IMAGE_MAP[key]
    return None


def patch_json_file(filepath: str) -> dict:
    """Patch a single staged JSON file with the correct image URL."""
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Handle both list and dict formats
    robots = data if isinstance(data, list) else [data]
    patched_count = 0

    for robot in robots:
        name = robot.get("name", "")
        model = robot.get("model_name", "")
        
        # Check if image is missing or empty
        current_image = robot.get("image_url", "")
        if current_image and current_image.strip():
            continue  # Already has an image, skip
        
        image_url = get_image_url(name, model)
        if image_url:
            robot["image_url"] = image_url
            patched_count += 1
            print(f"  ✓ {name} ({model}) → {image_url[:80]}...")
        else:
            print(f"  ✗ No image found for: {name} ({model})")

    if patched_count > 0 and not DRY_RUN:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    return {"file": filepath, "patched": patched_count}


def main():
    base_dir = Path(__file__).parent / "staging" / "robots" / "staubli-robotics"
    
    if not base_dir.exists():
        print(f"ERROR: Staging directory not found: {base_dir}")
        sys.exit(1)

    json_files = list(base_dir.rglob("robot_*.json"))
    
    if not json_files:
        print(f"No robot JSON files found in {base_dir}")
        sys.exit(1)

    print(f"{'[DRY RUN] ' if DRY_RUN else ''}Found {len(json_files)} JSON files to patch")
    print("=" * 60)

    total_patched = 0
    total_skipped = 0

    for filepath in sorted(json_files):
        print(f"\nProcessing: {filepath.name}")
        result = patch_json_file(str(filepath))
        if result["patched"] > 0:
            total_patched += result["patched"]
        else:
            total_skipped += 1

    print("\n" + "=" * 60)
    print(f"SUMMARY: {total_patched} robots patched with images, {total_skipped} files skipped (already had images or no match)")
    if DRY_RUN:
        print("[DRY RUN] No files were actually modified.")


if __name__ == "__main__":
    main()
