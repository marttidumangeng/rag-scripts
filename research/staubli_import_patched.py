"""
staubli_import_patched.py
Imports all patched Stäubli Robotics staged robot JSONs (with corrected image URLs)
into the RobotAIGeek database via the bulk import API.

Run from: scripts/research/
Usage: python staubli_import_patched.py [--dry-run]
"""

import json
import os
import sys
import time
import glob
import requests
from pathlib import Path

DRY_RUN = "--dry-run" in sys.argv

# Use the same client pattern as import_staging.py
from api_client import ResearchApiClient
from load_env import load_research_env

load_research_env()

client = ResearchApiClient()


def load_robot_json(filepath: str) -> dict | None:
    """Load a single robot JSON file, handling both list and dict formats."""
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data[0] if data else None
    return data


def import_robot(robot: dict, filepath: str) -> dict:
    """Import a single robot via the API using the bulk_import_robots endpoint."""
    robot_id = robot.get("id")
    name = robot.get("name", "Unknown")
    model = robot.get("model_name", "")

    if DRY_RUN:
        has_image = bool(robot.get("image_url", "").strip())
        print(f"  [DRY RUN] Would import: {name} ({model}) | image={'✓' if has_image else '✗'}")
        return {"status": "dry_run", "name": name}

    try:
        result = client.bulk_import_robots(
            [robot],
            update_existing=True,
            patch_existing=True,
            status="published",
            skip_company_update=True,
            created_by_id=None,
            replace_media=True,
        )
        imported = result.get("imported", 0)
        updated = result.get("updated", 0)
        errors = result.get("errors", [])
        if errors:
            print(f"  ✗ Import error: {name} — {errors}")
            return {"status": "error", "name": name, "detail": str(errors)}
        action = "updated" if updated else "created"
        result_id = result.get("ids", [robot_id])[0] if result.get("ids") else robot_id
        print(f"  ✓ {action.capitalize()}: {name} ({model}) → ID {result_id}")
        return {"status": "success", "id": result_id, "name": name, "action": action}
    except Exception as e:
        print(f"  ✗ Exception: {name} — {e}")
        return {"status": "exception", "name": name, "error": str(e)}


def main():
    base_dir = Path(__file__).parent / "staging" / "robots" / "staubli-robotics"

    if not base_dir.exists():
        print(f"ERROR: Staging directory not found: {base_dir}")
        sys.exit(1)

    # Collect all JSON files across all subdirectories, deduplicate by robot ID
    all_files = list(base_dir.rglob("robot_*.json"))
    
    # Deduplicate: prefer overnight/ subdirectory files, then most recently modified
    seen_ids = {}
    for f in sorted(all_files, key=lambda x: ("overnight" not in str(x), x.stat().st_mtime)):
        robot = load_robot_json(str(f))
        if not robot:
            continue
        robot_id = robot.get("id") or f.stem  # Use file stem as key if no ID
        if robot_id not in seen_ids:
            seen_ids[robot_id] = (f, robot)

    robots_to_import = list(seen_ids.values())
    print(f"{'[DRY RUN] ' if DRY_RUN else ''}Found {len(robots_to_import)} unique robots to import")
    print("=" * 60)

    results = []
    for filepath, robot in sorted(robots_to_import, key=lambda x: x[0].name):
        name = robot.get("name", "Unknown")
        model = robot.get("model_name", "")
        has_image = bool(robot.get("image_url", "").strip())
        print(f"\nProcessing: {filepath.name} — {name} ({model}) | image={'✓' if has_image else '✗'}")
        
        result = import_robot(robot, str(filepath))
        results.append(result)
        
        if not DRY_RUN:
            time.sleep(0.3)  # Rate limit

    # Summary
    print("\n" + "=" * 60)
    success = [r for r in results if r.get("status") == "success"]
    errors = [r for r in results if r.get("status") == "error"]
    exceptions = [r for r in results if r.get("status") == "exception"]
    
    created = [r for r in success if r.get("action") == "post"]
    updated = [r for r in success if r.get("action") == "patch"]

    print(f"SUMMARY: {len(created)} created, {len(updated)} updated, {len(errors)} errors, {len(exceptions)} exceptions")
    
    if errors:
        print("\nErrors:")
        for e in errors:
            print(f"  - {e['name']}: HTTP {e.get('code')} — {e.get('detail', '')[:100]}")

    # Save results
    result_path = Path(__file__).parent / "staging" / "reports" / "staubli_image_import_result.json"
    result_path.parent.mkdir(exist_ok=True)
    with open(result_path, "w") as f:
        json.dump({"total": len(results), "created": len(created), "updated": len(updated),
                   "errors": len(errors), "results": results}, f, indent=2)
    print(f"\nResults saved to: {result_path}")


if __name__ == "__main__":
    main()
