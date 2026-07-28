"""
muka_scrape_images.py
=====================
Custom image scraper for Xiamen MUKA Intelligent Technology Co., Ltd.
(company_id: 1480)

Root cause: The overnight enrichment pipeline rejected MUKA product images
because it classified the WooCommerce WebP thumbnails as "generic assets".
The product pages ARE correctly stored in the staged JSON `url` field.

Strategy:
1. Read all staged JSON files for MUKA from the overnight directory
2. For each robot, fetch its product URL and extract the hero image via:
   - og:image meta tag (most reliable, returns full-res PNG/WebP)
   - Fallback: .woocommerce-product-gallery__image img[data-large_image]
3. Validate the image URL (HTTP 200, image content-type)
4. PATCH the robot record via the API with the confirmed image URL

Usage:
    python muka_scrape_images.py [--dry-run] [--limit N]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from load_env import load_research_env
load_research_env()
from api_client import ResearchApiClient

# ── Config ──────────────────────────────────────────────────────────────────
COMPANY_ID = 1480
COMPANY_SLUG = "xiamen-muka-intelligent-technology"
STAGING_DIR = _RESEARCH_DIR / "staging" / "robots" / COMPANY_SLUG / "overnight"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
REQUEST_DELAY = 1.5  # seconds between requests to be polite


def fetch_og_image(product_url: str, session: requests.Session) -> str | None:
    """Fetch the og:image URL from a WooCommerce product page."""
    try:
        resp = session.get(product_url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # 1. og:image (most reliable — full-res image)
        og = soup.find("meta", property="og:image")
        if og and og.get("content"):
            url = og["content"].strip()
            # Strip WP resize params if present
            if "?" in url:
                url = url.split("?")[0]
            return url

        # 2. WooCommerce gallery main image data-large_image
        gallery_img = soup.select_one(
            ".woocommerce-product-gallery__image img[data-large_image]"
        )
        if gallery_img:
            return gallery_img["data-large_image"].strip()

        # 3. WooCommerce featured image src (full size link)
        featured_link = soup.select_one(
            ".woocommerce-product-gallery__image > a[href]"
        )
        if featured_link:
            href = featured_link["href"].strip()
            if href.startswith("http") and any(
                href.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".webp"]
            ):
                return href

        return None
    except Exception as exc:
        print(f"    [WARN] fetch_og_image failed for {product_url}: {exc}")
        return None


def validate_image_url(url: str, session: requests.Session) -> bool:
    """Check that an image URL returns HTTP 200 with an image content-type."""
    try:
        resp = session.head(url, headers=HEADERS, timeout=10, allow_redirects=True)
        ct = resp.headers.get("Content-Type", "")
        return resp.status_code == 200 and "image" in ct
    except Exception:
        return False


def load_staged_robots() -> list[dict]:
    """Load all staged JSON files for MUKA and return list of robot dicts."""
    robots = []
    if not STAGING_DIR.exists():
        print(f"[ERROR] Staging directory not found: {STAGING_DIR}")
        return robots
    for json_file in sorted(STAGING_DIR.glob("robot_*.json")):
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            if isinstance(data, list) and data:
                robot = data[0]
                robot["_staged_file"] = str(json_file)
                robots.append(robot)
        except Exception as exc:
            print(f"[WARN] Failed to parse {json_file}: {exc}")
    return robots


def get_robot_id_from_api(client: ResearchApiClient, robot_name: str) -> int | None:
    """Look up the robot's database ID by name and company."""
    try:
        resp = client._get(
            "robots/robots/",
            params={
                "company_id": COMPANY_ID,
                "search": robot_name[:50],
                "page_size": 5,
            },
        )
        results = resp.get("results", [])
        for r in results:
            if r.get("name", "").strip().lower() == robot_name.strip().lower():
                return r["id"]
        if results:
            return results[0]["id"]
    except Exception as exc:
        print(f"    [WARN] API lookup failed for '{robot_name}': {exc}")
    return None


def patch_robot_image(
    client: ResearchApiClient, robot_id: int, image_url: str, dry_run: bool
) -> bool:
    """PATCH the robot record with the confirmed image URL."""
    if dry_run:
        print(f"    [DRY-RUN] Would PATCH robot {robot_id} image={image_url}")
        return True
    try:
        client._patch(f"robots/robots/{robot_id}/", {"image": image_url})
        return True
    except Exception as exc:
        print(f"    [ERROR] PATCH failed for robot {robot_id}: {exc}")
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape and patch MUKA robot images")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--limit", type=int, default=0, help="Limit to N robots (0=all)")
    args = parser.parse_args()

    client = ResearchApiClient()
    http_session = requests.Session()

    robots = load_staged_robots()
    if args.limit:
        robots = robots[:args.limit]

    print(f"=== MUKA Image Scraper ===")
    print(f"Robots to process: {len(robots)}")
    print(f"Dry run: {args.dry_run}")
    print()

    ok = 0
    skip = 0
    fail = 0
    results = []

    for i, robot in enumerate(robots, 1):
        name = robot.get("name", "unknown")
        product_url = robot.get("url", "")
        existing_image = robot.get("image", "")
        staged_file = robot.get("_staged_file", "")

        print(f"[{i}/{len(robots)}] {name}")

        if existing_image:
            print(f"    skip — already has image: {existing_image[:60]}...")
            skip += 1
            results.append({"name": name, "status": "skip_has_image", "image": existing_image})
            continue

        if not product_url:
            print(f"    skip — no product URL in staged JSON")
            skip += 1
            results.append({"name": name, "status": "skip_no_url", "image": ""})
            continue

        # Fetch og:image from product page
        image_url = fetch_og_image(product_url, http_session)
        time.sleep(REQUEST_DELAY)

        if not image_url:
            print(f"    [FAIL] No image found on: {product_url}")
            fail += 1
            results.append({"name": name, "status": "fail_no_image", "image": "", "url": product_url})
            continue

        # Validate the image URL
        if not validate_image_url(image_url, http_session):
            print(f"    [FAIL] Image URL invalid (not 200/image): {image_url}")
            fail += 1
            results.append({"name": name, "status": "fail_invalid_url", "image": image_url, "url": product_url})
            continue

        print(f"    image={image_url[:80]}")

        # Look up robot ID in the database
        robot_id = get_robot_id_from_api(client, name)
        if not robot_id:
            print(f"    [FAIL] Robot not found in DB: {name}")
            fail += 1
            results.append({"name": name, "status": "fail_not_in_db", "image": image_url})
            continue

        # Patch the robot record
        success = patch_robot_image(client, robot_id, image_url, args.dry_run)
        if success:
            print(f"    OK — patched robot {robot_id}")
            ok += 1
            results.append({"name": name, "status": "ok", "robot_id": robot_id, "image": image_url})
        else:
            fail += 1
            results.append({"name": name, "status": "fail_patch", "robot_id": robot_id, "image": image_url})

    # Save results
    results_path = _RESEARCH_DIR / "staging" / "reports" / "muka_image_patch_results.json"
    results_path.write_text(json.dumps({"ok": ok, "skip": skip, "fail": fail, "results": results}, indent=2), encoding="utf-8")

    print()
    print(f"=== DONE === ok={ok} skip={skip} fail={fail}")
    print(f"Results saved: {results_path}")


if __name__ == "__main__":
    main()
