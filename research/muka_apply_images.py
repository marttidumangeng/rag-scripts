"""
muka_apply_images.py
Reads the scraped MUKA image URLs (from sandbox browser scrape) and patches all
65 robots via the RobotAIGeek API using the correct IMPORT_SYNC_API_KEY.

Usage:
    python muka_apply_images.py           # live run
    python muka_apply_images.py --dry-run # preview only
"""
from __future__ import annotations

import json
import os
import sys
import argparse
from pathlib import Path

# ── Load env ──────────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))
from load_env import load_research_env
load_research_env()

import requests

BASE_URL = os.environ.get("IMPORT_SYNC_API_BASE_URL", "https://api.robotaigeek.com/api/v1/").rstrip("/")
API_KEY  = os.environ.get("IMPORT_SYNC_API_KEY", "")

if not API_KEY:
    print("ERROR: IMPORT_SYNC_API_KEY not set. Check robotaigeek-server/.env")
    sys.exit(1)

HEADERS = {
    "X-API-Key": API_KEY,
    "Content-Type": "application/json",
    "User-Agent": "RobotAIGeek-Research/1.0",
}

# ── Paths ─────────────────────────────────────────────────────────────────────
STAGING_REPORTS = Path(__file__).parent / "staging" / "reports"
SCRAPE_FILE     = STAGING_REPORTS / "muka_image_scrape.json"
UNIQUE_URLS     = STAGING_REPORTS / "muka_unique_urls.json"
RESULTS_FILE    = STAGING_REPORTS / "muka_patch_results.json"

# ── Load scraped image results ────────────────────────────────────────────────
scrape_data = json.loads(SCRAPE_FILE.read_text(encoding="utf-8"))
url_to_image: dict[str, str] = {}
not_found: list[str] = []

for item in scrape_data["results"]:
    url = item["output"]["product_url"]
    img = item["output"]["image_url"]
    if img and img != "NOT_FOUND" and "muka-tech.com" in img:
        url_to_image[url] = img
    else:
        not_found.append(url)

print(f"Scraped results: {len(url_to_image)} with images, {len(not_found)} NOT_FOUND")

# ── Build robot_id -> image_url mapping ──────────────────────────────────────
unique_urls = json.loads(UNIQUE_URLS.read_text(encoding="utf-8"))
robot_patches: dict[str, str] = {}

for entry in unique_urls:
    url = entry["url"]
    ids = entry["ids"]
    img = url_to_image.get(url)
    if img:
        for rid in ids:
            robot_patches[rid] = img

print(f"Robots to patch: {len(robot_patches)}")

# ── Parse args ────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser()
parser.add_argument("--dry-run", action="store_true", help="Preview only, do not call API")
args = parser.parse_args()

if args.dry_run:
    print("\n[DRY RUN] Would patch the following robots:")
    for rid, img in list(robot_patches.items())[:10]:
        print(f"  Robot {rid}: {img[:80]}")
    if len(robot_patches) > 10:
        print(f"  ... and {len(robot_patches) - 10} more")
    if not_found:
        print(f"\nNOT_FOUND ({len(not_found)} URLs):")
        for u in not_found:
            print(f"  {u}")
    sys.exit(0)

# ── Apply patches ─────────────────────────────────────────────────────────────
ok = 0
fail = 0
results = []

for robot_id, image_url in robot_patches.items():
    try:
        resp = requests.patch(
            f"{BASE_URL}/robots/robots/{robot_id}/",
            headers=HEADERS,
            json={"image": image_url},
            timeout=15,
        )
        if resp.status_code in (200, 201):
            ok += 1
            results.append({"id": robot_id, "status": "ok", "image": image_url})
            print(f"  [OK] Robot {robot_id}: {image_url[:80]}")
        else:
            fail += 1
            results.append({"id": robot_id, "status": "fail", "code": resp.status_code, "body": resp.text[:200]})
            print(f"  [FAIL] Robot {robot_id}: HTTP {resp.status_code} - {resp.text[:100]}")
    except Exception as e:
        fail += 1
        results.append({"id": robot_id, "status": "error", "error": str(e)})
        print(f"  [ERROR] Robot {robot_id}: {e}")

print(f"\n=== DONE === ok={ok} fail={fail}")

if not_found:
    print(f"\nNOT_FOUND URLs ({len(not_found)}):")
    for u in not_found:
        print(f"  {u}")

# Save results
RESULTS_FILE.write_text(json.dumps(results, indent=2), encoding="utf-8")
print(f"Results saved to {RESULTS_FILE}")
