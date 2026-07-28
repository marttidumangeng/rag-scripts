"""Scrape iRobot product pages and backfill photos, features, specs, and videos."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient
from import_staging import import_staging, resolve_created_by_id
from robot_auto_research import (
    _infer_movement,
    _infer_sub_category,
    search_youtube_videos_for_robot,
    slugify_robot_name,
)
from youtube_metadata import enrich_video_list, fetch_youtube_metadata

COMPANY_ID = 342
COMPANY_SLUG = "irobot-now-part-of-amazon-robotics"
COMPANY_NAME = "iRobot (part of Amazon Robotics)"
BASE = "https://www.irobot.com"

SKIP_STATUSES = {"published"}
SKIP_URL_PARTS = ("logo", "icon", "sprite", "footer", "social", "favicon")

# Robots whose stored URL is a shop anchor, wrong SKU, or discontinued PDP.
MANUAL_URL_BY_ID: dict[int, str] = {
    3704: f"{BASE}/en_US/roomba-combo-i5-robot-vacuum-and-mop/G284020.html",
    3702: f"{BASE}/en_US/roomba-combo-10-max-robot-with-autowash-dock/X085020.html",
    3703: f"{BASE}/en_US/roomba-combo-j9plus-auto-fill-robot-vacuum-and-mop/C975020.html",
    3697: f"{BASE}/en_US/roomba-max-705-combo-robot-plus-autowash-dock/X185020.html",
    3698: f"{BASE}/en_US/roomba-plus-505-combo-robot-plus-autowash-dock/N185020.html",
    3699: f"{BASE}/en_US/roomba-plus-405-combo-robot-plus-autowash-dock/G185020.html",
    3700: f"{BASE}/en_US/roomba-205-dustcompactor-combo-robot/L124020.html",
    3701: f"{BASE}/en_US/roomba-105-combo-robot/Y314020.html",
    # j9 (non-plus) PDP is discontinued; closest live product page is j9+.
    2031: f"{BASE}/en_US/roomba-j9plus-self-emptying-robot-vacuum/J955020.html",
}

FEATURE_SKIP = (
    "answer a few simple",
    "cookie",
    "sign in",
    "subscribe",
    "owner's guide",
    "click here",
    "add to cart",
)


def _normalize_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    if url.startswith("/"):
        return urljoin(BASE, url)
    if url.startswith("http"):
        return url
    return urljoin(BASE + "/", url)


def _extract_sku(url: str) -> str:
    m = re.search(r"/([A-Z][0-9]{5,6})\.html", url or "", re.I)
    return m.group(1).upper() if m else ""


def resolve_product_url(robot: dict) -> str:
    rid = int(robot["id"])
    if rid in MANUAL_URL_BY_ID:
        return MANUAL_URL_BY_ID[rid]

    url = _normalize_url(robot.get("url") or "")
    if not url or "irobot.com" not in url.lower():
        return ""

    low = url.lower()
    if "shop/combo.html" in low or low.rstrip("/") in (
        "https://www.irobot.com",
        "https://www.irobot.com/",
        "https://www.irobot.com/en_us",
        "https://www.irobot.com/en_us/",
    ):
        return ""

    if re.search(r"/[A-Z][0-9]{5,6}\.html", url, re.I):
        return url
    return ""


def fetch_pdp(url: str) -> tuple[int, str]:
    resp = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0", "Accept": "text/html"},
        timeout=30,
        allow_redirects=True,
    )
    return resp.status_code, resp.text


def _parse_weight_lbs(val: str) -> float | None:
    val = re.sub(r"&nbsp;", " ", val or "")
    m = re.search(r"([\d.]+)\s*(?:lbs?\.?|pounds?)", val, re.I)
    if m:
        return float(m.group(1))
    m = re.search(r"^([\d.]+)$", val.strip())
    if m:
        return float(m.group(1))
    return None


def _parse_dims(val: str) -> dict[str, Any]:
    val = re.sub(r"&nbsp;", " ", val or "").replace("×", "x")
    out: dict[str, Any] = {}

    m = re.search(r"([\d.]+)\s*x\s*([\d.]+)\s*x\s*([\d.]+)", val, re.I)
    if m:
        w_in, d_in, h_in = (float(x) for x in m.groups())
        w_mm, d_mm, h_mm = (round(x * 25.4, 1) for x in (w_in, d_in, h_in))
        out.update(
            width_mm=w_mm,
            length_mm=d_mm,
            height_mm=h_mm,
            width=f'{w_in}"',
            length=f'{d_in}"',
            height=f'{h_in}"',
            dimensions_mm=f"{round(w_mm)}x{round(d_mm)}x{round(h_mm)}",
        )
        return out

    m = re.search(
        r"([\d.]+)\s*inches?\s*wide\s*x\s*([\d.]+)\s*inches?\s*high(?:\s*x\s*([\d.]+)\s*inches?\s*deep)?",
        val,
        re.I,
    )
    if m:
        w_in, h_in = float(m.group(1)), float(m.group(2))
        d_in = float(m.group(3)) if m.group(3) else w_in
        w_mm, h_mm, d_mm = (round(x * 25.4, 1) for x in (w_in, h_in, d_in))
        out.update(
            width_mm=w_mm,
            height_mm=h_mm,
            length_mm=d_mm,
            width=f'{w_in}"',
            height=f'{h_in}"',
            length=f'{d_in}"',
            dimensions_mm=f"{round(w_mm)}x{round(d_mm)}x{round(h_mm)}",
        )
        return out

    m = re.search(
        r"([\d.]+)\s*inches?\s*width\s*x\s*([\d.]+)\s*inches?\s*high",
        val,
        re.I,
    )
    if m:
        w_in, h_in = float(m.group(1)), float(m.group(2))
        w_mm, h_mm = round(w_in * 25.4, 1), round(h_in * 25.4, 1)
        out.update(
            width_mm=w_mm,
            height_mm=h_mm,
            width=f'{w_in}"',
            height=f'{h_in}"',
            dimensions_mm=f"{round(w_mm)}x{round(w_mm)}x{round(h_mm)}",
        )
    return out


def _apply_spec_field(specs: dict[str, Any], label: str, val: str) -> None:
    low = label.lower().strip().rstrip(":")
    val = re.sub(r"\s+", " ", val.replace("&reg;", "").strip())
    if not val:
        return

    if "robot weight" in low or (low == "weight" and "dock" not in low and "clean base" not in low):
        lbs = _parse_weight_lbs(val)
        if lbs:
            specs["weight_kg"] = round(lbs * 0.453592, 2)
            specs["weight"] = f"{lbs} lbs"
    elif "robot dimension" in low or (
        "dimension" in low and "dock" not in low and "retail" not in low and "box" not in low
    ):
        specs.update(_parse_dims(val))
    elif "battery" in low and "type" in low:
        specs["battery_capacity"] = val
    elif "runtime" in low or "run time" in low:
        specs["runtime"] = val
        m = re.search(r"([\d.]+)", val)
        if m:
            specs["runtime_minutes"] = int(float(m.group(1)) * 60)


def parse_specs(html: str) -> dict[str, Any]:
    specs: dict[str, Any] = {}
    if not html:
        return specs

    for label, val in re.findall(
        r"<li><strong>([^<]+)</strong>\s*(?:\([^)]+\))?:\s*([^<]+)</li>",
        html,
        re.I,
    ):
        _apply_spec_field(specs, label, val)

    for label, val in re.findall(
        r"<(?:strong|b)>([^<]+?):?</(?:strong|b)>\s*(?:&nbsp;)*([^<]+?)(?:<br|</p)",
        html,
        re.I,
    ):
        _apply_spec_field(specs, label, val)

    soup = BeautifulSoup(html, "html.parser")
    spec_div = soup.select_one("#collapsible-specs, .specifications")
    if spec_div:
        block = spec_div.get_text("\n", strip=True)
        for line in block.split("\n"):
            if ":" not in line:
                continue
            label, val = line.split(":", 1)
            _apply_spec_field(specs, label, val)

    return specs


def _clean_feature_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()
    if len(text) < 25:
        return ""
    low = text.lower()
    if any(x in low for x in FEATURE_SKIP):
        return ""
    return text


def parse_features(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    bullets: list[str] = []

    meta = soup.find("meta", attrs={"name": "description"})
    if meta and meta.get("content"):
        desc = _clean_feature_text(meta["content"])
        if desc:
            bullets.append(desc)

    for h in soup.select("h2, h3"):
        title = h.get_text(" ", strip=True)
        if not (5 < len(title) < 90):
            continue
        if any(x in title.lower() for x in ("specification", "in the box", "review", "faq", "compare")):
            continue
        nxt = h.find_next(["p", "li"])
        if not nxt:
            continue
        body = _clean_feature_text(nxt.get_text(" ", strip=True))
        if not body:
            continue
        bullets.append(f"{title}: {body}")
        if len(bullets) >= 5:
            break

    if len(bullets) <= 1:
        for el in soup.select("[class*='highlight']"):
            text = _clean_feature_text(el.get_text(" ", strip=True))
            if text and len(text) > 60:
                bullets.append(text)
                break

    return " ".join(dict.fromkeys(bullets))[:1500]


def score_image(url: str, sku: str) -> int:
    low = url.lower()
    if any(x in low for x in SKIP_URL_PARTS):
        return -100
    score = 0
    if "pdp-images" in low:
        score += 25
    if sku and sku.lower() in low:
        score += 80
    elif sku and sku[:5].lower() in low:
        score += 40
    if low.endswith((".jpg", ".jpeg", ".png", ".webp")):
        score += 5
    return score


def parse_images(html: str, sku: str) -> tuple[str, list[str]]:
    if not html:
        return "", []
    raw = re.findall(r"https://www\.irobot\.com/dw/image/v2/[^\"'\s>]+", html, re.I)
    scored: list[tuple[int, str]] = []
    for url in raw:
        clean = url.split("?")[0]
        scored.append((score_image(clean, sku), clean))
    scored.sort(key=lambda x: (-x[0], x[1]))
    ordered = list(dict.fromkeys(u for s, u in scored if s > 0))
    if not ordered:
        ordered = list(dict.fromkeys(u for s, u in scored if s >= 20))
    if not ordered:
        return "", []
    return ordered[0], ordered[1:6]


def parse_videos(html: str) -> list[str]:
    if not html:
        return []
    ids = re.findall(r'"videoId":"([\w-]{11})"', html)
    urls = [f"https://www.youtube.com/watch?v={vid}" for vid in dict.fromkeys(ids)]
    return urls[:3]


def _model_tokens(robot_name: str) -> list[str]:
    name = re.sub(r"[®™]", "", robot_name or "")
    return [t for t in re.split(r"[^a-z0-9+]+", name.lower()) if len(t) > 2]


def search_youtube_for_model(robot_name: str, *, limit: int = 2) -> list[str]:
    """Find model-relevant iRobot videos via public YouTube search results."""
    query = re.sub(r"[^\w\s+]", " ", robot_name)
    search_url = "https://www.youtube.com/results"
    try:
        resp = requests.get(
            search_url,
            params={"search_query": f"iRobot {query}".strip()},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=30,
        )
    except requests.RequestException:
        return []
    if not resp.ok:
        return []

    tokens = _model_tokens(robot_name)
    if not tokens:
        return []

    picked: list[str] = []
    seen: set[str] = set()
    for vid in re.findall(r'"videoId":"([\w-]{11})"', resp.text):
        if vid in seen:
            continue
        seen.add(vid)
        watch = f"https://www.youtube.com/watch?v={vid}"
        meta = fetch_youtube_metadata(watch)
        title = (meta.get("title") or "").lower()
        if sum(1 for t in tokens if t in title) < 1:
            continue
        picked.append(watch)
        if len(picked) >= limit:
            break
    return picked


def video_search_name(robot: dict, url: str) -> str:
    name = (robot.get("name") or "").strip()
    if len(name) >= 10 and name.lower() not in {"irobot"}:
        return name
    m = re.search(r"/en_US/([^/]+)/[A-Z][0-9]{5,6}\.html", url, re.I)
    if m:
        return m.group(1).replace("-", " ")
    return name or "iRobot Roomba"


def find_videos(robot_name: str, html: str) -> list[dict[str, str]]:
    urls = parse_videos(html)
    if not urls:
        urls = search_youtube_for_model(robot_name, limit=2)
    if not urls:
        yt = search_youtube_videos_for_robot(
            robot_name,
            COMPANY_NAME,
            company_website="https://www.irobot.com",
            max_videos=2,
        )
        urls = yt.get("video_urls") or []
    return enrich_video_list(urls[:2])


def scrape_robot(robot: dict) -> dict[str, Any] | None:
    url = resolve_product_url(robot)
    if not url:
        return None

    status, html = fetch_pdp(url)
    if status >= 500 or len(html) < 5000:
        return None

    sku = _extract_sku(url)
    hero, gallery = parse_images(html, sku)
    features = parse_features(html)
    specs = parse_specs(html)
    videos = find_videos(video_search_name(robot, url), html)

    meta = re.search(r'<meta name="description" content="([^"]+)"', html)
    description = robot.get("description") or ""
    if meta and meta.group(1).strip() and meta.group(1).strip().lower() != "irobot":
        description = meta.group(1).strip()

    row: dict[str, Any] = {
        "name": robot["name"],
        "company_slug": COMPANY_SLUG,
        "company_name": COMPANY_NAME,
        "manufacturer_country_code": "US",
        "description": description or robot["name"],
        "purpose": robot.get("purpose") or description or robot["name"],
        "features": features,
        "url": url,
        "image": hero,
        "images": [hero, *gallery] if hero else gallery,
        "video_urls": videos,
        "movement_type_keys": _infer_movement(robot["name"], features),
        "sub_category_slug": _infer_sub_category(robot["name"], features) or "cleaning-facilities",
        "category_slugs": "service-robots",
        "tags": "",
        "sources": [{"url": url, "type": "website"}],
        "research_notes": (
            f"PDP scrape from {url} (HTTP {status}). "
            f"Specs/features/images extracted from iRobot product page."
        ),
    }
    row.update(specs)
    return row


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
        copy_url = f"{api}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/"
        try:
            resp = requests.post(copy_url, headers={"X-Internal-Secret": secret}, timeout=120)
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
    parser = argparse.ArgumentParser(description="Fix iRobot robot PDP data for company 342")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--copy-media", action="store_true")
    parser.add_argument("--created-by-id", type=int, default=1)
    parser.add_argument("--robot-ids", type=str, default="", help="Comma-separated robot IDs to limit scope")
    parser.add_argument("--batch-size", type=int, default=3)
    args = parser.parse_args()

    limit_ids: set[int] | None = None
    if args.robot_ids.strip():
        limit_ids = {int(x.strip()) for x in args.robot_ids.split(",") if x.strip().isdigit()}

    client = ResearchApiClient()
    robots = client.list_robots_for_company(COMPANY_ID)
    targets = [r for r in robots if (r.get("status") or "") not in SKIP_STATUSES]
    if limit_ids:
        targets = [r for r in targets if int(r["id"]) in limit_ids]
    print(f"targets: {len(targets)} / {len(robots)} (skipping published)")

    plan: list[dict[str, Any]] = []
    staging_by_id: dict[int, dict[str, Any]] = {}
    for robot in targets:
        row = scrape_robot(robot)
        if not row:
            print(f"SKIP {robot['id']} {robot['name']}: no PDP")
            continue
        plan.append(
            {
                "id": robot["id"],
                "name": robot["name"],
                "url": row["url"],
                "image": row.get("image"),
                "features_len": len(row.get("features") or ""),
                "spec_keys": sorted(k for k in row if k.endswith("_mm") or k in ("weight_kg", "runtime")),
                "videos": len(row.get("video_urls") or []),
            }
        )
        staging_by_id[robot["id"]] = row
        print(
            f"{robot['name']}: img={'yes' if row.get('image') else 'no'} "
            f"features={len(row.get('features') or '')} "
            f"specs={len([k for k in row if k.endswith('_mm') or k in ('weight_kg', 'runtime')])} "
            f"videos={len(row.get('video_urls') or [])}"
        )

    preview = _RESEARCH_DIR / "staging" / "reports" / "irobot-fix-preview.json"
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    missing = [p for p in plan if not p.get("image")]
    weak = [p for p in plan if not p.get("features_len")]
    if missing:
        print(f"WARNING: {len(missing)} robots still missing hero image", file=sys.stderr)
    if weak:
        print(f"WARNING: {len(weak)} robots still missing features", file=sys.stderr)

    if not plan:
        print("ERROR: nothing to import", file=sys.stderr)
        return 1
    if not args.apply:
        print(f"Preview: {preview}. Re-run with --apply --copy-media")
        return 0

    tmp = Path(tempfile.mkdtemp(prefix="irobot-fix-"))
    imported_ids: list[int] = []
    totals = {"updated_count": 0, "error_count": 0, "skipped_count": 0}
    all_ok = True

    for item in plan:
        rid = item["id"]
        row = staging_by_id[rid]
        fname = f"{slugify_robot_name(row['name'])}-{rid}"
        fpath = tmp / f"{fname}.json"
        fpath.write_text(json.dumps(row, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        result = import_staging(
            fpath,
            patch=False,
            force_overwrite=True,
            status="pending_review",
            dry_run=False,
            created_by_id=resolve_created_by_id(args.created_by_id),
            replace_media=True,
            batch_size=1,
            skip_company_update=True,
        )
        if not result.get("ok"):
            all_ok = False
            print(f"IMPORT FAIL {rid} {row['name']}: {result.get('errors')}", file=sys.stderr)
            continue
        imported_ids.append(rid)
        for key in totals:
            totals[key] += result.get(key, 0) or 0

    print(json.dumps({"ok": all_ok, **totals}, indent=2))

    if args.copy_media and imported_ids:
        ok, fail = trigger_copy_media(imported_ids)
        print(f"copy-media ok={ok} fail={fail}")

    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
