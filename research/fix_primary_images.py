"""
fix_primary_images.py
---------------------
Generalized script to fix bad primary images for any company's robots in the
Robot AI Geek database.

Strategy (in priority order):
  1. IMAGE_OVERRIDES dict — hardcoded per-robot URL for edge cases.
  2. Gallery promotion — find the best non-bad photo in the robot's existing
     gallery and promote it to primary.
  3. Page scrape — fetch the robot's product URL and extract the first clean
     product image found on the page.
  4. FAIL — log the robot as unresolvable for manual review.

What counts as a "bad" image is controlled by BAD_URL_PATTERNS below.
Add company-specific patterns when you encounter new bad image types.

Usage:
    # Dry run — preview changes without writing
    python fix_primary_images.py --company-id 1416 --dry-run

    # Apply fixes for a whole company
    python fix_primary_images.py --company-id 1416

    # Apply fixes for specific robot IDs only
    python fix_primary_images.py --robot-ids 2222 2226 2231

    # Apply fixes and prefer page scraping over gallery (useful when gallery
    # photos are also bad)
    python fix_primary_images.py --company-id 1416 --prefer-scrape

    # Add a custom bad URL pattern on the fly
    python fix_primary_images.py --company-id 1234 --bad-pattern "logo_banner"
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
# Known bad image URL patterns (applies to ALL companies)
# Add company-specific patterns via --bad-pattern CLI arg or IMAGE_OVERRIDES.
# ---------------------------------------------------------------------------
DEFAULT_BAD_URL_PATTERNS = [
    # Generic bad patterns (apply to all companies)
    r"indexbanner",             # site-wide banner images
    r"index_plan_bg",           # background graphic
    r"GongAnBeiAnTuBiao",       # Chinese government filing icon
    r"linkedin_code",           # QR code for LinkedIn
    r"linkedin",                # social media icon
    r"/pc/img/",                # generic site chrome
    r"qr[_\-]?code",            # QR codes
    r"footer",                  # footer images
    r"header[_\-]bg",           # header backgrounds
    r"banner[_\-]bg",           # banner backgrounds
    r"logo\.png",               # generic logo files
    r"logo\.jpg",
    r"logo\.svg",
    # RobotAIGeek CDN: "original" copies are the raw imported images (often banners)
    r"robots/original/robot-\d+",
    # ROKAE-specific
    r"rokae\+",
    r"ROKAE\+",
    r"indexbanner_img",
]

# ---------------------------------------------------------------------------
# Per-robot hardcoded image overrides.
# Add entries here when scraping fails and you've manually found a good image.
# Format: {robot_id: "https://..."}
# ---------------------------------------------------------------------------
IMAGE_OVERRIDES: dict[int, str] = {
    # ROKAE CR20-17/2.0C-5 (ID 3386): gallery only had website chrome.
    # Manually sourced from official EN product page 2024-07-22.
    3386: "https://www.rokae.com/public/uploads/20240307/7ee6bc415e2a727e516185fe41d5cad7.png",
    # ROKAE CR7-7/0.98C, CR12-12/1.4C, CR20-20/1.8C (IDs 3382-3384): no gallery photos,
    # all point to the same xMateCR page. Using the same clean product shot as 3386.
    3382: "https://www.rokae.com/public/uploads/20240307/7ee6bc415e2a727e516185fe41d5cad7.png",
    3383: "https://www.rokae.com/public/uploads/20240307/7ee6bc415e2a727e516185fe41d5cad7.png",
    3384: "https://www.rokae.com/public/uploads/20240307/7ee6bc415e2a727e516185fe41d5cad7.png",
    # ROKAE NB25 Series (ID 3392): hero lineup shot from official EN product page.
    3392: "https://www.rokae.com/public/uploads/20230214/eef47aff499f491c9f9292002b9c48e7.jpg",
    # ROKAE NB25h Series (ID 3393): hero shot from official EN product page.
    3393: "https://www.rokae.com/public/uploads/20241210/7a6fb13f150c686dffea0b23093ee499.png",
    # ROKAE NB80 Series (ID 3394): hero shot from official EN product page.
    3394: "https://www.rokae.com/public/uploads/20241211/8486d289d0ef4b81a51c55c1bca9ac69.png",
}


def build_bad_url_re(extra_patterns: list[str] | None = None) -> re.Pattern:
    patterns = DEFAULT_BAD_URL_PATTERNS[:]
    if extra_patterns:
        patterns.extend(extra_patterns)
    return re.compile("|".join(patterns), re.IGNORECASE)


def is_bad_image(url: str, bad_re: re.Pattern) -> bool:
    return bool(bad_re.search(url))


def best_gallery_photo(photos: list[dict], bad_re: re.Pattern) -> Optional[str]:
    """Return the URL of the best non-bad gallery photo, or None.

    Preference order:
      1. Non-primary photos that are not bad (sorted by order ascending)
      2. Any photo that is not bad (including current primary)
    """
    non_primary = [
        p for p in photos
        if not p.get("is_primary") and not is_bad_image(p.get("url", ""), bad_re)
    ]
    if non_primary:
        non_primary.sort(key=lambda p: p.get("order", 9999))
        return non_primary[0]["url"]

    any_good = [p for p in photos if not is_bad_image(p.get("url", ""), bad_re)]
    if any_good:
        any_good.sort(key=lambda p: p.get("order", 9999))
        return any_good[0]["url"]

    return None


def scrape_product_image(product_url: str, fetcher: WebFetcher, bad_re: re.Pattern) -> Optional[str]:
    """Fetch the robot's product page and return the first clean product image URL."""
    if not product_url:
        return None
    try:
        html = fetcher.get(product_url)
        if not html:
            return None
        page = parse_page(html, url=product_url)

        # parse_page may return a string or an object depending on the page type
        if isinstance(page, str):
            # Fallback: extract image URLs from raw HTML using regex
            img_urls = re.findall(r'(?:src|href)=["\']([^"\'>]+\.(?:jpg|jpeg|png|webp))["\']', page, re.IGNORECASE)
            images = img_urls
        else:
            images = getattr(page, 'images', None) or []

        # First pass: prefer images from the same domain's upload/static paths
        for img in images:
            url = img if isinstance(img, str) else img.get("url", "") if hasattr(img, 'get') else str(img)
            if not url or is_bad_image(url, bad_re):
                continue
            if any(kw in url for kw in ["/uploads/", "/static/", "/product/", "/products/"]):
                return url

        # Second pass: any non-bad image
        for img in images:
            url = img if isinstance(img, str) else img.get("url", "") if hasattr(img, 'get') else str(img)
            if url and not is_bad_image(url, bad_re):
                return url

    except Exception as e:
        print(f"  [scrape error] {product_url}: {e}")
    return None


def patch_primary_image(
    client: ResearchApiClient,
    robot_id: int,
    new_image_url: str,
    photos: list[dict],
    dry_run: bool,
) -> bool:
    """Patch robot.image and optionally promote the matching RobotPhoto record."""
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

    # 2. Promote the matching RobotPhoto record (best-effort; 404 is non-fatal)
    matching_photo = next((p for p in photos if p.get("url") == new_image_url), None)
    if matching_photo:
        try:
            for p in photos:
                if p.get("is_primary") and p.get("id") != matching_photo["id"]:
                    client._patch(
                        f"robots/robots/{robot_id}/photos/{p['id']}/",
                        {"is_primary": False},
                    )
            client._patch(
                f"robots/robots/{robot_id}/photos/{matching_photo['id']}/",
                {"is_primary": True},
            )
        except Exception as e:
            print(f"  [WARN] Could not update photo is_primary flags: {e}")
    else:
        print("  [INFO] New image URL not in existing gallery — robot.image patched only.")

    return True


def fetch_robots_for_company(client: ResearchApiClient, company_id: int) -> list[dict]:
    """Fetch all robots for a company using the correct API method."""
    try:
        return client.list_robots_for_company(company_id)
    except Exception as e:
        print(f"[ERROR] Failed to fetch robots for company {company_id}: {e}")
        return []


def main():
    parser = argparse.ArgumentParser(
        description="Fix bad primary images for any company's robots."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--company-id",
        type=int,
        help="Fix all robots for this company ID.",
    )
    group.add_argument(
        "--robot-ids",
        type=int,
        nargs="+",
        help="Fix only these specific robot IDs.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing to the database.",
    )
    parser.add_argument(
        "--prefer-scrape",
        action="store_true",
        help="Try page scraping before gallery promotion (useful when gallery photos are also bad).",
    )
    parser.add_argument(
        "--bad-pattern",
        action="append",
        dest="bad_patterns",
        metavar="PATTERN",
        help="Additional regex pattern to treat as a bad image URL. Can be repeated.",
    )
    args = parser.parse_args()

    bad_re = build_bad_url_re(args.bad_patterns)
    client = ResearchApiClient()
    fetcher = WebFetcher()

    # Build the list of robots to process
    if args.robot_ids:
        robots = []
        for rid in args.robot_ids:
            try:
                detail = client._get(f"robots/robots/{rid}/")
                robots.append(detail)
            except Exception as e:
                print(f"[ERROR] Could not fetch robot {rid}: {e}")
    else:
        print(f"Fetching robots for company {args.company_id}...")
        robots = fetch_robots_for_company(client, args.company_id)
        print(f"Found {len(robots)} robots.")

    results = []
    fixed = skipped = failed = 0

    for robot in robots:
        robot_id = robot.get("id")
        name = robot.get("name", f"Robot {robot_id}")
        current_primary = robot.get("image") or ""
        photos = robot.get("photos") or []

        print(f"\n[{robot_id}] {name}")
        print(f"  Primary: {current_primary[:80] if current_primary else '(none)'}")
        print(f"  Gallery: {len(photos)} photos")

        # Skip if the current primary is already good
        if current_primary and not is_bad_image(current_primary, bad_re):
            print("  [SKIP] Current primary looks OK.")
            skipped += 1
            results.append({"id": robot_id, "name": name, "status": "skipped", "reason": "primary_ok"})
            continue

        new_image: Optional[str] = None
        source = "unknown"

        # Priority 1: hardcoded override
        if robot_id in IMAGE_OVERRIDES:
            new_image = IMAGE_OVERRIDES[robot_id]
            source = "override"
            print("  [override] Using hardcoded image override.")

        # Priority 2 / 3: gallery vs scrape (order depends on --prefer-scrape)
        elif args.prefer_scrape:
            product_url = robot.get("url") or ""
            print(f"  [scrape] Scraping {product_url[:70]}...")
            new_image = scrape_product_image(product_url, fetcher, bad_re)
            source = "scrape"
            if not new_image:
                new_image = best_gallery_photo(photos, bad_re)
                source = "gallery"
                if new_image:
                    print("  [gallery] Scrape failed — using gallery photo.")
        else:
            new_image = best_gallery_photo(photos, bad_re)
            source = "gallery"
            if new_image:
                print("  [gallery] Found usable gallery photo.")
            else:
                product_url = robot.get("url") or ""
                print(f"  [scrape] No gallery photo — scraping {product_url[:70]}...")
                new_image = scrape_product_image(product_url, fetcher, bad_re)
                source = "scrape"

        if not new_image:
            print(f"  [FAIL] No suitable image found.")
            failed += 1
            results.append({"id": robot_id, "name": name, "status": "failed", "reason": "no_image_found"})
            continue

        success = patch_primary_image(client, robot_id, new_image, photos, args.dry_run)
        status = ("fixed" if not args.dry_run else "dry_run") if success else "failed"
        if success:
            fixed += 1
        else:
            failed += 1
        results.append({"id": robot_id, "name": name, "status": status, "source": source, "new_image": new_image})

    # Summary
    print(f"\n{'=' * 60}")
    print(f"Summary: fixed={fixed}, skipped={skipped}, failed={failed}")
    if args.dry_run:
        print("(DRY RUN — no changes written)")

    # Save results
    company_tag = f"company_{args.company_id}" if args.company_id else "robots_" + "_".join(str(r) for r in (args.robot_ids or []))
    out_path = os.path.join(
        os.path.dirname(__file__), "staging", "reports", f"image_fix_{company_tag}.json"
    )
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"Results saved to {out_path}")


if __name__ == "__main__":
    main()
