"""Replace SIASUN loading.png placeholders with real product heroes from en.siasun.com."""

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

COMPANY_ID = 1424
COMPANY_SLUG = "siasun-robot-automation-co-ltd"
COMPANY_NAME = "SIASUN Robot & Automation Co., Ltd."

LOADING_BYTES = 6776
SKIP_URL_PARTS = ("loading", "loadings", "logo", "150x150", "shoujilogo")
# Shared footer/sidebar assets repeated on every product page.
BLOCKED_GLOBAL_FILES = {
    "未标题-2-1.png",
    "1-9.png",
    "3-16.png",
    "3-14.png",
    "1-13.png",
    "3-10.png",
    "4-6.png",
    "1.png",
    "2.png",
    "3.png",
    "4.png",
}
IMAGE_RE = re.compile(
    r"https://en\.siasun\.com/wp-content/uploads/[^\"'\s>]+\.(?:jpg|jpeg|png|webp)",
    re.I,
)


def _model_keys(name: str) -> list[str]:
    """Build fuzzy match tokens from robot model name e.g. SN7B-7/0.90."""
    raw = name.strip().upper()
    keys = [raw.lower()]
    keys.append(raw.replace("/", "-").lower())
    keys.append(re.sub(r"[^a-z0-9]", "", raw.lower()))
    # SN10A-10/1.15 -> sn10a-10-115 style used on site filenames
    m = re.match(r"^([A-Z]+\d*[A-Z]?)-(\d+)/(\d+\.?\d*)$", raw)
    if m:
        prefix, a, b = m.groups()
        b_compact = b.replace(".", "")
        keys.append(f"{prefix.lower()}-{a}-{b_compact}")
        keys.append(f"{prefix.lower()}{a}{b_compact}")
    return list(dict.fromkeys(keys))


def score_image(url: str, model_name: str) -> int:
    low = url.lower()
    filename = low.rsplit("/", 1)[-1]
    if filename in {b.lower() for b in BLOCKED_GLOBAL_FILES}:
        return -1000
    if any(x in low for x in SKIP_URL_PARTS):
        return -1000
    compact = re.sub(r"[^a-z0-9]", "", low)
    score = 0
    for key in _model_keys(model_name):
        k = re.sub(r"[^a-z0-9]", "", key)
        if k and k in compact:
            score += 80
            break
    prefix = model_name.split("/")[0].lower()
    if prefix.replace("/", "-") in low:
        score += 40
    if low.endswith("-1.png") or low.endswith("-1.jpg") or low.endswith("-1.webp"):
        score += 10
    return score


def extract_candidates(page_url: str) -> tuple[list[str], list[str]]:
    resp = requests.get(
        page_url,
        headers={"User-Agent": "Mozilla/5.0", "Accept": "text/html"},
        timeout=30,
        allow_redirects=True,
    )
    resp.raise_for_status()
    data_src = [
        u.split("?")[0].strip()
        for u in re.findall(r'data-src="([^"]+)"', resp.text)
        if u.startswith("https://en.siasun.com/wp-content/uploads/")
    ]
    inline = [
        u.split("?")[0].strip()
        for u in IMAGE_RE.findall(resp.text)
    ]
    og = re.search(r'property="og:image" content="([^"]+)"', resp.text)
    extras: list[str] = []
    if og:
        extras.append(og.group(1).split("?")[0])
    extras.extend(inline)
    ordered = list(dict.fromkeys(data_src))
    all_candidates = list(dict.fromkeys([*ordered, *extras]))
    return ordered, all_candidates


def verify_image_url(url: str) -> bool:
    try:
        resp = requests.get(
            url,
            timeout=30,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://en.siasun.com/",
            },
            stream=True,
        )
        resp.raise_for_status()
        size = len(resp.content)
        if size <= LOADING_BYTES + 100:
            return False
        ct = resp.headers.get("content-type", "")
        return ct.startswith("image/")
    except requests.RequestException:
        return False


def pick_image(model_name: str, page_url: str) -> str:
    data_src_ordered, candidates = extract_candidates(page_url)
    verified = [u for u in candidates if score_image(u, model_name) >= 0 and verify_image_url(u)]

    strong = [u for u in verified if score_image(u, model_name) >= 40]
    if strong:
        return sorted(strong, key=lambda u: score_image(u, model_name), reverse=True)[0]

    for u in data_src_ordered:
        if u in verified:
            return u

    return verified[0] if verified else ""


def is_loading_placeholder(robot: dict) -> bool:
    img = (robot.get("s3_image") or robot.get("image") or "").strip()
    if not img.startswith("http"):
        return True
    try:
        resp = requests.get(
            img,
            timeout=20,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        return len(resp.content) <= LOADING_BYTES + 100
    except requests.RequestException:
        return True


def build_staging_row(robot: dict, image: str) -> dict:
    url = (robot.get("url") or "").strip()
    country = robot.get("manufacturer_country_ref") or {}
    return {
        "name": robot["name"],
        "company_slug": COMPANY_SLUG,
        "company_name": COMPANY_NAME,
        "manufacturer_country_code": (country.get("code") or "CN").upper(),
        "description": robot.get("description") or robot.get("purpose") or robot["name"],
        "purpose": robot.get("purpose") or "",
        "features": robot.get("features") or "",
        "url": url,
        "image": image,
        "images": [image] if image else [],
        "sources": [{"url": url or "https://en.siasun.com/", "type": "website"}],
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
    parser = argparse.ArgumentParser(description="Fix SIASUN loading.png robot images")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--copy-media", action="store_true")
    parser.add_argument("--created-by-id", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=3)
    args = parser.parse_args()

    client = ResearchApiClient()
    robots = client.list_robots_for_company(COMPANY_ID)
    targets = [r for r in robots if is_loading_placeholder(r)]
    print(f"loading-placeholder targets: {len(targets)} / {len(robots)}")

    plan: list[dict] = []
    for robot in targets:
        page_url = (robot.get("url") or "").strip()
        image = pick_image(robot["name"], page_url) if page_url else ""
        plan.append({
            "id": robot["id"],
            "name": robot["name"],
            "url": page_url,
            "old_image": robot.get("image"),
            "new_image": image,
        })
        status = "OK" if image else "MISSING"
        print(f"{robot['name']}: {status}")
        if image:
            print(f"  -> {image}")

    preview = _RESEARCH_DIR / "staging" / "reports" / "siasun-image-fix-preview.json"
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    missing = [p for p in plan if not p["new_image"]]
    if missing:
        print(f"ERROR: no replacement for {len(missing)} robots", file=sys.stderr)
        for p in missing:
            print(f"  - {p['name']}", file=sys.stderr)
        return 1
    if not args.apply:
        print(f"Preview: {preview}. Re-run with --apply --copy-media")
        return 0

    robot_by_id = {r["id"]: r for r in targets}
    tmp = Path(tempfile.mkdtemp(prefix="siasun-images-"))
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
    }, indent=2))

    if args.copy_media and result.get("ok"):
        ok, fail = trigger_copy_media([p["id"] for p in plan])
        print(f"copy-media ok={ok} fail={fail}")

    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
