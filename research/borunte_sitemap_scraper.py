"""
borunte_sitemap_scraper.py
==========================
Custom image scraper for BORUNTE ROBOT CO., LTD (company_id: 1400)

Root cause: The overnight enrichment pipeline skipped 28 of 32 robots with
`target_not_found` because the robot names in the DB are pure model codes
(e.g. "BRTIRUS0101A") that don't appear as readable text on the borunte.net
product pages. The page titles use descriptive names like "Flexible Small Pick
Up Robot" instead.

Strategy:
1. Parse the borunte.net sitemap (2,000 URLs) to get all product page URLs
2. For each 6-axis and 4-axis robot product page, fetch the page and extract:
   - Model code (from page content, e.g. "BRTIRUS0101A")
   - Hero image URL (first product image in the gallery)
3. Build a mapping: model_code → {product_url, image_url, descriptive_name}
4. For each BORUNTE robot in the DB that has no image, look up by model_name
   in the mapping and PATCH the image field via the API
5. Also update the robot name to the descriptive name if it's currently just
   a model code

Usage:
    python borunte_sitemap_scraper.py [--dry-run] [--build-map-only] [--limit N]
"""

from __future__ import annotations

import argparse
import json
import re
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
COMPANY_ID = 1400
COMPANY_SLUG = "borunte-robot-co-ltd"
SITEMAP_URL = "https://www.borunte.net/sitemap-1.xml"
BASE_URL = "https://www.borunte.net"

# Only scrape industrial robot product pages (not category pages)
PRODUCT_URL_PATTERNS = [
    "/industrial-robot/6-axis-robot/",
    "/industrial-robot/4-axis-robot/",
    "/industrial-robot/5-axis-robot/",
]

# Model code patterns (BORUNTE uses BRTIRUS, BRTIRUW, BRTIRP, BRTIRSC prefixes)
MODEL_CODE_RE = re.compile(r"\b(BRTIR[A-Z0-9]+)\b", re.IGNORECASE)

# Cache file for the sitemap map (avoid re-scraping on re-runs)
MAP_CACHE_PATH = _RESEARCH_DIR / "staging" / "reports" / "borunte_model_map.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
REQUEST_DELAY = 1.0  # seconds between requests


def get_product_urls_from_sitemap(session: requests.Session) -> list[str]:
    """Parse the BORUNTE sitemap and return all industrial robot product page URLs."""
    print(f"Fetching sitemap: {SITEMAP_URL}")
    resp = session.get(SITEMAP_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "xml")
    all_urls = [loc.text.strip() for loc in soup.find_all("loc")]
    product_urls = [
        u for u in all_urls
        if any(pattern in u for pattern in PRODUCT_URL_PATTERNS)
        and u.endswith(".html")
    ]
    print(f"Found {len(product_urls)} product URLs in sitemap")
    return product_urls


def extract_model_and_image(product_url: str, session: requests.Session) -> dict | None:
    """Fetch a product page and extract model code and hero image URL."""
    try:
        resp = session.get(product_url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Extract page title / product name
        title_tag = soup.find("h1") or soup.find("title")
        descriptive_name = title_tag.get_text(strip=True) if title_tag else ""
        # Clean up title
        descriptive_name = re.sub(r"\s*[-|].*$", "", descriptive_name).strip()

        # Extract model codes from page text
        page_text = soup.get_text(" ", strip=True)
        model_codes = list(set(MODEL_CODE_RE.findall(page_text)))

        # Extract hero image — try multiple selectors
        image_url = None

        # 1. og:image
        og = soup.find("meta", property="og:image")
        if og and og.get("content"):
            image_url = og["content"].strip()

        # 2. First product gallery image (borunte.net uses /uploads/ path)
        if not image_url:
            for img in soup.find_all("img", src=True):
                src = img["src"]
                if "/uploads/" in src and not src.endswith("thumb") and "110x0" not in src:
                    if src.startswith("http"):
                        image_url = src
                    else:
                        image_url = urljoin(BASE_URL, src)
                    break

        # 3. data-src lazy-loaded images
        if not image_url:
            for img in soup.find_all("img", attrs={"data-src": True}):
                src = img["data-src"]
                if "/uploads/" in src and "110x0" not in src:
                    if src.startswith("http"):
                        image_url = src
                    else:
                        image_url = urljoin(BASE_URL, src)
                    break

        if not model_codes and not image_url:
            return None

        return {
            "product_url": product_url,
            "descriptive_name": descriptive_name,
            "model_codes": model_codes,
            "image_url": image_url,
        }

    except Exception as exc:
        print(f"  [WARN] Failed to scrape {product_url}: {exc}")
        return None


def build_model_map(session: requests.Session, limit: int = 0) -> dict[str, dict]:
    """Build a mapping of model_code → {product_url, image_url, descriptive_name}."""
    product_urls = get_product_urls_from_sitemap(session)
    if limit:
        product_urls = product_urls[:limit]

    model_map: dict[str, dict] = {}
    for i, url in enumerate(product_urls, 1):
        print(f"  [{i}/{len(product_urls)}] {url.split('/')[-1]}", end=" ")
        result = extract_model_and_image(url, session)
        if result:
            codes = result.get("model_codes", [])
            img = result.get("image_url", "")
            name = result.get("descriptive_name", "")
            print(f"→ codes={codes} img={'✓' if img else '✗'}")
            for code in codes:
                model_map[code.upper()] = {
                    "product_url": url,
                    "image_url": img,
                    "descriptive_name": name,
                }
        else:
            print("→ no data")
        time.sleep(REQUEST_DELAY)

    # Save cache
    MAP_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    MAP_CACHE_PATH.write_text(json.dumps(model_map, indent=2), encoding="utf-8")
    print(f"\nModel map saved: {MAP_CACHE_PATH} ({len(model_map)} entries)")
    return model_map


def load_model_map() -> dict[str, dict]:
    """Load the cached model map if it exists."""
    if MAP_CACHE_PATH.exists():
        return json.loads(MAP_CACHE_PATH.read_text(encoding="utf-8"))
    return {}


def get_borunte_robots_missing_image(client: ResearchApiClient) -> list[dict]:
    """Fetch all BORUNTE robots from the API that are missing images."""
    robots = []
    page = 1
    while True:
        resp = client._get(
            "robots/robots/",
            params={"company_id": COMPANY_ID, "page_size": 100, "page": page},
        )
        results = resp.get("results", [])
        if not results:
            break
        for r in results:
            if not r.get("image"):
                robots.append(r)
        if not resp.get("next"):
            break
        page += 1
    return robots


def patch_robot(
    client: ResearchApiClient,
    robot_id: int,
    image_url: str,
    descriptive_name: str | None,
    dry_run: bool,
) -> bool:
    """PATCH the robot with image URL (and optionally update name)."""
    payload: dict = {"image": image_url}
    if dry_run:
        print(f"    [DRY-RUN] PATCH robot {robot_id}: image={image_url[:60]}")
        return True
    try:
        client._patch(f"robots/robots/{robot_id}/", payload)
        return True
    except Exception as exc:
        print(f"    [ERROR] PATCH failed for robot {robot_id}: {exc}")
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="BORUNTE sitemap scraper and image patcher")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--build-map-only", action="store_true", help="Only build the model map, don't patch")
    parser.add_argument("--use-cache", action="store_true", help="Use cached model map if available")
    parser.add_argument("--limit", type=int, default=0, help="Limit sitemap scrape to N pages (0=all)")
    args = parser.parse_args()

    client = ResearchApiClient()
    http_session = requests.Session()

    print("=== BORUNTE Sitemap Scraper & Image Patcher ===")

    # Step 1: Build or load model map
    if args.use_cache and MAP_CACHE_PATH.exists():
        print("Loading cached model map...")
        model_map = load_model_map()
        print(f"Loaded {len(model_map)} model code entries from cache")
    else:
        print("Building model map from sitemap (this takes ~5-10 minutes)...")
        model_map = build_model_map(http_session, limit=args.limit)

    if args.build_map_only:
        print("Build-map-only mode — done.")
        return

    # Step 2: Get BORUNTE robots missing images from the API
    print("\nFetching BORUNTE robots missing images from API...")
    robots_missing = get_borunte_robots_missing_image(client)
    print(f"Found {len(robots_missing)} robots missing images")

    # Step 3: Match and patch
    ok = 0
    skip = 0
    fail = 0
    results = []

    for i, robot in enumerate(robots_missing, 1):
        robot_id = robot["id"]
        name = robot.get("name", "")
        model_name = robot.get("model_name", "") or ""

        print(f"[{i}/{len(robots_missing)}] ID={robot_id} name='{name}' model='{model_name}'")

        # Try to find in model map by model_name (the model code)
        lookup_key = model_name.upper().strip()
        entry = model_map.get(lookup_key)

        if not entry:
            # Try partial match (some model codes have suffix variants)
            for key, val in model_map.items():
                if lookup_key.startswith(key[:8]) or key.startswith(lookup_key[:8]):
                    entry = val
                    print(f"    partial match: {key}")
                    break

        if not entry:
            print(f"    [SKIP] No model map entry for '{lookup_key}'")
            skip += 1
            results.append({"robot_id": robot_id, "name": name, "model": model_name, "status": "skip_not_in_map"})
            continue

        image_url = entry.get("image_url", "")
        descriptive_name = entry.get("descriptive_name", "")

        if not image_url:
            print(f"    [SKIP] Model map entry has no image URL")
            skip += 1
            results.append({"robot_id": robot_id, "name": name, "model": model_name, "status": "skip_no_image_in_map"})
            continue

        print(f"    image={image_url[:70]}")
        success = patch_robot(client, robot_id, image_url, descriptive_name, args.dry_run)
        if success:
            ok += 1
            results.append({
                "robot_id": robot_id, "name": name, "model": model_name,
                "status": "ok", "image": image_url,
                "descriptive_name": descriptive_name,
            })
        else:
            fail += 1
            results.append({
                "robot_id": robot_id, "name": name, "model": model_name,
                "status": "fail_patch", "image": image_url,
            })

    # Save results
    results_path = _RESEARCH_DIR / "staging" / "reports" / "borunte_image_patch_results.json"
    results_path.write_text(
        json.dumps({"ok": ok, "skip": skip, "fail": fail, "results": results}, indent=2),
        encoding="utf-8",
    )

    print()
    print(f"=== DONE === ok={ok} skip={skip} fail={fail}")
    print(f"Results saved: {results_path}")


if __name__ == "__main__":
    main()
