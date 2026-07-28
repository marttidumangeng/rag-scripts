"""
fix_rokae_primary_images.py
---------------------------
Fix the primary images for 15 ROKAE robots that currently have logo banners
or website chrome as their primary image.

Strategy:
  1. For each robot, fetch all gallery photos from the API.
  2. Identify the best product shot from the existing gallery (skip known bad
     patterns: logo banners, website chrome, QR codes, spec-callout graphics).
  3. If a good gallery photo is found, patch robot.image to that URL and set
     the corresponding RobotPhoto.is_primary = True.
  4. For robots with no usable gallery photo (e.g. robot 3386), scrape the
     official ROKAE product page and use the first clean product image found.

Usage:
    python fix_rokae_primary_images.py [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Optional

sys.path.insert(0, os.path.dirname(__file__))
from api_client import ResearchApiClient
from web_extract import parse_page, WebFetcher

# ---------------------------------------------------------------------------
# Known bad image URL patterns (skip these as primary candidates)
# ---------------------------------------------------------------------------
BAD_URL_PATTERNS = [
    r"indexbanner",          # site-wide banner images
    r"index_plan_bg",        # background graphic
    r"GongAnBeiAnTuBiao",    # government filing icon
    r"linkedin_code",        # QR code
    r"linkedin",             # social media
    r"/pc/img/",             # generic site chrome
    r"rokae\+",              # ROKAE+ brand banner (neon logo)
    r"ROKAE\+",
    r"indexbanner_bg",       # banner background
    r"indexbanner_img",      # banner image
    # Detect the specific neon ROKAE logo banner by its known CDN path
    r"robots/original/robot-\d+",  # the original-source copies (all banners)
]

BAD_URL_RE = re.compile("|".join(BAD_URL_PATTERNS), re.IGNORECASE)


def is_bad_image(url: str) -> bool:
    return bool(BAD_URL_RE.search(url))


# ---------------------------------------------------------------------------
# Hardcoded image overrides for robots where gallery scraping fails
# ---------------------------------------------------------------------------
IMAGE_OVERRIDES = {
    # Robot 3386 (ROKAE CR20-17/2.0C-5): all gallery photos are website chrome.
    # Best clean product shot sourced manually from the official EN product page.
    3386: "https://www.rokae.com/public/uploads/20240307/7ee6bc415e2a727e516185fe41d5cad7.png",
}

# ---------------------------------------------------------------------------
# Robots to fix: id -> product_url (for fallback scraping)
# ---------------------------------------------------------------------------
ROBOTS_TO_FIX = {
    2222: "https://www.rokae.com/cn/product/show/1/xMateCR.html",
    2226: "https://www.rokae.com/cn/product/show/1/xMateCR.html",
    2231: "https://www.rokae.com/cn/product/show/1/xMateCR.html",
    2235: "https://www.rokae.com/cn/product/show/1/xMateCR.html",
    2240: "https://www.rokae.com/cn/product/show/1/xMateCR.html",
    2245: "https://www.rokae.com/cn/product/show/1/xMateCR.html",
    2250: "https://www.rokae.com/cn/product/show/1/xMateCR.html",
    2254: "https://www.rokae.com/cn/product/show/1/xMateCR.html",
    2257: "https://www.rokae.com/cn/product/show/1/xMateSR.html",
    2263: "https://www.rokae.com/cn/product/show/1/xMateSR.html",
    2266: "https://www.rokae.com/cn/product/show/1/xMateSR.html",
    2269: "https://www.rokae.com/cn/product/show/1/xMateER.html",
    2273: "https://www.rokae.com/cn/product/show/1/xMateER.html",
    2277: "https://www.rokae.com/cn/product/show/1/xMateER.html",
    3386: "https://www.rokae.com/en/product/show/545/xMateCR.html",  # EN page
}


def best_gallery_photo(photos: list[dict]) -> Optional[str]:
    """Return the URL of the best non-bad gallery photo, or None."""
    # Prefer photos that are NOT the current primary and NOT bad
    non_primary = [p for p in photos if not p.get("is_primary") and not is_bad_image(p.get("url", ""))]
    if non_primary:
        # Sort by order ascending, take first
        non_primary.sort(key=lambda p: p.get("order", 0))
        return non_primary[0]["url"]
    # Fallback: any non-bad photo including current primary
    any_good = [p for p in photos if not is_bad_image(p.get("url", ""))]
    if any_good:
        any_good.sort(key=lambda p: p.get("order", 0))
        return any_good[0]["url"]
    return None


def scrape_product_image(product_url: str, fetcher: WebFetcher) -> Optional[str]:
    """Scrape the ROKAE product page and return the first clean product image URL."""
    try:
        html = fetcher.get(product_url)
        if not html:
            return None
        page = parse_page(html, url=product_url)
        # Look for product images in the page images list
        for img in (page.images or []):
            url = img if isinstance(img, str) else img.get("url", "")
            if not url:
                continue
            if is_bad_image(url):
                continue
            # Prefer rokae.com uploads (dated paths)
            if "rokae.com/public/uploads/" in url or "static.rokae.com" in url:
                return url
        # Fallback: any image from the page
        for img in (page.images or []):
            url = img if isinstance(img, str) else img.get("url", "")
            if url and not is_bad_image(url):
                return url
    except Exception as e:
        print(f"  [scrape error] {product_url}: {e}")
    return None


def patch_primary_image(client: ResearchApiClient, robot_id: int, new_image_url: str, photos: list[dict], dry_run: bool) -> bool:
    """Set robot.image to new_image_url and mark the matching photo as is_primary."""
    print(f"  -> New primary: {new_image_url[:90]}")
    if dry_run:
        print("  [dry-run] Would patch robot image and photo is_primary.")
        return True

    # 1. Patch the robot's image field
    try:
        client._patch(f"robots/robots/{robot_id}/", {"image": new_image_url})
    except Exception as e:
        print(f"  [ERROR] Failed to patch robot {robot_id} image: {e}")
        return False

    # 2. Find the matching photo and set is_primary=True; clear others
    matching_photo = next((p for p in photos if p.get("url") == new_image_url), None)
    if matching_photo:
        try:
            # Clear is_primary on all other photos first
            for p in photos:
                if p.get("is_primary") and p.get("id") != matching_photo["id"]:
                    client._patch(f"robots/robots/{robot_id}/photos/{p['id']}/", {"is_primary": False})
            # Set is_primary on the new primary
            client._patch(f"robots/robots/{robot_id}/photos/{matching_photo['id']}/", {"is_primary": True})
        except Exception as e:
            print(f"  [WARN] Could not update photo is_primary flags: {e}")
    else:
        print(f"  [INFO] New image URL not in existing gallery — robot.image patched but no photo promoted.")
    return True


def main():
    parser = argparse.ArgumentParser(description="Fix ROKAE primary images")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    args = parser.parse_args()

    client = ResearchApiClient()
    fetcher = WebFetcher()

    results = []
    fixed = 0
    skipped = 0
    failed = 0

    for robot_id, product_url in ROBOTS_TO_FIX.items():
        print(f"\n[{robot_id}] Fetching robot detail...")
        try:
            detail = client._get(f"robots/robots/{robot_id}/")
        except Exception as e:
            print(f"  [ERROR] Could not fetch robot {robot_id}: {e}")
            failed += 1
            results.append({"id": robot_id, "status": "error", "error": str(e)})
            continue

        name = detail.get("name", f"Robot {robot_id}")
        photos = detail.get("photos") or []
        current_primary = detail.get("image") or ""

        print(f"  Name: {name}")
        print(f"  Current primary: {current_primary[:80] if current_primary else '(none)'}")
        print(f"  Gallery photos: {len(photos)}")

        # Check if current primary is already good
        if current_primary and not is_bad_image(current_primary):
            print(f"  [SKIP] Current primary looks OK.")
            skipped += 1
            results.append({"id": robot_id, "name": name, "status": "skipped", "reason": "primary_ok"})
            continue

        # Check hardcoded override first
        if robot_id in IMAGE_OVERRIDES:
            new_image = IMAGE_OVERRIDES[robot_id]
            print(f"  [override] Using hardcoded image override.")
        else:
            # Try to find a good image from the existing gallery
            new_image = best_gallery_photo(photos)

        if new_image and robot_id not in IMAGE_OVERRIDES:
            print(f"  [gallery] Found usable gallery photo.")
        elif not new_image:
            print(f"  [scrape] No usable gallery photo — scraping {product_url}...")
            new_image = scrape_product_image(product_url, fetcher)

        if not new_image:
            print(f"  [FAIL] No suitable image found for robot {robot_id}.")
            failed += 1
            results.append({"id": robot_id, "name": name, "status": "failed", "reason": "no_image_found"})
            continue

        success = patch_primary_image(client, robot_id, new_image, photos, args.dry_run)
        if success:
            fixed += 1
            results.append({"id": robot_id, "name": name, "status": "fixed" if not args.dry_run else "dry_run", "new_image": new_image})
        else:
            failed += 1
            results.append({"id": robot_id, "name": name, "status": "failed", "reason": "patch_error"})

    print(f"\n{'='*60}")
    print(f"Summary: fixed={fixed}, skipped={skipped}, failed={failed}")
    if args.dry_run:
        print("(DRY RUN — no changes written)")

    out_path = os.path.join(os.path.dirname(__file__), "staging", "reports", "rokae_image_fix_results.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"Results saved to {out_path}")


if __name__ == "__main__":
    main()
