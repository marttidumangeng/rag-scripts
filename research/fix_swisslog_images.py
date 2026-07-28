"""Refresh broken Swisslog robot hero images from current product pages."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

import requests

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient
from import_staging import import_staging, resolve_created_by_id
from robot_auto_research import slugify_robot_name

COMPANY_ID = 372
COMPANY_SLUG = "swisslog-holding-ag"
COMPANY_NAME = "Swisslog Holding AG"

SKIP_IN_URL = ("logo", "icon", "footer", "social", "career", "newsroom", "portrait-pictures")
IMAGE_HOSTS = ("www.swisslog.com", "www.swisslog-healthcare.com")

# Healthcare product pages 404 after relaunch; use category hero until dedicated pages return.
MANUAL_IMAGES = {
    "PillPick": "https://www.swisslog-healthcare.com/-/media/swisslog-healthcare/images/products-and-services/pharmacy-automation/pharmacy-automation-image.jpg",
    "BoxPicker": "https://www.swisslog-healthcare.com/-/media/swisslog-healthcare/images/products-and-services/pharmacy-automation/pharmacy-automation-image.jpg",
}


def _product_slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def score_image(url: str, product_name: str) -> int:
    low = url.lower()
    slug = _product_slug(product_name)
    compact = low.replace("-", "").replace("_", "")
    score = 0
    if slug and slug in compact:
        score += 50
    if "swisslog-product" in low or "product-picture" in low or "web_image-swisslog" in low:
        score += 20
    if "relaunch-2024/media-folder/close" in low:
        score -= 100
    if "case-study" in low and slug not in compact:
        score -= 15
    if "healthcare" in low or "pharmacy" in low:
        score += 5
    return score


def extract_image_candidates(page_url: str) -> list[str]:
    if not page_url:
        return []
    resp = requests.get(
        page_url,
        headers={"User-Agent": "Mozilla/5.0", "Accept": "text/html"},
        timeout=30,
        allow_redirects=True,
    )
    pattern = re.compile(
        r"https://(?:www\.swisslog\.com|www\.swisslog-healthcare\.com)[^\"'\s>]+\.(?:jpg|jpeg|png|webp)",
        re.I,
    )
    candidates = sorted(set(pattern.findall(resp.text)))
    ok: list[str] = []
    for url in candidates:
        low = url.lower()
        if any(x in low for x in SKIP_IN_URL):
            continue
        clean = url.split("?")[0]
        try:
            head = requests.head(clean, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            if head.status_code == 200:
                ok.append(clean)
        except requests.RequestException:
            pass
    return ok


def pick_image(product_name: str, page_url: str) -> str:
    if product_name in MANUAL_IMAGES:
        return MANUAL_IMAGES[product_name]
    candidates = extract_image_candidates(page_url)
    if not candidates:
        return ""
    ranked = sorted(candidates, key=lambda u: score_image(u, product_name), reverse=True)
    best = ranked[0]
    if score_image(best, product_name) < 0 and len(ranked) > 1:
        return ranked[1]
    return best


def build_staging_row(robot: dict, image: str) -> dict:
    url = (robot.get("url") or "").strip()
    country = robot.get("manufacturer_country_ref") or {}
    return {
        "name": robot["name"],
        "company_slug": COMPANY_SLUG,
        "company_name": COMPANY_NAME,
        "manufacturer_country_code": (country.get("code") or "CH").upper(),
        "description": robot.get("description") or robot.get("purpose") or robot["name"],
        "purpose": robot.get("purpose") or "",
        "features": robot.get("features") or "",
        "url": url,
        "image": image,
        "images": [image] if image else [],
        "sources": [{"url": url or "https://www.swisslog.com/en-us", "type": "website"}],
    }


def trigger_copy_media(robot_ids: list[int]) -> tuple[int, int]:
    secret = os.environ.get("INTERNAL_API_SECRET", "").strip()
    env_file = _RESEARCH_DIR.parents[1] / "robotaigeek-server" / ".env"
    if not secret and env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                secret = line.split("=", 1)[1].strip()
    api = os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/").replace("/api/v1", "")
    if not secret or not api:
        return 0, len(robot_ids)

    ok = fail = 0
    for rid in robot_ids:
        url = f"{api}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/"
        try:
            resp = requests.post(url, headers={"X-Internal-Secret": secret}, timeout=120)
            if resp.ok:
                ok += 1
            else:
                fail += 1
                print(f"copy-media fail {rid}: HTTP {resp.status_code}")
        except requests.RequestException as exc:
            fail += 1
            print(f"copy-media fail {rid}: {exc}")
        time.sleep(0.15)
    return ok, fail


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix Swisslog robot images on prod")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--copy-media", action="store_true", help="Run copy-media after import")
    parser.add_argument("--created-by-id", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=3)
    args = parser.parse_args()

    client = ResearchApiClient()
    robots = client.list_robots_for_company(COMPANY_ID)
    targets = [r for r in robots if (r.get("image") or "").startswith("https://www.swisslog.com")]
    print(f"broken hotlink targets: {len(targets)}")

    plan: list[dict] = []
    for robot in targets:
        image = pick_image(robot["name"], robot.get("url") or "")
        plan.append({
            "id": robot["id"],
            "name": robot["name"],
            "old_image": robot.get("image"),
            "new_image": image,
        })
        print(f"{robot['name']}: {'OK' if image else 'MISSING'}")

    preview = _RESEARCH_DIR / "staging" / "reports" / "swisslog-image-fix-preview.json"
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    missing = [p for p in plan if not p["new_image"]]
    if missing:
        print(f"ERROR: no replacement image for {len(missing)} robots", file=sys.stderr)
        return 1
    if not args.apply:
        print(f"Preview written to {preview}. Re-run with --apply --copy-media")
        return 0

    tmp = Path(tempfile.mkdtemp(prefix="swisslog-images-"))
    robot_by_id = {r["id"]: r for r in targets}
    for item in plan:
        row = build_staging_row(robot_by_id[item["id"]], item["new_image"])
        fname = slugify_robot_name(row["name"])
        (tmp / f"{fname}.json").write_text(json.dumps(row, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    result = import_staging(
        tmp,
        patch=False,
        force_overwrite=True,
        status="pending_review",
        dry_run=False,
        created_by_id=resolve_created_by_id(args.created_by_id),
        replace_media=True,
        batch_size=args.batch_size,
        skip_company_update=True,
    )
    print(json.dumps({
        "ok": result.get("ok"),
        "updated_count": result.get("updated_count"),
        "error_count": result.get("error_count"),
        "warnings": (result.get("warnings") or [])[:5],
    }, indent=2))

    if args.copy_media and result.get("ok"):
        ids = [p["id"] for p in plan]
        ok, fail = trigger_copy_media(ids)
        print(f"copy-media ok={ok} fail={fail}")

    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
